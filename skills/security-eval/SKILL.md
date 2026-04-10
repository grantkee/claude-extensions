---
name: security-eval
description: |
  Comprehensive security evaluation for telcoin-network PRs and branches.
  Orchestrates 8 parallel security agents covering consensus safety, state transitions,
  cryptographic correctness, DoS vectors, determinism, contract safety, dependency auditing,
  and deep business logic auditing via nemesis. Includes independent verification to eliminate
  false positives and root-cause remediation with actionable fixes.
  Trigger on: "security eval", "security review", "security audit PR", "is this PR safe", "pre-merge security"
---

# Security Evaluation Orchestrator

Comprehensive security evaluation for telcoin-network code changes. Spawns 8 specialized security agents in parallel, each focused on a specific attack surface, then independently verifies findings to eliminate false positives and provides root-cause remediation for confirmed vulnerabilities.

## Severity Scale (Blockchain-Calibrated)

| Level        | Definition                                              | Examples                                                                                    |
| ------------ | ------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| **CRITICAL** | Consensus break, fund loss, chain halt, or forked state | Quorum miscalculation, determinism violation in state transition, unprotected fund transfer |
| **HIGH**     | Security degradation or data corruption                 | Missing signature verification, unbounded allocation, unsafe key handling                   |
| **MEDIUM**   | Defense-in-depth gap or reliability issue               | Missing input validation on network boundary, inadequate error handling in consensus path   |
| **LOW**      | Code quality issue with security implications           | Inconsistent error types, missing logging in security-relevant paths                        |
| **INFO**     | Observation or hardening suggestion                     | Style inconsistency, documentation gap in security-sensitive code                           |

## Process

### Phase 1: Scope Identification

Determine what code to evaluate:

- If given a PR number: run `git diff main...HEAD` or `gh pr diff <number>`
- If given a branch: run `git diff main...<branch>`
- If given specific files: use those directly
- Read all changed files in full plus their direct dependents

### Phase 2: Spawn Security Agents

Spawn ALL 8 agents in parallel using the Agent tool. Each agent receives:

1. The list of changed files and their diffs
2. The full content of changed files
3. Instructions to read `.claude/project-context.md` for architecture context

The 8 agents and their focus areas:

| Agent                  | Focus                                                                | Skills to Invoke           |
| ---------------------- | -------------------------------------------------------------------- | -------------------------- |
| `consensus-safety`     | BFT assumptions, quorum logic, vote counting, leader election        | harden-tn + threat-model   |
| `state-transitions`    | Invariant violations, partial state updates, rollback safety         | nemesis + review-tn        |
| `crypto-correctness`   | Signatures, hashing, key management, nonce handling                  | review-tn (crypto paths)   |
| `dos-vectors`          | Resource exhaustion, unbounded allocations, amplification            | harden-tn (blocking audit) |
| `determinism-verifier` | HashMap iteration, SystemTime, thread-dependent ordering, randomness | harden-tn (determinism)    |
| `contract-safety`      | Access control, reentrancy, accounting, upgrade safety               | review-tn-contracts        |
| `dependency-auditor`   | New crates, CVE exposure, supply chain, feature flags                | Cargo.toml diff analysis   |
| `nemesis-auditor`      | Deep iterative business logic + state inconsistency cross-analysis   | nemesis                    |

### Phase 3: Extract Structured Findings

After all 8 agents complete, extract each discrete finding into a canonical structure:

```
Finding ID: [agent-name]-[N]
Source Agent: [which of the 8]
Severity: CRITICAL / HIGH / MEDIUM / LOW / INFO
Title: [one-line summary]
Location: file_path:line_number
Claim: [standalone factual assertion — what is wrong]
Key Question: [the specific thing a verifier must answer]
Relevant Files: [files needed to verify]
```

**Critical**: The `Claim` field contains ONLY the factual assertion (e.g. "function X does not validate input Y"), never the reasoning chain that led to it. This preserves independence for Phase 4 verifiers.

Assign each finding a verification tier:

| Tier | Severities | Verification Strategy |
|------|------------|----------------------|
| **Tier 1** | CRITICAL, HIGH | Verified individually — one agent per finding |
| **Tier 2** | MEDIUM | Batched 2-3 per agent, grouped by subsystem |
| **Tier 3** | LOW | Batched 3-5 per agent |
| **Skip** | INFO | No verification — observations, not vulnerability claims |

### Phase 4: Independent Verification

Spawn verification agents in parallel. Each agent receives ONLY the claim, the relevant code, and the key question — never the original agent's reasoning. This eliminates confirmation bias.

**Verification agent prompt template:**

```
You are verifying a security claim. You have NOT seen the original analysis.
Answer the Key Question below using ONLY the code provided.

Claim: [factual assertion from Phase 3]
Key Question: [what must be answered]
Relevant Files: [attached code]

Provide:
- Verdict: CONFIRMED / FALSE_POSITIVE / PARTIALLY_VALID / DESIGN_DECISION
- Confidence: HIGH / MEDIUM / LOW
- Verified Severity: CRITICAL / HIGH / MEDIUM / LOW
- Evidence: specific code citations, traced paths, guards found or absent
```

**Re-verification rule**: If a CRITICAL or HIGH finding receives a MEDIUM-confidence verdict, spawn one additional verifier for that finding. This is the only case where re-verification occurs.

**Agent caps**:
- Max 12 verification agents total
- If findings exceed capacity, prioritize Tier 1 and Tier 2
- Tier 3 findings that exceed capacity go to the "Not Verified" report section

### Phase 5: Root-Cause Remediation

For each CONFIRMED or PARTIALLY_VALID finding, spawn a remediation agent that focuses on root cause, not symptoms.

**Decision tree for output format:**

1. **One clear fix** (no API changes, no architectural decisions, no trade-offs) → Provide specific before/after code
2. **Multiple valid approaches** (different trade-offs in performance, complexity, API breakage) → List ALL options with pros/cons/effort, recommend one, flag for human review
3. **Architectural decision required** (protocol changes, new abstractions, fork-gated behavior) → List options, do NOT recommend one, explicitly state "requires human decision"

**Remediation agents also check for:**
- Similar patterns elsewhere in the codebase (same root cause in other locations)
- Collateral effects (test breakage, determinism impact, serialization changes)
- Upgrade requirements (rolling vs coordinated validator upgrade)

**Agent caps**:
- Max 8 remediation agents total
- CRITICAL and HIGH findings get individual agents
- MEDIUM findings batched 2-3 per agent
- LOW findings get a one-line suggestion from the orchestrator (no dedicated agent)

### Phase 6: Present Results

Present the unified report using this template:

```
# Security Evaluation Report

## Executive Summary
- **Overall Risk**: CRITICAL / HIGH / MEDIUM / LOW / CLEAN
- **Agents Run**: 8/8
- **Initial Findings**: N
- **After Verification**: M confirmed, P false positives eliminated
- **Remediation Status**: X with clear fixes, Y requiring human decision
- **Recommendation**: BLOCK / APPROVE_WITH_FIXES / APPROVE

## Verified Findings — Clear Remediation
[Confirmed findings with specific before/after code fixes ready to apply]
[Each includes: finding ID, severity, location, claim, verdict, confidence, fix]

## Verified Findings — Requires Human Decision
[Confirmed findings with multiple options or architectural trade-offs]
[Each includes: finding ID, severity, location, claim, options with pros/cons]

## Partially Valid Findings
[Concerns that exist but at lower impact than initially assessed]
[Each includes: finding ID, adjusted severity, explanation of reduced scope]

## Eliminated False Positives
| Finding ID | Original Severity | Claim | Why Dismissed |
|------------|------------------|-------|---------------|
[Summary table — transparency on what was ruled out and why]

## Not Verified
[Tier 3 findings that exceeded verification capacity — listed with original severity]

## Raw Agent Reports

### consensus-safety
[Full agent report]

### state-transitions
[Full agent report]

### crypto-correctness
[Full agent report]

### dos-vectors
[Full agent report]

### determinism-verifier
[Full agent report]

### contract-safety
[Full agent report]

### dependency-auditor
[Full agent report]

### nemesis-auditor
[Full agent report]

## Methodology Notes
- All 8 agents ran independently with no shared state
- Each agent used its designated skills for domain-specific analysis
- Severity calibrated for blockchain: consensus breaks and fund loss are CRITICAL
- Verification agents received claims WITHOUT original reasoning (independence guarantee)
- Verification stats: N findings → M verified, P false positives (P/N = X% false positive rate)
- Re-verification triggered for: [list any CRITICAL/HIGH findings with MEDIUM-confidence verdicts]
```

## Expected Agent Counts

| Phase | Agents | Notes |
|-------|--------|-------|
| 2 | 8 | Fixed — one per security domain |
| 4 | 6-12 | Depends on finding count and tiers |
| 4 (re-verify) | 0-3 | Low-confidence CRITICAL/HIGH verdicts only |
| 5 | 3-8 | Confirmed findings only |
| **Total** | **17-31** | Typical ~22 |
