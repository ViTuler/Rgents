# Hand-start a task under `tasks/active/<TASK-ID>/` (rare).
#
# Normal path: `/spec` creates the directory and the orchestrator writes `intake.json`.
# This template exists for:
#   1. repairing a task whose artifacts are incomplete
#   2. working without slash commands
#
# There is no `tasks/_template/` folder in the repo — follow this README when placing
# artifacts under `tasks/active/<TASK-ID>/`.
#
# Validate in pipeline order, for example:
#   python .agent/tools/validate.py --task <TASK-ID> --stage plan
#   python .agent/tools/validate.py --task <TASK-ID> --stage implementation
#   python .agent/tools/validate.py --task <TASK-ID> --stage qa
#   python .agent/tools/validate.py --task <TASK-ID> --stage review
#   python .agent/tools/validate.py --task <TASK-ID> --stage completion
#
# Files, in the order they are written:
#
#   task.yaml               orchestrator   lifecycle state and resume anchor (not schema-validated)
#   intake.json             orchestrator   classification, risk, activated and skipped specialists
#   requirements.json       product        goal, actors, user stories, acceptance criteria, out-of-scope
#   design.json             tech-lead      architecture, interfaces, data model, ADRs, risks
#   plan.json               tech-lead      steps, affected_files, acceptance_mapping, parallel groups
#   ux-report.json          ux             flows, states, accessibility        (conditional)
#   worker-result.json      developer      what changed, tests run, concerns
#   db-report.json          database       schema, migration, query safety     (conditional)
#   qa-report.json          qa             per-criterion verdicts, edge cases, regressions
#   security-report.json    security       threat model, findings, blocking items (conditional)
#   perf-report.json        performance    measured budgets, bottlenecks        (conditional)
#   data-report.json        data           event contracts, consumer impact     (conditional)
#   review-report.json      reviewer       verdict, blockers/concerns/nits, drift
#   delivery-report.json    devops         build, migration, rollback, observability (conditional)
#
# One writer per artifact. Never edit a file another role owns.
# Pass artifact PATHS between agents, never artifact contents.
