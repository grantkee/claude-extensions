# Web3 safety angle

## Why this angle matters here

This is the code between a click and a signed transaction. Three write paths exist. The legacy Polygon staking path builds `approve`, `stake`, `withdraw`, `exit`, and `getReward` calls for Synthetix-style reward contracts in `src/web3/transactions/transactions.ts` and sends them with viem's `walletClient.sendTransaction`. The Merkl claim calls `claim` on the Merkl Distributor through `walletClient.writeContract` in `src/merkl/useMerklClaim.ts`. The Uniswap v4 subscribe and unsubscribe path lives in `src/components/common/UserPositions.tsx`. A mistake on any of them costs a user gas at best and funds at worst: a wrong spender on an unlimited approval, a transaction sent on the wrong chain, an amount built from a float.

## File map

Read first:

- `src/lib/wagmiClient.ts`: RainbowKit `getDefaultConfig`, chains 1, 137, and 8453, one Alchemy `http()` transport per chain with no fallback, `ssr: true`, a WalletConnect project id that falls back to an empty string.
- `src/lib/contracts.ts`: per-chain PositionManager, hook, legacy subscriber, and PositionRegistry addresses; the Merkl registry and subscriber shared across chains; `MERKL_UNISWAP_POOL_IDS`; `getUniswapChainAddresses` with a Polygon fallback for unknown chains; RPC URLs.
- `src/lib/alchemySdk.ts`: alchemy-sdk clients and ethers `AlchemyProvider`s. The Polygon `provider` backs every legacy read, and the Polygon client supplies the gas price and receipts for every legacy write. `src/lib/constants.ts`.
- `src/web3/transactions/transactions.ts`: the calldata builders (`MaxUint256` approve, stake, withdraw, exit), `getAllowanceBool`, and `initiateTransaction`, the only legacy write path. `hookTransactions.ts` is a byte-identical copy with no importer; a fix must land in both or one must go.
- `src/components/contract/ContractStakeForm.tsx` (approve, stake, and unstake handlers, input and Max parsing), `ContractStakeFormStake.tsx`, `ContractStakeFormUnstake.tsx`, `ContractSectionStake.tsx` (allowance effect; routes Uniswap pools to `UserPositions`), `ContractSectionDeprecated.tsx` (exit, or withdraw on the six faulty contracts), `ContractActions.tsx`, `ContractApprove.tsx`.
- `src/components/modal/ModalStake.tsx`, `ModalUnstake.tsx`, `ModalRewards.tsx`: confirmation previews whose confirm button sends.
- `src/merkl/useMerklClaim.ts`, `src/merkl/merklConstants.ts` (Distributor `0x3Ef3D8bA38EBe18DB133cEc108f4D14CE00Dd9Ae` on all three chains, the claim ABI), `src/merkl/merklService.ts` (which entries reach `claim()`), `src/merkl/MerklClaimCard.tsx`, `src/merkl/merklToasts.tsx`.
- `src/components/Portfolio/UnclaimedUniswapRewardsCard.tsx` (legacy `PositionRegistry.claim` per chain) and `UnclaimedRewardsCard.tsx` (legacy staking claim through `initiateTransaction`).
- `src/components/common/UserPositions.tsx`, `src/components/common/PositionCard.tsx`, `src/components/pool/PositionInputCard.tsx`: the Uniswap v4 subscribe and unsubscribe writes. `UserPositions` is the only write site. It calls `PositionManager.subscribe(tokenId, subscriber, "0x")` and `unsubscribe(tokenId)` through wagmi's `writeContractAsync` with an inline ABI that has drifted from `src/web3/abis/PositionManager.json` (nonpayable versus payable). The subscriber comes from `getUniswapChainAddresses`: Merkl pools get `MERKL_TELX_SUBSCRIBER`, shared across chains, and the rest get the per-chain legacy subscriber. No `chainId`, no simulation, a `useWaitForTransactionReceipt` without `chainId` or timeout, and `receipt.status` is never read. Positions are discovered through `/api/uniswap-user-positions-{chain}` (The Graph plus registry reads), and `isSubscribed` comes from the registry, not from `PositionManager.subscriber(tokenId)`.
- `src/web3/getContracts/<protocol>/*`: these decide `stakeContractAddress`, which is both the transaction target and the approve spender. Balancer and DFX fall back to `deprecatedStakingAddresses[0]`, QuickSwap to the last entry.
- `src/hooks/useCheckChain.ts` (auto `switchChain`, called from `PoolDetails.tsx` with a target that defaults to Polygon until pool data arrives, and it swallows rejection), `src/components/layout/CustomConnectButton.tsx` (chain switcher commented out), `src/components/wallet/WalletItemWeb3.tsx` (a `useChainId() !== 137` hint), `src/redux/slices/web3Slice.ts` (one global `isTransacting` lock for the whole app), `src/components/toast/*.tsx`.
- `src/web3/abis/*.json`: check selectors when one ABI encodes calls for several contract types. `staking_dual_rewards.json` encodes the single, dual, and multi contracts alike.

## Checklist

### Before the send

- Chain. Every write names its chain (`chain` or `chainId` on `sendTransaction` and `writeContract`, or a `switchChain` first), and the target address is looked up by that chain. The legacy path passes no chain, so a wallet sitting on Base sends Polygon calldata to the same address on Base and then polls Polygon for a receipt that never comes. The Merkl claim switches chain first. The v4 subscribe passes no `chainId` and never checks or switches: a wallet on another chain sends to that chain's PositionManager address, which likely mines as a no-op while the UI shows success and an explorer link for the pool's chain rather than the transaction's.
- Spender and target. The approve spender is the contract that will pull the tokens, comes from a trusted source (`pool.json` metadata is checked in, but the fallback between `activeStakingAddress` and `deprecatedStakingAddresses` differs per protocol), and is compared case-insensitively. Unlimited approvals with `MaxUint256` are the norm here. Report them as Medium with an exact-amount alternative, and as Critical only when the spender can be wrong.
- Amount. Built with `parseUnits(string, decimals)` from the user's string, never from a float (`parseFloat`, `Number(formatUnits(...))`, `substring` truncation, `toFixed`). Max uses the on-chain balance as a `bigint`, not a float round trip that can exceed it by a few wei and revert. Scientific-notation input such as `1e-7` throws inside `parseUnits` before any try block.
- Preconditions. The amount is checked against the balance or staked amount before sending. The allowance is compared with the amount being staked, not the whole wallet balance. A failed allowance read does not count as approved: with both reads falling back to zero, `getAllowanceBool` returns true.
- Simulation. `simulateContract` or `estimateGas` before `writeContract` turns a certain revert into a message instead of a wasted fee. None of the three paths simulates today; recommend it at Medium.
- Gas. The legacy path fetches Polygon's gas price through alchemy-sdk and sets it as both `maxFeePerGas` and `maxPriorityFeePerGas`: no headroom for a rising base fee, the wrong chain if reused, and an ethers BigNumber handed to viem. Letting the wallet estimate is the fix.
- Double submit. The lock (`isConfirming`, `isTransacting`) is set before the first await, and every button reads it.

### After the send

- Receipt. `waitForTransactionReceipt` or the polling loop checks `receipt.status === "success"` before the success toast and the refetch. `useMerklClaim.ts` and `UnclaimedUniswapRewardsCard.tsx` do not check status, and the legacy loop treats any truthy status as success.
- Polling loops have a timeout and a try/catch, are cleared on unmount and on every exit path, cannot fire the success path twice from overlapping async ticks, and resolve the UI when a transaction is replaced or dropped.
- Errors. User rejection (viem's `UserRejectedRequestError` found through `BaseError.walk`, code 4001, `ACTION_REJECTED`) is told apart from a revert and from an RPC failure. The user sees a short message, not a raw provider string. Every rejection path clears the transacting flag. Un-awaited `initiateTransaction` calls leak their rejections.
- Refetch. After a successful receipt, the balances, allowance, and rewards the user just changed are refetched, and the 60 second caches cannot serve the stale value.

### Reads that feed writes

- Legacy reads go through the Polygon ethers provider regardless of the connected chain. That is right for Polygon-only staking and wrong the moment a contract lives elsewhere.
- Which staking contract is read and written. `ContractSectionDeprecated` reads only the latest deprecated contract, so a stake in an older one is invisible and cannot be exited from the UI.
- Mixed numeric APIs. `parseInt(bigint) == bigint` loses precision (the "100% withdraw becomes exit()" branch), and an ethers v5 `.gt()` on a v6 bigint throws (the faulty-contract withdraw button).
- Case-sensitive address checks against checksummed constants (`deprecatedFaultyAddresses`, `STAKE_ADDRESS_TEL_DFX`).
- Subscription state. The UI reads `isSubscribed` from the registry while the PositionManager knows the real subscriber. A position held by a different subscriber shows as not subscribed, `subscribe` reverts with `AlreadySubscribed` (and the error is swallowed), and unsubscribe stays disabled. The subscriber and registry chosen for a pool are a coupled pair; changing one without the other means the UI never shows the new state.
- Selection. A hidden position stays selected when the tab changes, and closed (zero liquidity) positions can be selected and subscribed. The buttons must act only on what is on screen.

### Wallet and configuration

- Supported chains. The wrong-network hint compares `useChainId()`, the app's chain, against 137 instead of `useAccount().chainId`, the wallet's, so it flags supported chains and can miss unsupported ones. The only auto-switch helper runs on the pool page with a target that defaults to Polygon before the pool's chain is known.
- RPC. One Alchemy transport per chain keyed by the public `NEXT_PUBLIC_ALCHEMY_ID` with no fallback, and an unset key yields `/v2/undefined`. A `fallback([http(alchemy), http()])` transport is the fix.
- The WalletConnect project id falls back to an empty string, so misconfiguration fails at connect time rather than build time.
- Explorer links in toasts and cards use the explorer for the transaction's chain.

## Severity examples

- Critical: an approve or claim built for one chain and sendable on another to a different contract; a spender chosen from an untrusted or wrong-index source; an amount built with the wrong decimals.
- High: a withdraw or exit path that throws or reverts for a class of users; a success toast on a reverted transaction; a Max unstake that reverts or leaves dust and unclaimed rewards; a stuck global lock that disables every pool's buttons.
- Medium: an unlimited approval where an exact one would do; no simulation; a float on the amount path that rounds safely today; a rejection shown as a raw error; an allowance fallback that skips Approve on an RPC failure.
- Low: the duplicated transaction module; wrong-network copy that says Polygon only.
- Informational: `any` on transaction helper parameters, naming.

## Do not flag

- Unlimited approvals as Critical by reflex. They are the industry default. The finding is the spender, or a Medium with the exact-amount alternative.
- Legacy staking being Polygon-only. It is. The finding is code that assumes Polygon on a path that can run on another chain.
- The reference Solidity in `src/web3/contractCode/`. Read it only to confirm a selector or a return order.
- Wallet-side gas estimation. Letting the wallet estimate is fine; the issue is overriding it badly.
