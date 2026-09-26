# Sandbox E2E 暴露的框架修复任务

- **日期:** 2026-09-23（草案）/ **落地:** 2026-09-24（S1–S7）
- **来源:** `H:\RainV\Rgents-Sandbox` 端到端测试（TASK-001…008）
- **当前框架版本:** 1.0.1
- **状态:** **S1–S7 已直接合入**；**S1 sandbox 端到端已闭环（TASK-011，无 plan.json）**。
- **证据:** `--selftest` canary S1/S2/S3/S5/S7；sandbox TASK-011 `--stage implementation` PASS without `plan.json`；`CHANGELOG` 1.0.1

约定：**框架修正不在框架仓内开 task 测**；验证靠 selftest，端到端在 sandbox。

---

## 批次与状态

| 批次 | ID | 优先级 | 状态 | 说明 |
|------|-----|--------|------|------|
| **E1** | **S1** | P0 | **已落地 + sandbox E2E** | trivial 无 plan；TASK-011 闭环（无 `plan.json`，`--all` PASS） |
| **E1** | **S2** | P0 | **已落地** | 计划外脏文件不误杀；worker 超报仍报错 |
| **E2** | **S3** | P1 | **已落地** | stale log 提示 fresh uuid |
| **E2** | **S4** | P2 | **已落地** | ux 激活/跳过边界（config + ux.md + 中文指南） |
| **E3** | **S5** | P2 | **已落地** | likely 仅对 **active** 强制人裁；completed 可 orchestrator+rationale |
| **E3** | **S6** | P3 | **已落地** | `guide.zh-CN.md` 多 active 工作区卫生 |
| **E4** | **S7** | P1 | **已落地** | `/ship` 归档工具 + `archive_active_residual` |

**播种产品同步:** `seed_framework.py upgrade`（replaceable 含 validate/config/.cursor/docs/architecture；**`.gitignore` 为 product_owned**；**不含** `docs/zh/`）。

---

## S1–S3（validate）

见前次落地说明；selftest canary 名含 `S1:` / `S2:` / `S3:`。

**S1 sandbox 闭环（TASK-011，2026-09-24）：** 人确认 trivial；**无** `plan.json`；仅改 `docs/knowledge/project-memory.md` Constraints；`--stage implementation` / `--all` / `--stage completion` **PASS**；已归档 `tasks/completed/TASK-011/`。顺带修正：S1 校验不得因 `docs/knowledge/` 属 SCOPE_EXEMPT 而对已声明且已改动的知识文件误报 `scope_missing`。

## S4 — UX 激活边界

- `config.yaml` → 新 trigger `ux_specification_for_upcoming_surface`；新 skips `agent_or_framework_docs_only`、`ux_spec_is_the_sole_deliverable`
- `.cursor/agents/specialists/ux.md`、`docs/zh/workflow.zh-CN.md`、`roles.zh-CN.md` 对齐

## S5 — ship/overlap 人裁范围

- `overlap_needs_human` 仅当 recorded **likely** 且对应任务仍在 `tasks/active/`
- completed/archive 的 likely + `decided_by=orchestrator` + rationale → 允许

## S6 — 并行卫生文档

- `docs/zh/guide.zh-CN.md`：串行 commit、disjoint affected_files、worktree、勿扩 SCOPE_EXEMPT

---

## S7 — `/ship` 归档残留（已落地 2026-09-24）

- **问题:** agent 复制 active→completed 后删 active 常被拦，双目录残留；`resolve_task_dir` 仍优先 active。
- **修复:** `.agent/tools/archive_task.py`（含 `task.yaml` `artifact_path` 前缀重写）；completion 校验 `archive_active_residual`；`/ship` 先 `--all` 再 completion；orchestrator 文案。
- **selftest:** `archive_active_residual when both…` / `archive_task.py removes residual…` / `rewrites task.yaml active artifact_path`

---

## 附录 — sandbox 映射

| Sandbox 任务 | 暴露项 |
|--------------|--------|
| TASK-005/008 | S1（旧：用最小 plan 绕过） |
| **TASK-011** | **S1 E2E（无 plan.json）** |
| TASK-003…006 | S2 |
| TASK-002/007 | S3 / S5 |
| TASK-005 | S4 |
| 并行脏树 | S6 |
