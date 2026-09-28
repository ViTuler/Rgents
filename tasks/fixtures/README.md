# Fixture tasks for `python .agent/tools/validate.py --fixtures`

Each subdirectory `TASK-*` is a **known-bad** (or known-good) task tree plus `fixture.yaml`:

```yaml
defect_class: short_machine_name
stage: plan          # stage checker to run
must_fire: ["check_id"]
must_not_fire: []    # negative control — these check ids must not appear
```

Fixtures prove that real task shapes trigger the right invariants (and do not false-fire).
They are framework self-checks only — not live work. Do not move them to `tasks/active/`.
