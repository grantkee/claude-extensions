# App security angle

## Why this angle matters here

Three private credentials live on the server (`TELX_BACKEND_SECRET_KEY`, `TELCOIN_API_KEY`, `UNISWAP_API_KEY`), and thirteen route handlers use them to proxy upstream services for the browser. The site is wallet-connected, so any script injection is a wallet-drainer vector, and the CSP in `src/middleware.ts` is the main defense against it. Route handlers are public and unauthenticated by design. The question for each one is what an anonymous caller can make the server do with its secrets and its upstream quota.

## File map

Read first:

- `src/middleware.ts`: CSP, security headers, and the matcher, which excludes `/api`, `_next/static`, `_next/image`, the favicon, and router prefetches.
- `src/app/api/**/route.ts`, the thirteen handlers. `backend/subgraphs/*-grouped` and `backend/subgraphs/dfx` call api.telx.network with a bearer `TELX_BACKEND_SECRET_KEY`. `uniswap-user-positions-{polygon,base,ethereum}` query The Graph gateway with `UNISWAP_API_KEY` and then do viem RPC reads. `uniswap-user-rewards` reads the PositionRegistry on three chains. `merkl-user-rewards` proxies Merkl v4 with validated inputs. `dfx` forwards a POST body to a public Goldsky subgraph. `market-rate` embeds `TELCOIN_API_KEY` in the upstream URL path.
- `src/app/api/backendHelpers/helpers.ts`: viem public clients per chain and position decoding. Client components import it too, so anything added here ships to the browser.
- `.env.sample`, `next.config.ts`, `package.json`, `package-lock.json`, `scripts/security-check.js`.

Then:

- `src/components/common/RichText.tsx` (react-markdown with `rehype-raw`), `src/components/common/ContentfulRichText.tsx` (`documentToHtmlString`), `src/components/search/CardSearchAbout.tsx` (`dangerouslySetInnerHTML`), `src/app/search/SearchPage.tsx`, `src/app/about/[slug]/page.tsx`, `src/lib/getAboutPages.ts`.
- `src/app/DataDogRum.tsx`, `src/app/layout.tsx`, `public/ga.js`, `public/.well-known/security.txt`, `public/security.txt`.
- `src/lib/alchemySdk.ts`, `src/lib/contracts.ts`, `src/lib/wagmiClient.ts`: which keys reach the client (`NEXT_PUBLIC_ALCHEMY_ID`, `NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID`).

## Checklist

### Route handlers

- Every client-supplied value (`userAddress`, `poolAddress`, `chainId`, `reloadChainId`, `amount0Decimals`, `amount1Decimals`, POST bodies) is checked against a fixed shape before it touches an upstream URL, header, or query. Addresses match `^0x[0-9a-fA-F]{40}$`, chain ids are one of 1, 137, 8453, decimals are small integers, v4 pool ids are 32-byte hex. `merkl-user-rewards` is the model; compare every other handler to it. A value interpolated into a path that carries the bearer secret (`backend/subgraphs/dfx` builds `.../get/dfx/${poolAddress}`) lets a caller steer that secret to any path on the host with `../`, `%2F`, `?`, or `#`.
- Secrets never appear in a response body, an error message, or a log line. Watch for `error.message` passed through from axios or fetch, since the message can contain the URL and with it a key embedded in the path (`market-rate`), and for upstream error bodies returned verbatim (the `*-grouped` routes).
- Caching and cost are deliberate. Does each handler set `revalidate`, `cache`, or `Cache-Control` on purpose? A cache bypass the client controls (`reloadChainId`) with no rate limit lets one caller spend the server's upstream quota. A route that does several RPC reads per owned position with no cap (`uniswap-user-positions-*`, called once per pool from the portfolio) is a quota drain. Check the opposite failure too: a GET handler that never reads the request and sets no `dynamic`, which some Next versions render once at build time.
- Failure responses are a generic message with a consistent `{ error }` shape, not a stack trace or an upstream body.
- The three per-chain positions routes are copies. A fix present in one and missing from the others is one finding with three locations.
- Server-only modules stay server-only. `src/app/api/backendHelpers/helpers.ts` is imported by `"use client"` files (`src/merkl/useMerklClaim.ts`, `src/components/Portfolio/UnclaimedUniswapRewardsCard.tsx`), so a secret or private RPC URL added there would ship to every visitor.

### Middleware and headers

- `script-src` includes `'unsafe-inline'` and `'unsafe-eval'` while the middleware also mints an `x-nonce`. Find out whether anything consumes the nonce. If the wallet SDKs genuinely need `unsafe-eval` (cite the SDK docs or test by removing it), the finding is "nonce unused, inline allowed" at Low. If nothing needs it, it is Medium or High, because an injected inline script can call the connected wallet.
- `connect-src`, `img-src`, and `frame-src` are allowlists. Every host the client actually calls (Alchemy per chain, `polygon-rpc.com`, `mainnet.base.org`, the WalletConnect relays, Datadog, api.telx.network) must be present or the feature fails silently in the browser. Wildcards (`*.vercel.app`, `*.vercel-storage.com`) widen the surface. Look for hosts that appear in code but not in the CSP, and the reverse.
- `X-Frame-Options: DENY` sits next to `frame-ancestors 'self' https://verify.walletconnect.org https://telx.network`. Browsers that support `frame-ancestors` ignore `X-Frame-Options`, so decide which is intended; WalletConnect verification frames need the CSP form.
- `Access-Control-Allow-Origin` is set on page responses, where it does nothing, and not on `/api`, which the matcher excludes. API responses therefore carry no `X-Content-Type-Options` or CSP either. Low unless an endpoint returns HTML.
- `Permissions-Policy: autoplay=*`, `Referrer-Policy: strict-origin`, `X-XSS-Protection: 0`: note deviations from the usual hardening set (`camera=()`, `microphone=()`, `geolocation=()`) as Informational.
- The `/install.html` branch sets `script-src 'unsafe-inline'` without `'self'`, and no such file exists under `public/`. Dead configuration, Informational.
- Router prefetch requests bypass the middleware by design (the matcher's `missing` clause). Confirm nothing security-relevant added later, such as an auth gate, depends on the middleware running for them.

### Injection and rendering

- `RichText.tsx` renders markdown through `rehype-raw`, which passes raw HTML through. Trace what feeds it: `content/about/*.md`, `pool.json` `notice` fields, and `src/data/notices.json` are repo-controlled and fine. Contentful documents come from a CMS, and a compromised editor account becomes stored XSS on a wallet site. Ask the same of `documentToHtmlString` output rendered with `dangerouslySetInnerHTML` in `CardSearchAbout.tsx`.
- `src/lib/getAboutPages.ts` parses `content/about/*.md` with gray-matter's default engines, which include `---js` front matter evaluated at build time. Once outside contributors send markdown PRs, a front matter block can run code in the build with the deployment's secrets in the environment. Restrict the engines to YAML.
- User-controlled strings that reach the DOM or metadata: the search query on `/search`, `poolID` from the URL on `/pool/[poolID]`, wallet addresses, and token names from subgraphs (a token symbol is attacker-chosen on-chain). React escapes text children; the risks are `dangerouslySetInnerHTML`, an `href` built from data that could be a `javascript:` URL, and `metadata` exports built from data.
- External links open with `target="_blank"`. Modern browsers imply `noopener` for those, so a missing `rel` is Informational unless the `href` comes from data.
- `next.config.ts` bounds `next/image` sources (`images.ctfassets.net`) and its redirects are static. Flag anything that would let a user supply a redirect target.

### Secrets and environment

- A key that is public today stays compromised after it moves server-side; the fix for an exposed key is rotate, then move, and the finding should say so. Renaming `NEXT_PUBLIC_ALCHEMY_ID` to a server-only variable without rotating it leaves the old key live in every cached bundle.
- `NEXT_PUBLIC_*` values ship to every visitor by design: `NEXT_PUBLIC_ALCHEMY_ID` (recommend a domain allowlist in the Alchemy dashboard, Low if undocumented), the WalletConnect project id, the Datadog application id and client token, and `NEXT_PUBLIC_ORIGIN`, which is sent as a spoofed `Origin` header on server-side RPC calls with a `http://localhost:3000/` fallback.
- The server secrets are read only inside route handlers. A server component passing one to a client component as a prop, or a `"use client"` file reading one, is Critical.
- `.env*` is gitignored and `.env.sample` holds empty values. Before the repository goes public, one pass over history for key-shaped strings is worth a single command (`git log -p --all | grep -E -i '(api[_-]?key|secret|token)["'\''=: ]+[A-Za-z0-9_-]{16,}'`); go deeper only when asked.

### Dependencies and supply chain

- `scripts/security-check.js` blocks a pinned list of compromised versions on `prebuild`. It is a denylist, not an audit. Run `npm audit --omit=dev --audit-level=high` and report reachable high or critical advisories; dev-only advisories are Informational.
- Unused or suspicious dependencies: `package.json` lists `init`, a generic npm package name imported nowhere under `src/` or `scripts/`. An unused dependency that could be anything is a supply-chain smell, Low. Leave the duplicated stacks (`ethers` and `viem`, `@apollo/client` and `@urql/core`, `axios` and `fetch`) to the best-practices angle.
- `package-lock.json` is committed and installs should use `npm ci`. Flag a lockfile that has drifted from `package.json`.

### Telemetry and privacy

- Datadog RUM samples 100% of sessions and replays 20% in production with `defaultPrivacyLevel: "mask-user-input"` and `trackUserInteractions: true`. Wallet addresses and balances are rendered text, not inputs, so they can appear in replays. That is privacy rather than security: Low, with `mask` as the fix if the team wants it.
- Google Analytics loads from `public/ga.js` with a GTM container id. Whoever holds that GTM account can load arbitrary scripts, and the CSP allows `googletagmanager.com`. Informational context for any CSP finding.

## Severity examples

- Critical: a server secret readable from the client bundle, the RSC payload, or a route response; a handler that fetches a caller-supplied URL with a secret header attached.
- High: a caller-controlled path or query segment reaching an upstream that trusts the bearer secret; a CSP that lets an injected inline script run when nothing in the stack needs `unsafe-inline` or `unsafe-eval`; stored XSS reachable through a third-party content source.
- Medium: an unvalidated route parameter with limited blast radius (a bad chain id that only produces a 500); a client-controlled cache bypass with no rate limit; `rehype-raw` over CMS content.
- Low: missing security headers on `/api`; `X-Frame-Options` and `frame-ancestors` in conflict; an unused dependency; a public key with no documented domain allowlist.
- Informational: `Permissions-Policy` scope, security.txt contents, dead CSP branches.

## Do not flag

- Route handlers being public and unauthenticated. That is the design. Findings are about what a caller can make the server do, not that it can call.
- `NEXT_PUBLIC_*` values being visible in the bundle.
- The reference Solidity in `src/web3/contractCode/`. It is neither compiled nor deployed from this repository (see `SECURITY.md`).
- The known gaps documented in `CONTRIBUTING.md`.
- The `[Reown Config] ... 403` lines in a build log produced with a placeholder WalletConnect project id.
