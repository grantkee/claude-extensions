# Performance angle

## Why this angle matters here

The root layout is a client component, so every route ships the whole provider tree: wagmi, RainbowKit, Redux, Datadog RUM, and the toast container load before a visitor sees a single pool. Pages are thin server shells; all data work happens in client components after hydration, through the app's own route handlers, which do no server-side caching. The levers are bundle weight in the client layout, request waterfalls after mount, and caching or deduplication of the proxied upstream calls.

## Baseline

From the `npm run build` route table in September 2026. Treat growth above about 5% on a main route as a regression to explain in the report.

| Route | Mode | Route size | First Load JS |
|---|---|---|---|
| `/` | static | 6.2 kB | 555 kB |
| `/pools` | static | 1.7 kB | 458 kB |
| `/pool/[poolID]` | SSG, 0 pages prerendered | 108 kB | 742 kB |
| `/portfolio` | static | 13.9 kB | 681 kB |
| `/search` | static | 13.4 kB | 557 kB |
| shared by all routes | | | 105 kB |
| middleware | | | 35 kB |

The current route table is in `tasks/telx-review/toolchain.md`. The table omits the root layout's own chunks, which every route loads; add them (from `.next/build-manifest.json`) when you need the real first load.

## File map

Read first:

- `tasks/telx-review/toolchain.md`: the route table for this review.
- `src/app/layout.tsx` (`"use client"` root), `src/app/Providers.tsx` (provider tree, module-level `QueryClient` and Redux store, GA through `next/script`), `src/app/DataDogRum.tsx` (module-scope init, 100% session sampling), `src/components/layout/AppLayout.tsx` (client shell on every page, imports `pool.json`).
- `src/app/globals.css` (render-blocking Typekit `@import` on line 1, `@font-face` rules), `next.config.ts` (`images.domains`, strict mode off, lightningcss off, SVGR).
- Pages: `src/app/page.tsx` with `HomePage.tsx`; `src/app/pools/page.tsx` (passes all of `pool.json` as a prop, so it lands in the RSC payload) with `src/components/pools/PoolTabs.tsx`; `src/app/pool/[poolID]/page.tsx` (`generateStaticParams` returns `slug` for a `[poolID]` segment, so no pool page prerenders) with `PoolDetails.tsx`; `src/app/portfolio/PortfolioPage.tsx` with `src/components/Portfolio/ProductRewardsMain.tsx`; `src/app/search/SearchPage.tsx`.
- Data fetching: `src/helpers/prefetchGroupedSubgraph.ts` (single-slot 60 second cache; the `inflight` map is never populated), `src/helpers/fetchGroupedSubgraph.ts`, `src/helpers/getTokenPricesCached.ts`, `src/web3/getContracts/shared.ts` (`getAllContractData`, one `Promise.all` over every pool with ethers reads per pool), `src/redux/slices/contractsSlice.ts`.
- Route handlers under `src/app/api/**`: no `revalidate` and no `Cache-Control`; the positions routes do four sequential RPC reads per owned position and query the subgraph without `first`.
- Heavy client imports: `src/components/chart/PoolChart.tsx` (static recharts import, two `ResponsiveContainer`s mounted with one hidden), `src/lib/alchemySdk.ts` (alchemy-sdk and ethers providers for two calls viem already makes), `src/lib/wagmiClient.ts` (the wallet list).
- `package.json`: the duplicated stacks and the unused dependencies that still ship if anything imports them.

## Checklist

### Bundle and loading

- Anything newly imported from `layout.tsx`, `Providers.tsx`, or `AppLayout.tsx` ships to every route. Large libraries (recharts, alchemy-sdk, ethers, Apollo) belong behind `next/dynamic` or inside the route that needs them.
- ethers and viem, Apollo and urql, and axios beside fetch all sit in the client graph. Count importers before flagging. The finding is "X loads on every route for two calls", not "two libraries exist".
- `pool.json` (86 kB) is imported by client components and also serialized as a prop. A server-side read with a trimmed shape would drop it from the bundle.
- Fonts: the Typekit `@import` blocks first paint, `font-display` on the `@font-face` rules decides whether text waits for it, and `next/font` is not used.
- Third-party scripts: Datadog RUM in the main bundle with 100% sampling, GA as `afterInteractive`, and `public/ga.js` dead. The RUM data has value; the cost is bundle weight and a request per page.
- Images: `next/image` everywhere except `ContentfulRichText.tsx`; `images.domains` is deprecated in favor of `remotePatterns`; SVG logos through SVGR become inline React, which is fine for icons and heavy for large art.

### Rendering mode

- The route table says which pages are static. `/pool/[poolID]` prerenders nothing because `generateStaticParams` returns the wrong key; fixing it makes fourteen pool pages static HTML.
- Server shells pass props into client trees. Check that a client page does not refetch what the server could have embedded.
- Strict mode is off, so double-invoked effects never reveal missing cleanups in development. Any effect with a subscription, interval, or fetch needs its cleanup checked by reading.

### Waterfalls and duplication

- On the portfolio, Merkl rewards are fetched per chain by the page and again by each claim card, and positions are fetched once per Uniswap pool, each triggering sequential RPC reads on the server. Look for `Promise.all` chains that serialize what could run in parallel and for the same request made by sibling components.
- `AppLayout` dispatches `fetchAllContractData` on every route for every visitor, anonymous ones on the About pages included, so each visit fans out to every pool's on-chain reads through the client-side Alchemy key. Count the calls per visit (pools times reads per pool) and say which routes need none of it.
- `getAllContractData` runs every pool's reads in one `Promise.all`. One rejection loses all pool data (also a correctness finding) and the slowest pool gates the whole list.
- `prefetchGroupedSubgraph` deduplication does not work because `inflight` is never set, so concurrent mounts fire five requests each.
- There are no polling loops in the UI. The receipt `setInterval` in `transactions.ts` is the only timer and is never cleared on unmount.

### Caching

- Route handlers set no `revalidate` or `Cache-Control`, so every visitor's page load hits the TELx backend, The Graph, and Merkl. Grouped pool data changes slowly and can be cached at the edge for 30 to 60 seconds. The client caches (60 second TTL) are per tab, so they help repeat views, not first paint.
- The single-slot client cache stores a failure as `{}` for its TTL.
- React Query is present through wagmi but app data goes through Redux thunks and module caches. Where `useQuery` would replace a hand-rolled cache is a best-practices note, not a performance finding.

### Re-renders

- Provider-level state (Redux, `SkrimProvider`, `useWindowDimensions`) that updates on scroll or resize re-renders everything beneath it. Check for unthrottled resize listeners and context values recreated on every render.
- Large lists (`PoolsMain`, `SearchPoolsCards`) keyed by `pool.json` ids re-mount cards on update, because ids repeat (32 three times, 33 and 34 twice).
- `PoolChart` mounts two `ResponsiveContainer`s, one at zero width, and reverses arrays across two files on each render.

## Severity examples

- High: a route that cannot render, or a request pattern that scales with pools times positions per page load on an unauthenticated route.
- Medium: a First Load JS regression on a main route; a waterfall that delays first data by a full round trip; caching absent where upstream quota is metered; a timer or listener without cleanup.
- Low: a static import that could be dynamic; duplicated requests the browser cache absorbs; deprecated config options.
- Informational: unused dependencies, dead scripts.

## Do not flag

- The size of RainbowKit and wagmi themselves. Wallet connection needs them on every route where the header shows a connect button.
- Datadog RUM being present in production. Sampling rate and lazy loading are the discussion, not its existence.
- `reactStrictMode: false` on its own. Flag the specific effect that leaks because of it; the setting belongs to best-practices.
