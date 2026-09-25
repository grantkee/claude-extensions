# UX angle

## Why this angle matters here

A liquidity provider comes here to answer three questions: what are my positions worth, what can I claim, and did my transaction go through. The app answers them with one full-height spinner for loading, empty, and error alike; with toasts for some transactions and console-only failures for others; and with copy that has drifted from the UI. Every state the interface fails to distinguish becomes a support ticket or a repeated transaction. This angle reviews flows and states. Visual polish and markup belong to the UI angle, and whether the numbers are right belongs to data-correctness.

## File map

Read first:

- Transaction flows: `src/components/common/UserPositions.tsx` (v4 positions: the not-connected prompt, the hardcoded `visibleIds` gate, subscribe and unsubscribe status messages, errors that reach only the console), `src/components/contract/ContractStakeForm.tsx` with `ContractStakeFormStake.tsx`, `ContractStakeFormUnstake.tsx`, `ContractApprove.tsx`, `ContractSectionStake.tsx`, and `ContractSectionDeprecated.tsx` (legacy approve, stake, unstake, and exit flows, Max, input parsing), `src/components/modal/ModalStake.tsx`, `ModalUnstake.tsx`, `ModalRewards.tsx` (confirmation previews), `src/merkl/MerklClaimCard.tsx` with `src/merkl/useMerklClaim.ts` and `merklToasts.tsx` (claim and the reconciliation state), `src/components/Portfolio/UnclaimedUniswapRewardsCard.tsx`, `UnclaimedRewardsCard.tsx`, `ProductRewardsMain.tsx`, `StatsSection.tsx`.
- Feedback: `src/components/toast/*.tsx` (generators keyed by transaction hash; the default `txHash=""` makes hashless toasts collide), `src/app/Providers.tsx` (the ToastContainer), `src/web3/transactions/transactions.ts` (which callbacks fire toasts; the raw `error.message` on rejection).
- States: `src/components/common/LoadingWrapper.tsx` (the one spinner), `src/components/pools/PoolsMain.tsx`, `src/components/archive/ArchiveCards.tsx`, `src/components/home/PoolsHomePage.tsx` (an empty list spins forever), `src/components/stats/PoolsHeaderStats.tsx` (zero is treated as loading), `src/app/pool/[poolID]/PoolDetails.tsx` (an unknown pool spins forever; `targetChain` defaults to Polygon until data arrives), `src/components/common/LabelRewardsRow.tsx` (`isError` ignored; $0.00 while loading), `src/components/pool/PoolFees.tsx` (renders a literal 0).
- Wallet and network: `src/components/layout/CustomConnectButton.tsx` (Connect, Wrong network, account), `src/hooks/useCheckChain.ts` (called from the pool page; swallows rejection), `src/components/wallet/WalletItemWeb3.tsx` (a Polygon-only hint), `src/data/notices.json` (connect and stake prompts).
- Navigation and search: `src/app/search/page.tsx` and `SearchPage.tsx` (the page reads `params.s` on a route with no dynamic segment; archive-only results show "couldn't find"), `src/components/search/*.tsx`, `src/components/pools/PoolTabs.tsx` (tabs never reach the URL), `src/app/about/[slug]/page.tsx` (an unknown slug renders an empty page with status 200), `src/components/common/LabelViewPoolRow.tsx`, `LabelPoolAddressRow.tsx`, `LabelStakeAddressRow.tsx`, `src/components/archive/ArchiveCard.tsx` (div rows that navigate with `router.push`), `src/components/pool/PoolSnapshotGeneralized.tsx` and `src/components/generalized/CardGeneralized.tsx` (links to a route that does not exist), `src/components/common/PoolIdentity.tsx`, `src/components/stats/PoolsNav.tsx`.
- Copy: `src/data/notices.json`, `src/data/homePageData.json`, `src/app/HomePage.tsx`, `src/helpers/getRewardsById.ts` (labels), the page metadata blocks, hardcoded strings such as "Rewards / 7 days" and "Reward Distribution 3x/day", and `content/about/*.md` when the scope includes it.

## Checklist

### Transaction flows, from the user's seat

- Every write shows five states in order: idle, waiting for the wallet, submitted (with the hash and an explorer link for the right chain), confirmed, failed. `UserPositions` shows "Transaction pending..." while the wallet prompt is open, nothing while the transaction mines, and "sent" only after confirmation. The legacy path shows its pending toast only once it has a hash.
- Rejection is not an error. Cancelling in the wallet gives a calm message and re-enables the button. It never shows a raw provider string or leaves a spinner running.
- Failures reach the user. A `catch` that only logs (subscribe and unsubscribe in `UserPositions`, allowance reads that fall back to zero, the chart fetch) is a finding at Medium whenever the user could act on the failure.
- Buttons are disabled while a transaction is in flight and re-enabled on every exit path, including rejection and timeout. The one global lock in `web3Slice` disables every pool's buttons, so a stuck receipt poll freezes the whole app.
- Confirmation previews in `Modal*` show the amount, token, and destination the transaction will actually use, and Max agrees with what is sent.
- After success, the screen updates without a reload: balances, allowance, the subscribed badge, claimable rewards. The Merkl claim disables its button for up to five minutes of reconciliation; the user should be told why.
- Amount inputs reject or clamp negatives, more decimals than the token has, and more than the balance, with an inline message, before a transaction can be attempted.
- Approve versus action: the user understands why an approval is needed and what it authorizes (unlimited), and an unstake never demands a fresh approval.

### Loading, empty, error, and stale

- Loading, empty, and error are three states with three renderings. Today one spinner covers all three in the pools list, the archive tab, the home page list, the header stats, and the pool detail page. Each such place is a finding; group them by pattern with every location listed.
- A failed fetch says so. `UserPositions` tells a user whose positions call failed that they have no positions, and `LabelRewardsRow` shows $0.00 on a failed price fetch.
- Stale data has a cue. Nothing shows a timestamp or a refresh control, and data refetches only on account change or after a transaction.
- Skeletons versus spinners: the full-height spinner replaces the layout and the table jumps in. Note it once, at Low.

### Wallet and network

- Not connected: every page that needs a wallet says so where the data would be, with the connect action, not only through the header button.
- Wrong network: the app names the chain the pool is on and offers a switch. `useCheckChain` runs on the pool page and RainbowKit's "Wrong network" appears only for unsupported chains. Check that the pool page cannot prompt a switch to Polygon before the pool's chain is known, and that copy saying "Polygon" is right for Base and Ethereum pools.
- Disconnect and account change refetch and clear the previous account's data.

### Navigation, search, and content

- Deep links work: `/search?s=` (the page reads `params.s`, which does not exist on a static route), `/pool/[poolID]?chain=` (the chain survives through `getPoolPath`), and tabs or filters that live only in state are lost on refresh.
- Dead ends: links to routes that do not exist (`pools/generalized-incentives`), `#` links, legacy `/${slug}/...` paths, and an unknown about slug that should call `notFound()`.
- Rows that navigate on click are real links (href, middle click, keyboard), and an inner link inside a clickable row does not also fire the row.
- External links use the right explorer for the chain (`getTokenExplorerUrl` exists, yet several components hardcode Polygonscan and omit Ethereum) and the right protocol for "View pool" (always Uniswap today).
- The About and FAQ pages under `content/about/` describe the legacy TEL (addresses, bridging steps) while the active pools and Merkl rewards use the new TEL; a reader who follows them buys or bridges the wrong token. Check every address and step against `src/lib/tokens.ts` and `src/merkl/merklConstants.ts`.
- Copy matches the UI and the facts: a notice says "Connect Wallet on the sidebar" for a header button labelled "Connect"; metadata says "Polygon and Base" after Ethereum launched; reward labels carry no year; hero text is duplicated between code and JSON.

### Deprecated and archived pools

- A deprecated-but-active pool shows the badge, an explanation, and a working path out (unstake or exit). Archived pools are reachable and their stakes visible; only the latest deprecated contract is read today, so older stakes are invisible.

## Severity examples

- High: a transaction flow where the user cannot tell whether their money moved (no pending or failure state, success shown before the receipt); a claim or exit control that stays disabled or invisible for a class of users (the `visibleIds` gate, a stuck lock).
- Medium: failures that only reach the console; loading shown for empty or error; a deep link that silently shows nothing; a rejection surfaced as a raw error; a wrong-chain prompt.
- Low: missing skeletons; inconsistent placeholders ("Unavailable", "N/A", blank); stale copy; tabs not in the URL.
- Informational: tone and wording of labels.

## Do not flag

- The absence of a light theme or a dark-mode toggle. One theme is a design decision.
- Marketing copy quality on the home page, beyond factual drift.
- Visual polish, contrast, and markup semantics. Those belong to the UI angle; put them in "Also noted" if you trip over them.
