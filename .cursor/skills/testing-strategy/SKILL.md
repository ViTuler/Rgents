---
name: testing-strategy
description: "Derive and execute an independent verification strategy for a change — mapping every acceptance criterion to evidence, deriving adversarial edge cases rather than adopting the implementer's list, and reporting honest per-criterion verdicts. Use when verification is required (the /verify stage), when a bugfix needs a failing reproduction first, or when a refactor needs a characterization baseline."
---

# Testing strategy

## When to use

- You are the QA agent and a change is awaiting verification.
- A bugfix needs a reproduction that fails before the fix and passes after.
- A refactor needs a behavior baseline captured before anything is touched.
- You need to decide what "verified" actually means for a given criterion.

## Procedure

### 1. Establish what must be proven

Read `requirements.json` and extract every acceptance criterion. **Do not use the developer's test list
as your input** — use the criteria. If a criterion is not checkable as written, that is a
`requirement_defect` and it routes to Product, not something to interpret generously.

For each criterion, write down before testing:

- the observable condition that must hold
- how you will observe it (command, request, UI action, query)
- what would falsify it

### 2. Characterize the current state

Before testing the change, capture the baseline: does the suite pass as-is? Record pre-existing
failures explicitly so they are not later attributed to this change.

### 3. Derive the cases independently

For each criterion, derive cases from the requirement rather than from the implementation:

| Category | Ask |
|---|---|
| happy path | does the stated behavior actually occur? |
| empty | zero items, empty string, null, missing optional field |
| duplicate | the same action twice; the same unique key twice |
| expired | time-bounded state past its boundary |
| unauthorized | wrong role, no role, another tenant's object |
| concurrent | two actors doing it at once; double submit |
| already done | the operation repeated after it succeeded |
| partial failure | a dependency fails mid-operation — is state left consistent? |
| missing dependency | required external resource unavailable |
| boundary | zero, one, maximum, off-by-one, oversized |
| regression | the neighbouring code paths this change touches |

### 4. Test at the right level

Verify the boundary under test with real behavior. Prefer a real database, real HTTP call, or real
render over a mock of the thing being verified. Mock only what genuinely cannot be run, and record what
the mock leaves unverified in `mocks_used`.

### 5. Execute and record

Run every command yourself. Record the exact command and its actual result. Never report a run you did
not perform, and never reconstruct a count from memory.

### 6. Report per criterion

Every criterion gets exactly one verdict:

| Verdict | Use when |
|---|---|
| `PASS` | you observed the criterion holding, with evidence |
| `FAIL` | you observed it not holding, with reproduction |
| `NOT VERIFIED` | you could not check it — say why |

`NOT VERIFIED` is a first-class result. An unverifiable criterion reported as PASS is worse than one
reported as NOT VERIFIED, because it converts a known gap into false confidence.

### 7. Classify ownership of each failure

Name the role that owns the defect. The orchestrator routes on your classification, so getting this
right matters as much as finding the bug:

| Classification | When |
|---|---|
| `implementation_defect` | behavior does not match the design or criteria → developer |
| `requirement_defect` | the criterion is wrong, ambiguous, or contradictory → product |
| `plan_defect` | the interface or plan cannot satisfy the requirement → tech-lead |
| `test_defect` | the assertion is wrong or the harness is broken → qa |
| `escalate` | you cannot determine the owner |

## Output

`tasks/<TASK-ID>/qa-report.json`, matching `.agent/schemas/qa-report.schema.json`.

Validate before handing off:

```bash
python .agent/tools/validate.py --artifact tasks/active/<TASK-ID>/qa-report.json
python .agent/tools/validate.py --task <TASK-ID> --stage qa
```

The gate check verifies that every acceptance criterion received a verdict.

## Over-verification vs. under-verification

Do not stop at the first failing case and report `FAIL` with everything else unverified — complete the
matrix, because a second defect behind the first is common and its discovery cost doubles when it is
found in the next round.

Do not report `FAIL` for a case you did not actually run. An untested suspicion belongs in
`not_verified`, not in `findings`.

## Anti-patterns

- **Re-running the developer's tests and calling it verification.** That confirms the developer's
  assumptions, not the requirements.
- **Testing the implementation instead of the requirement.** If the code does something reasonable but
  not what the criterion says, that is a `FAIL`.
- **Marking a criterion PASS because it "obviously works".** Evidence or `NOT VERIFIED`.
- **Retrying a flaky test until it passes.** Report flakiness as a finding; retrying to green hides an
  intermittent defect.
- **Skipping the regression run** because the change "is small". Small changes break neighbours most often.
- **Weakening an assertion** to make the suite pass.
