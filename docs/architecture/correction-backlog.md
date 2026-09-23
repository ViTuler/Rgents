# Rgents 修正清单与方案

- **日期:** 2026-09-22（收束 / 版本标记 2026-09-23）
- **状态:** **第一次设计修正已结束 · 框架版本 1.0.0**
- **框架版本:** **1.0.0**（`VERSION`；`.agent/framework-manifest.yaml → release`）
- **权威文本:** 本文档（画布 `rgents-correction-backlog.canvas.tsx` 仅为 IDE 对照，不进仓库）
- **范围:** 框架设计与工具修正 C0–C7 + N2/N3（本仓库是框架本身，不是产品应用）
- **治理:** 人类已授权主线程直接改；本轮关闭。下版入口见 `next-edition-notes.md`（N1）
- **下一步:** 新开产品项目做播种与端到端测试

---

## 开干检查清单

在第一次改仓库文件之前，确认：

| # | 项 | 状态 |
|---|-----|------|
| 1 | 本清单 C0–C7 方案已读且无异议 | 设计侧：已冻结 |
| 2 | 人类授权：「允许为 C0–C7 修改 `.agent` 与 `.cursor`（及必要的 docs/README）」 | **已授权（批次 A–D）** |
| 3 | 实施切分：建议 **批次 A** = C0+C6+C7；**批次 B** = C3+C4；**批次 C** = C5+C1；**批次 D** = C2（单独任务） | **A–D 完成** |
| 4 | 环境：conda 非 base；改 validate 后跑 `python .agent/tools/validate.py --selftest` 与 `--check-setup` | 实施时执行 |
| 5 | 走正式任务车道：`/spec` 起任务（或你声明 bypass 流水线由主线程直接改） | bypass 主线程 |

---

## 建议动手顺序（批次）

| 批次 | 顺序 | ID | 优先级 | 说明 |
|------|------|-----|--------|------|
| A | 1 | C0 可移植性 | P0 | 唯一已知红灯类问题；触点集中在 validate |
| A | 2 | C6 项目基线 | P0 | 结构化基线 + 环境门对照 |
| A | 3 | C7 项目 init / 本地 git | P0 | init 脚本；可与 C1 扫描钩子预留 |
| B | 4 | C3 trivial 人闸 | P1 | schema + orchestrator + validate |
| B | 5 | C4 validate log + QA 挂 log | P1 | validate 落盘；completion 核 log |
| C | 6 | C5 product/reviewer 不改源码 | P2 | 契约文案 |
| C | 7 | C1 模型编配 | P2 | 目录 + assignments；依赖 C7 init 钩子 |
| D | 8 | C2 worktree + 锁 | P3 | **单独任务**；体量最大 |

---

## 修正项总表

| ID | 问题 | 约定方案 | 主要触点 | 状态 | 优先级 |
|----|------|----------|----------|------|--------|
| **C0** | 可移植性误扫 `tasks/**`；豁免前缀仍为 `ReferDoc/` | 只扫框架源码；`tasks/**` 整目录豁免；前缀改 `refers/`；停止堆字段名豁免 | `validate.py`；README 过期表述 | **已落地** | P0 |
| **C1** | 全体 `inherit` → 同一观察者 | 见「C1 详细方案」 | init；模型目录；intake；orchestrator；validate | **已落地** | P2 |
| **C2** | 并行无 worktree | 见「C2 详细方案」 | worktree 工具；plan；locks；orchestrator；config | **已落地** | P3 |
| **C3** | 误标 trivial 裁工序 | trivial 出站须 `decided_by: human` | intake/task schema；orchestrator；validate；`/spec` | **已落地** | P1 |
| **C4** | 门检自证 | validate 自写 uuid log；completion 核；QA 挂 log id；暂不 CI 重跑测试 | validate；schemas；completion；QA | **已落地** | P1 |
| **C5** | 计划内角色可改源码 | 不上 MD5；product/reviewer 原则上不改业务源码；reviewer 扫 diff | `product.md`；`reviewer.md`；rules | **已落地** | P2 |
| **C6** | 栈靠手填 md / 每任务重问 | 项目级首次 spec→design → 结构化基线；后续只对照 | config/schema；product；tech-lead；环境门 | **已落地** | P0 |
| **C7** | 新项目无本地 git | init：`git init`，不设 remote；与 bootstrap 衔接 | init 脚本；bootstrap README | **已落地** | P0 |

---

## C0 摘要 — 可移植性

- **问题：** 扫描器扫整仓；任务工件里的真实解释器路径被报 `machine_specific_path`；字段名豁免无效；前缀仍写已不存在的 `ReferDoc/`。
- **方案：** 可移植性规则只约束**框架源码**；`tasks/**` **整目录豁免**；豁免前缀改为 `refers/`；删除或停用靠字段名堆豁免的策略。
- **验收：** 框架仓 `--check-setup` / `--selftest` 绿；Sandox 若仍有 tasks 内路径不再因此红。

---

## C1 详细方案 — 模型目录与编配（已冻结）

### 意图

- 避免全体 `inherit` 导致实现与审查同一模型盲点。
- 以 init 探测的模型目录为机器可读真相源；编排建议；角色可覆盖**下一次**派发。
- 为跳出 Cursor 预留适配器。

### 流程

1. **Init（与 C7 同期）**  
   - 适配器扫描（首期 `cursor_api`）。无密钥 → `manual_seed`，标明 `source: seed`。  
   - 写入 YAML/JSON（可选 md 摘要）：`id`、显示名、`context_tokens?`、概述、`source`。  
   - **禁止**写入 API Key。默认不每任务重扫；`init --refresh-models`；`fetched_at` 过期仅警告。

2. **编排**  
   - 写入 **`model_assignments`**。Agent 可继续 `model: inherit`。  
   - 真相源 = assignments + Task `model`。**根编排者**由人在 UI 选，不编配。

3. **约束**  
   - **硬：** qa / reviewer / security 两两不同。  
   - **软：** developer 尽量不同。其余角色建议即可。

4. **覆盖**  
   - 仅下次派发；`overridden_by` + `rationale`；不得破坏三角互异。

5. **目录 ∩ IDE 允许集**  
   - 派发 slug ∈ 交集；不足 3 个互异 → 问人，禁止静默同模。

6. **审计**  
   - 用 `assigned_model`，勿冒称 `executed_model`。

7. **适配器**  
   - `list_models() -> [...]`；首期 `cursor_api`、`manual_seed`。

### 可行性

| 能力 | 结论 |
|------|------|
| API/SDK 列模型 | 可以（需 Key） |
| 读本地 settings 得全表 | 不可以 |
| 运行中热切换自身模型 | 不可以 |
| 派发时指定子 agent 模型 | 可以 |

### 实施可微调

- 默认路径建议 `.agent/models/available.yaml`  
- API id ↔ IDE slug 映射  
- 种子文件最小字段  

---

## C2 详细方案 — Worktree + 文件锁（已冻结）

### 意图

1. **地址空间隔离** → 每条并行步骤一个 **git worktree**（类进程）。  
2. **临界区** → **路径排他锁 + merge 互斥锁**（类 mutex）。

对齐 `config.yaml → parallelization`：默认串行；仅 `parallel_group` 且文件集不交时并行。

### 对照

| 并发概念 | 本框架 |
|----------|--------|
| 进程 | git worktree + 步骤分支 |
| mutex（资源） | 路径排他锁（path lease） |
| mutex（临界区） | merge lock |
| rwlock | 首期不做，预留 |
| 死锁预防 | 计划期 `claimed_paths` 两两不交；先 path 后 merge |
| 租约 | `expires_at` + 回收 |

### 生命周期

```
plan: parallel_group + claimed_paths
  → validate 不交
  → acquire path locks → worktree add → 派发（仅改该树）
  → 全成功 → acquire merge lock → 合入 rgents/<task>/integrate
  → release → 成功则 remove worktree；冲突保留并升级
```

### 锁

- 仓库相对路径；工具写锁表（任务级 + 仓库级 index 防跨任务）。  
- 字段：`path`、`mode=exclusive`、`holder`、`acquired_at`、`expires_at`、`worktree`。  
- 原子更新（`os.replace` 等）。

### Worktree

- `<repo>/.rgents/worktrees/<task>/<step>/`（gitignore）  
- 分支 `rgents/<task>/<step>`  
- 并行步禁止改主工作区  

### 首期不做

分布式锁、字节级锁、依赖 IDE worktree UI。

### 触点

`parallel_worktree.py`（或等价）；plan schema；orchestrator；config；`.gitignore`。

---

## C3 摘要 — trivial 人闸

- `complexity: trivial` 出站进入实现前，必须有人确认（`decided_by: human` 或等价字段）。  
- `standard` / `complex` 默认可自走。  
- validate 缺确认则 error。

---

## C4 摘要 — validate log

- `validate.py` 写入 `tasks/<id>/logs/validate-<uuid>.json`：stage、exit、时间、HEAD、artifact sha256。  
- completion 按 id 核对；工件变则旧 log 作废。  
- QA 报告引用 log id。只读防手滑，非防伪造。  
- **不做**会话外重跑测试。

---

## C5 摘要 — 写权限约定

- 不上 MD5 账本。  
- product / reviewer：NON-GOALS / 规则写明原则上不修改业务源码。  
- 计划内越界：reviewer 审 `git diff`。

---

## C6 摘要 — 项目基线

- 不靠每个新项目手填 `project-memory.md`。  
- 项目级首次 spec→design：人 + product + tech-lead → **结构化基线**。  
- 后续任务环境门只对照基线；md 若保留仅为摘要。

---

## C7 摘要 — init 与本地 git

- `init.py` 及/或 cmd/bat/bash/sh：`git init`，**不** `remote add`，默认不代做首次 commit。  
- 修订 bootstrap「故意不 git init」：播种后跑 init。  
- 可挂 C1 模型扫描、C6 基线占位步骤。

---

## 明确不在本轮

| 项 | 原因 |
|----|------|
| 会话外（CI）重跑测试 | 已推迟；2026-09-23 人确认暂不考虑（影响分析见会话，不阻塞本包） |
| `accepted_risk` 清单、retry 死代码核查、四专家补测 | 未纳入本包 |
| 「框架无 git」 | 已过时（本仓已有 git）；扁平历史另议 |
| 角色间辩论 / 协作拓扑 | **本版不做**；已记入 `docs/architecture/next-edition-notes.md` → N1 |

下版候选备忘的权威入口：[`next-edition-notes.md`](./next-edition-notes.md)。

---

## 治理与授权（待回复）

请人类回复其一（或改写）：

1. **授权全文：**「允许为实施 C0–C7 修改 `.agent/**`、`.cursor/**`、相关 `docs/**` 与 `README.md`。」  
2. **授权批次 A：**「仅允许先做批次 A（C0/C6/C7）。」  
3. **走流水线：**「先 `/spec` 开 TASK，再按 plan 改。」  

未授权前，代理**只维护本清单类文档，不改治理面与 validate 行为。**

---

## 修订记录

| 日期 | 变更 |
|------|------|
| 2026-09-22 | 初稿 C0–C6；C1/C2 为最早点名的设计点 |
| 2026-09-22 | 增补 C7；C1 改为目录+建议+三角互异+可覆盖 |
| 2026-09-22 | C1 可行性检索结论 |
| 2026-09-22 | C1/C2 方案冻结（含锁与 worktree） |
| 2026-09-22 | 定稿：状态改为准备实施；补 C0/C3–C7 摘要；开干检查清单与批次；待授权 |
| 2026-09-22 | **批次 A 落地：** C0 可移植性只扫框架/`tasks`+`refers`豁免；C6 `project-baseline`；C7 `init_project`；selftest+check-setup PASS |
| 2026-09-22 | **批次 B 落地：** C3 `classification_confirmation`；C4 validate logs + QA `validate_log_ids`；selftest+TASK-002 --all PASS |
| 2026-09-22 | **批次 C 落地：** C5 product/reviewer NON-GOALS + reviewer diff；C1 models catalog + assignments + triangle validate；init --refresh-models |
| 2026-09-22 | **批次 D 落地：** C2 `parallel_worktree.py`（path lease + merge lock + git worktree）；plan `streams[].claimed_paths`；validate 相交检查 |
| 2026-09-23 | 人确认：CI 重跑暂不考虑；角色辩论/协作记入 `next-edition-notes.md` N1；播种修正进入讨论 |
| 2026-09-23 | **播种升级落地：** `framework-manifest.yaml` + `seed_framework.py` create/upgrade；bootstrap 薄封装；N2 关闭 |
| 2026-09-23 | **轻量 CI 落地：** `framework-ci.yml` + `validate --ci-changed`（active `--all`）；N3 关闭；仍不重跑产品测试 |
| 2026-09-23 | **框架版本标记为 1.0.0**（`VERSION` + manifest `release`）；第一次设计修正收束 |
