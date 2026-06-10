---
name: outline-code
description: >
  Trace code flow as an indented-outline document where indentation marks logic forks.
  Produces a flow doc with an overview, a coupling/wiring table (channels, shared state,
  events), per-flow outlines citing file:line on every node, and a goal-driven analysis
  section (condensation opportunities by default). Use this whenever the user wants to
  understand how a module/crate/subsystem flows, says code "feels loosely organized" or
  "hard to follow", wants to "track the flow", "outline the logic", "map the call paths",
  "see every branch/fork", or wants to understand code well enough to condense, simplify,
  or refactor it — even if they don't say the word "outline". Also trigger when the user
  asks for a document tracing which events cause which functions to run.
---

# outline-code

Produce a flow document for a code scope: every function traced as an indented outline where each indent level is a logic fork, every node cites `file:line`, plus the implicit coupling between flows (channels, watches, queues, shared state) as a wiring table. The document exists so a reader can hold the whole subsystem's control flow in their head and act on a goal — usually spotting ways to condense the logic.

## Phase 0 — Scope, goal, output

Parse these from the prompt before reading any code:

- **Scope**: the @-mentioned files, named module/crate, or directory. Then expand to *coupled context* — the document is far more useful with it: (a) the spawn/call sites of the scope's entry points, (b) the upstream writers that feed any channel/watch/shared state the scope reads, (c) the downstream consumers of what the scope produces. The scope's own files get full fork-level detail; coupled files get traced only along the paths that touch the scope.
- **Goal**: what the user wants the document *for*. "Condense / simplify / loosely organized" → condensation opportunities. "Find bugs / suspicious" → risk observations. "Onboarding / understand" → reading-order notes. No stated goal → default to condensation opportunities. The goal shapes only the final analysis section; the outlines are always neutral.
- **Output path**: explicit path if given; otherwise `<scope-name>-flow.md` at the repo root.

Ask the user only when something is genuinely undecidable — two plausible scopes, a goal that could be read two ways, or a presentation choice the prompt doesn't settle (e.g., mermaid vs tables). Otherwise infer and proceed; state your inferences in the final summary so they can be corrected.

## Phase 1 — Trace the source map first

Before writing anything, build a map by grepping, not by reading files end-to-end:

1. List the scope's functions and entry points (spawned tasks, public API, handlers).
2. For each entry point, find its call/spawn sites — including outside the scope. Note the gating conditions (mode checks, feature flags, config).
3. Find the coupling mechanisms: channel/watch/queue accessors, shared structs, event topics, globals. Grep each name across the repo to enumerate every producer and consumer site. Whatever the codebase's mechanism is — a message bus, tokio watches, event emitters, pub/sub, callbacks — that's the wiring table's subject.
4. Record everything as `item → defined at → called/spawned from` with file:line.

This map is the input for every later step. Getting it right up front prevents agents (or you) from mislabeling producers/consumers later.

## Document structure

Use this exact skeleton:

1. **Title + notation line** — one sentence stating what the doc traces, then: outline notation is `- event/condition → function_name (file.rs:line)`; each indent level is a logic fork. Follow with a **file key table** mapping the bare file names used in citations to full paths.
2. **Overview** — the long-running tasks / entry points as a list, each with `function (file:line)`, its spawn site, and the condition gating it (mode, flag). End with one paragraph giving the mental model — typically *who produces targets, who produces data, who consumes* — refined to match what the code actually does.
3. **Coupling wiring table** — one row per channel/shared-state item: name | primitive + definition line | producers (each `function (file:line)`) | consumers (same). After the table, at most 2-3 one-line notes for non-obvious semantics (dedupe-before-send guards, mutex-wrapped receivers, lookalike fields that are NOT part of the wiring).
4. **Flow outlines** (h2) — one h3 per flow. Order: startup topology first, then one section per major flow following the data (e.g., trigger → transform → consume), the downstream consumer last. If verification finds functions no flow covers, add a final "helpers called from outside the flows above" subsection rather than silently dropping them — the doc's claim is *every* function.
5. **Analysis section** (goal-adapted; default heading "Condensation opportunities") — titled bullets, 2-4 sentences each: what's duplicated/awkward with file:line for *each* occurrence, then the concrete remedy (helper name/shape, merged function, enum). Order by impact. Mark borderline items lower-confidence and say what would need confirming. No code blocks unless a 2-3 line sketch genuinely clarifies.

## Outline style contract

These rules are what make the document scannable; hold every section to them:

- Node format: `- <event/condition> → function_name (file.rs:line)`. Condition first, then arrow, then target. Branches that don't call a function: `- <condition> → <action> (file:line)`.
- 2-space indent per level. Indentation means exactly one thing: a logic fork. Every `if`/`else`, `match` arm, `select!` arm, early return, and loop exit in a traced function appears as a child node under the node where the fork happens.
- One line per node. No prose paragraphs inside outlines. A single one-line lead-in sentence per section is allowed.
- When a flow reaches another flow's territory, reference it (`→ epoch pack download flow`) instead of expanding it — each flow is documented once.
- Overloaded semantics deserve a callout on the node itself (e.g., a return value meaning retry vs continue vs done).
- Completeness bar: every non-test function in the scope appears at least once; every branch point appears as a fork. Coupled files only need the branches on paths that touch the scope.

Example (from a consensus state-sync trace):

```
- watch updated → `spawn_track_recent_consensus` loop wakes (consensus.rs:130)
  - `rx_gossip_update.changed()` fires → forward `(epoch, number, hash)` into `consensus_request_queue` (consensus.rs:142-145)
  - `rx_shutdown` fires → return (consensus.rs:148-150)
- queue item received → `manage_new_consensus` (consensus.rs:314)
  - first gossip: `first_gossipped_epoch.is_none()` → spawn backtracking fetch to genesis (consensus.rs:332-354)
  - subsequent gossip → throttle on AtomicI32 `tasks` (consensus.rs:355-359)
    - `task_num < 6` → spawn bounded backtracking fetch (consensus.rs:361-383)
    - `task_num >= 6` → skip; subsumed by later gossip (consensus.rs:360)
```

## Execution — scale to the scope

**Small scope (roughly ≤2 files / ≤800 lines of in-scope code):** trace and write inline. Still do Phase 1 first and still run the verification pass below.

**Larger scope:** parallelize with subagents, **one agent per document section** — never bundle sections into one agent. Spawn the whole batch in one message: one agent each for the overview, the wiring table, and each flow outline. Give every agent:

- the exact file paths and relevant line ranges,
- the Phase 1 source map (as hints to verify, not trust),
- the style contract above,
- an output contract: *"Your final message is consumed by an orchestrator assembling a larger document. Return ONLY the finished markdown for your section, starting with its heading — no preamble, no commentary. Verify every line number against the source you read."*

Then assemble and normalize. Expect cross-agent discrepancies — two agents will describe the same producer/consumer with different file or function labels. Resolve every conflict by reading the cited source yourself before assembly; never pick one agent's label over another's without checking the code.

After assembly, spawn **one analysis agent** for the final section. It reads the *assembled document* plus the source, so its observations build on the verified outlines. Seed it with any duplication/awkwardness you noticed during Phase 1 and assembly, and tell it to confirm or drop each seed with line evidence and to find what the seeds miss.

## Verification — always, before presenting

Two independent checks (parallel agents for large scopes, inline for small):

1. **Citation check**: extract every `file:line` reference and verify the named construct sits there (±2 lines). Read each source file once and batch-check its citations. Report wrong vs off-by-small separately.
2. **Completeness check**: (a) enumerate every non-test function in scope — each must appear in the doc by name; (b) walk every traced function's branch points — each must appear as an outline fork; (c) grep every coupling accessor — each non-test usage site must appear in the wiring table.

Fix everything found: correct off-by-small anchors, fix mislabeled function names in the table, add missing wiring rows, and cover missed functions (usually as the "helpers" subsection). This pass routinely catches real errors — in practice it has found missing functions, a missing table consumer, and wrong function labels that section agents introduced confidently.

Finish by summarizing for the user: what was produced, the inferences made in Phase 0, the verification results (citations checked, anything fixed), and the top findings from the analysis section.
