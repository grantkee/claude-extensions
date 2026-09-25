---
name: telx-review
description: "Multi-angle review of the telx-frontend repo (telx.network: Next.js, wagmi, Uniswap v4 pools on Polygon, Base, and Ethereum, Merkl rewards). Parallel reviewers cover web3 transaction safety, app security, data correctness, UX, UI, performance, and best practices, and every finding is verified before it is reported. Use whenever the user asks to review, audit, check, or assess this codebase, a branch, a PR, or a feature area, or asks whether a change is safe or ready to merge."
---

# telx-review

Review telx-frontend, the Next.js dapp behind telx.network, from seven angles at once: web3 transaction safety, app security, data correctness, UX, UI, performance, and best practices. One Opus agent owns each angle and works from its own checklist. Their findings are merged and handed to `findings-verifier`, which re-derives every claim from the code before anything reaches the user. Use this skill for a full review, a branch or PR, or one feature area.

## Project context

telx.network is the TELx liquidity-provider dashboard. Users add liquidity to Uniswap v4 pools on Polygon (137), Base (8453), and Ethereum (1) on Uniswap itself, then come here to subscribe those position NFTs to the TELx subscriber contract (`PositionManager.subscribe` from `src/components/common/UserPositions.tsx`), watch positions and rewards, and claim the TELx rewards that Merkl distributes (this app builds and sends the claim on the Merkl Distributor). Older Polygon programs (Balancer, QuickSwap, DFX) still have Synthetix-style staking contracts that this app approves, stakes, unstakes, and exits.

The code that can hurt a user sits in three places. First, everything between a click and a signed transaction: spender, recipient, contract address, chain, amount, and decimals. Second, the pipeline that turns chain and subgraph data into the numbers people act on: prices, APRs, balances, and unclaimed rewards. Third, the route handlers under `src/app/api/`, which hold private credentials and proxy upstream services.

Stack: Next.js 15 App Router, React 19, TypeScript (strict), Tailwind v4 with CSS-first config in `src/app/globals.css`, Redux Toolkit, wagmi 2 with viem 2 and RainbowKit 2, ethers 6 and alchemy-sdk on the legacy staking paths, axios beside fetch, Apollo and urql for subgraphs, recharts, react-toastify, Datadog RUM, and Google Analytics. The pool registry is `src/data/pool.json` (44 pools: 30 legacy Polygon pools and 14 Uniswap v4 pools across the three chains); the About section is markdown in `content/about/`; some copy comes from Contentful exports.

```
src/app/            pages, layouts, route handlers (src/app/api/** proxies subgraphs, Merkl, Uniswap, and the private TELx backend)
src/components/     React components by area: contract, modal, wallet, pool, pools, Portfolio, row, common, layout, toast, and more
src/web3/           ABIs, contract getters per protocol, transaction builders (transactions.ts, hookTransactions.ts)
src/merkl/          Merkl rewards: service, claim hook, claim card, constants (Distributor, new TEL)
src/lib/            wagmi client, contract config, constants, tokens, Alchemy SDK
src/helpers/        formatting, normalization, subgraph fetch and prefetch, price caching
src/redux/          store and slices (contracts, marketRate, web3)
src/data/pool.json  the pool registry: ids, protocol, network, addresses, decimals, active, deprecated
src/middleware.ts   CSP and security headers; its matcher excludes /api
```

TEL exists in two on-chain versions and the app must never confuse them. The legacy TEL has 2 decimals and sits behind the older Polygon pools and staking contracts. The new TEL has 18 decimals, lives at `0x7E13B43065380aCdeC1c2d138c579cbBbafA0731` on every EVM chain, and is what the Merkl pools and rewards use. `src/lib/tokens.ts` and `src/merkl/merklConstants.ts` carry the distinction. A decimals mix-up is the most common way a wrong number reaches the screen or a transaction.

Toolchain: `npx tsc --noEmit`, `npm run lint`, `npx jest`, and `npm run build`, which runs `scripts/security-check.js` first. There is no CI, so the review runs these itself. Pool, portfolio, and market-rate pages need private API keys, so end-to-end rendering is usually impossible locally; the review is static unless the user gives a running URL. `CONTRIBUTING.md` documents known rough edges under "Known gaps" (Prettier configured but not installed, permissive lint, thin tests). Do not report those again.

## Severity scale

Calibrated for a dapp frontend. The question is what happens to a liquidity provider, not to a server.

| Level | Meaning | Examples |
|---|---|---|
| Critical | Funds can be lost or stolen through this UI, or private credentials leak | approve, stake, or claim sent to the wrong spender, recipient, contract, or chain; an amount built with the wrong decimals; a server secret reachable from the client bundle or through a route handler; script injection that can reach the wallet |
| High | A user can be misled into a bad financial decision or left with funds committed and no way out, or the server can be abused | balances, APRs, or rewards wrong by orders of magnitude; a claim, unstake, or exit path that reverts or silently no-ops; a route handler usable as an open proxy or for SSRF; CSP or headers that permit wallet-hijacking injection; a broken build |
| Medium | Wrong under specific conditions, poor recovery, or a real cost to users | stale balances after a transaction; no feedback after a failed transaction; unvalidated route input with limited blast radius; a keyboard-only user who cannot complete a flow; a request waterfall or polling loop that measurably slows a page |
| Low | Works, but fragile or inconsistent | inconsistent number or address formatting; a missing loading state; duplicated logic that will drift; dead code on a money path; a lint-suppressed hazard |
| Informational | Style, naming, docs, tidy-ups | naming, comments, ordering, unused imports |

## Process

The base directory printed when this skill loads is `SKILL_DIR`. Reference files live in `SKILL_DIR/references/` and scripts in `SKILL_DIR/scripts/`. `REPO` is the telx-frontend checkout, normally the working directory; confirm with `git rev-parse --show-toplevel` and the `name` field of `package.json` (`telx.network`). Pass absolute paths to every agent.

### Phase 0: Orient

1. Note the branch and working tree: `git branch --show-current`, `git status --short`.
   The review reads the checkout as it is when each agent reaches a file. If the user may switch branches in this checkout while the review runs, or asks for a worktree, create one for the branch under review (`git worktree add <path> <branch>`, then `npm ci` there, outside the repository so the root's jest and tsc never see it) and use that path as `REPO`.
2. Start the toolchain in the background so the results exist before the agents need them:

   ```
   bash SKILL_DIR/scripts/toolchain.sh REPO
   ```

   It writes `REPO/tasks/telx-review/toolchain.md` with the type check, lint, tests, and build (including the route table). It skips the build when a dev server holds port 3000 or another build is running. Pass `--no-build` when the user asks for a quick look. Nothing else in the review runs the build.
   Then, in the foreground, check the pool registry against the chain (public RPC, a few seconds, no dependencies):

   ```
   node SKILL_DIR/scripts/check-pools.mjs REPO > REPO/tasks/telx-review/pools-onchain.md
   ```

   It reports every active pool whose asset addresses lack code on the stated chain or whose configured decimals differ from the token's `decimals()`. A non-empty table is a High finding for the data-correctness angle; an RPC outage (exit code 1) is noted in the report, not treated as a finding.
3. Read the "Known gaps" section of `CONTRIBUTING.md` if you have not this session.

### Phase 1: Scope

Pick one mode from the request:

- Diff, the default on a feature branch: `bash SKILL_DIR/scripts/scope.sh REPO [base]` writes `REPO/tasks/telx-review/scope.md` with the changed files and every file that imports them. For a PR number, `gh pr checkout N` first.
- Area, when the user names a feature or directory ("the Merkl claim flow", `src/app/api`): write `scope.md` yourself with the mode, the directories and files in scope, and one sentence on what the area does.
- Full: everything under `src/`, `content/`, `scripts/`, `public/`, and the config files. Write `scope.md` with mode "full" and whatever the user asked to prioritize.

Run all seven angles for area and full reviews. For a diff, drop an angle only when none of the changed files or their importers fall in that angle's file map (each reference lists one). When unsure, keep it; an agent that finds nothing costs less than a missed finding.

### Phase 2: Spawn the angle reviewers

Spawn every selected angle in the same turn with the Agent tool, `subagent_type: "general-purpose"` and `model: "opus"`. Each agent owns one angle and one reference file:

| Angle | Reference | Owns |
|---|---|---|
| web3-safety | references/web3-safety.md | wallet config, chain switching, approvals, stake, unstake, exit, and claim transaction builders, Merkl claim, receipt handling |
| app-security | references/app-security.md | route handlers, secrets and env exposure, middleware CSP and headers, XSS and markdown rendering, dependencies |
| data-correctness | references/data-correctness.md | pool.json integrity, decimals (legacy TEL vs new TEL), price, APR, TVL, and reward math, subgraph normalization, numeric types |
| ux | references/ux.md | flows and states (connect, wrong network, pending, error, empty, stale), feedback, copy, recoverability |
| ui | references/ui.md | design tokens, component reuse, responsiveness, overflow, accessibility, visual consistency |
| performance | references/performance.md | rendering mode per route, fetch waterfalls, caching and polling, bundle weight, re-renders, third-party scripts |
| best-practices | references/best-practices.md | React, Next.js, and TypeScript idioms, server and client boundaries, error handling, duplication, tests, config hygiene |

Prompt template, with the braces replaced:

```
You are the {ANGLE} reviewer for telx-frontend, the Next.js dapp behind telx.network, where liquidity providers track Uniswap v4 positions on Polygon, Base, and Ethereum, stake legacy LP tokens, and claim TELx rewards distributed through Merkl. Repository: {REPO}.

Read these first, in order:
1. {SKILL_DIR}/references/{ANGLE}.md: your checklist, file map, severity examples, and the patterns you must not flag.
2. {REPO}/tasks/telx-review/scope.md: the review scope.
3. {REPO}/tasks/telx-review/toolchain.md: build, type check, lint, and test results already collected. If it does not exist yet, start reading code and come back to it. Do not run the build yourself.

Scope: {SCOPE_SENTENCE}. Read every in-scope file in your file map in full. Read other in-scope files when your checklist points at them, and read a file outside the scope only to verify a claim about one inside it. Stay inside {REPO}. Do not modify source files.

Checkpoint file: {REPO}/tasks/telx-review/{ANGLE}.md. On start, read it if it exists and continue from the first unfinished section. Rewrite it after each finding you add, with a `status:` header (in-progress or done) and the list of files you have finished reading. If Write is refused, return the complete text in your final answer instead. Budget: stay under 150k tokens. If you trend past that, mark the checkpoint done with a "Not covered" list and hand back.

Write findings in exactly this format; the verifier depends on the field names:

### Finding N: [title]
- **Severity (initial)**: Critical / High / Medium / Low / Informational
- **Category**: {ANGLE} / [sub-category from your reference]
- **Location**: `file_path:line_number`
- **Claim**: one to three sentences of plain fact about the code, with no consequences and no reasoning (no "so", "which means", "likely"). The impact belongs in the title and the severity. Good: "`initiateTransaction` calls `signer.sendTransaction` without a `chain`, and nothing on its call path checks or switches the wallet's chain." Bad: the same sentence followed by "so a wallet on Base sends to the wrong contract".
- **Key Question**: the single question a verifier must answer by reading the code
- **Relevant Files**: files needed to verify
- **Source**: telx-review/{ANGLE}

Rules:
- Read the code before claiming anything. Quote the flagged line in the Claim when it is short.
- Submit the ten or so most important findings for verification, highest severity first. Everything else goes in an "## Also noted" list at the end of the checkpoint file, one line each and every line with a file:line, so nothing you saw is lost; those lines are reported but not verified.
- One finding per root cause. If the same defect appears in several files, list every location in that one finding.
- Do not re-report the known gaps documented in CONTRIBUTING.md. A finding may build on one, but it must add something concrete.
- Calibrate with the severity scale in your reference. Style is Informational.

Return a summary only, no file dumps: counts by severity, the three most important findings in one line each, and the files you did not get to.
```

When an agent hands back with a "Not covered" list, spawn a fresh agent for that angle, in the same turn as any others that need it, with the same prompt plus: "A previous agent covered part of this angle. Read the checkpoint first, then review only the files listed under Not covered, and append your findings to the checkpoint, continuing the numbering." Wait for those before Phase 3.

### Phase 3: Assemble the findings

Read the angle checkpoint files under `REPO/tasks/telx-review/`. Triage before writing anything:

1. Merge duplicates. The same location and the same defect from two angles become one finding that lists both sources.
2. Re-check severity against the scale. Angle agents rate their own area high; a UX or UI finding is High only when the user cannot tell whether their money moved or cannot complete a transaction, and a performance finding is High only when a route cannot render.
3. Decide what the verifier sees. Every Critical, High, and Medium finding goes to verification. Low findings go to verification for a diff or area review; for a full review they move to "Also noted" so the verifier's capacity goes to findings that matter.

Then number the findings and write `REPO/report-{branch}.md`, with `/` in the branch name replaced by `-`, in this shape. Copy each finding's fields verbatim from its checkpoint; edit only the title, severity, category, and source lines when triage changed them, and list every merged location.

```
# telx-review: [scope description]
Date: [date]
Branch: [branch]
Scope: [mode, then the file list or area]
Angles: [angles that ran]

## Toolchain
[one line each for type check, lint, tests, build: pass or fail, with the failing output when it fails]

## Summary
[1-2 sentences]
| # | Title | Severity (initial) | Category | Status |
|---|-------|--------------------|----------|--------|

## Action items
[filled in after verification: fix before merge (Critical and High), fix soon (Medium), backlog (Low), each item as "N. title (file_path)"]

## Findings
[each finding in the canonical schema, Status: Pending verification]

## Also noted
[the angle agents' unverified one-liners, grouped by angle]

## Coverage
[per angle: files read, files not covered]
```

A failing build, type check, or test run is itself a finding and goes in the table: High for the build, Medium for the rest unless the failure is on a money path.

### Phase 4: Verify

Spawn the `findings-verifier` agent with the Agent tool (`subagent_type: "findings-verifier"`). Do not present anything before it returns. Pass it:

1. The path to `report-{branch}.md` and the instruction to update that file in place.
2. The scope context and the file list from `scope.md`.
3. The severity scale from this skill, verbatim, with a note that the codebase is TypeScript, React, and Next.js, so its Rust guidance (`debug_assert!`, borrow checker, consensus determinism) does not apply. Verifiers should check TypeScript types, runtime guards, wagmi and viem semantics, Next.js server and client boundaries, and existing tests instead. Ask it to include the scale in every verification subagent prompt.
4. For a full review, permission to raise its verification agent cap from 12 to 30, and the instruction to batch Tier 1 findings two per agent, grouped by subsystem, whenever there are more than ten of them.
5. A note on shape: readers scan the summary table and then open one finding, so each finding should read in about a minute. Evidence is citations with `file_path:line_number`, not narrative, and a proposed fix is the smallest diff that resolves the claim, not a redesign. Verifiers keep the content that supports the verdict and drop the rest.

The verifier confirms or dismisses each finding, proposes a fix for each confirmed one, updates the report, and presents the confirmed results with verification statistics.

### Phase 5: Present

After the verifier's summary, add what it cannot know:

- The toolchain line: build, type check, lint, tests.
- Which angles ran and any files an angle did not cover.
- Action items grouped as fix before merge (Critical and High), fix soon (Medium), and backlog (Low), in that order. Write the same list into the report's "Action items" section so the report stands alone; a reader who opens the file a week later must not need the chat.

Keep the conversation summary short; the report holds the detail. Then spawn the `format-output` agent on the report path so the file gets the repository's markdown layout rules.

## Rules

- No finding reaches the user without verification. Unverified findings cost the reader more than they give.
- Read the code before claiming anything, and give `file_path:line_number` for every finding.
- A Claim is a factual assertion, never a reasoning chain. A verifier must be able to test it cold.
- A finding without a fix is half-finished. The verifier proposes one for each confirmed finding, and the report is not done until it does.
- Severity follows the user's exposure, not the size of the diff. A one-character decimals change can be Critical; a 400-line refactor of the About page is rarely above Low.
- Token amounts on money paths are `bigint` built with `parseUnits` and the token's real decimals. `number` arithmetic on a raw token amount is at least Medium.
- A route handler that takes a URL, address, chain, or pool id from the client checks it against an allowlist before using it upstream. Anything else is at least High.
- Respect the documented known gaps and report what is new.
