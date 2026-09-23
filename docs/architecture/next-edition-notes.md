# Rgents — 下版修正备忘（next edition notes）

- **创建:** 2026-09-23
- **当前框架版本:** **1.0.0**
- **状态:** 第一次修正已收束；N2/N3 已落地；**开项仅剩 N1**（及未立项杂项）
- **权威:** 本文档（承接 `correction-backlog.md`）

---

## N1 — 角色间辩论与协作（拓扑）

- **来源:** 2026-09-23 人工确认：当前深度-1 星形拓扑职权分离强，但角色之间几乎不存在辩论/协作；**本版暂不改拓扑**，纳入下版。
- **问题:** 编排者星形派发 → 角色只对编排者与磁盘工件负责；product / tech-lead / developer / qa / reviewer / 专家之间没有受控的对辩或联合裁决通道。冲突靠编排者串话或返工门链，成本高且易在提示词通道里被裁剪。
- **方向（未冻结）:** 在不破坏「每工件唯一写者 / 禁止自我批准」的前提下，引入有限的协作原语，例如：
  - 设计期或门失败后的 **structured debate** 工件（双方各写主张 + 对方反驳，第三者或人裁决）；
  - 或 **consultation 扩展为双边**，而不仅是专家→tech-lead 单向；
  - 仍禁止角色互相直接改对方工件。
- **非目标（暂定）:** 不做多 agent 自由聊天室；不做深度 >1 的互相派发（Cursor 平台限制仍在）。
- **状态:** note only — 下版修正候选之一。

---

## 已记录、本包明确推迟（供对照）

| ID | 项 | 说明 |
|----|------|------|
| （原清单） | 会话外 CI **重跑产品测试** | 仍不做；轻量框架 CI 见 N3（已落地） |
| （原清单） | `accepted_risk` / retry 死代码 / 四专家补测 | 仍未立项 |
| （原清单） | 播种后框架升级协议 | 见 N2（已落地） |

---

## N2 — 项目播种与升级

- **状态:** **已落地（2026-09-23）**
- **触点:** `.agent/framework-manifest.yaml`；`.agent/tools/seed_framework.py`（create / upgrade / show）；`bootstrap-project.ps1` 改为 create 薄封装；`.agent/seeded-from.yaml`；validate `check_seeded_from`
- **行为摘要:**
  - create：空目录；模板脚手架 baseline/knowledge；剥离 provisioning 与 selftest/`__pycache__`；写 `seeded-from`；git init 无 remote
  - upgrade：仅替换 manifest `replaceable`；永不碰 `product_owned`；`.rgents/upgrade-backups/`；须 `--dry-run` 或 `--yes`
- **仍可后续增强:** 产品侧 overlays、semver 变更日志、从 GitHub release 拉包升级

---

## N3 — 会话外 CI（轻量；已落地）

- **约束（2026-09-23）:** 不做「validate 完整重跑产品测试」；validate **默认信任开发者**（否则角色边界模糊）。
- **落地:**
  - `.github/workflows/framework-ci.yml` — 三 job：`--selftest` / `--check-setup` / `--ci-changed`
  - `validate.py --ci-changed --base <ref>` — 仅对 diff 触及的 `tasks/active/TASK-*` 跑适用 stage 的 `--all`（形状）；completed/archive 忽略
- **非目标:** 产品 `commands.test`、重放 `commands_run`、用 CI 代替 QA。
- **状态:** **已落地（2026-09-23）**
