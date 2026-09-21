---
name: threat-modeling
description: "Systematically threat-model a change by enumerating the trust boundaries it crosses, what an attacker controls at each, and the abuse case that follows — then assess authentication, authorization, input validation, data protection, and dependency risk with a blocking severity verdict. Use when a change touches authentication, authorization, user input reaching persistence or a shell, secrets, payments, personal data, new public endpoints, or new dependencies."
---

# Threat modeling

## When to use

Any change matching a security activation trigger in `.agent/config.yaml → specialists.security`.
Also use it proactively at design time for anything crossing a trust boundary — a specialist consulted
during design costs one message; consulted after implementation it costs a rework cycle.

## Procedure

### 1. Enumerate trust boundaries

For the change, list every point where data or control crosses from a less-trusted context to a
more-trusted one:

| Boundary | What crosses | Who controls the other side |
|---|---|---|
| HTTP entry point | | |
| Message queue / event | | |
| Webhook / callback | | |
| File upload | | |
| Third-party API response | | |
| Browser → server | | |
| Service → database | | |

### 2. Ask the attacker's question at each boundary

For every boundary, do not ask "is this secure" — ask **"what does an attacker control here, and what
do they gain by controlling it?"** Write the abuse case concretely, as a sequence of steps.

If you cannot write the attack path, you have a hypothesis, not a finding. Investigate until you can,
or record it as unconfirmed with the uncertainty stated.

### 3. Assess each area against the change

- **Authentication** — credentials verified server-side? session/token issuance, scope, expiry, revocation correct?
- **Authorization** — checked server-side, per request, *for this specific resource*? Any identifier
  arriving from the client is an object-level authorization question. Client-side checks are not access control.
- **Input validation** — can malicious input reach a query, template, path, shell, deserializer, or
  outbound request? Validate on entry, **encode at the point of use** — validation alone does not
  prevent injection into a different context.
- **Data protection** — secrets, tokens, PII in responses, logs, errors, URLs, or client storage?
- **Resource access** — can another user or tenant reach this by changing an identifier?
- **Rate limiting / abuse** — can this endpoint enumerate, brute-force, spam, or amplify?
- **Dependencies** — any new package: known vulnerabilities, maintenance status, transitive footprint,
  and whether the standard library suffices?
- **Error disclosure** — do failures leak stack traces, internal paths, query fragments, or versions?
- **Cryptography** — hand-rolled crypto, home-made tokens, deprecated primitives, hardcoded keys or IVs?
- **Destructive operations** — is the irreversible path authorized, confirmed, and minimally scoped?

### 4. Assign severity honestly

| Severity | Meaning | Effect |
|---|---|---|
| `critical` | remotely exploitable with real impact, or trivially exploitable | **blocks**; escalates to human if unfixable in scope |
| `high` | exploitable under plausible conditions with significant impact | **blocks** |
| `medium` | requires unusual preconditions or has limited impact | fix before the task completes |
| `low` | hardening; defense in depth | record only |

Report a suspected issue with its uncertainty stated rather than omitting it. False negatives are
expensive; false positives are cheap.

### 5. Declare coverage

Record which areas you assessed, which were not applicable, and which you **could not** assess. A
`PASS` that silently skipped authentication is worse than a `FAIL`, because it is trusted.

### 6. Report blocking items concretely

`required_before_merge` is a fix list a developer can execute without re-deriving your reasoning. Each
item names the file, the line, and the exact change.

## Output

`tasks/<TASK-ID>/security-report.json`, matching `.agent/schemas/security-report.schema.json`.

```bash
python .agent/tools/validate.py --artifact tasks/active/<TASK-ID>/security-report.json
```

## Constraints

- **Never demonstrate a vulnerability destructively** against real data, production systems, or systems
  you have not been explicitly authorized to test.
- **Never use real credentials or personal data** in a proof of concept. Use synthetic records you created.
- Blocking findings are not negotiable by deadline. A release date is not a security control.

## Anti-patterns

- **Checklist review without a threat model.** Produces "looks fine" on genuinely vulnerable code.
- **Reporting a vulnerability without an attack path.** Unactionable; the developer cannot verify the fix.
- **Severity inflation.** Marking hardening items `critical` trains the team to ignore the severity field.
- **Assessing authorization only in the client.** The server is the only boundary that counts.
- **Silent gaps.** Use `not_assessed` rather than leaving an area unmentioned.
- **Stopping at the entry point.** Input validated at the door and then concatenated into a query is
  still an injection.
