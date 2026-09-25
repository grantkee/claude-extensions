# Best practices angle

## Why this angle matters here

The codebase grew fast with several authors and no CI. TypeScript is strict, but `any` is allowed and unused variables are not linted, so a passing `tsc` and a clean `lint` prove less than usual. Copy-pasted per-chain and per-protocol modules mean a fix in one place is often missing in the others. This angle keeps the codebase maintainable and catches the class of bug that consistency would have prevented: the duplicate that drifted, the type that lies, the effect that leaks.

## File map

Read first:

- `package.json`, `tsconfig.json`, `eslint.config.mjs`, `jest.config.ts`, `jest.setup.ts`, `prettier.config.js`, `next.config.ts`, `CONTRIBUTING.md`, and `tasks/telx-review/toolchain.md`.
- `src/types/*.ts`: Strapi-era shapes out of sync with `pool.json`. `Pool` lacks `network`, `decimals`, `deprecated`, and `hidden`; `PoolAsset` lacks `address`; `rewards_type` lacks `"uniswap"`; `StakeAddress` types dates as `Date` over strings.
- Duplicates: `src/web3/transactions/transactions.ts` and `hookTransactions.ts` (byte-identical); `src/app/api/uniswap-user-positions-{polygon,base,ethereum}/route.ts`; the four `src/web3/getContracts/<protocol>/getSingleContractData.ts` view models; `formatStakingContractDate` in `ContractHeading.tsx` and `ContractStartEnd.tsx`; the archived-contracts filter in `WalletItemContracts.tsx` and `WalletItemRewards.tsx`.
- Boundaries: `src/app/layout.tsx` (`"use client"` root), `src/app/Providers.tsx` (no directive of its own, module singletons), `src/app/api/backendHelpers/helpers.ts` (imported by client and server code), the server shells under `src/app/**/page.tsx`.
- Hooks and effects: `src/components/contract/ContractSectionStake.tsx` (allowance effect without cancellation), `src/web3/transactions/transactions.ts` (`setInterval`), `src/hooks/*`, `src/merkl/useMerklClaim.ts`.
- State: `src/redux/slices/*.ts` (a single global transaction lock in `web3Slice`, `any`-typed contract data, values that may not be serializable), `src/redux/store.ts`.
- Error handling: the `*-grouped` route handlers (no try/catch), `src/web3/getContracts/quickswap/*` (no try/catch, so one throw rejects the shared `Promise.all`), errors swallowed with `console.error` and a zero fallback.
- Tests: `src/helpers/normalizeMiningContracts.test.ts`, `src/lib/tokens.test.ts`; `jest.config.ts` has `setupFilesAfterEnv` commented out, so `jest.setup.ts` never loads.

## Checklist

### TypeScript honesty

- `any` on money and identity paths: amounts, addresses, chain, pool keys. Each one is a place `tsc` cannot help. Flag the ones that hide a real mismatch, such as a string compared to a bigint or a `Date` type over a string.
- Types that do not describe the data: `src/types/Pool.ts` against `pool.json`. A PR that adds a pool field without updating the type is a finding.
- `process?.env?.X || ""` typed `any`. A missing variable fails at runtime with "undefined" inside a URL (`/v2/undefined`).
- Casts (`as any`, `as unknown as`) that silence a real error.

### React and Next.js

- Server and client boundary: pages are server components passing props to client components. A `"use client"` file importing a server-only module, or the reverse, is a finding. `Providers.tsx` depends on the client root layout for its boundary.
- Hooks: effects without cleanup (intervals, listeners, subscriptions), async effects without a cancelled flag (the allowance check), state copied from props that should be derived, and dependency arrays lint cannot check because of `any`.
- Keys: lists keyed by `pool.json` ids that repeat (32, 33, 34) or by array index.
- `reactStrictMode: false`: name the bug it hides rather than the setting.
- Deprecated APIs: `images.domains` (use `remotePatterns`); `next lint` (documented, do not re-report the deprecation, do report new code that depends on it).
- Module-level singletons (`QueryClient`, the Redux store) evaluated during SSR are fine while nothing dispatches on the server. Flag any server-side dispatch or prefetch into them.

### Duplication and drift

- Byte-identical or near-identical modules: diff them and report the drift. The finding names what differs and which copy is right.
- The same constant in two places: TEL addresses in `tokens.ts` and `merklConstants.ts`, chain ids as numbers in the Merkl module and as strings elsewhere, 500,000 TEL in `getRewardsById.ts` and in `pool.json` names.
- Dead code: `hookTransactions.ts`, `src/components/layout/Layout.tsx`, `public/ga.js`, the staking period in `defaultRewards.json`, `YourRewards.tsx` (its guard makes it always return null), `userUniswapContracts` typed as a map but holding an array, the unused `Base` instances in `alchemySdk.ts`.

### Error handling

- `Promise.all` that fails everything on one rejection (`shared.ts`, the portfolio's per-chain fetches).
- Errors caught, logged, and replaced by zero. The user sees a zero balance instead of an error. Report the places where a zero can be mistaken for the truth: balances, rewards, allowances.
- Route handlers without try/catch, or that return `data.data` unchecked.
- Un-awaited `initiateTransaction` calls whose rejections nobody handles.

### Dependencies and configuration hygiene

- Declared but never imported: `@wagmi/core`, `@tanstack/query-core`, `next-seo`, `@remixicon/react`, `init`, `@react-stately/datepicker`, `tailwind-variants`. Imported but not declared: `@tanstack/react-query`, which resolves only through wagmi's peer dependency. Two spinner libraries each serving one component. Four overlapping network stacks (ethers, viem, Apollo, urql, axios).
- `eslint-config-next` pinned at 15.2.4 against next 15.5.9; `eslint-plugin-storybook` installed with no Storybook; the prettier configs are not last in `extends`.
- `jest.setup.ts` is disconnected and imports a removed path. `npm test` runs, but DOM matchers are unavailable until this is fixed.
- `scripts/security-check.js` matching: substring `includes` (`^4.4.20` matches `4.4.2`) and basename-only lock matching (`@scope/debug` collides with `debug`).

### Contributor readiness

- Filenames under `content/about/` contain `?` and `:`, which are invalid on Windows and break `git checkout` there. Slugs are derived from titles, so the files can be renamed without changing URLs.
- `CONTRIBUTING.md` and `README.md` state facts that drift (test count, supported chains); report the specific stale sentence.

### Tests

- The two test files pin `pool.json` invariants. Report the untested paths that carry money: amount parsing in `ContractStakeForm.tsx`, `getAllowanceBool`, Merkl `parseRewards`, `formatSqrtPriceX96`, route input validation. Suggest the specific test (function, input, expected value) rather than "add tests".

## Severity examples

- High: a duplicate that drifted so one copy carries a fixed bug and the other does not, on a money path; a server-only module leaking to the client.
- Medium: an effect that leaks a timer or races a stale response into state; `Promise.all` that blanks all pool data on one failure; a type lie that hides a unit mismatch.
- Low: unused dependencies; deprecated config; `any` on non-money paths; duplicated helpers.
- Informational: naming, comment style, import order, dead files.

## Do not flag

- The documented known gaps (Prettier, permissive lint, the `next lint` deprecation, thin tests) as findings in themselves.
- `any` in presentational components with no data consequences.
- Commit message style and branch naming. Those are process, not code.
- The Tremor Raw copy-paste components existing. They exist because `@tremor/react` is not React 19 compatible.
