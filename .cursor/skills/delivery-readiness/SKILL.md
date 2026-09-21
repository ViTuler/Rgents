---
name: delivery-readiness
description: "Assess whether a change is actually deployable and operable — reproducible build, complete configuration, secret handling, migration and rollback safety, health checks, and observability of the new failure modes. Use when the build pipeline, deployment surface, runtime configuration, secrets handling, or observability changes."
---

# Delivery readiness

## When to use

When the change alters how the system is built, configured, deployed, or observed — matching the
devops activation triggers in `.agent/config.yaml`. Also use it before any release of a `high`-risk change.

## The gap this closes

> Developer: "The feature works locally."
> The questions that decide whether it survives production: does it build in CI, does it run there,
> is it configured, can we roll it back, and will we see it fail?

## Procedure

### 1. Reproducible build

- Does a clean checkout build? Not "it built here" — a clean checkout, the way CI does it.
- Are lockfiles updated and consistent with the manifest?
- Does any build step depend on something present only on one machine?
- Are new runtimes, system packages, or native extensions declared everywhere they are needed?

### 2. Configuration

For **every** new configuration value, confirm all five:

| Check | Requirement |
|---|---|
| documented | present in `.env.example` or the project's equivalent |
| present everywhere | declared in every environment's config |
| validated | checked at startup, not at first use |
| defaulted or required | a safe default, or startup fails loudly |
| typed | parsed and validated, not read as a string at the point of use |

**Fail loudly, not silently.** A missing required setting that degrades quietly is one of the most
expensive production failures to diagnose, because nothing announces it.

### 3. Secrets

- No secret committed — not in config, not in a sample, not in a test fixture, not in a Dockerfile,
  not in CI logs. Search the diff explicitly.
- Secrets injected at deploy time, scoped to the minimum capability, rotatable.
- Nothing secret is logged, even partially masked.

### 4. Migration safety

- Lock behavior and duration analyzed (see the `safe-migration` skill).
- Safe while the previous application version is still running.
- Migration ordering relative to the deploy is explicit.
- Any migration is proposed, never executed by an agent.

### 5. Rollback

Write the procedure down. If none exists, that is a **finding to raise before merge**, not after a failure.

- Is it forward-and-backward compatible, so rollback is a redeploy rather than data repair?
- Does rollback require a data repair step? Say so.
- If rollback has never been exercised, state that the procedure is untested — that is an assumption,
  not a guarantee.

### 6. Health and readiness

- Do health/readiness probes reflect the new dependency?
- Does readiness fail when a required dependency is unreachable?
- A readiness check that passes while a required dependency is down is a false signal — worse than none.

### 7. Observability

For every new failure mode the change introduces:

- Is it logged with enough context to diagnose?
- Is it counted or measured where an operator would need to alert on it?
- **Can an operator determine what broke from telemetry alone, without reading the source?**

If the answer to the last question is no, observability is incomplete.

### 8. Resource footprint

Estimate CPU, memory, disk, and connection-pool impact at expected load. Flag anything that changes the
deployment's resource envelope — that is a capacity decision, not an implementation detail.

## Output

`tasks/<TASK-ID>/delivery-report.json`, matching `.agent/schemas/specialist-report.schema.json` with
`role: devops`.

```bash
python .agent/tools/validate.py --artifact tasks/active/<TASK-ID>/delivery-report.json
```

## Hard constraints

Agents never perform, and never work around: deploying to production, deleting or truncating data,
rotating credentials, tearing down infrastructure, force pushing, or merging a pull request. Propose
the operation with its rollback plan; a human executes it.

## Anti-patterns

- **Accepting "works locally" as build evidence.** Build it the way CI builds it.
- **Configuration added to one environment only.** The failure appears in the environment nobody tested.
- **Silent degradation on missing config.** Fail loudly.
- **A rollback plan that has never been run** presented as a guarantee. Say it is untested.
- **Health check that does not check dependencies.** Always green, therefore useless.
- **Assuming existing monitoring covers the new failure mode.** Verify it does.
- **Marking a readiness check as passing without running it.**
