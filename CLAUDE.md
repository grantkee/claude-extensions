## Workflow Orchestration
### 1. Plan Mode Default
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately - don't keep pushing
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity
### 2. Subagent Strategy
- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- Always use opus subagents for execution and implementation tasks - not fable
- Never use fable agent tokens for basic subagent tasks like file searching
#### 2a. Scope, don't count (no fixed concurrency cap)
- There is NO maximum number of concurrent subagents. Fan-out width follows from how independent the work is.
- What IS capped is each agent's context. One narrow deliverable, an explicit list of paths it may read, and an instruction to hand back rather than explore past them.
- Budget each agent well under ~250k tokens. An agent trending past that was scoped wrong: it checkpoints, hands back what it has, and the orchestrator respawns a fresh agent for the remainder. Never let one agent balloon to 300k+.
- Every agent returns a summary, not file dumps.
#### 2b. Checkpoint to disk so any session survives a rate limit
- Every subagent prompt names a checkpoint file (prefer the worktree's own `tasks/` path) and requires a `status:` header plus a list of completed sections, rewritten after EACH section — not once at the end.
- Every subagent prompt says: "on start, read your own checkpoint and continue from the first unfinished section."
- If Write is refused, do not work around it — return the complete text in the final answer and let the orchestrator save it.
- After a `429` / session limit: read the checkpoint files on disk BEFORE assuming work was lost (the failure notice under-reports what landed), then resume with SendMessage naming the sections that already exist.
### 3. Self-Improvement Loop
- After ANY correction from the user: update 'tasks/lessons.md" with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until mistake rate drops
- Review lessons at session start for relevant project
### 4. Verification Before Done
- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness
### 5. Demand Elegance (Balanced)
- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes - don't over-engineer
- Challenge your own work before presenting it
### 6. Autonomous Bug Fixes
- When given a bug report: identify the root of the problem before suggesting fixes
- Point at logs, errors, failing tests - then identify what caused them
- Fix failing tests without being told how
## Task Management
1. **Plan First**: Write plan to "tasks/plan.md" with checkable items
2. **Verify Plan**: Check in before starting implementation
3. **Track Progress**: Mark items complete as you go
4. **Explain Changes**: High-level summary at each step
5. **Document Results**: Add review section to 'tasks/todo.md"
6. **Capture Lessons**: Update 'tasks/lessons.md" after corrections
## Core Principles
- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **No Laziness**: Find root causes. No temporary fixes. Senior developer standards.
- **Minimat Impact**: Changes should only touch what's necessary. Avoid introducing bugs.
## Agent Triggering Manifest
Agents must be spawned proactively based on detected conditions, not reactively after the user asks. Claude's agent-spawning decisions should be driven by the agent's `description` frontmatter.
