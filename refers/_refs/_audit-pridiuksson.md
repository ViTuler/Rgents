# 深度结构审计报告：`pridiuksson/cursor-agents`

- **审计对象**：`H:\RainV\Rgents Team\Refer Doc\_refs\pridiuksson-cursor-agents`
- **远端来源**：`https://github.com/pridiuksson/cursor-agents.git`（`.git/config` 中的 `remote.origin.url`）
- **审计时的仓库状态**：branch `master`，HEAD = `ee174ebb6d7adb7be21f40154e185d7dd0c48334`
  - commit 元信息：`ee174ebb... | 2025-08-25 12:44:44 +0200 | pridiuksson | docs(qa): update wf-testing.md to reflect SYS-002/003 implementation status`
  - **浅克隆（shallow）**：`.git/shallow` 存在，`git rev-list --count HEAD` = `1`，`git rev-parse --is-shallow-repository` = `true`。因此**无法审计演进历史**，只能审计当前快照。
  - 本地无未提交改动（`git status --short` 为空），无 tag。
  - 已用 GitHub API 交叉验证上游 `master` 的 tree（`.../git/trees/master?recursive=1`，返回 `truncated: false`，sha 与本仓库 HEAD sha 一致），**逐个 blob 的 sha/大小与本地一致**。结论：本地克隆是完整快照，不存在“漏克隆了 `.cursor/` 目录”的可能——上游公开仓库本身就只有这 8 个文件。
- **审计方法**：`glob` 全树枚举 + `pwsh` 递归列目录（含隐藏项）+ `read` 逐文件全文读取（含 `kiro.md` 1701 行分两次读完）+ `grep` 定点取证 + GitHub API 外部校验。**下文每条结论均给出文件路径与行号，未读取过的内容不作断言。**
- **报告语言**：中文。

---

## 0. 最重要的结论（先看这一条）

**这个仓库不是一个 agent 框架，也不是一个可运行的模板仓库；它是一个“设计说明 + 营销文案 + 路线图”的文档仓库。**

证据链：

1. 全仓库树（排除 `.git`）只有 8 个 `.md`，**零目录、零代码、零配置文件、零 CI 定义**：

   | 文件 | 行数 | 上游 blob 大小 |
   |---|---|---|
   | `readme.md` | 193 | 9360 B |
   | `backlog.md` | 92 | 5140 B |
   | `process.md` | 497 | 20391 B |
   | `geminicli.md` | 217 | 10434 B |
   | `kiro.md` | 1701 | 66263 B |
   | `vs-cursor.md` | 231 | 9050 B |
   | `vs-geminicli.md` | 106 | 8303 B |
   | `wf-testing.md` | 342 | 11972 B |
   | **合计** | **3379 行** | ≈140 KB |

2. 仓库里**没有任何 `agent`/`persona`/`role` 的定义文件**。审计中穷举检索 `.mdc`、`alwaysApply`、`frontmatter`、`description:`、`globs`，命中项**全部是“对别处文件的引用或计划”，没有一处是本仓库内的定义文件**：

   - `backlog.md:30`（这是**未来要做的事**，不是已存在的东西）：
     > `- **STORY 1.1**: Extract core personas (system-architect.mdc, feature-dev.mdc, docs-writer.mdc, quality-reviewer.mdc) to .cursor/rules/agents/.`
   - `readme.md:191`（自己承认模板还没发布）：
     > `**Next Up**: Template repository with agent personas, quality gate examples, and step-by-step tutorials.`
   - `kiro.md:1658` 是**唯一一次**公开提到 Cursor rule 的 frontmatter 字段名：
     > `- `.kiro/steering/` vs existing `.cursor/rules/` with `alwaysApply: true``

3. 被描述的“真实系统”在**另一个（未公开的）仓库**里。它的关键文件在本仓库中只以引用形式出现，从未展示内容：`ARCHITECTURE.md`、`agents.md`、`PROJECT_BACKLOG.md`、`ADR/`（`ADR-003-ai-adapter-pattern-for-experimental-models`、`ADR-005`、`ADR-021`）、`docs/agentic-workflow/`、`docs/testing/`、`supabase/functions/`、`tests/`、`scripts/health-checks/run-architecture-audit.js`、`.github/workflows/ci-lite.yml`、`.cursor/rules/agents/*.mdc`。

4. 本仓库中**唯一可直接复制使用的“agent 定义”**是 `geminicli.md:109-214` 里的 9 段 Gemini CLI 自定义命令 TOML（见 §2.3）。

**对本次审计任务的影响**：任务书里的第 2、5、6 问（agent 定义格式、门禁独立性、人机协作）在**本仓库内无法从源文件回答，只能从“描述”回答**。下文严格区分两类证据：**【原文可引用】= 仓库内实际存在的文本**；**【仅被描述】= 只以引用/计划/示意图形式出现，无定义文件可查**。

---

## 1. 仓库整体结构

### 1.1 布局与命名约定

- **布局**：完全扁平，8 个文件全在仓库根，无子目录。**没有** `docs/`、`src/`、`.cursor/`、`.gemini/`、`tests/`、`.github/`。
- **命名**：全小写 `.md`，但**风格不统一**，可分成三种：
  - 连字符式：`vs-cursor.md`、`vs-geminicli.md`、`wf-testing.md`
  - 无分隔式：`readme.md`、`backlog.md`、`process.md`、`kiro.md`
  - 混合：`geminicli.md`（正文标题却写作 “Gemini CLI”），且**同时存在 `geminicli.md` 与 `vs-geminicli.md` 两个前缀相同的文件**，靠前缀无法判断关系。
- **`readme.md` 小写**（非 `README.md`）。GitHub 仍能识别并渲染，但在大小写敏感文件系统（Linux CI）上按名引用 `README.md` 会 404。这是一个真实的移植风险点。

### 1.2 分层方式：按“文档职能”分层，而非按代码分层

`readme.md:12-15` 自己声明了导航分层：

> ```
> ### **📖 Documentation Navigation**
> - **This README**: Overview, benefits, and competitive comparison
> - **[process.md](./process.md)**: See the workflow in action with real examples and multi-agent coordination  
> - **[backlog.md](./backlog.md)**: Public roadmap with MVP plans and future development phases
> ```

实际可归纳为 4 个文档族：

| 族 | 文件 | 职能 | 写作人称 |
|---|---|---|---|
| A. 产品/入口 | `readme.md`, `backlog.md`, `process.md` | 定位、路线图、实战案例 | 第三人称 / “我们” |
| B. 工具代言 | `vs-cursor.md`, `vs-geminicli.md`, `geminicli.md` | 以“我是 Cursor IDE”“我是 Gemini CLI”的口吻论证采纳理由与命令参考 | **第一人称拟人** |
| C. 异构 IDE 集成 | `kiro.md` | Kiro IDE 集成方案（含自我批判与否定原方案） | 方案书 |
| D. 领域附件 | `wf-testing.md` | QA/测试策略（**从源项目泄漏出来的真实内部文档**） | 内部规范 |

**族 B 的写作策略值得注意**（`vs-cursor.md:3-4`、`vs-geminicli.md:3`）：

> `I’m Cursor IDE, with an embedded AI assistant powered by GPT‑5. This document explains why I adopt the repository’s agentic workflow, ...`
>
> `I’m Gemini CLI, the command-line interface that executes tasks within this project. This document explains why I adopt the repository’s agentic workflow, ...`

即：**用“工具自述”的方式写 README 级文档**，来推销一套针对该工具的工作流。这是一种叙事技巧，不是工程结构。

### 1.3 `kiro.md` 的特殊性（1701 行，占全仓 50%）

`kiro.md` 结构上是一个**被否定的方案的完整存档**：前半部分（约 1-1180 行）提出 `.kiro/` 与 `.cursor/` 双系统双向同步架构，后半部分 `kiro.md:1650-1669` 自己列出该方案的致命缺陷：

> ```
> ## **🔍 CRITICAL FLAWS IDENTIFIED IN ORIGINAL PLAN**
> ### **1. Fundamental Misunderstanding of System Maturity**
> **FLAW**: Treated this as a "basic" system needing Kiro enhancement.
> **REALITY**: This is already a highly sophisticated, battle-tested multi-agent system.
> ### **2. Redundant Feature Overlap**
> ...
> ### **3. Architecture Violation**
> **FLAW**: Proposed `.kiro/` directory structure violates the established "Single Entry Point" principle.
> ### **4. Workflow Disruption Risk**
> **FLAW**: "Hybrid" approach would create decision paralysis and conflict between systems.
> ```

审计提示：**`kiro.md` 中的 `.kiro/**` 目录树、JSON 配置、`class KiroXxx { ... }` 全是“conceptual implementation”（`kiro.md:1529` 原话）的蓝图/伪代码，不是仓库内的实际文件**，其中还保留着大量 `✅ RESOLVED`（如 `kiro.md:325-339`）这类自我宣称的完成标记，与“这些文件在本仓库不存在”直接冲突。引用该文件时不可当作已实现事实。

---

## 2. Agent 定义

### 2.1 角色清单（【仅被描述】，但描述足够具体）

`readme.md:53-59` 给出“最佳组合专业化”的 5 个核心角色，且**把角色和具体模型绑定**：

> ```
> ### **1. Best-of-Breed Specialization**
> Each AI model handles what it does best:
> - **System Architect (Claude)**: Strategic planning and coordination
> - **Security Reviewer (Qwen Code)**: Security analysis and architecture validation  
> - **Context Specialist (Gemini CLI)**: Deep codebase analysis and pattern discovery
> - **Feature Developer (Claude)**: Implementation and testing
> - **Documentation Writer (Claude)**: Knowledge transfer and maintenance
> ```

`readme.md:113-119` 的 “Agent Specialization Matrix” 补充了**触发条件**（“When They're Critical”），这是比角色名更有价值的一栏：

> ```
> | Specialist | Primary Responsibility | When They're Critical |
> | **System Architect** | Strategic planning, task coordination | Complex features, architectural decisions |
> | **Security Reviewer** | Code quality, security validation | All production code, critical systems |
> | **Context Specialist** | Codebase analysis, pattern discovery | Large refactors, complex integrations |
> | **Feature Developer** | Implementation, testing | All development work |
> | **Documentation Writer** | Knowledge transfer, maintenance | Feature completion, architectural changes |
> ```

`backlog.md:69-74` 的 “Agent Decision Matrix” 进一步按**任务类型**给出主角色 + 门禁 + 收益：

> ```
> | Task Type | Primary Agent | Quality Gate | Benefit |
> | Feature Planning | System Architect | Review plan | Strategic alignment |
> | Implementation | Feature Developer | Code review | Clean execution |
> | Validation | Quality Reviewer | Tests/security check | Catches issues early |
> | Documentation | Docs Writer | Accuracy validation | Maintainable knowledge |
> ```

`wf-testing.md:33-56` 又补充了 QA 视角下的**第 6～9 个角色**（Head of QA、Refactoring Engineer、Docs Writer、以及被点名的 `system-architect.mdc` / `feature-dev.mdc`）。

`geminicli.md` 的命令清单隐含了更多角色：**Refactoring Engineer**（`geminicli.md:61`）、**QA Engineer**（`geminicli.md:66-68`）、**Technical Writer**（`geminicli.md:71-74`）、**Git Specialist**（`geminicli.md:76-78`）、**Workflow Maintainer**（`geminicli.md:82-84`）。

**角色命名不一致（真实缺口）**：同一概念在不同文件里名字不同——“Security Reviewer” 与 “Quality Reviewer” 混用（`readme.md:116` vs `backlog.md:73`），而文件名叫 `quality-reviewer.mdc`（`backlog.md:30`）；“Feature Developer” 的文件名却是 `feature-dev.mdc`；“Documentation Writer” 的文件名是 `docs-writer.mdc`。**没有单一的角色注册表（roster）**，这是本仓库最值得批评的结构问题之一。

### 2.2 定义文件格式：**Cursor `.mdc` 的格式在本仓库中不可审计**

穷举检索结果：全仓库对 `.mdc` 的 12 处提及**全部是路径引用或变更检测模式**，例如：

- `wf-testing.md:42-49`：以 `(`system-architect.mdc`)` 形式在正文里标注角色与文件的对应关系
- `kiro.md:1360-1362`（监控通配符）：
  > ```
  > - .cursor/rules/agents/*.mdc
  > - .cursor/rules/core/*.mdc
  > - .cursor/rules/protocols/*.mdc
  > ```
- `kiro.md:1358-1368` 给出了**规则文件的分类约定**（agents / core / protocols 三分类）以及“新增/修改/删除规则时该做什么”的同步动作表
- `kiro.md:1658`：唯一披露的 frontmatter 字段 `alwaysApply: true`

**因此：关于 Cursor agent 定义的 frontmatter 字段集、正文小节结构、输入/输出/边界声明方式，本仓库没有任何一手材料。** 任何声称“该仓库的 agent 定义包含 X 字段”的说法都是猜测。

可以确定的约定只有三条（均来自计划文本）：
1. 目录：`.cursor/rules/agents/`（`backlog.md:30`）、`.cursor/rules/core/`（`backlog.md:32`）、`.cursor/rules/protocols/`（`kiro.md:1362, 1466`）
2. 文件名：`<role-kebab>.mdc`
3. 至少存在 `alwaysApply: true` 这一 frontmatter 字段（`kiro.md:1658`）

以及一条**通用的核心协议**计划：`backlog.md:32` —

> `- **STORY 1.3**: Create core-protocol.mdc in .cursor/rules/core with universal patterns (two-tier memory, code-first docs).`

### 2.3 【原文完整示例】`/plan/breakdown.toml` —— 本仓库唯一实际存在的 agent 定义

这是本仓库中**唯一一份带有“角色 + 指令 + 输入占位符 + 输出契约”的完整、可复制的定义**，位于 `geminicli.md:109-123`。原文逐字引用：

```toml
description = "(System Architect) Decomposes a high-level goal into a step-by-step execution plan."
prompt = '''
Act as the Senior System Architect. Your primary responsibility is to translate the user's high-level goal into a concrete, step-by-step implementation plan.

**Core Directives:**
1.  **Analyze**: Decompose the request into the smallest logical, atomic steps (code, test, docs, etc.).
2.  **Consult**: Use tools to analyze the codebase to ground your plan in the current implementation.
3.  **Assign**: For each step, explicitly assign the correct specialist command (e.g., `@dev:implement`, `@test:create`).
4.  **Output**: Your final output MUST be a markdown-formatted checklist.

Begin planning for the following task: {{args}}
'''
```

**这份定义的结构可归纳为 4 段模板**（其余 8 个命令严格同构）：

| 段 | 作用 | 本示例内容 |
|---|---|---|
| `description` | **角色在括号里前置** + 一句话职责 | `(System Architect) Decomposes a high-level goal into a step-by-step execution plan.` |
| 首句 | `Act as the <Role>.` + `Your primary responsibility is to ...` | `Act as the Senior System Architect. Your primary responsibility is to translate ...` |
| `**Core Directives:**` 编号列表 | 编号硬指令（Analyze / Consult / Assign / Output） | 4 条 |
| 末尾调用行 | 输入注入点 | `Begin planning for the following task: {{args}}` |

**输入 / 输出 / 边界的定义方式**（这是任务书第 2 问的实质答案）：

- **输入**：统一用 `{{args}}` 占位符注入（`geminicli.md:121, 135, 151, 164, 179, 193`）。另有一个特殊输入机制——shell 注入：`geminicli.md:200-205` 的 `/git/commit.toml` 用
  > `!{git diff --staged}`
  直接把命令输出嵌进 prompt（该文档写作 ```` ```diff !{git diff --staged} ``` ````）。此外 `dev:analyze` 接受“文件或目录路径”作为输入（`geminicli.md:50`）。
- **输出契约**：只有两处被显式约束，其余靠自然语言。
  - `plan:breakdown`：`Your final output MUST be a markdown-formatted checklist.`（`geminicli.md:119`）
  - `dev:analyze`：`Provide a concise summary of your findings.`（`geminicli.md:133`）
  - `dev:refactor`：`Clearly state *what* you changed and *why* the new version is better.`（`geminicli.md:162`）
- **边界（不能做什么）**：**这是全仓库最有价值的一类文本，但只覆盖了 4 个角色中的 3 条禁令**：

  | 角色 | 原文禁令 | 位置 |
  |---|---|---|
  | Refactoring Engineer | `**No New Features**: You are strictly forbidden from adding new features.` 且 `without changing its public API` | `geminicli.md:158-161` |
  | QA Engineer | `**Real API Testing**: Mocks are forbidden.` | `geminicli.md:175` |
  | Technical Writer | `**Code-First Philosophy**: Point to code using semantic search patterns; do not duplicate it.` | `geminicli.md:190` |
  | Feature Developer | 强制项（非禁令）：`**Testing is Required**: If you modify logic, you MUST also update or create corresponding tests.` 与 `**Adhere to Architecture**: Strictly follow project principles and ADRs.` | `geminicli.md:146-148` |

- **关键遗漏**：**没有任何一条“不得自我批准 / 不得自评通过”的边界声明**。审查独立性完全依赖“换一个模型来审”（见 §5），而非依赖写进角色定义的禁令。

### 2.4 定义文件的“真相源”与“副本”问题

`geminicli.md:208-214` 的 `/workflow/sync.toml` 揭示了一个真实存在的运维问题：命令定义（`.toml`）与规则定义（`.mdc`）是**两套物理文件里的重复内容**，因此需要一个专门的 Workflow Maintainer 角色来做 diff：

> ```toml
> description = "(Workflow Maintainer) Reviews all .cursor/rules and suggests updates to these commands."
> prompt = '''
> Act as the Workflow Maintainer. Read all files in `/.cursor/rules/agents/` and `/.cursor/rules/core/`. Compare their contents to the prompts defined in the `.toml` files within `/.gemini/commands/`. Suggest changes to the `.toml` files to ensure they remain in sync with the ground-truth rules.
> '''
> ```

并且明确了**优先级**：`.cursor/rules/` 是 ground truth，`.toml` 是跟随者。这一点还得到 `kiro.md:1334-1338` 的冲突裁决顺序确认：

> ```
> ### Priority Hierarchy (When conflicts occur):
> 1. .cursor/rules/ ALWAYS wins (ground truth)
> 2. agents.md navigation ALWAYS preserved
> 3. PROJECT_BACKLOG.md task assignments respected
> 4. Kiro enhancements adapt to changes, never override
> ```

---

## 3. 工作流 / 编排

### 3.1 编排模型：**线性流水线 + 一条条件回退边**（不是状态机，也不是依赖图）

`readme.md:79-109` 给出主流程（Mermaid sequenceDiagram，原文）：

> ```
>     User->>SystemArchitect: "New Feature Request"
>     SystemArchitect-->>User: "Strategic Plan Created"
>     User->>FeatureDeveloper: "Implement According to Plan"
>     FeatureDeveloper->>FeatureDeveloper: "Write Code & Tests"
>     FeatureDeveloper->>SecurityReviewer: "Quality & Security Review"
>     activate SecurityReviewer
>     alt Review Passes
>         SecurityReviewer-->>FeatureDeveloper: "Approved"
>     else Critical Issues Found
>         SecurityReviewer-->>FeatureDeveloper: "Fix Required"
>         FeatureDeveloper->>FeatureDeveloper: "Address Issues"
>         FeatureDeveloper->>SecurityReviewer: "Re-submit for Review"
>         SecurityReviewer-->>FeatureDeveloper: "Final Approval"
>     end
>     deactivate SecurityReviewer
>     FeatureDeveloper->>DocsWriter: "Update Documentation"
>     DocsWriter-->>User: "Feature Complete"
> ```

可判定为：
- **顺序阶段**：Plan → Implement(+Test) → Review → Docs → Done
- **一条条件回退边**：`Critical Issues Found` → `Fix Required` → `Address Issues` → `Re-submit for Review`（**这就是 rework loop，只有一层，无上限、无计数、无超时**）
- **人工在两个位置介入**：发起请求、以及作为 Plan 与 Implement 之间的派发者（`User->>FeatureDeveloper: "Implement According to Plan"`）

### 3.2 门禁与回退的显式定义

`readme.md:135-146` 是本仓库对“门禁 + 回退”最清晰的一处定义（Mermaid flowchart，原文）：

> ```
>     A[Code Complete] --> B{Security Critical?}
>     B -->|Yes| C[🔒 Security Review Required]
>     B -->|No| D[📋 Standard Testing]
>     C --> E[🧪 Real API Testing]
>     D --> E
>     E --> F{All Gates Pass?}
>     F -->|No| G[🔄 Return for Fixes]
>     F -->|Yes| H[✅ Production Ready]
>     G --> A
> ```

要点：
- **条件门禁**：`{Security Critical?}` 是唯一的分支判定，安全审查**按风险分级触发**，不是全量强制
- **无条件门禁**：`🧪 Real API Testing` 对两条分支都必经
- **回退**：`G[🔄 Return for Fixes] --> A` 回到 `Code Complete`，即**回到实现阶段重新走整条门禁链**
- 没有“豁免（waiver）”路径，没有“技术债记账后放行”路径

`wf-testing.md` 提供了**工业化版本的门禁定义**，比 readme 的示意图更可操作：

- 门禁 1 —— **pre-merge**（`wf-testing.md:217-219`）：`CI‑Lite green (all steps pass).`
- 门禁 2 —— **pre-release**（`wf-testing.md:221-226`）：本地干净环境跑通 integration 套件 + 安全校验通过 + `tests/regression/` 无未关闭的 critical 回归
- 门禁 3 —— **文档门禁**（`wf-testing.md:106`）：`Documentation validation — semantic anchors enforced.`
- 门禁 4 —— **配置门禁**（`wf-testing.md:104-105`）：Supabase Edge Function 必须列出 `verify_jwt = false`，否则出现 “Invalid JWT”
- **非阻塞旁路**（重要反例，`wf-testing.md:112-115`）：

  > ```
  > **Non-blocking Architecture Audit** (runs after fast checks)
  > - Deep architectural scan using `scripts/health-checks/run-architecture-audit.js`
  > - Uploads `HEALTH_REPORT.md` as artifact for review
  > - Does not block merges; informational only
  > ```

  即：**架构漂移审计被刻意设计成不阻塞合并**，产出报告作为 artifact 供人看。

### 3.3 阶段命名

本仓库的阶段命名**不是固定状态 id，而是“阶段序号 + agent + 活动”**，且在两处示例中各自命名：

- `process.md:44-119`（文档改造任务）：`Phase 1: Strategic Analysis & Context Gathering` → `Phase 2: Quality Gate Analysis` → `Phase 3: Document Transformation`
- `process.md:336-438`（`/user-profile` 实现任务，多 agent）：`Phase 1: Gemini CLI - Pattern Discovery` → `Phase 2: Qwen Code - Security Analysis` → `Phase 3: System Architect - Integration & Orchestration`

**唯一出现的可机读任务 ID 方案**在 `kiro.md:1122-1160`（`tasks.md` 模板），形如 `MULT-001`，子任务用 `1.1 / 2.1 / 3.1 / 4.1` 编号，并按**执行角色**分组：

> ```
> ### Phase 1: Foundation (System Architect)
> - [ ] 1.1 Create database schema for battle tables
>   - **Design Reference**: Section 3.2 - Data Models
>   - **Requirements Trace**: REQ-003 - Battle state persistence
>   - **Quality Gate**: Architecture review required
> ...
> ### Phase 2: Core Implementation (Feature Developer)
> ### Phase 3: Integration & Testing (Quality Assurance)
> ### Phase 4: Documentation (Documentation Writer)
> ```

`wf-testing.md:263-277` 用的是另一种前缀：`SYS-002`、`SYS-003`。**两种 ID 方案（`MULT-nnn` / `SYS-nnn`）互不关联，无统一命名规范**。

### 3.4 交接产物（artifact）命名与存放路径

**核心机制：交接靠文件，不靠对话。** 汇总（区分【实际存在】与【被描述的路径】）：

| 产物 | 路径 | 作用 | 证据 | 状态 |
|---|---|---|---|---|
| **任务总线** | `PROJECT_BACKLOG.md` | 唯一任务队列；每个任务携带 agent 指派 + 门禁 + 上下文链接 | `kiro.md:51, 269, 302-306, 1176` | 被描述（本仓库无此文件） |
| **单一入口** | `agents.md` | 导航层次，唯一入口 | `kiro.md:12, 49, 1664` | 被描述 |
| 长期记忆 | `ARCHITECTURE.md` | 稳定架构原则 | `process.md:127` | 被描述 |
| 决策记录 | `ADR/`（`ADR-003`/`ADR-005`/`ADR-021`） | 架构决策 | `geminicli.md:172, 178`；`kiro.md:395` | 被描述 |
| 测试规范 | `TESTING.md` + `docs/testing/{README,ci-cd-guide,local-development-guide,troubleshooting-cookbook,browser-testing-guide}.md` | 拆分后的测试文档枢纽 | `wf-testing.md:272-277, 336-342` | 被描述 |
| **审计报告** | `HEALTH_REPORT.md` | 架构漂移报告，CI artifact | `wf-testing.md:114, 266` | 被描述 |
| CI 定义 | `.github/workflows/ci-lite.yml` | 阻塞式门禁流水线 | `wf-testing.md:95` | 被描述 |
| 审计脚本 | `scripts/health-checks/run-architecture-audit.js` | 非阻塞深扫 | `wf-testing.md:113, 263` | 被描述 |
| Gemini 命令 | `.gemini/commands/{plan,dev,test,docs,git,workflow}/*.toml` | agent 定义本体 | `geminicli.md:92-214` | **仓库内有完整原文**（但无实际文件） |
| Cursor 规则 | `.cursor/rules/{agents,core,protocols}/*.mdc` | ground truth 规则 | `backlog.md:30-32`；`kiro.md:1360-1362` | 被描述（**内容不可审计**） |
| Kiro 规格 | `.kiro/specs/<feature>/{requirements,design,tasks,context}.md` | 规格驱动产物 | `kiro.md:142-148, 1172-1176` | 被描述（蓝图） |
| Kiro 链接 | `.kiro/links/spec-backlog-links.json` | 双向追溯 | `kiro.md:644-663` | 被描述（蓝图） |
| Kiro 执行上下文 | `.kiro/context/execution-context.json` | 跨阶段上下文 | `kiro.md:666-680` | 被描述（蓝图） |

**追溯性设计（值得直接借鉴）**：`kiro.md:1128-1160` 要求**每个任务同时携带三样东西**：`Design Reference`（设计文档小节号）+ `Requirements Trace`（`REQ-00x`）+ `Quality Gate`（该任务必须过哪道门）。这是把“需求→设计→任务→门禁”串成可检查链的最轻量做法。

### 3.5 星形拓扑：编排者即综合者

`process.md:287-334` 的 Mermaid 显示拓扑是**星形**，不是流水线：

> ```
>     SA->>GC: "Analyze existing API patterns for user endpoints"
>     GC->>SA: "Found 3 patterns: RLS auth, Zod validation, error handling"
>     SA->>QC: "Review proposed endpoint design for security"
>     QC->>SA: "Security recommendations"
>     SA->>Code: Create comprehensive example
>     SA->>GC: "Validate implementation follows discovered patterns"
>     SA->>QC: "Final security review of implementation"
> ```

System Architect 是唯一的中枢：专家之间**从不直接对话**，全部经由 SA 转述。`process.md:414` 明说：`**My Role**: Synthesize insights from both specialists into a cohesive, production-ready implementation.`

**这是“避免整段对话在 agent 之间传递”的结构性答案**：拓扑上就不存在 A→B 的直连，只存在 专家→中枢 的**结论回传**。

---

## 4. 上下文与记忆管理

### 4.1 命名模型：“双层记忆（Two-Tier Memory）”

`readme.md:61-64` 是正式定义：

> ```
> ### **2. Formal Cognitive Architecture**
> **Long-Term Memory**: Stable architectural principles in documentation  
> **Short-Term Memory**: Live codebase accessed through structured analysis  
> **Result**: AI agents reason like senior engineers, validating every change against established principles
> ```

`process.md:121-151` 给出了可操作的落地形式：

- **长期记忆来源表**（`process.md:125-131`，含“抽取了什么 / 如何影响决策”两列）：

  > ```
  > | Document | Information Extracted | How It Influenced Decisions |
  > | `ARCHITECTURE.md` | Core principles, agent memory model | Ensured MVP demonstrated two-tier memory |
  > | `agents.md` | Agent roles and coordination patterns | Validated agent selection for backlog tasks |
  > | `docs/agentic-workflow/` | Coordination protocols, quality gates | Added quality reviewer to MVP scope |
  > | `workflow/readme.md` | Public messaging patterns | Applied competitive positioning language |
  > ```

- **短期记忆 = 当前真实状态**：`process.md:132-150` 用 gap analysis 图描述“当前 backlog 现状 → 差距 → 建议”。

- **使用规程**（`process.md:251-255`）：

  > ```
  > ### **Two-Tier Memory Best Practices**
  > - Always start with long-term memory consultation for stable principles
  > - Use short-term memory for current state analysis
  > - Synthesize both for grounded recommendations
  > - Document the memory sources used for future reference
  > ```

  最后一条“**记录本次用到了哪些记忆来源**”是一个便宜且高效的审计线索，值得抄。

### 4.2 是否存在 memory / lessons / decisions 持久化文件？

**逐项核查结论：**

| 期待的文件类型 | 本仓库是否存在 | 实际对应物 |
|---|---|---|
| `memory/` 目录 | ❌ 不存在 | 无 |
| `lessons.md` / 经验教训 | ❌ **不存在，且全仓库无任何等价描述** | **这是最明显的空白** |
| `decisions/` / ADR | ❌ 目录不存在，但 **ADR 机制被大量引用** | `ADR/`（`geminicli.md:172, 178`；`kiro.md:395` 提到 `ADR-005`；`vs-cursor.md:17-19` 称 ADR 被编码为门禁） |
| 上下文持久化 | ❌ 不存在 | `.kiro/context/execution-context.json`（`kiro.md:666-680`，蓝图） |
| 逐步指令/引导规则 | ❌ 不存在 | `.kiro/steering/{always-apply,supabase-patterns,security-focus}.md`（`kiro.md:1178-1180`，蓝图） |

**最接近“lessons 持久化”的机制**是 `wf-testing.md:272-277` 里被强制 schema 化的故障手册：

> ```
> - **SYS‑003: TESTING.md Restructure for AI Agent Efficiency** ✅ **Implemented**
>   - **What (concise)**: Split `TESTING.md` into a hub + 4 focused guides
>     (`ci-cd-guide`, `local-development-guide`, `troubleshooting-cookbook`,
>     `browser-testing-guide`); enforce cookbook schema (Error, Symptom, Root
>     Cause, Solution, Verification); add governance/validation; migrate via safe
>     2‑PR rollout.
>   - **Why**: Improve findability and reduce cognitive load for AI agents;
>     enforce code-first semantic anchors; ensure maintainable, query‑friendly
>     docs.
> ```

即：**“教训”的载体是 troubleshooting cookbook，并且有强制的 5 字段 schema（Error / Symptom / Root Cause / Solution / Verification）**，还专门说明动机是“降低 AI agent 的认知负荷”。这是全仓库最可直接复制的一条记忆管理设计。

另一个等价物是 `wf-testing.md:251-259` 的 “Continuous Improvement Backlog”，其中明确 `Expand tests/regression/ continuously as defects are discovered and fixed.` —— **回归测试充当“缺陷记忆”**。

### 4.3 如何避免把整段对话传给下一个 agent？

可提炼出 **5 个具体手法**（全部有原文依据）：

1. **拓扑隔离**：星形拓扑，专家之间无直连（`process.md:287-334`，见 §3.5）。
2. **查询式取数而非转录**：给专家的输入是一条**限定范围的查询**，而不是历史对话。原文（`process.md:338`）：
   > `**System Architect Query**: *"@supabase/functions/ What patterns should I follow for implementing a user-profile endpoint with authentication and validation?"*`
3. **强制短结论回传**：专家回传的是**结论级摘要**，不是过程。原文（`process.md:303`、`process.md:314`）：
   > `GC->>SA: "Found 3 patterns: RLS auth, Zod validation, error handling"`
   > `QC->>SA: "Recommend: Rate limiting, sanitization, audit logging"`
4. **文件即状态**：任务状态放在 `PROJECT_BACKLOG.md` 的任务行里（`kiro.md:302-306`），下一个 agent 读文件即可接续，无需历史。
5. **Kiro 的“上下文注入”方案（蓝图，未实现）**：`kiro.md:540-552` 的 `getContextDuringExecution(taskId)` 按 taskId 反查 `requirements/design/taskContext/projectContext`，即**按需拉取而非默认全量携带**。`kiro.md:26` 宣称 `**Context Preservation**: Zero context loss across agent handoffs`。

### 4.4 token / 成本控制

**结论：全仓库没有任何显式的 token 预算、算力配额、成本核算或用量遥测机制。** 穷举检索 `token` 的结果**全部是鉴权意义上的 Bearer token**（`wf-testing.md:79`、`process.md:457, 459, 461`），与 LLM token 无关；检索 `context window`、预算类词汇均为零命中。

存在的**隐式/结构性成本控制**（共 6 条，均有原文）：

1. **范围限定查询**：`@supabase/functions/` 这种路径前缀限定（`process.md:338`、`geminicli.md:50`）。
2. **要求“简洁”输出**：`Provide a concise summary of your findings.`（`geminicli.md:133`）。
3. **文档不复制代码**：`Point to code using semantic search patterns; do not duplicate it.`（`geminicli.md:190`）——既防文档腐烂，也压缩了喂给模型的文档体积。
4. **单 agent 优先的决策纪律**：`process.md:183-186` 明确拒绝了“多 agent”方案：
   > ```
   > **Alternative Approaches Considered**:
   > - **Multiple Agents**: Would have added handoff complexity for minimal benefit
   > - **Feature Developer**: Lacks strategic planning and public communication expertise
   > - **Documentation Writer**: Could handle messaging but not strategic architecture decisions
   > ```
   这是**成本控制即编排纪律**的体现：能用 1 个就不上 3 个。
5. **门禁按风险分级**：`{Security Critical?}` 才触发安全审查（`readme.md:137-139`），常规改动走“Standard Testing”。
6. **快慢分层与时间预算**：Tier 1 `finishes in ~60 seconds`（`wf-testing.md:13-14`），深扫被设为 non-blocking（`wf-testing.md:112-115`）；并给出量化目标 `CI‑Lite time to green (target: ≤60s median)`（`wf-testing.md:230`）。

---

## 5. 质量门禁：审查如何独立于实现者

### 5.1 独立性的真实机制：**换模型**，而不是换 prompt

本方案之所以能谈“独立审查”，根本原因是**审查者与实现者是不同的厂商/模型**：

- 实现者：**Claude**（`readme.md:58`，`Feature Developer (Claude)`）
- 安全审查者：**Qwen Code**（`readme.md:56`：`**Security Reviewer (Qwen Code)**: Security analysis and architecture validation`）
- 上下文/模式审查者：**Gemini CLI**（`readme.md:57`）
- readme 的竞品对比表把这一点当作核心卖点（`readme.md:41`）：
  > `| **Security** | Ad-hoc security considerations | Generalist security knowledge | Dedicated security specialist (Qwen Code) for all critical paths |`

并且明确了“为什么必须是别人审”——`process.md:378`（以 Claude 第一人称写的自述）：

> `**Value for Claude**: Security expertise that I lack as a generalist. Qwen catches vulnerabilities I would miss and provides specific remediation strategies.`

### 5.2 “不允许自我批准”的显式机制：**有，但只有一处，且形式是竞品对比表**

`process.md:440-449`（原文）：

> ```
> | Capability | Single Claude | Multi-Agent (Claude + Gemini + Qwen) |
> | **Quality Validation** | Self-review only | Independent expert validation |
> ```

同一表里还有两行构成同一论点的旁证（`process.md:445, 449`）：

> `| **Security Analysis** | Basic security awareness | Specialized vulnerability assessment |`
>
> `| **Result Quality** | Good but potentially inconsistent | Excellent and systematically validated |`

以及 `readme.md:40` 与 `readme.md:162` 对单 agent 的批评：

> `| **Code Quality** | Inconsistent patterns, no oversight | Good but no systematic validation | Mandatory quality gates with specialized reviewers |`
>
> `**❌ No Quality Control**: No systematic validation of AI-generated code`

**定性判断**：本仓库**没有把“实现者不得批准自己的工作”写成一条可执行的规则**（在 §2.3 穷举的 9 个 agent 定义中没有任何一条这样的禁令），它只在**营销对比表**里把“self-review only”标记为单 agent 的缺点。换言之：**机制是隐含在“用不同模型”这个结构性事实里的，不是抽查得到的策略性约束。**

### 5.3 审查流程的独立性（正面证据）

`readme.md:96-102` 的 alt 分支明确体现“作者 ≠ 批准者”：

> ```
>     alt Review Passes
>         SecurityReviewer-->>FeatureDeveloper: "Approved"
>     else Critical Issues Found
>         SecurityReviewer-->>FeatureDeveloper: "Fix Required"
>         FeatureDeveloper->>FeatureDeveloper: "Address Issues"
>         FeatureDeveloper->>SecurityReviewer: "Re-submit for Review"
>         SecurityReviewer-->>FeatureDeveloper: "Final Approval"
> ```

- 批准动作（`Approved` / `Final Approval`）只由 SecurityReviewer 发出
- 修复动作（`Address Issues`）只由 FeatureDeveloper 执行，修复后**必须重交审查**，不能自宣通过

### 5.4 但存在三处削弱独立性的反例（必须报告）

1. **编排者“植入缺陷”再让审查者抓**：`process.md:420` 原文
   > `4. **Quality Gates**: Design deliberate issues for quality reviewer to catch`
   
   以及 `process.md:429-431`：
   > ```
   >     D --> F[Deliberate Security Issue]
   >     D --> G[Quality Gate Demo]
   > ```
   
   这是为了做 demo 而人为制造问题，说明**该示例中的“门禁成功”是设计的产物**，不能作为门禁有效性的独立证据。`backlog.md:46` 也把这个套路列进了 MVP 计划（`including starter code, expected output, and deliberate 'bugs' for quality gate demo`）。

2. **CI 失败后的“自我分诊”**：`wf-testing.md:207-211`
   > ```
   > ### Escalation and responsibilities
   > - The committer (or owning agent) triages and fixes.
   > - Head of QA monitors recurring failures, flakiness, and documentation gaps.
   > - System Architect updates quality gates and CI checks as needed.
   > ```
   
   即修复者就是分诊者；Head of QA 只承担**监控**职责，不承担逐次复核。

3. **分支保护只是“建议”**：`wf-testing.md:135`
   > `- CI‑Lite must be green for merges (branch protection recommended).`
   
   本仓库内**没有** `CODEOWNERS`、没有 `branch protection` 配置、没有 PR 模板、没有必需的 review 规则文件（`glob` 全树已确认只有 8 个 `.md`）。

### 5.5 独立验证的“技术性”手段（可借鉴）

1. **由不同模型执行审计脚本**：`wf-testing.md:263-270`
   > ```
   > - **SYS‑002: Automated Project Health Check & Quality Gate System** ✅ **Implemented**
   >   - **What (concise)**: Two‑layer health system: fast CI checks + a single
   >     deep‑scan script (`scripts/health-checks/run-architecture-audit.js`) using
   >     Gemini CLI; non‑blocking "Architecture Audit" job in CI‑Lite uploads
   >     `HEALTH_REPORT.md`.
   > ```
   审计者是 Gemini CLI，实现者是 Claude → **审计方与实现方是不同的模型（异构审查）**。

2. **“禁止 mock”作为反捷径门禁**（本仓库最强硬的一条质量规则，出现 5 次以上）：
   - `geminicli.md:175`：`**Real API Testing**: Mocks are forbidden.`
   - `readme.md:67`：`- **Real API Testing**: No mocking allowed—ensures production readiness`
   - `readme.md:149`：`- **Real API Testing**: No mocking—if it doesn't work with real APIs, it doesn't ship`
   - `wf-testing.md:19-20`：`**Real API Testing**: We never mock AI model outputs.`
3. **环境隔离作为测试前置条件**：`wf-testing.md:85-89` 与 `wf-testing.md:243-245`
   > ```
   > Environment isolation
   > - Tests force local base URLs like `http://127.0.0.1:45321` to avoid production.
   > - Secrets are read from `.env`; tests skip or fail fast if required vars are missing.
   > ```
   > ```
   > - Environment isolation: tests must force local URLs and never hit production endpoints.
   > ```
4. **三层测试分层 + 量化目标**：`wf-testing.md:12-18`（Tier1 CI‑Lite ~60s 阻塞 / Tier2 本地真实服务手动 / Tier3 Browserbase 按需）与 `wf-testing.md:228-234`（`CI‑Lite time to green (target: ≤60s median)`、`pass rate ... (target: ≥95%)`、`Flakiness ... (target: ≤2%)`、`MTTR (target: ≤1 hour)`）。
5. **文档门禁可机检**：`wf-testing.md:106` `Documentation validation — semantic anchors enforced.`；配合 `vs-cursor.md:193-194` `**Documentation Governance (Semantic Landmarks)**: Keeps docs authoritative and durable as code evolves.`

---

## 6. 人机协作：需要人工确认/审批的环节

穷举后的**明确人工介入点共 7 处**：

| # | 环节 | 原文证据 | 人工动作性质 |
|---|---|---|---|
| 1 | **派发执行**（计划完成 → 交给开发者） | `readme.md:90` `User->>FeatureDeveloper: "Implement According to Plan"` | **人工是 Plan 与 Implement 之间的派发者**（计划不会自动执行） |
| 2 | **计划/建议验收** | `process.md:60` `SA->>User: Strategic recommendations with specific enhancements`；`process.md:83-86` `K--> L[Approve Enhanced Plan]` / `K-->|No| M[Simplify Recommendations]` | 审批 + 打回 |
| 3 | **成果验收** | `process.md:110` `User->>Doc: Accept changes` | 显式 accept |
| 4 | **路由决策（规格 vs 待办）** | `kiro.md:110` `Kiro suggests: "This looks complex - would you like me to create a systematic spec for this, or handle it as a standard backlog task?"` | 建议式询问，人选择 |
| 5 | **反向同步需人工批准** | `kiro.md:1462-1467` `### **Step 2: Human Review**` / `Kiro presents suggestion to user:` / `User approves: "Yes, add to .cursor/rules/protocols/websocket-patterns.mdc"`；`kiro.md:1469-1471` `User creates: .cursor/rules/protocols/websocket-patterns.mdc` | **规则（ground truth）的修改权归人**，AI 只能提议 |
| 6 | **需求采集是一场实时访谈** | `kiro.md:199-204` `Kiro: "I'll structure this. What about turn timing?" / User: "30 seconds per turn, with timeout handling" / Kiro: "What happens if someone disconnects?" / User: "Game should pause and allow reconnection"` | 交互式确认 |
| 7 | **发布 go/no-go** | `wf-testing.md:35-40` `**Head of QA** ... Owns regression suite scope, flakiness reviews, and release go/no‑go criteria.`；`wf-testing.md:221` `Pre‑release gate (for milestones)` | 人工发布决策 |

**人机协作的空白（值得指出）**：
- **合并（merge）没有人工审批门禁**，只有 CI 绿灯 + “recommended” 的分支保护（`wf-testing.md:135`）。即：自动化门禁 = 放行条件，人工不是必需的。
- **部署（deploy）环节完全没有描述**任何人工确认。
- **没有任何“危险操作需二次确认”的清单**（如删除数据、改 schema、动密钥）。

---

## 7. 可直接借鉴清单（含 Cursor 专属 / IDE 无关标注）

### 7.1 Cursor 专属（移植需替换为等价机制）

| 机制 | 证据 | 说明 |
|---|---|---|
| `.cursor/rules/{agents,core,protocols}/*.mdc` 三分类目录 + `alwaysApply: true` frontmatter | `backlog.md:30-32`；`kiro.md:1360-1362, 1658` | Cursor Rules 格式；**本仓库未展示内容**，只能借鉴“三分类”这一结构约定 |
| `@path/` 代码库范围引用（如 `@supabase/functions/`） | `process.md:338`；`geminicli.md:50` | Cursor/Gemini 的 @ 提及语义 |
| 依赖 IDE 自身能力：embeddings/RAG、shadow workspace、fast-apply 多文件 diff | `vs-cursor.md:58-65` | 属 Cursor 内建能力，非本工作流提供 |
| `vs-cursor.md` 整套“工具自述式”文档体裁 | `vs-cursor.md:1-231` | 文案技巧，非机制 |

### 7.2 Gemini CLI 专属

| 机制 | 证据 | 说明 |
|---|---|---|
| `.gemini/commands/<ns>/<verb>.toml`，字段仅 `description` + `prompt` | `geminicli.md:92-107, 109-214` | Gemini CLI 自定义命令契约；命名空间目录 `plan/dev/test/docs/git/workflow` |
| `{{args}}` 参数占位符 | `geminicli.md:121, 135, 151, 164, 179, 193` | 输入注入点 |
| `!{git diff --staged}` shell 输出内联 | `geminicli.md:200-205` | 把命令输出直接注入 prompt |
| 文档自称依据 `https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/commands.md` | `geminicli.md:90` | 外部依赖，跨工具不可移植 |

### 7.3 IDE 无关（**建议优先引入我们的框架**）

按价值/成本比从高到低：

| # | 可借鉴机制 | 证据 | 为什么值得抄 |
|---|---|---|---|
| 1 | **任务行三件套：`Design Reference` + `Requirements Trace (REQ-00x)` + `Quality Gate`** | `kiro.md:1128-1160` | 用最轻的格式把需求→设计→任务→门禁串成可审计链；每条任务自带“该过哪道门” |
| 2 | **故障手册强制 5 字段 schema：Error / Symptom / Root Cause / Solution / Verification** | `wf-testing.md:272-277` | 把“教训”变成可检索、可校验、AI 友好的结构化记忆；直接可作为我们 `lessons` 文件的 schema |
| 3 | **独立审查 = 换模型（异厂商）**，而非换 prompt | `readme.md:56-58, 41`；`process.md:378, 447` | 结构性消除自评偏差；对任何多 agent 运行时都成立 |
| 4 | **条件安全门禁（`Security Critical?` 分支）+ 无条件真实集成测试门禁** | `readme.md:135-146` | 风险分级避免全量审查拖慢吞吐；真实测试门禁防止 mock 走捷径 |
| 5 | **回退边：`Return for Fixes → Code Complete` 与 `Re-submit for Review`** | `readme.md:98-102, 135-146` | rework loop 的最小正确形态（回到起点重走门禁，而非局部打补丁） |
| 6 | **非阻塞咨询式审计（不阻塞合并，产出 `HEALTH_REPORT.md` artifact）** | `wf-testing.md:112-115, 263-270` | 早期架构漂移预警 + 零吞吐代价；比“什么都阻塞”更可持续 |
| 7 | **文件即交接（`PROJECT_BACKLOG.md` 作为唯一任务总线，任务行携带 agent 指派 + 门禁 + 上下文链接）** | `kiro.md:51, 269, 302-306` | 从机制上避免传递对话历史 |
| 8 | **星形拓扑 + 结论级回传（专家之间不直连，查询带路径范围，回传“发现 N 条模式”级摘要）** | `process.md:287-334, 303, 314, 338, 414` | 上下文与成本控制的真正来源 |
| 9 | **CI 三层分级 + 量化指标**（Tier1 阻塞 ≈60s / Tier2 本地真实服务 / Tier3 按需）与 `≥95% pass`、`≤2% flaky`、`MTTR ≤1h` | `wf-testing.md:12-18, 228-234` | 门禁必须带预算，否则必然被绕过 |
| 10 | **“单 agent 优先”的编排纪律 + 记录被否决方案** | `process.md:183-186` | 多 agent 有握手成本，默认少用；把“为什么不上多 agent”写进记录 |
| 11 | **双层记忆 + 每次任务登记“用了哪些记忆来源”** | `readme.md:61-64`；`process.md:125-131, 251-255` | 长期记忆=稳定原则文档，短期记忆=实时代码扫描；来源可追溯 |
| 12 | **自维护同步命令（规则文件 vs 命令提示词的 diff 巡检）** | `geminicli.md:208-214` | 防止 agent 定义与规则指针漂移；任何“定义在多处”的框架都需要 |
| 13 | **真相源冲突裁决顺序（规则 > 导航 > 任务 > 增强）** | `kiro.md:1334-1338` | 多来源配置共存时的确定性仲裁 |
| 14 | **规则（ground truth）的修改权归人，AI 只能提议** | `kiro.md:1462-1471` | 人机共享的关键防线：AI 不得自行改写约束 |
| 15 | **文档“代码优先 + 语义锚点”，且锚点由 CI 校验** | `geminicli.md:190`；`wf-testing.md:106`；`vs-cursor.md:193-194` | 靠机器检查阻止文档腐烂，而不是靠人自觉 |
| 16 | **回归测试充当缺陷记忆（每个缺陷修复必带回归用例）** | `wf-testing.md:61-62`：`Immediately after fixing a defect (add a regression test).` | 低成本、可执行的“经验固化” |
| 17 | **门禁的角色定义含“触发条件”列（When They're Critical）** | `readme.md:113-119` | 编排时可直接按触发条件选角色，避免人肉判断 |
| 18 | **失败分诊协议：程序化拉取 CI 日志（`gh` CLI）→ 定位失败步骤名 → 本地复现修复 → 重跑** | `wf-testing.md:191-197, 325-332` | 禁止复制粘贴日志，降低 agent 的上下文噪声 |

### 7.4 明确**不建议**照抄的部分

| 反模式 | 证据 | 理由 |
|---|---|---|
| `.kiro/` 与 `.cursor/` 双系统双向同步（watchers/mappings/sync-engine） | `kiro.md:141-181, 1218-1405` | 作者自己在 `kiro.md:1650-1669` 判定为架构违规 + 决策瘫痪风险；且全部为未实现的伪代码蓝图 |
| 用“植入缺陷再抓出”来演示门禁有效性 | `process.md:420, 429-431`；`backlog.md:46` | 演示效果好，但会污染“门禁有效”的证据链 |
| 用 1700 行文档承载一个被否决的方案 | `kiro.md`（1701 行，占全仓 50%） | 信息密度低，含大量 `✅ RESOLVED` 之类与事实冲突的自我宣称 |
| 角色命名与文件名不统一（Security/Quality Reviewer 混用） | `readme.md:116` vs `backlog.md:30, 73` | 无单一 roster，多 agent 编排的常见腐化点 |
| 全仓库无 LICENSE / 无代码 / 无 CI，但 README 高度宣称“production-grade / battle-tested” | `readme.md:4, 8`；全树只有 8 个 `.md` | 引用其结论时须降权：**该仓库的“证据”是自述，不是可复现产物** |

---

## 8. 审计结论摘要

**这个仓库的实际价值不在于“它是什么”，而在于“它讲了什么”。**

- 作为**模板仓库**：**未交付**。README 宣称的 `production-ready`、`battle-tested` 系统、agent personas、quality gate examples，在本仓库内**均不存在**；`backlog.md` 本身承认这是 MVP 目标（`backlog.md:11-49`），`readme.md:191` 承认模板“Next Up”。
- 作为**设计文档**：**有真实价值**。双层记忆、门禁分级与回退边、需求追溯三件套、故障手册 schema、非阻塞审计、CI 三层分级等机制描述具体到可直接落地（见 §7.3 的 18 条）。
- 作为**一线证据**：唯一的一手材料是 `geminicli.md:109-214` 的 9 段命令 TOML 与 `wf-testing.md` 整篇 QA 规范（后者是真实项目的内部规范外泄，含具体命令、端口、环境变量名、CI 步骤与量化指标，可用性最高）。
- **引用风险提示**：任何来自 `kiro.md` 的目录树/JSON/类定义、任何以 `.mdc`/`.cursor/`/`PROJECT_BACKLOG.md`/`agents.md` 为路径的断言，在本仓库内**都没有对应文件可验证**，属于“被描述的实现”，引用时必须标注为设计意图而非既成事实。

---

*审计方法可复现：`glob **/*`（8 个文件）+ `Get-ChildItem -Force -Recurse`（确认无隐藏目录）+ 全文 `read`（3379 行）+ `grep` 定点取证 + `git`/GitHub API 交叉校验（上游 tree sha 与本地 HEAD 一致，`truncated: false`）。*
