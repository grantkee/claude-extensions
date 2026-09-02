---
name: report-to-pr-comments
description: >
  Turn a code-review findings report into inline GitHub PR review comments, published as a
  PENDING review that the user submits by hand. Takes a report (typically `report.md` from
  tn-review / findings-verifier, but any findings list works) plus a PR, strips the audit
  scaffolding, anchors each finding to a real diff line, and creates the review without
  submitting it. Use this whenever the user wants review findings put onto a PR — "post the
  findings", "turn the report into PR comments", "comment these on the PR", "leave inline
  comments", "draft a pending review" — even if they don't say "pending". Do NOT trigger for
  producing the review itself (that's tn-review) or for local markdown files (that's gh-issue).
---

# report-to-pr-comments

Take a findings report and put it on a pull request as inline review comments, one per finding, each anchored to the diff line it is about. The review is created but never submitted, so the user reads every comment in the GitHub UI and decides what to send.

A report and a PR review are different documents written for different readers. The report is an audit artifact: numbered findings, severities, verdicts, verifier counts. The PR review is a maintainer talking to an author about their diff. This skill does that conversion. What it must not do is turn a page of evidence into two terse sentences — the author cannot act on "this may panic", and the reasoning that made the finding worth reporting is exactly what makes the comment worth reading.

Three failure modes to design against, in order of how often they bite:

1. Over-condensing. The comment ends up less useful than the report it came from.
2. Bad anchors. A comment's line is not in the diff, so the API rejects the whole review, or the anchor lands on unrelated code.
3. Accidental submission. Passing an `event` turns a draft into a published review under the user's name.

## Process

### Phase 1: Establish the target

Collect and confirm before touching any content:

- The repo and PR number. `gh pr view --json number,headRefOid,baseRefOid,url` if a PR is checked out, otherwise ask.
- The PR head SHA: `gh api repos/{owner}/{repo}/pulls/{n} --jq .head.sha`.
- The local checkout SHA: `git rev-parse HEAD`.
- The report path. Default to `report.md` or `report-*.md` in the repo root.

If the head SHA and the local HEAD differ, stop and say so. Line numbers in the report were computed against the local tree; the diff you anchor into belongs to the remote head. Mapping one onto the other silently produces anchors that are off by however far the file drifted. Either fetch and check out the head SHA, or ask the user which is authoritative.

Check auth with `gh auth status`. See the permissions section at the end if the token is new.

#### Working files

Everything this skill writes is scratch: `anchors.json`, one markdown file per comment, the review body, and the payload. None of it belongs in the user's repo. Make a working directory outside the checkout (the session scratchpad, or `mktemp -d`), `cd` there, and keep the paths below relative to it.

The two helper scripts live beside this file, which after `make install` means `~/.claude/skills/report-to-pr-comments/scripts/`. Set `SKILL_DIR` to wherever this SKILL.md was loaded from and call them as `python3 "$SKILL_DIR/scripts/..."`; the snippets below write `scripts/...` for brevity.

### Phase 2: Pre-flight — audit what is already on the PR

Never draft against an empty slate. Read all three comment surfaces, because they hold different things and only reading one leaves you re-raising something already settled:

```bash
gh api repos/{owner}/{repo}/issues/{n}/comments --paginate   # PR conversation comments
gh api repos/{owner}/{repo}/pulls/{n}/reviews  --paginate    # review summaries + state
gh api repos/{owner}/{repo}/pulls/{n}/comments --paginate    # inline comments, all threads
```

That reviews call also answers the blocking question: GitHub allows **one pending review per user per PR**, and a second `POST` is rejected.

```bash
gh api repos/{owner}/{repo}/pulls/{n}/reviews --paginate --jq '.[] | select(.state=="PENDING") | {id, user: .user.login}'
```

The API only ever shows the authenticated user their own pending review, so anything this returns belongs to the user. If it returns something, stop here and tell them, before drafting anything. Do not delete it — a pending review is unpublished work nobody else can see, and deleting it destroys it with no recovery. Ask whether they want to submit or discard it first, and let them do it.

From the inline comments, keep for each one: `id`, `path`, `line`, `original_line`, `position`, `in_reply_to_id`, `user.login`, `body`. A `position` of `null` means the comment is outdated against the current head — the code it was written about has moved or gone. Outdated does not mean resolved; read the body before assuming the point was addressed.

Then check every finding against that history and classify it:

| What you find | What to do |
|---|---|
| Duplicate — the point was already raised | Drop it, or reframe it to engage with how it was resolved. A thread closed as "OBE" where only half the issue actually went obsolete deserves a new comment about the surviving half, not a restatement of the original. |
| Contradiction — the finding asks to undo a change a reviewer explicitly requested and the author made | Never post as-is. Either drop it or rewrite it as a question about the tradeoff the requested change introduced, acknowledging the request. |
| Design intent — the finding's premise is a documented, deliberate choice | Reframe from a correctness claim to a cost or observability one. "This is wrong" becomes "this costs X per epoch and there's no metric for it, is that the intended tradeoff?" |
| Overlaps an open thread but adds new information | Post a new comment that opens by linking the existing thread (see the reply gotcha below). |
| New | Post it. |

Report this reconciliation to the user before drafting. It is the step most likely to change what gets posted, and the user usually knows context you don't.

### Phase 3: Select findings and map anchors

Drop every finding marked FALSE_POSITIVE. Those never become comments. If one is worth recording — the author might reasonably wonder about it — mention it in the review body as checked and fine, in one clause.

For each surviving finding, resolve an anchor. Dump the diff once so you can read patches by hand, which step 3 below needs:

```bash
gh api repos/{owner}/{repo}/pulls/{n}/files --paginate > files.json
```

Each entry has `filename`, `status`, and `patch`. A comment's `line` **must fall inside a hunk of that file's patch**. This is the single most common way the whole request fails: findings routinely cite code the PR only *affects* rather than changes.

`scripts/diff_anchors.py` does the lookup:

```bash
python3 scripts/diff_anchors.py check OWNER/REPO 1234 crates/worker/src/batch_fetcher.rs 212
python3 scripts/diff_anchors.py lines OWNER/REPO 1234           # every commentable line, per file
```

Anchor selection, in order:

1. The cited line is in the diff on a `+` line. Use it.
2. The cited line is in the diff but is a context line. Prefer the nearest `+` line in the same hunk if it is the same code — the same statement, the same function. Otherwise keep the context line; context lines are commentable.
3. The cited line is not in the diff. Pick the nearest in-diff line that is *topically* right, not numerically nearest. Read the patch: anchor on the call that reaches the problem code, the changed guard that stops protecting it, the new field it reads. A `+` line beats a context line.
4. Nothing in the file fits, or the file has no `patch` at all (too large, binary, pure rename). Move the finding into the review body with its `file:line` and say why it has no anchor.

**Whenever the anchor is not the cited line, name the real line in the comment body.** One sentence: "The code I'm asking about is `crates/worker/src/batch_fetcher.rs:412`, which this PR doesn't change — commenting here because this is the call that reaches it." Without that the author reads the comment against the wrong code.

For a finding about a block, anchor a range with `start_line` and `line`. Both must be on the same side and in the same hunk, and `start_line` must be less than `line`.

Record anchors as you go, in `anchors.json`, naming each finding's body file here even though Phase 4 is what writes it. Phase 5 then builds the payload without re-deriving anything:

```json
[
  {"file": "01-batch-fetcher-backoff.md", "path": "crates/worker/src/batch_fetcher.rs", "line": 212},
  {"file": "02-epoch-guard.md", "path": "crates/epoch/src/manager.rs", "start_line": 88, "line": 94}
]
```

### Phase 4: Write the comment bodies

Write each comment to its own file, `comments/NN-slug.md`. Separate files keep the unwrap step and the payload assembly mechanical, and let you re-read a body without scrolling a JSON blob.

**The content is the report's content.** Preserve the concrete line numbers, the code excerpts, the call chain, the failure scenario, the regression evidence against the merge base, the proposed fix. If the report showed that `main` had a backoff and this branch dropped it, that comparison is the strongest thing in the comment — keep it. The comment should be roughly as long as the finding was, minus the scaffolding.

What to strip and what to keep:

| Report element | Comment |
|---|---|
| Severity (Critical / High / Medium / Low / Informational) | Drop. Urgency comes from what the comment describes. |
| Verdict (CONFIRMED / PARTIALLY_VALID / FALSE_POSITIVE) | Drop. FALSE_POSITIVE means don't post at all. |
| Confidence rating, verifier counts ("2/2 verifiers agreed") | Drop. |
| Finding number, category label | Drop. |
| Prose arguing why a finding got its severity | Drop. Nobody is grading the finding. |
| Field labels (Claim, Key Question, Location, Relevant Files) | Drop the labels, keep the content. The Claim becomes the opening sentence. |
| Code excerpts, line numbers, call chains, repro steps | Keep verbatim. |
| Regression evidence vs the merge base | Keep. |
| Proposed fix | Keep, as a suggestion rather than an instruction. |

Voice: a maintainer reading a diff. Ask about things you're not sure of, propose fixes as suggestions, and state facts as facts without ceremony.

| Report | Comment |
|---|---|
| "**Severity**: High. **Verdict**: CONFIRMED (2/2). The `unwrap()` at line 88 panics on an empty batch." | "This `unwrap()` panics if a peer sends an empty batch, which takes the node down instead of dropping the message." |
| "**Claim**: The retry loop has no backoff." | "The retry loop reissues immediately after a timeout, so a slow peer gets hammered at the same rate as a fast one. On `main` this waited on `retry_backoff` first; that wait is gone in this diff." |
| "Recommendation: add bounds checking." | "Could we bound this by `MAX_BATCH` before the index? An untrusted `header.len()` reaches it directly from the network path." |

When the fix is a small in-place edit, a suggestion block lets the author accept it with one click:

````markdown
```suggestion
    let backoff = self.retry_backoff * attempt;
```
````

The suggested text replaces exactly the anchored lines, so use it only when the anchor is precisely the lines being replaced. Otherwise use a plain fenced block.

#### The linebreak rule

GitHub renders a single `\n` inside a comment paragraph as `<br>`. A report hard-wrapped at 80 columns becomes a ragged column of short lines in the comment box. **Every prose paragraph must be one long line.** Fenced code blocks, table rows, and list items keep their own lines — joining those breaks them.

Worked example. Report source:

```markdown
The retry loop reissues the request immediately after a timeout, so a slow
peer gets hammered at the same rate as a fast one. On `main` the same loop
waited on `retry_backoff` before reissuing.

- `batch_fetcher.rs:212` — the loop
- `batch_fetcher.rs:240` — where the backoff used to be applied
```

Comment body:

```markdown
The retry loop reissues the request immediately after a timeout, so a slow peer gets hammered at the same rate as a fast one. On `main` the same loop waited on `retry_backoff` before reissuing.

- `batch_fetcher.rs:212` — the loop
- `batch_fetcher.rs:240` — where the backoff used to be applied
```

The two prose lines joined into one; the list items did not.

`scripts/unwrap_prose.py` does this, skipping fences, tables, list items, headings, and blockquotes:

```bash
for f in comments/*.md; do python3 scripts/unwrap_prose.py "$f" > "$f.tmp" && mv "$f.tmp" "$f"; done
```

Run it, then read one body back to confirm it did the right thing. The script is a convenience, not an excuse to skip looking.

#### Review body

Write `review-body.md`: what was reviewed (scope, base..head), how many comments follow, anything checked and cleared, and any finding that could not be anchored inline. Same voice. No severity table, no verdict counts.

#### Overlapping an existing thread

A pending review cannot reply into an existing thread. Replies are a separate, immediate-post API (`POST /pulls/{n}/comments/{id}/replies`) and posting one would publish under the user's name without review. So when a finding overlaps an open thread, post a **new** comment that opens by linking the old one, which keeps it from reading as thread-forking:

```markdown
Following up on https://github.com/OWNER/REPO/pull/1234#discussion_r2044556677 — that thread closed as OBE, but the `flush_on_drop` half of it still applies here because ...
```

Use the full URL. A bare `#discussion_r...` does not link.

### Phase 5: Create the pending review

Assemble the payload from the files, rather than by hand, so no body gets mangled by shell quoting:

```bash
export HEAD_SHA=$(gh api repos/{owner}/{repo}/pulls/{n} --jq .head.sha)

python3 - <<'PY' > payload.json
import json, os, pathlib
head = os.environ["HEAD_SHA"]
anchors = json.loads(pathlib.Path("anchors.json").read_text())
comments = []
for a in anchors:
    c = {"path": a["path"], "line": a["line"], "side": "RIGHT",
         "body": pathlib.Path("comments", a["file"]).read_text().rstrip()}
    if "start_line" in a:
        c["start_line"] = a["start_line"]
        c["start_side"] = "RIGHT"
    comments.append(c)
payload = {"commit_id": head,
           "body": pathlib.Path("review-body.md").read_text().rstrip(),
           "comments": comments}
print(json.dumps(payload, indent=2))
PY

gh api repos/{owner}/{repo}/pulls/{n}/reviews --method POST --input payload.json \
  --jq '{id, state, html_url}'
```

The response must say `"state": "PENDING"`. Anything else means an `event` slipped into the payload and the review is now public. Keep the `id` — Phase 6 needs it.

Pass `commit_id` explicitly, set to the head SHA from Phase 1. Left out, GitHub anchors against whatever the head is at request time, so a push landing between the files fetch and the POST silently moves every comment.

**Omitting `event` is what makes the review PENDING.** Never pass `APPROVE`, `REQUEST_CHANGES`, or `COMMENT`. This skill does not submit reviews under any circumstance, including when the user says "post it" — posting means creating the pending review. Submitting is theirs.

Re-run the Phase 2 pending-review check immediately before the POST. Drafting takes a while and the user may have opened one in the browser meanwhile; the same rule applies, stop rather than delete.

`side: "RIGHT"` anchors to the post-change file and is what you want for nearly everything. Use `"LEFT"` only to comment on a removed line, where `line` is its number in the pre-change file.

Errors to expect from the POST, all 422, all rejecting the whole request so nothing is created:

| Message | Cause |
|---|---|
| `pull_request_review_thread.line must be part of the diff` | An anchor is off-diff. Re-run the Phase 3 check for that comment. |
| `pull_request_review_thread.start_line must be part of the same hunk as the line` | A range spans two hunks. Split it or shrink it. |
| `pull_request_review_thread.diff_hunk can't be blank` / `path diff too large` | The file's patch isn't in the API response. Move the finding to the review body. |
| `User can only have one pending review per pull request` | The pending-review check above was skipped. |

Because a rejection is all-or-nothing, fix and re-POST the whole payload. Nothing partial was created.

### Phase 6: Verify the anchors landed

Do not skip this, and do not verify it by eye from the payload. Pending-review comments come back with `line: null` and a `position` that is a **diff position, not a file line**:

```bash
gh api repos/{owner}/{repo}/pulls/{n}/reviews/{review_id}/comments --paginate
```

The mapping rule, which is where this goes wrong: **position 1 is the first line AFTER the first `@@` header. Every following patch line consumes one position, including later `@@` headers and `-` deletions. `-` lines and headers map to no new-file line.** Equivalently: split the patch on newlines, and `position` indexes directly into that list, where index 0 is the first `@@` header. Treating later `@@` headers as free, or starting the count at the header, produces a consistent off-by-N that makes every anchor look misplaced and sends you re-anchoring correct comments.

```bash
python3 scripts/diff_anchors.py verify OWNER/REPO 1234 REVIEW_ID
```

It prints `path:line` per comment with the first line of the body. Check each against the finding it came from.

To fix a wrong anchor, delete the pending review you just created and re-POST the corrected payload:

```bash
gh api repos/{owner}/{repo}/pulls/{n}/reviews/{review_id} --method DELETE
```

That endpoint only works on pending reviews, which is what makes it safe. Do not reach for `POST /pulls/{n}/comments` to patch a single comment — that endpoint publishes immediately and standalone, outside the review. REST has no way to append a comment to an existing pending review, so whole-payload replacement is the only route.

### Phase 7: Hand off

Give the user:

- The link: `https://github.com/{owner}/{repo}/pull/{n}/files`, where the pending comments appear inline with a Pending badge and a "Finish your review" button at the top.
- A list of the comments as `path:line — first line of body`.
- What was dropped in Phase 2 and why.
- Any finding that ended up in the review body instead of inline.
- A reminder that nothing is visible to anyone else until they submit.

## Rules

- Never pass `event`. Never call the submit endpoint. Never call the replies endpoint. All three publish immediately.
- Never delete a pending review you did not create in this run. Deleting and re-POSTing your own, to fix an anchor, is fine.
- Verify every anchor against the diff before posting and every position after posting.
- The comment carries the report's evidence. If you find yourself writing a one-sentence summary of a twelve-line finding, you have thrown away the part the author needed.
- Prose paragraphs are single lines. Code, tables, and list items are not.
- Findings marked false positive are not posted, ever.
- If a finding's premise turns out to be wrong during pre-flight — already fixed, explicitly requested, deliberate design — say so rather than posting a reframed version that still implies the author erred.
- State the real line whenever the anchor isn't it.

## Token permissions

A fine-grained PAT scoped to the single repo with **Pull requests: Read and write** is enough. Metadata: Read-only is mandatory and GitHub adds it automatically. Nothing else is needed — not Contents, not Actions.

Classic tokens have no per-resource granularity here; the equivalent is the whole `repo` scope, which grants read and write to code, issues, and settings across every repo the user can reach. Prefer fine-grained.

For org-owned repos: the org must have fine-grained PATs enabled, the token may need an owner to approve it before it works, and if the org enforces SAML the token needs to be SSO-authorized. A token that is unapproved or unauthorized fails as 404 on the repo, not 403, which reads like a typo in the repo name.

Use it for a single call without disturbing the user's `gh` login:

```bash
GH_TOKEN="$(cat ~/.config/gh/pr-review-token)" gh api repos/{owner}/{repo}/pulls/{n}/reviews --method POST --input payload.json
```
