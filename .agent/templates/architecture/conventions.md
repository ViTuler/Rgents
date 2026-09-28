# Conventions (product template)

> **Product-owned.** Rgents seeds this file once on `create`; upgrades never overwrite it.
> Defaults for how *this product* writes code and documents. Where the codebase already has a
> convention, **the codebase wins**. You may also record project-specific notes in
> `docs/knowledge/project-memory.md`.

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
| Functions | verb phrase describing the outcome |
| Booleans | `is` / `has` / `should` prefix |
| Events | past tense, domain-noun first |
| Tests | describe behavior and condition |
| Branches | project convention (record it here) |
| Commits | project convention (record it here) |

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
- Update documentation in the same change that alters the behavior it describes.

## Reporting

- Evidence over assertion. Every claim maps to something you actually ran or observed.
- Use the honest-gap fields (`not_verified`, `not_assessed`, `not_measured`, `not_run`) rather than
  overstating coverage.
- State uncertainty explicitly. "I could not verify X because Y" is a useful report; an implied pass is not.
