---
name: safe-migration
description: "Plan, review, and verify a database migration that is safe to run on a live system with a large table and a concurrent deploy — covering lock behavior, duration, backward compatibility, reversibility, and batched backfill. Use whenever a schema change, migration, or data backfill is part of the change."
---

# Safe migration

## When to use

Any schema change, migration, index change, or data backfill. Also at design time, before the migration
is written — this procedure is far cheaper applied to a design than to a deployed migration.

## The governing assumption

**Assume the table is large and the deploy is concurrent.** Both assumptions are usually true in
production and cost nothing when they are not. An `ALTER` that takes an exclusive lock on a table with
tens of millions of rows is an outage, and the migration that caused it passed every test on a
developer machine with a thousand rows.

## Procedure

### 1. Classify the operation's risk

| Operation | Risk | Required mitigation |
|---|---|---|
| Add a nullable column | low | none |
| Add a `NOT NULL` column with a default | **high** on older engines | two-step, or a constant default the engine handles without a rewrite |
| Add an index | medium | concurrent index creation where supported |
| Change a column type | **high** | new column + backfill + swap |
| Rename a column/table | **high** | additive rename: add new, dual-write, migrate readers, drop old |
| Drop a column/table | **critical** | must follow a release that stopped using it |
| Add a constraint | medium to high | validate against existing data first |
| Backfill an existing table | medium to high | batched, throttled, resumable |
| Data repair / dedupe | **critical** | human approval before execution |

### 2. Analyze lock behavior and duration

Determine, with evidence rather than intuition:

- What lock does this take, and for how long?
- Does it rewrite the table, or is it metadata-only?
- Does it block reads, writes, or both?
- Has it been measured against a realistic row count?

Record the evidence in `migration_analysis`. A claim about lock behavior without measurement is a
guess, and a guess is not sufficient grounds for a production migration.

### 3. Confirm backward compatibility

The previous application version runs during the deploy window. The migration must be safe while it does.

Use **expand/contract**:

1. **Expand** — add the new shape (nullable column, new table, new index). Previous version unaffected.
2. **Deploy** — code writes both shapes, reads the new one.
3. **Migrate** — backfill existing rows in batches.
4. **Contract** — deploy code that no longer uses the old shape.
5. **Remove** — drop the old shape in a *later* release, after confirming nothing uses it.

### 4. Establish reversibility

- Is there a down migration? Is it lossy?
- If a rollback would destroy data, say so explicitly and escalate — that is a human decision.
- Is the change forward-and-backward compatible, so rollback is a redeploy rather than data repair?

If there is no rollback path, that is a finding to raise **before** the migration runs, not after it fails.

### 5. Design the backfill

- **Batched** — bounded chunks, never one long transaction
- **Throttled** — yields under load; does not saturate the database
- **Resumable** — records progress so an interruption does not restart from zero
- **Idempotent** — running it twice produces the same result

### 6. Verify the queries

- For every new or changed query, confirm the predicate and join columns are indexed.
- Verify the query actually uses the index — cite `EXPLAIN` output, do not infer it from the schema.
- Composite index column order matches the query's selectivity and sort order.
- Check for N+1 patterns, unbounded result sets, and missing pagination.

### 7. Confirm integrity

- Are multi-step writes transactional? What happens on partial failure?
- Are constraints (NOT NULL, UNIQUE, FK, CHECK) present where an invariant must hold?
- Deletes: cascading as intended, or orphaning rows?

## Output

`tasks/<TASK-ID>/db-report.json`, matching `.agent/schemas/specialist-report.schema.json` with
`role: database`.

```bash
python .agent/tools/validate.py --artifact tasks/active/<TASK-ID>/db-report.json
```

## Hard constraints

- **Never run a migration against production or a shared environment.** Propose it with its rollback
  plan; a human executes it.
- **Never perform a destructive operation** — `DROP`, `TRUNCATE`, unbounded `DELETE`/`UPDATE` — against
  real data without explicit human approval.

## Anti-patterns

- **Testing the migration only against an empty or tiny table.** Lock behavior appears only at scale.
- **`NOT NULL` with a default added in one step** on a large table — often a full rewrite under an
  exclusive lock.
- **One long transaction for a backfill.** Holds locks, bloats the log, and cannot be resumed.
- **Dropping a column in the same release that stopped using it.** The previous version still reads it
  during the deploy window.
- **Asserting a query is fast without `EXPLAIN`.** Measure.
- **Renaming in place.** It breaks every reader for the duration of the deploy.
