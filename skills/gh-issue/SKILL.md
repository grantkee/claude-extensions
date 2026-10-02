---
name: gh-issue
description: Generate two markdown files for the current branch — a focused GitHub issue (Problem/Solution) and a PR body (Closes / Problem / Changes / Testing). Trigger on "create an issue", "gh issue", "draft issue", "issue for this branch", "PR body", "PR description", or when the user wants to describe their branch changes for reviewers. Do NOT trigger for posting to GitHub via the API — this skill writes local markdown files only.
---

# gh-issue

Generate two local markdown files for the current branch:

1. **`issue.md`** — A focused GitHub issue describing the core problem the branch solves and the high-level approach. Narrow scope: one problem, one solution.
2. **`comment.md`** — The PR body: the issue it closes, a one-paragraph problem summary, the changes as short bullets, and the testing that was run.

These serve different audiences at different moments. The issue is read before the code — it frames the "why" for maintainers and security researchers evaluating the PR. The PR body is read alongside the diff — it tells reviewers what was wrong, what changed, and how the change was checked, not a file-by-file inventory.

## Process

### Step 1: Gather branch context

Run these in parallel to understand the branch:

1. **Identify the base branch** — check if `main` or `master` exists, or use the most likely upstream branch.
2. **Get the full diff** — `git diff <base>...HEAD` to see all changes on this branch.
3. **Read commit messages** — `git log <base>..HEAD --oneline` for the commit history on this branch.
4. **Get the branch name** — `git branch --show-current` since the branch name often hints at intent.
5. **Find the issue number** — look in the user's request, the branch name, and the commit messages for the issue this branch closes (`#1444`, `issue-1444`). The PR body opens with it.
6. **Collect test results** — note every check that ran in this session (fmt, clippy, test suites, e2e runs) with its command and outcome, plus any results the user reported. The Testing section is built from these and nothing else.

### Step 2: Analyze the changes

Read through the diff and commits to understand:

- **What changed**: which files, modules, or components were touched
- **The primary motivation**: what single problem or need is the branch named after? This becomes the issue.
- **Everything else**: what other changes ride along — refactors, cleanups, dependency updates, test additions? These get their own bullets in the PR body.
- **What category each change falls into**: new feature, bug fix, security patch, refactor, configuration change, dependency update, etc.
- **What's at stake**: what happens if the primary problem isn't addressed? For bugs: what breaks. For features: what's missing. For security: what's the risk.

### Step 3: Write the issue file (`issue.md`)

The issue covers only the primary problem the branch addresses — the thing the branch is named after. If the branch adds a basefee contract, the issue is about the need for a basefee contract. If it fixes a validator timeout, the issue is about the timeout bug. Everything else belongs in the PR body.

```markdown
# [Concise title describing the problem or need]

## Problem

[2-4 paragraphs describing the problem, need, or context. Be specific about what's wrong, missing, or needed. Include:

- What the current behavior or state is
- Why it's problematic or insufficient
- What impact this has (on users, security, functionality, etc.)
- Any relevant background context that helps a reviewer understand the domain]

## Solution

[1-3 paragraphs outlining the proposed approach at a high level. Write as a proposal — what _should_ be done, not what _was_ done. Use prescriptive framing ("introduce X", "X should expose", "X should reject") even though the solution is based on actual code changes. The issue is read before the PR, so it should sound like a recommendation for reviewers to evaluate.

Describe:

- The general strategy for addressing the problem
- Key design decisions and why they were made
- Which components or areas are affected
- Any tradeoffs or considerations

If it helps clarify the approach, include brief pseudocode — but never include actual implementation code. Reviewers will see the real code in the linked PR.]
```

**Issue writing guidelines:**

- **Problem section**: Lead with what's wrong or missing. Be specific enough that a maintainer unfamiliar with the recent work can understand it. For security patches, describe the risk without providing exploit details — give enough for security researchers to assess the fix.
- **Solution section**: Write as a proposal — describe what _should_ happen, not what _has_ happened. Use prescriptive language ("introduce", "should expose", "should reject") rather than past-tense or present-tense descriptions of completed work ("exposes", "is deployed", "was added"). The content should still be informed by the actual code changes — you're describing the same approach, just framed as a recommendation rather than a changelog. This matters because the issue is meant to be read _before_ the PR, as context for evaluating whether the approach is sound.
- **No code**: Describe the approach in plain language. Focus on "what" and "why", not "how" at a code level. Mention affected components so reviewers know where to look. Never paste actual code from the diff.
- **Tone**: Precise technical language. Every sentence earns its place. Succinct means no filler, not fewer facts.
- **Length**: As long as the problem needs. An issue for a single branch is usually a few paragraphs a maintainer can scan in a couple of minutes. A research-backed issue that carries evidence, hazards and measurements can run to a couple of thousand words, and should be navigable by its headings. A word count from the user is a target, not a gate (see the `human-writing` skill, "A word count is a target, not a gate"): never drop verified content to reach it, never run a compression pass, and never hand a subagent a hard ceiling. If a draft runs past a suggested length, keep the content and tell the user the count.

### Step 4: Write the PR body file (`comment.md`)

The PR body has a fixed shape: the issue it closes, the problem, the changes, the testing, and an optional closing paragraph on limits. A reviewer should be able to read it top to bottom and know what was wrong, what the diff does about it, and what evidence says it works.

The file holds the body only, with no title heading. The PR title goes in GitHub's title field, so report a suggested title in Step 7 instead.

```markdown
Closes #[issue number].

## Problem

[One paragraph summarizing the problem the issue describes.]

## Changes

- **[Short label]:** [what changed, and why if the diff doesn't make it obvious]
- **[Short label]:** [next change]
- **Tests:** [what the new tests cover]

## Testing

- [command or lane, and its result with counts]
- [further checks, including any still pending]

[Optional closing paragraph: what this PR does not fix, known limits, follow-ups, merge order.]
```

A finished body looks like this:

```markdown
Closes #1444.

## Problem

`tn_worker_batches_sealed_total`, `tn_worker_batch_size_bytes` and `tn_worker_batch_transactions` were recorded when a batch reached quorum, before it was stored and reported to the primary. A validator that could not report re-sealed the same batch about every 2 s and counted it each time; one validator counted a 1,428-transaction batch 1,457 times in the 2026-09-23 run.

## Changes

- **Record after the report:** move the record from the quorum arm of `seal_non_empty` to after `report_own_batch` succeeds. A `FatalDBFailure` after quorum is no longer counted, since the batch was neither stored nor reported.
- **HELP text:** the three series now say "quorum reached, stored, and reported to the primary". No series is renamed.
- **Operator docs:** `validator-operations.md` says the histogram records each batch once, when its worker reports it, and that the summed estimate runs low.
- **Regression test:** `seal_records_batch_metrics_only_after_report` drains the recorder after each seal and asserts nothing after a failed report and exactly one count after a successful one.

## Testing

- `etc/ci-lanes.sh fmt` and `etc/ci-lanes.sh clippy` (default and all features, `-D warnings`) passed; `cargo nextest run -p tn-worker` passed 50/50, again after the rebase onto main.
- Mutation checks: recording at quorum, or only on the failed-report branch, fails the first-seal assertion.
- `make attest` is running on this commit.

The metric now means "reported", not "committed"; executor counts remain the source for committed volume. The batch-builder HELP lines and the 1,000 top bucket (#1511) are follow-ups.
```

**PR body writing guidelines:**

- **Closes line**: The first line, alone, as `Closes #N.` so GitHub links the issue and closes it on merge. Use the number found in Step 1. When `issue.md` is being drafted in the same run the issue usually has no number yet: write `Closes #TODO.` and tell the user in Step 7 to fill it in after filing the issue. Never guess a number.
- **Problem section**: One paragraph condensed from the issue's Problem section. Name the code at fault, say what it did wrong, and say what an operator or user saw as a result. Describe the old behavior in the past tense. Use concrete figures (counts, intervals, the date of the run that showed it) when the issue, the user, or the code supplies them, and never invent one. Background and the fix stay out of this section.
- **Changes section**: One bullet per behavior change, not per file or per commit. Each bullet opens with a short bold label ending in a colon, then one to three sentences. Name the functions, types, metrics and error variants a reviewer will look for in the diff. Tests and docs each get their own bullet. Say what was deliberately left alone when a reviewer would expect it to change ("No series is renamed", "`CACHE_MAX` stays 1 GiB"). Ride-along changes from Step 2 go here as their own bullets.
- **Testing section**: What was run and what happened. Give each command or lane in backticks with its result and counts ("passed 454/454, and 468/468 after the rebase onto main"). If the fix was reverted to confirm the new tests fail, say which revert fails which test. State pending checks as pending ("`make attest` is queued"). Report only results observed in this session or given by the user. With no results to report, list the checks that cover the change as not yet run and flag the section in Step 7 — a fabricated pass is worse than a gap.
- **Closing paragraph**: Optional and unheaded. Use it for what the PR does not fix (with issue numbers), known limits of the fix, follow-ups, and merge order relative to other PRs. Leave it out when there is nothing to say.
- **PR title**: Follow the repo's commit convention as seen in `git log`. For conventional commits that is `type(scope): summary` in the imperative, e.g. `fix(worker): record batch metrics only after the primary accepts the report`.

**Don't:**

- List every file changed — that's what the diff is for
- Repeat the title in the body or add a title heading
- Add sections beyond Problem, Changes and Testing
- Restate the issue at length — the Closes line links it
- Use filler like "This PR introduces...", "comprehensive", "robust", "enhance", "leverage"

### Step 5: Save the files

- **Issue file**: `issue.md` in the project root.
- **PR body file**: `comment.md` in the project root.

### Step 6: Evoke format-output agent

Evoke the `format-output` agent to ensure formatting is correct for all markdown files created by this skill.

### Step 7: Present the results

Show the user the full contents of both files so they can review inline. Mention both file paths, give the suggested PR title, and point out anything left for them to fill in: a `Closes #TODO.` line or checks listed as not yet run.
