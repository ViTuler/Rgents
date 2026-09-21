# Conventions

The defaults this team writes code and documents by. Where a project already has its own conventions,
**the project's conventions win** — consistency within a codebase outranks any preference stated here.
Record project-specific conventions in `docs/knowledge/project-memory.md`.

## Code

- Match the surrounding code: naming, structure, comment density, and idiom.
- **Minimal diffs.** Change what the task requires. Do not reformat untouched lines, reorder imports in
  unrelated files, or rename things opportunistically.
- Prefer the pattern already in the codebase over a better one you have seen elsewhere. Consistency
  beats local elegance.
- Extract a helper on the third genuine use, not the first. Three similar lines beat a premature abstraction.
- No dead code, no commented-out code, no leftover scaffolding, no debug output.
- Comments explain *why*. If a comment restates what the line does, delete it.
- Errors are handled where something meaningful can be done about them. Never swallow silently.

## Naming

| Thing | Convention |
|---|---|
| Files / modules | match the existing layout; do not introduce a second scheme |
| Functions | verb phrase describing the outcome (`inviteMember`, not `handleInviteThing`) |
| Booleans | `is` / `has` / `should` prefix |
| Events | past tense, domain-noun first (`invitation.accepted`) |
| Tests | describe behavior and condition (`rejects an expired invitation`) |
| Branches | `feature/`, `fix/`, `chore/`, `spike/` — lowercase, hyphenated, one issue per branch |
| Commits | conventional commits, scope = the task ID (`feat(TASK-014): send organization invitations`) |

## Tests

- Behavior over coverage. A test that would pass against a broken implementation is not a test.
- Cover the happy path, the failure paths, and boundaries. Derive edge cases from
  `requirements.json`, not from the implementation.
- Tests are independent and order-agnostic. No test requires another to run first.
- Mock only what genuinely cannot be run. State what the mocks leave unverified.
- Never weaken, skip, or delete a failing test to reach a green run.

## Artifacts and documentation

- Write the artifact the run needs, matching its schema in `.agent/schemas/`.
- Reference other artifacts by path. Never paste their contents.
- Document decisions and contracts, not code. Point at code rather than duplicating it.
- Update documentation in the same change that alters the behavior it describes. "Docs follow later"
  means the docs never arrive.
- Lead with the conclusion, then the reasoning. Concrete nouns over hedging.

## Reporting

- Evidence over assertion. Every claim maps to something you actually ran or observed.
- Use the honest-gap fields (`not_verified`, `not_assessed`, `not_measured`, `not_run`) rather than
  overstating coverage.
- State uncertainty explicitly. "I could not verify X because Y" is a useful report; an implied pass is not.
- Report unflattering findings. A developer that hides a problem has transferred it to QA and Review,
  where it costs more to find and more to fix.

## Prohibited patterns

These have no legitimate use in this team. Each has a legitimate alternative.

| Prohibited | Alternative |
|---|---|
| `@ts-ignore`, `# type: ignore`, bare `except` to silence a real error | fix the type or handle the error; if genuinely unavoidable, an inline comment stating why |
| Skipping a test, `--no-verify`, disabling a lint rule to reach green | fix the failure |
| Committing secrets, credentials, keys, or `.env` files | environment injection; update `.env.example` |
| Force pushing a shared branch | a new commit |
| Direct push to a protected branch, or merging a PR | open the PR; a human merges |
| `SELECT *` in production paths | select the columns used |
| Unbounded queries without pagination | paginate |
| Silently expanding scope | report the new work; it becomes a new task |
| Editing another role's artifact | write your own finding |
| Hand-rolling cryptography or a token format | the platform's vetted mechanism |
