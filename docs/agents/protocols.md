# Protocols — how agents hand work to each other

The single most important property of this system: **agents communicate through files, not through
relayed conversation.** An agent that receives a task receives *paths to artifacts*, reads them itself,
and writes its own artifact. Conversation history is not a communication channel.

That constraint is what keeps context bounded, makes every step independently checkable, and lets any
task be resumed by a different agent — or a human — from the artifacts alone.

## 1. Artifact ownership

Exactly one role writes each artifact. There are no shared writers.

| Artifact | Sole writer | Read by |
|---|---|---|
| `task.yaml` | orchestrator | everyone (state anchor) |
| `intake.json` | orchestrator | all downstream agents |
| `requirements.json` | product | tech-lead, developer, qa, ux, data, reviewer |
| `design.json` | tech-lead | developer, database, security, performance, qa, reviewer, devops |
| `plan.json` | tech-lead | developer, database, performance, qa, reviewer, devops |
| `ux-report.json` | ux | developer, qa, reviewer |
| `worker-result.json` | developer | qa, security, reviewer, devops, performance |
| `db-report.json` | database | developer, qa, reviewer, devops |
| `qa-report.json` | qa | reviewer, orchestrator |
| `security-report.json` | security | developer, reviewer, orchestrator |
| `perf-report.json` | performance | developer, reviewer |
| `data-report.json` | data | developer, reviewer |
| `review-report.json` | reviewer | developer, orchestrator |
| `delivery-report.json` | devops | orchestrator, human |

**Never edit another role's artifact.** If you disagree with its contents, write your own finding and
route it. Editing someone else's verdict destroys the independence that makes the gate meaningful.

## 2. Handoff format

### Dispatch target: roles, not the coordinator

**The orchestrator is the root agent.** It is a role the main thread adopts, not a subagent it
dispatches, because Cursor's Task tool cannot resolve a project agent through `subagent_type` — that
enum contains built-in agents only. The slash-command registry is a separate list which *does* contain
project agents, which is why a human invoking `/orchestrator` or `/spec` works while
`Task(subagent_type="orchestrator", ...)` fails.

So every dispatch in this framework targets a **role** — `product`, `tech-lead`, `developer`, `qa`,
`reviewer`, or one of the six specialists — and never the coordinator.

If a role cannot be dispatched, that is a blocker to report. **Do not produce that role's artifact in
its place:** a gate verifying the orchestrator's own work against itself verifies nothing, and the
entire point of separating implementation from verification would be lost.

### The dispatch itself

Every dispatch states four things. A dispatch missing any of them is incomplete:

```
Task:        TASK-014
Stage:       implementation
Read:        tasks/active/TASK-014/requirements.json
             tasks/active/TASK-014/design.json
             tasks/active/TASK-014/plan.json
Write:       tasks/active/TASK-014/worker-result.json
Done when:   every step in plan.json is implemented; lint, typecheck and tests run
             with their real results recorded in `tests_run`
```

Do **not** paste artifact contents into the dispatch. Pass the path. The receiving agent reads the
file, which keeps context bounded and guarantees it sees the current version rather than a stale copy.

## 3. Reading upstream artifacts

- Read the artifact from disk. Do not assume a summary in the prompt is complete.
- **A missing artifact means that stage has not run.** Never infer a result from its absence.
- If an upstream artifact is wrong or unworkable, do not silently work around it: report the defect
  and let the orchestrator route it to the owning role.
- Reference artifacts by path in your own output, never by pasted content.

## 4. Duplicate-request adjudication

Before a task is treated as new work, it is compared against every active task. This exists because
nothing else in the pipeline can see it: the per-task invariants check a task against its own plan and
never against another task, so two active tasks describing one request both look authoritative and
produce divergent requirement sets that both look correct.

**Checking is the orchestrator's job. Deciding is the human's.**

The orchestrator scores the request two ways and takes the higher:

| Comparison | Corpus | Catches |
|---|---|---|
| `request_narrow` | title and request only | a near-verbatim restatement — scores ~1.0 |
| `document_broad` | title, request, goal, and every acceptance criterion | the same feature described differently, including in another language |

Thresholds and vocabulary live in `.agent/config.yaml → duplicate_detection`, and the scoring is a
transparent token-overlap heuristic rather than semantic understanding, so a human can inspect the
shared terms and disagree with it.

The outcomes:

| Outcome | Means | Enforced |
|---|---|---|
| `new` | run as a separate task | requires a `rationale` whenever a match exists |
| `reuse` | continue the existing task | the validator errors if a new task directory exists |
| `supersede` | this task replaces the named one | the validator errors while that task is still under `tasks/active/` |
| `no_overlap` | nothing reached the threshold | must still be recorded |

**Why a `likely` match is not the orchestrator's call.** Choosing `new` silently forks work already in
flight; choosing `reuse` discards what the requester asked for. Both are the human's decision. The
orchestrator's job is to put the scores and shared terms in front of the human, and to record
`decision.decided_by: human`.

**Why `no_overlap` is recorded even when nothing was found.** An unrecorded "nothing found" is
indistinguishable from a check that was never run. The validator reports `overlap_check_missing` for a
silent intake, which is how this failure mode stays visible.

**Override.** A heuristic misses things and produces false positives. Both are recorded under
`override` **with a reason**: `false_positive` for a match that is real but not competitive work (a
shipped example, a deliberately separate task), `missed_match` for a genuine overlap the scoring did
not catch. An override without a reason is an error.

Verify with:

```bash
python .agent/tools/validate.py --task <TASK-ID> --stage duplicate_check
```

## 5. Failure routing

The orchestrator routes a failure to the role that owns the defect. Misattributing the owner is the
most expensive routing mistake, because it sends the fix to an agent that cannot make it.

| Defect class | Symptom | Owner |
|---|---|---|
| `implementation_defect` | behavior does not match the design or criteria | developer |
| `requirement_defect` | the acceptance criterion is wrong, ambiguous, or contradictory | product |
| `design_defect` | the interface or plan cannot satisfy the requirement | tech-lead |
| `test_defect` | the assertion is wrong, or the harness is broken | qa |
| `unclear_scope` | it is not determinable what work is in bounds | orchestrator (re-classify) |

**A failure always returns to the start of the gate chain**, not to a local patch. A fix invalidates
prior verification: QA passing before a change does not mean QA passes after it.

## 6. Escalation

Escalation is **cheap and expected**; it does not consume the retry budget. Guessing is the expensive path.

Escalate to the **tech lead** when:
- the design is ambiguous or internally inconsistent
- completing the task requires changing the architecture
- a specialist finding conflicts with the approved design

Escalate to the **human** when:
- requirements are ambiguous or a product decision is unresolved
- the change is irreversible
- a `critical` security finding cannot be fixed within scope
- the same stage has failed three times
- governance surfaces (`.cursor/**`, `.agent/**`, `AGENTS.md`, `docs/agents/**`) must change
- risk is `high` and the task is ready to complete

## 7. Proposing governance changes

Agents cannot edit the rules, agent definitions, configuration, or policies. When a governance change
is needed — a rule is missing, a role boundary is wrong, a gate does not match reality — the agent:

1. writes the proposal into its own report artifact, with the exact file and the exact change
2. states the concrete problem the change solves, and what went wrong without it
3. escalates to the human through the orchestrator

A human applies it. This boundary is deliberate: if agents could rewrite their own constraints, every
constraint would erode to whatever was most convenient at the time.

## 8. Parallel execution

Parallel work is safe only under all of these conditions:

- the plan declares the workstreams under a shared `parallel_group`
- the workstreams write to **disjoint file sets**
- no workstream consumes an interface another is still defining
- no workstream touches a shared schema, migration, or public contract

Forbidden without exception: two agents editing the same file; a frontend stream consuming an API
contract that is still being designed; parallel execution across steps the plan marks as dependent.

When parallel-safe conditions are not met, sequential is the default and is not a failure.

## 9. Resume protocol

Anyone — agent or human — must be able to resume from artifacts alone. `task.yaml` is the anchor:

- `status`: `in_progress` | `blocked` | `completed` | `failed` | `paused`
- `current_stage`: where to continue from
- `stages`: per-stage `{agent, result, summary, artifact_path}`
- `retries` and `routing_decisions`: why the task is where it is

On resume: read `task.yaml`, read the artifacts the current stage requires, and continue. Do not
re-derive earlier stages from conversation, and do not re-run a stage whose artifact already reflects
the current revision of its inputs.

## 10. Claim protocol

An agent states what it *did* and what it *observed*. It does not state what it believes will be true.

- Report commands you actually ran, with their actual output.
- Use the honest-gap fields — `not_verified`, `not_assessed`, `not_measured`, `not_run`,
  `NOT VERIFIED` — they exist so that uncertainty has somewhere to live other than a false claim.
- Never fabricate a path, a line number, a count, or a passing run. Every downstream gate trusts your
  artifact; a fabricated pass converts your uncertainty into everyone else's false confidence.
