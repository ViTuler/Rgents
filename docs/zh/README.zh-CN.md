# Rgents — 中文总览

一套用于 Cursor 的**多 Agent 软件开发团队**。它不是一个"角色提示词合集"，而是一个小型软件组织：
1 个协调者、5 个核心角色、6 个按风险按需激活的专家角色，加上产物契约与**可执行的质量门禁**。

英文正文位于仓库根目录（`AGENTS.md`、`README.md`）。本目录是中文配套文档，两者内容保持一致。

## 为什么这样设计

单个 AI Agent 做开发时，最大的问题是**没有独立验证**：写代码的 Agent 同时决定自己的代码是否正确、
是否安全、是否可维护。它的盲区就直接变成项目的缺陷。让 Agent"检查一下自己的工作"解决不了这个问题，
因为复查会继承实现时的同一个误解。

这套框架用三个结构性手段解决它：

| 手段 | 做法 |
|---|---|
| **角色不重叠** | 每个角色的 `NON-GOALS` 是一份互斥矩阵，明确"我不做什么，因为别人负责" |
| **产物即通信** | Agent 之间传递的是磁盘上的 JSON 文件路径，不是对话记录 |
| **门禁可执行** | 用零依赖校验脚本把常见失效模式变成硬错误，而不是文档承诺 |

## 团队构成

```
                    ┌──────────────────┐
                    │   ORCHESTRATOR   │  协调者（专家团队）
                    │  分类·路由·门禁   │  永不实现代码
                    └────────┬─────────┘
                             │
               ┌─────────────▼─────────────┐
               │        核心团队 Core        │
               │  product   需求             │
               │  tech-lead 架构与任务拆解     │
               │  developer 实现              │
               │  qa        功能验证           │
               │  reviewer  工程质量门禁        │
               └─────────────┬─────────────┘
                             │
               ┌─────────────▼─────────────┐
               │       专家团队 Specialists  │  按风险按需激活
               │  ux · security · devops     │
               │  database · data · performance
               └───────────────────────────┘
```

**核心团队** = 每个非平凡任务都会用到的 5 个角色。
**专家团队** = 按条件激活。**"每个任务都跑全部专家"是失效模式，不是严谨。**
**协调者** = 不承担工程角色，也不实现代码。

### 协调者是根 agent，不是被派发的子代理

这条是实战踩出来的，必须知道。Cursor 维护两份列表：斜杠命令注册表里**有**项目 agent，
而 Task 工具的 `subagent_type` enum 里**只有内置 agent**。所以：

- 你敲 `/spec`、`/build` → 协调者作为根 agent 跑起来 ✅
- 模型自己 `Task(subagent_type="orchestrator")` → 报 `not available in this session` ❌

**正确形态**：主线程**扮演**协调者，再由它派发各角色：

```
主 agent = 协调者
   └─ Task(product | tech-lead | developer | qa | reviewer | ux | security | devops | database | data | performance)
```

扮演协调者只给**路由权限**，不给实现权限。派发不出去的角色是**阻断项**，不是代写它产物的理由。

## 12 个角色

| 角色 | 一句话职责 | 它回答的问题 | 可改代码 |
|---|---|---|---|
| `orchestrator` | 分类、路由、激活专家、把守门禁、闭环任务 | 这个任务需要哪些角色、按什么顺序？ | ✗ |
| `product` | 需求、验收标准、边界、范围外清单 | 我们建的是对的东西吗？ | ✗ |
| `tech-lead` | 架构、接口契约、数据模型、任务拆解 | 什么是最简单的合理技术方案？ | 仅原型 |
| `developer` | 按既定设计实现、写测试、如实报告 | 我是否正确完成了分配的工作？ | ✓ |
| `qa` | 对抗性验证每条验收标准、边界、回归 | 系统真的按需求表现吗？ | 仅测试 |
| `reviewer` | 需求追溯、可维护性、架构漂移、复杂度、范围 | 半年后我还愿意维护它吗？ | ✗ |
| `ux` | 流程、状态覆盖、可访问性、文案 | 真实用户能理解并顺利使用吗？ | 仅 UI 规格 |
| `security` | 威胁建模、认证授权、输入校验、数据保护 | 有人能滥用它吗？ | 仅加固补丁 |
| `devops` | 构建可复现、配置、迁移、回滚、可观测性 | 它在生产环境真的能跑起来吗？ | 仅 CI/IaC |
| `database` | 表结构、索引、迁移锁与回滚、查询计划 | 数据比代码活得久，规模变大后会怎样？ | 仅迁移 |
| `data` | 事件与指标契约、管道、数据质量 | 下游消费方会因为这次改动静默失效吗？ | 仅管道 |
| `performance` | 在声明预算下测量延迟、吞吐、内存、并发 | 放大 100 倍会怎样？ | 仅基准 |

## 快速上手

```bash
# 1. 校验框架自身配置（零依赖，Python 3.8+）
python .agent/tools/validate.py --selftest
python .agent/tools/validate.py --check-setup

# 2. 在 Cursor 中用 slash 命令驱动一个任务
/spec    "用户应该能邀请同事加入组织"
/design  TASK-NNN
/build   TASK-NNN
/verify  TASK-NNN
/review-code TASK-NNN
/ship    TASK-NNN
```

每个命令都会委派给 `orchestrator`，由它读取 `.agent/config.yaml` 决定路由、读取
`.agent/workflows/<类型>.yaml` 决定阶段顺序。`tasks/active/` 平时为空；活任务做完后释放或归档。

## 生命周期

```
需求请求
  → 分类与规格      orchestrator, product
  → 设计与规划      tech-lead（高风险时并入 security / database / performance）
  → 实现            developer（用户可见时并入 ux；涉及数据管道时并入 data）
  → 功能验证        qa
  → 安全评审        security（命中激活条件时）
  → 工程评审        reviewer
  → 交付就绪        devops（交付面变化时）
  → 完成            orchestrator 收尾
```

**任何门禁失败，任务回到"实现"阶段，并且整条门禁链从 QA 重新跑一遍。**
局部重跑是不可用的选项——修复会使之前的验证失效。

## 产物即协议

Agent 之间不传对话，只传 `tasks/<TASK-ID>/` 下的文件，并且**传递路径而非内容**。

| 产物 | 唯一写入者 |
|---|---|
| `task.yaml` | orchestrator |
| `intake.json` | orchestrator |
| `requirements.json` | product |
| `design.json` / `plan.json` | tech-lead |
| `worker-result.json` | developer |
| `qa-report.json` | qa |
| `review-report.json` | reviewer |
| `security-report.json` | security |
| `ux-report.json` | ux |
| `db-report.json` | database |
| `perf-report.json` | performance |
| `data-report.json` | data |
| `delivery-report.json` | devops |

**一个产物只有一个写入者。永不修改别人拥有的产物**——如果你不同意它的结论，写自己的发现并上报。

## 可执行的门禁

`.agent/tools/validate.py` 把多 Agent 协作的经典失效模式变成硬错误。

| 失效模式 | 检查项 |
|---|---|
| **两个 active 任务描述同一需求** | `overlap_check_missing` / `overlap_unrecorded` / `overlap_needs_human` / `supersede_not_archived`：intake 必须比对 active 任务；命中 `likely` 必须由**人类**裁决；裁决为 supersede 时必须真的归档 |
| 计划与实现漂移 | `file_has_step` / `step_in_affected`：`affected_files` 与 `steps` 双向一致；`scope_extra` 对比真实 git diff |
| 越过失败继续往下跑 | `gate_not_passed` / `gate_not_run`：**没有产物 = 门禁没跑，绝不推断为通过** |
| PASS 里藏着 blocker | `verdict_consistent`：`verdict == PASS` 时 `blockers`、`concerns`、失败的验收标准、未决的 critical/high 发现都必须为空 |
| 验收标准被漏掉 | `acceptance_unmapped`（计划未覆盖）、`qa_criteria_incomplete`（QA 未给结论） |
| 需求本身没定清就开工 | `open_questions` 非空即报错 |
| 不可逆操作没有回滚方案 | `high_risk_rollback` / `irreversible_rollback` |
| SKIP 没有理由 | `skip_justified` |
| 谎报"跑过了" | `not_run_reason`、`blocked_has_reason` |
| 团队配置自身漂移 | `--check-setup`：角色注册、frontmatter 字段、必需小节、工作流引用的角色是否存在 |

自检（`--selftest`）会用**已知有缺陷的输入**逐个触发上述每一条不变量，证明它们真的会报警，
而不是只写在文档里。当前 17 项全部通过。

## 示例任务

| 目录 | 说明 |
|---|---|
| `tasks/completed/TASK-002/` | trivial 复杂度的示例（空状态文案），只跑 QA 就完成——用来展示分类如何削减不必要的流程 |
| `tasks/archive/TASK-004/` | 已归档的高风险邀请功能 intake/requirements 记录（未跑完门禁），需要更完整产物形状时可对照 |

对照阅读，能最直观地看出「按风险定流程」的实际含义。`tasks/active/` 不长期保留示例任务。

## 目录结构

| 路径 | 用途 |
|---|---|
| `AGENTS.md` | 团队宪法（英文，所有 Agent 首先读它） |
| `.cursor/agents/` | 12 个角色定义（Cursor 会把它们识别为 subagent） |
| `.cursor/rules/` | 行为约束（`00-global.mdc` 是总闸门） |
| `.cursor/skills/` | 可复用流程（测试策略、代码评审、威胁建模、安全迁移、交付就绪） |
| `.cursor/commands/` | 7 个 slash 命令 |
| `.agent/config.yaml` | 路由策略**单一真相源** |
| `.agent/workflows/` | feature / bugfix / refactor / incident 四条工作流 |
| `.agent/schemas/` | 产物 JSON Schema |
| `.agent/tools/validate.py` | 零依赖校验器 |
| `docs/agents/` | 职责矩阵、权限矩阵、协作协议 |
| `docs/knowledge/` | 项目记忆、经验教训、已知问题 |
| `tasks/` | 实际工作 |

## 继续阅读

- `docs/zh/roles.zh-CN.md` — 12 个角色的详细职责、边界与协作方式
- `docs/zh/workflow.zh-CN.md` — 工作流、门禁、任务状态机与返工机制
- `docs/agents/protocols.md` — 交接协议（英文）
- `Refer Doc/_refs/` — 两个参考项目的完整审计报告
