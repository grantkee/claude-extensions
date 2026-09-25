# Data correctness angle

## Why this angle matters here

The app shows liquidity providers numbers they act on: pool TVL and volume, their staked and unstaked balances, pending and unclaimed rewards, USD values, and reward rates. A number that is off by a power of ten is worse than no number, because it drives a stake, an unstake, or a claim. The two sources of error in this codebase are unit handling (which token, which decimals, which chain) and the float arithmetic that most of the legacy pipeline uses on raw amounts.

## File map

Read first:

- `src/data/pool.json`: the pool registry, Strapi-shaped, 44 entries: 30 legacy Polygon pools (Balancer, DFX, QuickSwap) and 14 Uniswap v4 pools (Polygon 7, Base 4, Ethereum 3). Fields that drive numbers: `protocol`, `network` and `blockchain`, `pool_address` (a bytes32 pool id for Uniswap v4 entries, an ERC20 address for legacy ones), `decimals.amount0Decimals` and `amount1Decimals`, `rewards_tokens` (strings like `"TEL 500000"` parsed with split and Number), `stake_addresses`, `pool_assets`, `active`, `deprecated`, `hidden`, `fetchSubgraph`.
- `src/helpers/normalizeMiningContracts.ts` and its test: pool.json into mining-contract view models; `deprecated = explicit ?? !active`; the string parsing.
- `src/lib/tokens.ts` and its test: the legacy TEL address list, `isLegacyTel`, `paysLegacyTelRewards`. `src/merkl/merklConstants.ts`: the new TEL address, `TEL_DECIMALS = 18`, the Distributor.
- `src/lib/contracts.ts`: `getUniswapChainAddresses`, `MERKL_UNISWAP_POOL_IDS`, `getPoolMapKey`, `isMerklUniswapPool`.
- `src/web3/getContracts/**`: the per-protocol readers that produce balances, rewards, and TVL. Decimals are hardcoded here: LP tokens as 18; legacy TEL as 2 in `quickswap/getStakeInfo.ts`, `balancer/getRewardsValues.ts`, and `balancer/getSingleContractData.ts`; a token decimals map in `balancer/vault.ts`.
- `src/merkl/merklService.ts`: bigint parsing of Merkl rewards, the TEL filter (symbol or address), USD totals.
- `src/app/api/backendHelpers/helpers.ts`: `formatSqrtPriceX96` and position decoding in float math. `src/app/api/uniswap-user-positions-*/route.ts`: position amounts scaled with client-supplied decimals. `src/app/api/uniswap-user-rewards/route.ts`: `formatUnits(x, 2)` on registry rewards.
- `src/helpers/getRewardsById.ts` (hardcoded weekly TEL and start-date labels), `src/helpers/getTokenPrices.ts`, `src/helpers/getTokenPricesCached.ts`, `src/redux/slices/marketRateSlice.ts`, `src/app/api/market-rate/route.ts` (ticker to USD; note `USDCe` requested versus `USDC.e` read).
- `src/redux/slices/contractsSlice.ts`: totals (bignumber.js then `.toNumber()`), user subsets, `userUniswapContracts`, the `deprecatedContracts` filter.
- `src/helpers/prefetchGroupedSubgraph.ts`, `src/helpers/fetchGroupedSubgraph.ts`, `src/helpers/normalizeSubgraphData.ts`: grouped subgraph fetch, key formats (`${chain}:${id}` for Uniswap, raw lowercase for the rest), the 60 second caches.
- `src/helpers/formatNumberToCurrencyString.ts`, `src/helpers/returnNumber.ts`, `src/helpers/shortenAddress.ts`, `src/helpers/getTimestamp.ts`: display formatting.

Then: `src/components/Portfolio/StatsSection.tsx`, `src/components/Portfolio/ProductRewardsMain.tsx`, `src/components/wallet/WalletItemRewards.tsx`, `src/components/wallet/WalletItemRewardItem.tsx`, `src/components/contract/ContractReward.tsx`, `src/components/row/*.tsx`, `src/components/pool/Pool*.tsx`, `src/components/common/LabelPositionRow.tsx`, `src/components/common/UserPositions.tsx`, `src/components/chart/chart.ts`.

## Checklist

### Units and decimals

- Every `formatUnits` and `parseUnits` names the right decimals for the token in hand: LP tokens 18, legacy TEL 2, new TEL 18, USDC 6, and whatever `pool.json` says for a v4 pair. A literal `2` or `18` is suspect unless the code path fixes the token.
- The same on-chain read is scaled the same way everywhere it is consumed. `PositionRegistry.unclaimedRewards` is scaled by 2 decimals in `uniswap-user-rewards`, by 1e18 in the Polygon positions route, and returned raw by the Base and Ethereum routes. The unit belongs at the source.
- Legacy TEL and new TEL are never summed or priced together as "TEL". Check the Merkl TEL filter (symbol or address lets a 2-decimal token with symbol TEL into an 18-decimal sum, formatted with the first entry's decimals), the wallet reward totals keyed by ticker, `StatsSection`, and any `prices.TEL.USD` applied to both.
- `pool.json` decimals match the tokens. TEL is currency1 on the Merkl pools with `amount1Decimals: 18` (the test enforces six of them); legacy TEL pools keep 2; stablecoins 6. A new pool entry without `decimals` is a finding.
- Client-supplied decimals in the positions routes (`amount0Decimals`, `amount1Decimals`) are not trusted for correctness: `Number(null)` is 0 and a typo gives NaN.

### Arithmetic and types

- Raw token amounts stay `bigint` until display. `Number(formatUnits(x))`, `parseFloat`, `toFixed(18)`, `parseInt` on a bigint, and `substring` truncation are findings on any amount that feeds a transaction (Medium at least, High if the amount is sent). On display paths they are Low unless the value can exceed 2^53, which an 18-decimal raw amount does.
- Mixed-type comparisons: `bigint == number`, an ethers v5 `.gt()` on a v6 bigint (throws), `undefined > 0`.
- `bignumber.js` totals that are converted with `.toNumber()` for storage or display lose nothing for USD and lose precision for raw amounts.
- NaN and empty inputs: `split` and `Number` on names like `"TEL 500000"`, empty arrays indexed at `[0]`, `prices[ticker].USD` on a missing ticker, which throws and empties the whole price map.
- Rates and periods: is the reward rate per week, per day, or per distribution, and does the label match? Merkl pools are described as paying 3 times a day while `getRewardsById` hardcodes 500,000 TEL per week. Any APR is annualized from the right period and divided by the right TVL.

### Identity: chain, protocol, pool

- Pool keys agree between producer and consumer: `getPoolMapKey(address, blockchain, protocol)`, Uniswap grouped keys `${chain}:${id}`, QuickSwap and Balancer keys raw lowercase. A mismatch shows an empty pool with no error.
- Address comparisons are case-insensitive wherever the source casing is not controlled. Pool metadata is checksummed in places and lowercase in others, and the faulty deprecated list and `STAKE_ADDRESS_TEL_DFX` are compared with `includes` and `===`.
- Chain defaults: `blockchain` defaulting to "polygon", `getUniswapChainAddresses` falling back to Polygon for an unknown chain, `fetchMerklRewards` defaulting to Base. A wrong default shows another chain's numbers with no error.
- `MERKL_UNISWAP_POOL_IDS` and `isMerklUniswapPool` decide Merkl versus legacy addresses. A Merkl pool missing from the set gets legacy registry reads: zero rewards and the wrong subscriber.
- Uniswap v4 entries store a bytes32 pool id in fields named `pool_address` and `poolContractAddress`. Helpers that treat that field as an ERC20 address (`paysLegacyTelRewards`, Balancer vault lookups) must handle both shapes.

### Freshness and caching

- Caches with a TTL (`prefetchGroupedSubgraph` and `getTokenPricesCached` at 60 seconds, route `revalidate`) can cache a failure as an empty object, and can serve the pre-transaction value after `fetchAllContractData` refetches.
- Post-claim reconciliation polls until `totalClaimable` is zero. Check the exit conditions and what the user sees meanwhile.
- `Promise.all` across chains: one failed chain makes the whole total fail or go silently stale (`ProductRewardsMain`). `Promise.allSettled` with a per-chain error state is the fix.

### The registry against the chain

- The orchestrator runs `node SKILL_DIR/scripts/check-pools.mjs REPO` in Phase 0 and writes the result to `tasks/telx-review/pools-onchain.md`; if that file is missing, run the command yourself (SKILL_DIR is the skill path you were given; the script needs no dependencies and uses public RPC endpoints). It checks that every active pool's asset addresses have code on the stated chain and that ERC-20 `decimals()` matches the `decimals` block on the Uniswap v4 entries. A decimals mismatch on an active pool is High; an address with no code on its chain is High. Paste the script's table into your checkpoint.
- For the active Uniswap v4 pools, check the pool's own state where you can: liquidity above zero and a current tick inside the range the "Add liquidity" link presets. An active pool that is empty on-chain sends the first depositor into a one-sided position that arbitrage drains; the link targets in `pool.json` (`link_pool_analytics`, `link_add_liquidity`) and the Uniswap v4 StateView contract on each chain are the sources. Report what you could not check.

### Static data hygiene

- In `pool.json`, `getRewardsById.ts`, and `notices.json`: dates without a year ("Starting Sept 30th"), hardcoded weekly rewards, notices that link to old routes (`/sms-network/pool/...`), deprecated pools still `active` on purpose (five today, documented by the test).
- Every address is hex of the right length, `subgraph_id` is present when `fetchSubgraph` is true, and `stake_addresses` dates parse.

## Severity examples

- Critical: a decimals or unit error in an amount that is sent in a transaction, such as a 2-versus-18 mix-up on a claim or withdraw.
- High: a displayed balance, reward, or USD total wrong by a power of ten or merged across the two TEL tokens; a chain default that shows another chain's data; a pool key mismatch that hides a user's stake.
- Medium: float arithmetic on raw amounts on a display path where the value can exceed 2^53; a missing ticker that empties every price; a cache that stores a failure; `Promise.all` that stales a total.
- Low: rounding that differs between components; hardcoded values that will go stale; case-sensitive comparisons that happen to work today.
- Informational: duplicated formatting helpers, naming.

## Do not flag

- USD values computed in floats. USD display precision is fine as `number`.
- `bignumber.js` for totals that only feed display.
- The 500,000 TEL weekly figure itself. Check that the label and the period match; the business number is not yours to question.
- The `hidden`, `active`, and `deprecated` semantics: `active` means listed, `deprecated` means the badge, and both can be true. The normalizeMiningContracts test documents this.
