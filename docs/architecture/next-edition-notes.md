# Rgents — 下版修正备忘（next edition notes）

- **创建:** 2026-09-23
- **状态:** **承接第一次修正之后**；N2/N3 已随第一次收束落地；**开项仅剩 N1**（及未立项杂项）
- **第一次修正权威收束:** [`correction-backlog.md`](./correction-backlog.md)（status: closed）
- **测试计划:** 人新开产品项目，用 `seed_framework.py create` 验证；本文件不跟踪测试任务

---

## N1 — 角色间辩论与协作（拓扑）

- **来源:** 2026-09-23 人工确认：当前深度-1 星形拓扑职权分离强，但角色之间几乎不存在辩论/协作；**第一次修正不改拓扑**，纳入下版。
- **问题:** 编排者星形派发 → 角色只对编排者与磁盘工件负责；product / tech-lead / developer / qa / reviewer / 专家之间没有受控的对辩或联合裁决通道。冲突靠编排者串话或返工门链，成本高且易在提示词通道里被裁剪。
- **方向（未冻结）:** 在不破坏「每工件唯一写者 / 禁止自我批准」的前提下，引入有限的协作原语，例如：
  - 设计期或门失败后的 **structured debate** 工件（双方各写主张 + 对方反驳，第三者或人裁决）；
  - 或 **consultation 扩展为双边**，而不仅是专家→tech-lead 单向；
  - 仍禁止角色互相直接改对方工件。
- **非目标（暂定）:** 不做多 agent 自由聊天室；不做深度 >1 的互相派发（Cursor 平台限制仍在）。
- **状态:** **下版首项候选**（未开工）。

---

## 第一次修正已关闭、仅作对照

| ID | 项 | 说明 |
|----|-----|------|
| C0–C7 | 修正包 | 见 correction-backlog；PR 已开 |
| N2 | 播种 create/upgrade | **已落地**；产品仓实测待人 |
| N3 | 轻量框架 CI | **已落地**；仍不重跑产品测试 |
| — | `accepted_risk` / retry 死代码 / 四专家补测 | 仍未立项 |
| — | N2 overlays / semver 变更日志 | 可增强，非阻塞 |

---

## N2 — 项目播种与升级（已随第一次修正关闭）

- **状态:** **已落地（2026-09-23）**
- **触点:** `.agent/framework-manifest.yaml`；`.agent/tools/seed_framework.py`；`bootstrap-project.ps1`；`.agent/seeded-from.yaml`；validate `check_seeded_from`
- **验证:** 留给新开产品项目（人侧）。

---

## N3 — 会话外 CI（轻量；已随第一次修正关闭）

- **状态:** **已落地（2026-09-23）**
- **触点:** `.github/workflows/framework-ci.yml`；`validate.py --ci-changed`
- **约束:** validate 默认信任开发者；不重跑产品测试。
