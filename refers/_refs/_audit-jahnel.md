# JahnelGroup/multi-agents 深度结构审计报告

- **被审计仓库**：`H:\RainV\Rgents Team\Refer Doc\_refs\jahnel-multi-agents`
- **仓库定位**：Cursor 多 agent 流水线模板仓库（含 `.cursor-foundation/`、`.cursor-practitioner/`、`.cursor-expert/` 三个层级捆绑包）
- **VERSION**：`1.1.1`
- **审计时 HEAD**：`f237ce31b417955130cfeabd05404b1329aed367`（`ci: add VERSION and hooks to deploy-docs paths filter`，Fri Feb 27 16:34:12 2026 -0500）
- **审计方法**：全部结论来自实际读取文件与**实际执行脚本**（schema.py / check.py 的通过、拒绝、退出码均已实测），非推测。

---

## 0. 仓库总体结构

```
jahnel-multi-agents/
├── .cursor-foundation/     3 agents, 1 rule, pipeline(schema.py + README.md, 无 check.py)
├── .cursor-practitioner/   8 agents, 4 rules, 2 skills, pipeline, templates
├── .cursor-expert/        15 agents, 5 rules, 2 skills, pipeline(扩展版), templates
├── lib/                    ★ 三层共享的真实校验逻辑（pipeline_schema_common.py / pipeline_check_common.py）
├── docs/                   三层教程、练习、walkthrough（含真实产物样例）
├── sandbox/                TypeScript + Jest 示例项目
├── hooks/version.py, scripts/check-docs.sh, Makefile, test-all.sh
└── README.md, TESTING.md, CONTRIBUTING.md, VERSION, mkdocs.yml
```

**关键结构性发现（也是本仓库最重要的架构点）**：`.cursor-*/pipeline/schema.py` 与 `check.py` 都不是自包含实现，而是**薄封装**——它们把 `Path(__file__).resolve().parents[2] / "lib"` 插入 `sys.path`，再 `from pipeline_schema_common import ...`。因此：

- 三个 tier 的校验逻辑**真正共享同一份实现**（`lib/`），tier 之间只做**增量扩展**。
- 这也意味着把 `.cursor-practitioner/` 单独 `cp` 到别的项目（README 第 64–68 行推荐的做法）后，**`schema.py` 和 `check.py` 会因为找不到 `lib/` 而直接 ImportError**。这是模板分发方式与代码依赖布局之间的真实不匹配，属于采用时必须在意的坑。

---

## 1. Agent 定义的契约格式

### 1.1 全量 frontmatter 实测（`.cursor-practitioner/agents/`，8 个文件）

用正则 `^readonly:|^name:|^model:|^description:` 精确提取，实测结果如下（字段名、取值均为原文）：

| 文件 | `name` | `model` | `description`（原文首句） | `readonly` |
|---|---|---|---|---|
| `jg-planner.md` | `jg-planner` | `gemini-3.1-pro` | Coordinates the implementation pipeline. Orchestrates plan -> implement -> test -> review -> git. Use when starting work on an issue or triaging pipeline failures. | `true` |
| `jg-subplanner.md` | `jg-subplanner` | `gpt-5.1-codex-max` | Decomposes issues into structured implementation plans with ordered steps and acceptance criteria mapping. Use when breaking down a complex issue into actionable tasks. | `true` |
| `jg-worker.md` | `jg-worker` | `gpt-5.3-codex` | Implements code and tests per plan; reports completion to the planner. Use for code implementation and test writing. | **（字段缺失）** |
| `jg-tester.md` | `jg-tester` | `gemini-3-flash` | Two-phase verification gate. Runs static checks and tests, then integration/runtime checks. Use after implementation to validate before review. | **（字段缺失）** |
| `jg-reviewer.md` | `jg-reviewer` | `gemini-3.1-pro` | Quality gate before commit. Reviews diff for scope creep, overengineering, and unnecessary complexity. Use after tests pass. | `true` |
| `jg-debugger.md` | `jg-debugger` | `claude-4.6-sonnet` | Failure classifier and diagnostician. Use when the planner routes a test failure for root cause analysis before dispatching a fix. | `false`（显式） |
| `jg-git.md` | `jg-git` | `gemini-3-flash` | Handles branching, conventional commits, and PR creation. Use after reviewer passes. Does not merge. | **（字段缺失）** |
| `jg-benchmarker.md` | `jg-benchmarker` | `gemini-3-flash` | Utility agent for pulling benchmark data, evaluating cost vs performance, and recommending which models to use for which agents. Use on-demand for model assignment reviews. | `false`（显式） |

**契约字段总结（这才是真实 schema）**：

- 只有 **4 个允许出现的字段**：`name`、`model`、`description`、`readonly`。
- **没有任何文件使用 `tools`、`inputs`、`outputs`、`globs` 等字段**——工具权限完全靠正文的 `NON-GOALS` 自然语言约束，而不是机器可读的白名单。
- `readonly` 是**可选**字段，且三种状态并存：`true`（planner/subplanner/reviewer）、`false`（debugger/benchmarker）、**缺省**（worker/tester/git）。
- `description` 是唯一的触发面：统一采用 **"做什么 + Use when…"** 两段式，这句直接影响 Cursor 的 agent 自动选择。

### 1.2 正文小节结构（8 个文件横向对比）

| 小节 | planner | subplanner | worker | tester | reviewer | debugger | git | benchmarker |
|---|---|---|---|---|---|---|---|---|
| `# JG-<ROLE>` 标题 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `## ROLE` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `## PRIMARY OBJECTIVE` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `## CORE RESPONSIBILITIES` | ✅ | ✅ | ✅ | ✅（内含 3 个 `###` 子节） | ✅ | ✅ | ✅ | ✅（内含 3 个 `###` 子节） |
| `## NON-GOALS` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 其他特有节 | `PIPELINE ARTIFACTS`、`TIERED DISPATCH` | `OUTPUT SHAPE`（JSON 代码块） | `DECISION FRAMEWORK` | `ARTIFACT` | `REVIEW FORMAT` | （self-assessment 写在正文内） | `DECISION FRAMEWORK` | `PER-AGENT BENCHMARK FOCUS`、`EXECUTION STYLE`、`ANTI-PATTERNS`、`SKILLS`、`OUTPUT` |

**统一骨架**：`ROLE → PRIMARY OBJECTIVE → CORE RESPONSIBILITIES → NON-GOALS`，四节是全部 8 个 agent 的公共最小集；`NON-GOALS` 出现率 8/8，是这套设计里**最关键的契约机制**（用"不做什么"来划权限边界，替代 `tools` 白名单）。

正文规模差异极大：最小 `jg-worker.md` 36 行，最大 `jg-benchmarker.md` 93 行（因为它是支撑型 agent，额外挂了 4 个专有节）。

### 1.3 完整原文示例：`jg-worker.md`（全文，36 行）

```markdown
---
name: jg-worker
model: gpt-5.3-codex
description: Implements code and tests per plan; reports completion to the planner. Use for code implementation and test writing.
---

# JG-WORKER

## ROLE

Implements code changes for a scoped task. Receives a task (from planner or subplanner) with files to edit and acceptance criteria. Writes implementation and tests. Reports completion to the planner. Does not plan, review, or do git operations.

## PRIMARY OBJECTIVE

Satisfy the task's acceptance criteria with the simplest correct implementation. Minimize unnecessary changes. Maximize behavior coverage in tests.

## CORE RESPONSIBILITIES

- Edit only files specified in the task scope.
- Read the implementation plan from `.pipeline/<issue-id>/plan.json` when the planner provides the artifact path. Follow the plan precisely.
- On completion, write `.pipeline/<issue-id>/worker-result.json` with status, files_changed, blockers, summary. Schema: **pipeline/README.md** in this bundle.
- When a debugger diagnosis is attached (classification: `fix_target`), follow the diagnosis fix instructions directly.
- Write tests that verify behavior, not just absence of exceptions. Follow project coding conventions.
- Report blockers immediately; do not guess past them.
- Pre-flight: run project lint and typecheck (e.g. `make lint && make typecheck`). Fix mechanical errors locally. Run tests; if failures are only in changed files and obvious, attempt up to 2 self-fixes before reporting to planner.

## NON-GOALS

- Does not select issues or decompose them into plans
- Does not make git commits or open PRs
- Does not run the full verification pipeline or review code
- Does not expand scope beyond the assigned task

## DECISION FRAMEWORK

Correctness > simplicity > speed. When in doubt, do less. If a simpler approach satisfies acceptance criteria, use it. If uncertain whether something is in scope, it is not.
```

### 1.4 完整原文示例：`jg-reviewer.md`（全文，46 行）

```markdown
---
name: jg-reviewer
model: gemini-3.1-pro
description: Quality gate before commit. Reviews diff for scope creep, overengineering, and unnecessary complexity. Use after tests pass.
readonly: true
---

# JG-REVIEWER

## ROLE

Qualitative review gate. Runs after tester reports PASS. Ensures the diff matches issue scope and is at the right abstraction level. Catches overengineering, scope creep, and unnecessary complexity that linters miss.

## PRIMARY OBJECTIVE

Ensure every line in the diff is justified by an acceptance criterion and implemented at the simplest appropriate level. Flag unjustified or overcomplicated code.

## CORE RESPONSIBILITIES

- Verify the changed file list matches the issue scope. If files are not traceable to acceptance criteria, flag as Blocker.
- Run project quality checks on changed files (e.g. sloppylint or project linter at appropriate severity).
- Inspect the diff for: unnecessary abstractions, scope creep, dead code, style drift, loose dicts where structured types belong. Compare each change to the issue's acceptance criteria.
- If the project uses a vision agent for UI/visual changes, invoke it for before/after review and fold findings into the verdict.
- Categorize findings: **Blocker** (must fix), **Concern** (should fix), **Nit** (optional).
- On any Blocker or Concern: FAIL with concrete trim instructions; route to planner.
- Write review to `.pipeline/<issue-id>/review-result.json`: verdict, blockers, concerns, nits, trim_instructions. Schema: **pipeline/README.md** in this bundle.
- On PASS (nits only): declare ready for git operations.

## REVIEW FORMAT

- Blockers: correctness, safety, scope violation, CI failure.
- Concerns: quality, maintainability, incomplete coverage.
- Nits: style, naming, optional improvements.
- Decision: APPROVE only when all remaining findings are Nits; REQUEST CHANGES when any Blocker or Concern is unresolved.

Each item in `blockers`, `concerns`, and `nits` arrays must be an object with these keys:

```json
{ "file": "src/foo.ts", "line": 42, "description": "Issue description", "fix": "Suggested fix" }
```

## NON-GOALS

- Does not write code or run tests
- Does not make git commits or merge PRs
- Does not diagnose test failures
```

### 1.5 精简对比表（8 agent 的职责/输入/输出/禁止项）

| Agent | 核心职责一句话 | 读 | 写 | NON-GOALS 关键约束 |
|---|---|---|---|---|
| planner | 编排全流程、按复杂度分流、路由失败 | 全部 artifact（只读）、issue | `state.yaml`（可选） | 不写代码、不跑测试、不审 diff、不 commit、不诊断 |
| subplanner | 把 issue 拆成有序步骤 + AC 映射 | issue body/comments | `plan.json` | 不写代码、不跑测试、不选 issue、不超出 AC |
| worker | 按 plan 实现代码与测试 | `plan.json`、`debug-diagnosis.json` | `worker-result.json` | 不选 issue、不 commit/PR、不做全流程验证、不扩范围 |
| tester | 两阶段验证门（Phase1 静态 → Phase2 集成） | （跑命令） | `test-result.json` | 不修代码、不分类根因（除 inline_triage）、不审质量 |
| reviewer | 质量门：scope / 过度设计 / slop | `plan.json`、`worker-result.json` | `review-result.json` | 不写代码、不跑测试、不 commit/merge、不诊断失败 |
| debugger | 失败分类 + 根因定位 | `test-result.json`、`plan.json`、源码 | `debug-diagnosis.json` | 不改代码、不改 plan、不重跑测试 |
| git | 分支/约定式提交/PR（**不 merge**） | git 状态 | `git-result.json` | 不写代码、不 merge、**不 force push / 不跳 hook / 不直推 main** |
| benchmarker | 拉基准、评估性价比、推荐模型分配 | benchmark 源 | 快照文件 | 不改 agent/rules、不跑测试、**不擅自改模型分配**、不跑基准套件 |

---

## 2. Rules 格式（`.cursor-practitioner/rules/`）

### 2.1 frontmatter 实测

| 文件 | `description` | `alwaysApply` | `globs` |
|---|---|---|---|
| `jg-planner-first.mdc` | `Delegate multi-step work to jg-planner first` | `true` | 无 |
| `jg-commit-conventions.mdc` | `Commit and PR conventions` | `false` | 无 |
| `jg-issue-workflow.mdc` | `Issue-as-source-of-truth and start/completion workflow` | `false` | 无 |
| `jg-pr-review.mdc` | `PR review categories and decision rules` | `false` | 无 |
| `README.md`（非 mdc） | — | — | — |

**重要实测结论**：全仓库 `.mdc` 文件**没有任何一个使用 `globs` 字段**（全仓库 grep `globs` 的 18 处命中全部落在 README 与 docs/ 教程说明文字里，规则文件本身 0 命中）。`globs` 是文档层面声明"可选但可用"的能力，本仓库的规则全部走 `alwaysApply` 或纯 `description` 相关性匹配。`docs/practitioner/tutorials/solutions/07-rule-reference.md` 第 37 行明确说明这是有意为之："No `globs` field because the rule applies based on pipeline stage, not file type"。

### 2.2 正文内容要点

**`jg-planner-first.mdc`（唯一 `alwaysApply: true`，是整套体系的总闸门）**

- `## Pre-Action Gate (MANDATORY)`：以引用块 + `**STOP.**` 开头，规定"任何 Write / StrReplace / Task 调用之前，必须先分类复杂度"；Trivial 可直接做，Standard/Complex **第一个工具调用必须是** `Task(subagent_type="jg-planner", ...)`；"If you cannot justify a Trivial classification, you must not proceed directly."
- `## First Step on Implementation Requests`：禁止绕过 planner 直接调 worker/tester/reviewer/git。
- `## Pipeline Order`：Plan → Implement → Verify → Review → Ship → On failure。
- `## Artifacts`：所有状态在 `.pipeline/<issue-id>/`，planner 在每次 dispatch 里传路径。
- `## Exempt`：三种豁免（单文件单次编辑、纯事实问答、用户显式 override）。
- 首行含 HTML 注释 `<!-- Canonical source: .cursor-expert/rules/... -->`，声明**规范源在 expert 层**，再同步到 practitioner 与 `.cursor`。

**`jg-commit-conventions.mdc`**：Conventional Commits + issue 作为 scope（`feat(ISSUE-123): ...` 等 6 类 + `!`/`BREAKING CHANGE:` footer）；分支前缀 `feature/ fix/ chore/ spike/`，小写连字符，一 issue 一分支；PR title 取主 commit，body 含 Summary + Test plan；**"Agents may open PRs; only a human may merge. No force push, no skip hooks, no direct push to main unless explicitly requested."**；频率：一 issue 一 commit，WIP 可本地但完成前 squash。

**`jg-issue-workflow.mdc`**：issue 是权威 spec，**不允许依赖会漂移的副本 spec 文件**；开工前必须确认 AC 存在且无歧义，否则停下问人，缺上下文时固定用话术 `"Unknown from repo context — confirm before implementing"`；过程中只实现 issue 指定内容，发现新工作**提新 issue 而不是扩权**；完成后回帖执行报告 + 打 done 标签 + 记录 unblock 关系。

**`jg-pr-review.mdc`**：Blocker/Concern/Nit 三分类表格（含 merge impact 列）；决策规则 **APPROVE 仅当只剩 Nit**、**任一 Blocker/Concern 则 REQUEST CHANGES**，且**禁止带条件的 approve**（"Do not post APPROVE with conditions"）；审阅范围**只审改动文件、锚定 AC**；给出固定 PR 审阅 body 模板（`## PR Audit — <short-ref>` + Blockers/Concerns/Nits 复选框 + CI Status + Decision + Rationale）。

### 2.3 Rules 层的一处真实不一致

`rules/README.md` 第 5 行的表格把 `jg-planner-first.mdc` 标注为 **`false`**，并在第 10 行说"Set `alwaysApply: true` on **jg-planner-first.mdc** when this pipeline is your default orchestration"；但该 mdc 文件**实际就是 `alwaysApply: true`**。仓库处于"默认已开启"状态而 README 表格仍描述为"可选开启"。属文档与产物不同步，采用时按需自行决定。

---

## 3. Skills 格式（`.cursor-practitioner/skills/`）

两个 skill 均为**目录 + `SKILL.md`** 结构（`skills/<skill-name>/SKILL.md`），frontmatter 只有 **2 个字段**：`name`、`description`。注意与 agents 的差异：**description 用双引号包裹且写得较长**，因为 skill 是**按 description 相关性"被拉取"**（pull），而 rule 是"被注入"（push）。

### 3.1 `jg-pipeline-artifact-io/SKILL.md`（77 行）

frontmatter：

```yaml
name: jg-pipeline-artifact-io
description: "Read/write layout for pipeline artifacts in .pipeline/. Use when any jg- agent reads upstream artifacts or writes its output."
```

小节结构：`Directory layout`（目录树代码块，逐个标注产出者）→ `Setup`（`mkdir -p`）→ `Reading`（"do not assume content is inline"，缺文件=该阶段未跑）→ `Writing`（`json.dumps(data, indent=2)` + 尾随换行；每份 artifact 带 `self_assessment`）→ `Per-agent mapping`（7 行读写表）→ `Archive on completion`（`mv` 到 `.pipeline/completed/`）→ `Artifact shapes`（指向 pipeline/README.md，并给出 `schema.py --validate` 命令）→ `Anti-patterns`（3 条）→ 尾注 lessons 文件。

**用途**：让 7 个 agent 对"文件放哪、谁读谁写、怎么序列化"形成单一共识，**核心反模式是"不要把 artifact 内容塞进 prompt，只传路径"**。

### 3.2 `jg-benchmark-ops/SKILL.md`（60 行）

frontmatter：

```yaml
name: jg-benchmark-ops
description: "Benchmark collection and evaluation workflow for agent model assignment reviews. Use when pulling benchmarks, evaluating cost/performance, or deciding which models to use for which agents."
```

小节结构：`When to Trigger`（新模型发布 / 用户要求 / 季度定期）→ `Collection Workflow`（4 步编号：Identify sources → Fetch and parse → Store → Validate）→ `Evaluation Workflow`（有 eval 脚本就走脚本，没有就用快照+定价自己算）→ `Verdict Definitions`（**五级判定表**：Excellent / Correct / Monitor / Tune / Upgrade，每级带量化阈值，如 Correct="within ~5% of tier leader"、Monitor="Trails leader by ~5–15%"、Tune=">5% 更便宜或同价更优"）→ `Cost and Performance` → `Output Expectations` → `Anti-Patterns`。

**用途**：把"该给哪个 agent 配哪个模型"从主观直觉变成**可审计的量化流程**（每条分数必须带 source URL + 日期；缺数据记 null，禁止估算）。

**expert 层两个 skill 同名但做了增量扩展**（实测非同一文件）：

| Skill | practitioner | expert | expert 增量 |
|---|---|---|---|
| `jg-pipeline-artifact-io` | 3065 B | 4025 B | 新增 `## Tier tracking fields`：`tier_used` / `cost_estimate` / `escalation_history{from_tier,to_tier,reason}` |
| `jg-benchmark-ops` | 3043 B | 3970 B | 新增 `### Per-Tier Cost Analysis`（fast/standard/high 三档各自的优化目标与可接受阈值）+ 报告表格增加 `Tier` 列 |

---

## 4. Pipeline 运行时

### 4.1 `schema.py` —— artifact JSON schema

**架构**：`.cursor-practitioner/pipeline/schema.py`（43 行）→ `from pipeline_schema_common import load_artifact, validate_required_keys`（`lib/pipeline_schema_common.py`）。

**真实 REQUIRED_KEYS 字典（`lib/pipeline_schema_common.py` 第 8–25 行，原文）**：

```python
REQUIRED_KEYS = {
    "plan.json": ["affected_files", "steps", "acceptance_mapping"],
    "worker-result.json": ["status", "files_changed", "blockers", "summary"],
    "worker-result-fast.json": ["status", "files_changed", "blockers", "summary"],
    "test-result.json": ["verdict", "phase_1"],
    "test-result-fail.json": ["verdict", "phase_1"],
    "test-result-pass.json": ["verdict", "phase_1"],
    "review-result.json": ["verdict", "blockers", "concerns", "nits"],
    "debug-diagnosis.json": [
        "failure_source", "failure_description", "root_cause",
        "root_cause_file", "root_cause_line", "classification",
    ],
    "git-result.json": ["branch", "commit_sha", "commit_message"],
}
```

**逐 artifact 的必填字段 + 完整字段集（来自 `.cursor-practitioner/pipeline/README.md` 第 32–98 行）**：

| Artifact | 写入者 | **必填**（schema 强制） | 可选字段（文档定义，schema 不校验） |
|---|---|---|---|
| `plan.json` | jg-subplanner | `affected_files: string[]`、`steps: [{order, action, file, description, rationale?, depends_on?}]`、`acceptance_mapping: {string: string}` | `commit_plan?: string[]`、`self_assessment?: {confidence, uncertainty_areas, recommendation}` |
| `worker-result.json` | jg-worker | `status: "completed"\|"blocked"`、`files_changed: string[]`、`blockers: string[]`、`summary: string` | `self_assessment?` |
| `test-result.json` | jg-tester | `verdict: "PASS"\|"FAIL"\|"SKIP"`、`phase_1: {check_name: {result, output?}}` | `phase_2?: {checks?, stack_trace?, reproduction?, timing_ms?}`、`classification?: null \| "fix_target"`、`inline_triage?: bool`、`fix_instruction?: string`、`self_assessment?` |
| `review-result.json` | jg-reviewer | `verdict`、`blockers: [{file,line,description,fix}]`、`concerns: 同构`、`nits: 同构` | `trim_instructions?: string`、`self_assessment?` |
| `debug-diagnosis.json` | jg-debugger | `failure_source`、`failure_description`、`root_cause`、`root_cause_file`、`root_cause_line`、`classification: "fix_target"\|"plan_defect"\|"escalate"` | `escalation_sub?: "technical_complexity"\|"ambiguous_requirement"`、`fix_instructions?`、`plan_fix_instructions?`、`related_failures?: string[]`、`self_assessment?` |
| `git-result.json` | jg-git | `branch`、`commit_sha`、`commit_message` | `pr_number?`、`pr_url?`、`ci_status?`、`downstream_unblocked?: string[]`、`self_assessment?` |

**注意 `worker-result-fast.json` 已在 REQUIRED_KEYS 里作为独立 artifact 键注册**（expert 层 fast 变体的产物名），说明 schema 层已为分层路由预留了产物名。

**两个不参与 schema 校验的 YAML**：
- `state.yaml`（planner 状态/续跑）：`issue`、`issue_number`、`status`(in_progress\|completed\|failed\|paused)、`current_stage`(triage\|plan\|implement\|test\|review\|git)、`acceptance_criteria: [{id, text, test_mapped?, status}]`、`stages: {stage: {agent, result, summary, artifact_path?}}`、`retries`、`routing_decisions`、`running_summary`。**"Not validated by schema.py"**。
- `lessons.yaml`：list of `{date, issue, pattern, frequency?, mitigation?}`。**同样不校验**。

**校验器实际行为（我实测执行的 5 组用例）**：

| 用例 | 命令 | 结果 |
|---|---|---|
| 真实 walkthrough 产物 | `schema.py --validate docs/practitioner/walkthrough/worker-result.json` | 输出 `OK`，**exit 0** ✅ |
| 合法 JSON 但缺键 `{"status":"completed"}` | 同名 `worker-result.json` | 逐条打印 `Missing required key: files_changed / blockers / summary`，**exit 1** ✅ |
| 未注册的 artifact 名（`lint-result.json`） | 同上 | `Unknown artifact: lint-result.json`，**exit 1** ✅ |
| expert 层 `tier_used: "turbo"` | expert `schema.py` | `tier_used must be one of ['fast', 'high', 'standard'], got 'turbo'`，**exit 1** ✅ |
| issue 目录不存在 | `check.py --issue NOPE --stage plan` | `ERROR: Pipeline directory not found`，**exit 2** ✅ |

**校验器的三个边界（真实的松紧度）**：
1. **只做"键是否存在"检查，不做类型/取值/形状校验**——`validate_required_keys` 只遍历 `if key not in data`。`plan.json` 的 `steps` 填个字符串也能过。唯一例外是 expert 层额外加的 `tier_used` 枚举与 `escalation_history` 结构校验。
2. **靠文件名白名单分派**（`load_artifact` 里 `if name not in REQUIRED_KEYS: return Unknown artifact`）——所以 `lint-result.json`（AGENTS.md 里 team-linter 的产物）**不在白名单中，无法被 schema 校验**，整条 lint 产物链是校验盲区。
3. **`test-result-fail.json` / `test-result-pass.json` / `worker-result-fast.json` 被显式登记**，是为了兼容 walkthrough 与分层命名，而非独立契约。

### 4.2 `check.py` —— stage gate 不变量校验

**架构**：`.cursor-practitioner/pipeline/check.py`（42 行）只做字典分派 `STAGE_CHECKERS = {"plan": check_plan, "implement": check_implement, "test": check_test, "review": check_review}`，真实逻辑在 `lib/pipeline_check_common.py`（184 行），入口 `run_checker()` 用 argparse 收 `--issue`（必填）、`--stage`（必填，choices 来自 STAGE_CHECKERS）、`--pipeline-dir`（可选，默认 `Path.cwd()/".pipeline"`）。

**实现了一个独立的数据结构 `InvariantViolation(check, message, severity="error")`**，支持 `error` / `warning` 两级：有 error → 打印 `N error(s), M warning(s) - FAIL` 并 return 1；只有 warning → `PASS with warnings`；全过 → `All invariants passed for stage '<s>' - PASS`，return 0。

**逐 stage 实际校验的不变量（原文 check 名称 + 逻辑）**：

| stage | check 名 | 不变量 | severity |
|---|---|---|---|
| plan | `plan_exists` | `plan.json` 存在且非空，否则立即返回 | error |
| plan | `affected_files` | `affected_files` 非空 | error |
| plan | `steps` | `steps` 非空 | error |
| plan | `ac_mapping` | `acceptance_mapping` 非空 | error |
| plan | `ac_test_mapped` | 每条 AC 必须有非空 test 映射 | error |
| plan | `file_has_step` | **`affected_files` 里每个文件必须在 `steps` 中有对应 step** | error |
| plan | `step_in_affected` | **每个 step 的 `file` 必须在 `affected_files` 里**（双向一致性） | error |
| implement | `plan_exists` | 无 plan 直接失败 | error |
| implement | `scope_extra` | 实际 `git diff --name-only` + `git ls-files --others --exclude-standard` 的结果**不得超出** `affected_files`（**自动豁免 `.pipeline/` 前缀**） | error |
| implement | `scope_missing` | plan 里列了但实际没改的文件 | **warning** |
| test | `test_result_exists` | `test-result.json` 存在且非空 | error |
| test | `phase_2_gated` | **`phase_1` 中任一 `result == "FAIL"` 时，`phase_2` 必须不存在**（禁止越过失败继续跑集成） | error |
| test | `classification_valid` | `classification` 若存在只能取 `"fix_target"` / `"plan_defect"`（**tester 只能做 inline triage，不能自己下诊断**） | error |
| review | `review_result_exists` | `review-result.json` 存在且非空 | error |
| review | `verdict_consistent` | **`verdict == "PASS"` 时 `blockers` 必须为空** | error |
| review | `finding_has_file` / `finding_has_line` | `blockers` 与 `concerns` 中每一项必须是对象且有 `file`、`line`（`nits` 不校验） | error |

**expert 层 `check.py`（135 行）的增量**：不重写而是 `from pipeline_check_common import ... as base_check_xxx` 包一层，新增 `TIER_ORDER = {"fast": 0, "standard": 1, "high": 2}` 与两类 tier 不变量：

- `tier_complex_no_fast`：读 `plan.json` 的 `complexity`，若为 `"complex"` 而 `worker-result.json` / `test-result.json` / `review-result.json` 的 `tier_used == "fast"` → error。（implement / test / review 三个阶段各自检查；**plan 阶段沿用基类，未做 tier 校验**。）
- `escalation_tier_progression`：`escalation_history` 每一项必须满足 `TIER_ORDER[from_tier] < TIER_ORDER[to_tier]`，即**升级只能向上，禁止降级或原地打转**。仅对 `worker-result.json` 与 `test-result.json` 生效（由 `ARTIFACTS_WITH_ESCALATION_HISTORY` 白名单约束）。

### 4.3 流水线阶段顺序（三处文档一致）

**Practitioner（README.md 第 26–37 行给出的 mermaid 图，是原生权威）**：

```
jg-planner → jg-subplanner → [plan.json] → jg-worker → [worker-result.json] → jg-tester
    jg-tester --verdict: PASS--> jg-reviewer --verdict: PASS--> jg-git --> PR ready for review
    jg-tester --verdict: FAIL--> jg-debugger --> [debug-diagnosis.json] --> jg-worker（回流）
    jg-reviewer --verdict: FAIL--> jg-planner（回流）
```

**带 3.5 号的完整编号顺序（AGENTS.md 第 10–20 行）**：

1. **jg-planner** — 入口，分类复杂度，trivial 时直接给 worker scope
2. **jg-subplanner** — 写 `plan.json`
3. **jg-worker** — 实现，写 `worker-result.json`
3.5. **team-linter**（可选）— 写 `lint-result.json`，FAIL → planner 重派 worker
4. **jg-tester** — 跑 CI + 集成，写 `test-result.json`，FAIL → debugger
5. **jg-debugger** — 写 `debug-diagnosis.json`，planner 按分类重派 worker / subplanner / 升级
6. **jg-reviewer** — **仅在 tester PASS 之后**，写 `review-result.json`，FAIL → planner
7. **jg-git** — **仅在 reviewer PASS 之后**，写 `git-result.json`，可选把 `.pipeline/<issue-id>` 归档

**失败分类的三路路由（debugger → planner）**：`fix_target` → worker；`plan_defect` → subplanner；`escalate` → human/architect（`escalate` 再细分 `technical_complexity` 与 `ambiguous_requirement`）。

**重试上限**：planner 强制"每 stage 最多 2 次重试"，超限升级到人；expert 层进一步规定"**每次升级不计入重试**"。

**关键认知**：这是一条**纯 prompt 驱动的流水线**，没有任何编排引擎/状态机在执行——stage gate 是**事后校验器**（`check.py` 由人/agent 主动调用），不是**阻断器**。管道能否正确流转完全依赖 planner agent 遵循 AGENTS.md 与 rules 的自然语言契约。

---

## 5. AGENTS.md 注册表

### 5.1 `.cursor-practitioner/AGENTS.md`（注册 8 + 1 个）

结构为四段：

1. **索引表**：列 `Agent | Model | Role | Reads | Writes` —— **5 列**，比 docs/reference/agents.md 少一个 `Tier` 列。8 个 pipeline agent + `team-linter` 共 9 行。
2. **角色澄清**：明确 "**jg-benchmarker** is a support agent (on-demand), not a pipeline stage." 与 "**team-linter** is a project-specific agent (add via tutorial exercise or copy from sandbox)." —— **用文字把"流水线阶段"与"支撑型 agent"区分开**，这是很干净的一招。
3. **`## Pipeline order`**：7 步编号清单（含 3.5 号插入位），每步写清"谁调用谁、写哪个 artifact、失败往哪走"。
4. **`## Subagent types (Cursor)`**：`planner → jg-planner`、`subplanner → jg-subplanner`、`worker → jg-worker`、`tester → jg-tester`、`reviewer → jg-reviewer`、`debugger → jg-debugger`、`git → jg-git`、`benchmarker → jg-benchmarker`、`linter → team-linter`。末句："Project-specific agent files (e.g. in `.cursor/agents/`) can be copies of these with different `name` and `model` if you want to keep jg- as a reference bundle."

**subagent_type 映射的本质**：注册表里的 key（`planner`/`worker`/…）是**抽象角色名**，value 是**具体 agent 文件**。rules 里两种写法并存——`Task(subagent_type="jg-planner", ...)`（直接写 agent 名）与 `subagent_type="planner"`（写角色名），说明这层映射是**供人/LLM 参考的约定**，不是 Cursor 强制的枚举。

### 5.2 `.cursor-expert/AGENTS.md`（注册 15 + 1 个）

与 practitioner 的关键差异：

1. **索引表多一列 `Tier`**，取值 `--` / `Fast` / `Standard` / `High`，16 行覆盖全部变体（`jg-subplanner-high`、`jg-worker-fast/-high`、`jg-tester-fast`、`jg-reviewer-fast/-high`、`jg-debugger-high`）。
2. **新增 `## Tier routing` 矩阵**（5 列：Subplanner/Worker/Tester/Reviewer/Debugger × 3 行：Trivial/Standard/Complex）。
3. **`## Pipeline order` 用方括号记法压缩变体**：`jg-subplanner[-high]`、`jg-worker[-fast|-high]`、`jg-tester[-fast]`、`jg-debugger[-high]`、`jg-reviewer[-fast|-high]`。**注意 `jg-tester` 没有 `-high` 变体**——Complex 行里 tester 仍是 `jg-tester`（standard 档），这是有意的成本控制。
4. **删掉了 practitioner 里的 `## Subagent types (Cursor)` 段**（expert 注册表只到 pipeline order 就结束，共 41 行）。

### 5.3 `.cursor-foundation/AGENTS.md`（注册 3 个）

只有一张 5 列表（planner / worker / git），无 Pipeline order、无 subagent 映射，开头即声明 "This tier uses 3 agents for learning concepts only. For production use, copy `.cursor-practitioner/` into your project as `.cursor/`."

三个 agent 文件顶部都插入了 HTML 引用块警告：

```markdown
> **NOTE**: This is a simplified educational example. Do not use in production. For real projects, copy `.cursor-practitioner/` into your project as `.cursor/`.
```

---

## 6. Expert 层的增量设计

### 6.1 `rules/jg-tier-routing.mdc`（expert 独有，`alwaysApply: true`）

全文 42 行，四节：

**`## Complexity Classification`** —— 给出**可判定的三档定义 + 举例**：

- **Trivial**：1-2 files, single domain, no new abstractions, no security implications（例：改 typo、改配置值、加简单 getter、重命名变量）
- **Standard**：3+ files, or cross-domain, or requires tests across modules（例：加一个带测试的 API endpoint、重构模块、按 spec 实现 feature）
- **Complex**：safety-critical code, new abstractions, architectural changes, real-time systems, concurrency（例：加认证授权、设计新数据管道、实现 WebSocket 层、加限流）

**`## Tier Assignment`** —— 与 AGENTS.md 同构的 3×5 路由表（**同一张表被写进 rule、AGENTS.md、jg-planner.md 三处**，靠"复制保持一致"而非单一引用源，属潜在漂移点）。

**`## Escalation`** —— 4 条：升级到下一档（fast → standard → high）；用**相同输入**重派；**不计入 retry**；已在 high 档仍 escalate → 升级到人。

**`## Cost Guardrails`** —— 4 条：每 stage 每档最多 2 次重试；**每份 artifact 都要记 `tier_used` 与 `cost_estimate`**；任一档重试 2 次后升级到下一档；high 档重试 2 次后升级到人。

### 6.2 Expert vs Practitioner 的 agents 目录差异（实测文件大小）

**expert 新增 7 个变体文件（全部是薄壳，显式继承标准档）**：

| 变体文件 | model | 行数/字节 | 增量内容 |
|---|---|---|---|
| `jg-worker-fast.md` | `gemini-3-flash` | 27 行 / 702 B | 只做单文件编辑、配置、typo；**超出范围返回 `status: escalate`**；不做多文件/复杂测试/新抽象 |
| `jg-worker-high.md` | `gpt-5.1-codex-max` | 29 行 / 842 B | "All standard worker responsibilities" + 实现前风险评审 + worker-result 里写 rollback notes + 详细 self_assessment |
| `jg-tester-fast.md` | `gemini-3-flash` | 27 行 / 652 B | 只跑 Phase 1（lint/typecheck/unit tests），**不跑 Phase 2** |
| `jg-reviewer-fast.md` | `gemini-3-flash` | 29 行 / 811 B | 只核对改动文件 vs plan affected_files + 查明显错误；**无架构/安全/性能审查** |
| `jg-reviewer-high.md` | `gemini-3.1-pro` | 32 行 / 945 B | "All standard reviewer responsibilities" + 架构/安全/性能/向后兼容 + 结果里加 `architecture_assessment` 字段 |
| `jg-subplanner-high.md` | `gpt-5.1-codex-max` | 28 行 / 826 B | + 步骤间依赖图（`depends_on`）+ 每步 `risk_level`(low/medium/high) + 高危步的 rollback 策略 |
| `jg-debugger-high.md` | **`claude-opus-4.6`** | 30 行 / 884 B | 多因分析、跨模块追踪、架构级根因；**标准 debugger 低置信度或 classification: escalate 时启用**；更高置信度门槛 |

**同名文件在 expert/practitioner 间的实际差异**（哈希对比）：

| 文件 | 是否逐字节相同 |
|---|---|
| `jg-benchmarker.md` | ✅ 完全相同 |
| `jg-git.md` | ✅ 完全相同 |
| `jg-reviewer.md` | ✅ 完全相同 |
| `jg-subplanner.md` | ✅ 完全相同 |
| `jg-tester.md` | ❌ 不同（2409 B vs 2454 B，expert 略短） |
| `jg-worker.md` | ❌ 不同（1905 B vs 1951 B） |
| `jg-planner.md` | ❌ **大幅不同**（1897 B vs 3050 B —— expert 版砍掉 artifact 清单与 tiered dispatch 段，改为内联 `TIER ROUTING TABLE` + `ESCALATION HANDLING`） |

**统一的模板产物（`.cursor-expert/templates/agent-fast.md` 与 `agent-high.md`）**：两个模板都显式要求产物里写 `tier_used`（`Include tier_used: "fast"` / `"high"`），高塔模板还要求 "Add `risk_notes` or `architecture_assessment` when the role warrants it"。**这说明分层不是靠复制粘贴，而是有模板作为生成契约。**

### 6.3 成本控制机制（三条腿）

1. **分级路由省 token**：trivial 任务走 `gemini-3-flash` 档（worker-fast/reviewer-fast/tester-fast），standard 走 `gpt-5.3-codex` / `gemini-3.1-pro`，只在 complex 才动用 `claude-opus-4.6`。**Tester 不设 -high**，Complex 任务也复用 standard tester——明确的成本取舍。
2. **升级不算重试**（`escalation is cheap and expected`，见 expert README 第 28 行）：鼓励 fast 档**宁可误升级也不硬扛**，避免"便宜模型硬做题导致返工"的更大浪费。
3. **硬性双上限**：每 stage 每档 2 次重试；任意档 2 次失败即升档；high 档 2 次失败交人。**并且这些上限被 `check.py` 的 `escalation_tier_progression` 与 `schema.py` 的 `tier_used` 枚举做成了可执行的校验**，不是空话。

expert README 第 30 行的排障条目直接点出了成本失控的机制性原因："**Cost higher than expected** -- Check the routing log for frequent escalations. Overly aggressive fast-tier assignment causes rework." —— 并配套 `docs/expert/walkthrough/routing-log.md` 与 `cost-summary.md` 作为观测载体。

### 6.4 状态与经验沉淀机制

**`templates/state.yaml.example`（30 行，续跑载体）**：

```yaml
issue: "SPEC-X-002"
issue_number: 42
status: "in_progress"  # in_progress | completed | failed | paused
current_stage: "test"  # triage | plan | implement | test | review | git
acceptance_criteria:
  - id: "AC-1"
    text: "Implement X per contract from SPEC-X-001"
    test_mapped: "tests/test_x.py::test_x_contract"
    status: "implemented"  # pending | implemented | verified
stages:
  plan:
    agent: "jg-subplanner"
    result: "PASS"
    summary: "Plan with 3 steps"
    artifact_path: ".pipeline/SPEC-X-002/plan.json"
  implement:
    agent: "jg-worker"
    result: "PASS"
    summary: "Implemented X and unit tests"
    artifact_path: ".pipeline/SPEC-X-002/worker-result.json"
retries: []
routing_decisions: []
running_summary: "Plan and implement done; tester next."
```

**设计要点**：`current_stage` 是**续跑锚点**（expert README 排障："Pipeline doesn't resume -- Check `.pipeline/<issue-id>/state.yaml` exists and has the correct `current_stage`"）；AC 用**三态**（pending → implemented → verified）把"验收标准"变成可追踪进度条；`stages` 用 `artifact_path` 做**指针而非内联内容**（与 skill 的反模式一致）；`routing_decisions` 为分层路由留了审计痕迹。

**`templates/lessons.yaml.example`（10 行，跨运行经验）**：

```yaml
# Schema per entry:
#   date: YYYY-MM-DD
#   issue: <issue-id>
#   pattern: "short description of what went wrong"
#   frequency: 1
#   mitigation: "what was done to prevent recurrence"
# Cap at ~50 entries; drop oldest when exceeded.
lessons: []
```

**设计要点**：单条结构极简（date/issue/pattern/frequency/mitigation）；**带 `frequency` 计数字段**（同一 pattern 复发几次是可量化信号）；**显式容量上限 ~50 条 + 淘汰最旧**（避免经验文件无界膨胀成 context 负担）；由 planner 在 pipeline 开始时读取。这是**跨 session 记忆的唯一载体**，也是这套设计里最有复用价值的机制之一。

### 6.5 一致性瑕疵（实测发现）

`docs/practitioner/walkthrough/state.yaml`（真实样例）与 `templates/state.yaml.example`（模板）**字段不一致**：

| 位置 | AC 字段名 | AC 状态 | stage 结果大小写 | retries |
|---|---|---|---|---|
| 模板 | `text` | `pending\|implemented\|verified` | `"PASS"` | `[]`（列表） |
| walkthrough 样例 | `description` | `verified`（无 `pending/implemented` 用例） | `pass`（小写） | `1`（整数） |

`status`/`current_stage` 取值在样例与模板间一致（`completed` / `git` 均合法），但 AC 字段名与 retries 类型的漂移意味着**该文件"project-defined, 不校验"的定位在实践中确实产生了分叉**。

---

## 7. 安全与护栏

### 7.1 README 的护栏声明原文（`README.md` 第 102–108 行）

```markdown
## Security and guardrails

- Agents that can write code: worker, debugger
- Agents that can run commands: tester, git
- Agents that cannot: merge PRs, force push, skip hooks, push to main
- `readonly: true` on planner, reviewer, subplanner
- Always review agent-generated PRs before merging
```

### 7.2 逐条落地证据（在 agent 文件与 rules 中的原文）

**① "Agents that can write code: worker, debugger"** —— 与 frontmatter 实测**不完全吻合**：

- `jg-worker.md` frontmatter **没有 `readonly` 字段**（缺省 = 可写），且正文明确 "Edit only files specified in the task scope." → **一致**。
- `jg-debugger.md` 写明 `readonly: false`，**但正文 NON-GOALS 第一条自我否决了写代码能力**：

```markdown
## NON-GOALS
- Does not edit code (worker does)
- Does not revise the plan (subplanner does)
- Does not re-run tests (tester does)
```

  `jg-debugger` 唯一的写入动作是 `debug-diagnosis.json`（"Write diagnosis to `.pipeline/<issue-id>/debug-diagnosis.json`"）。对照 `jg-worker.md` 的 `## NON-GOALS` 同样写着 "Does not run the full verification pipeline or review code"——**两个文件的 NON-GOALS 是严格的互斥矩阵**（worker 不诊断、debugger 不写代码、reviewer 不写代码不诊断、tester 不修代码不分类、subplanner 不写代码、git 不写代码不 merge）。**真正在约束行为的是 NON-GOALS 的互斥分工，`readonly` 只是标注。**
- `jg-benchmarker.md` 也是 `readonly: false`，但 README 的"可写代码"清单里没有它（它只写 benchmark 快照）。**说明 `readonly` 语义是"可写文件"，而非"可写代码"**，与 README 的措辞存在歧义。

**② "Agents that can run commands: tester, git"** —— 落地证据：

- `jg-tester.md` 两个 Phase 都在跑命令：`Run each project CI stage (e.g. make lint, make typecheck, make test)`、`Run project integration/eval steps (e.g. make eval or equivalent)`、`Verify no files outside the task allowlist were modified (e.g. git diff --name-only, untracked list)`。
- `jg-git.md` 跑 `git diff --name-only main...HEAD` 与 `gh pr checks`。
- 但 `jg-worker.md` 也允许跑命令（`Pre-flight: run project lint and typecheck (e.g. make lint && make typecheck)`），**README 的"可运行命令"清单同样不完备**。真正的收敛点是 **worker 的自我修复上限**："attempt up to **2 self-fixes** before reporting to planner"。

**③ "Agents that cannot: merge PRs, force push, skip hooks, push to main"** —— 这是**唯一在 agent 文件里逐字落地**的一条：

`jg-git.md` 的 `## NON-GOALS` 与 `## DECISION FRAMEWORK` 原文：

```markdown
## NON-GOALS

- Does not write code, run tests, or review code
- Does not merge PRs (human-only)
- Does not force push, skip hooks, or push to main directly
- Does not rebase/amend pushed commits unless explicitly requested

## DECISION FRAMEWORK

Safety > correctness > speed. If uncertain about a git operation, do not do it.
Destructive operations require explicit human request.
```

以及在 `jg-git.md` 的 `## ROLE` / `## PRIMARY OBJECTIVE` 中再次强化："Operates only after tester and reviewer have passed"、"Every commit references an issue"、"Every branch maps to one issue"。**规则层双重确认**：`jg-commit-conventions.mdc` 有 "Agents may open PRs; **only a human may merge**. No force push, no skip hooks, no direct push to main unless explicitly requested."；`jg-pr-review.mdc` 把 merge 影响写进分类表。**这是全仓库最完整、最可验证的护栏链（agent NON-GOALS + agent DECISION FRAMEWORK + rule + PR review 分类表，四层冗余）。**

**④ "`readonly: true` on planner, reviewer, subplanner"** —— frontmatter 逐字吻合（3/3 文件均 `readonly: true`）。

**⑤ "Always review agent-generated PRs before merging"** —— 由 `jg-git.md` "Does not merge PRs (human-only)" + `jg-pr-review.mdc` 的 APPROVE/REQUEST CHANGES 决策规则共同承接。

### 7.3 护栏机制的三个结构性弱点（审计发现的真实风险）

**弱点 1：`readonly` 是纯声明，无运行时强制。** `.cursor-practitioner/pipeline/` 下两个校验器都**没有任何代码读取 agent frontmatter 的 `readonly`**；`check_implement` 唯一的写范围约束是拿 `git diff` 对比 `plan.json` 的 `affected_files`，它**约束的是"改了计划外的文件"，不是"哪个 agent 改的"**。也就是说：如果 planner（`readonly: true`）真的去改了一个业务文件，而该文件恰好在 `affected_files` 里，`check.py --stage implement` **不会报错**。真正的防线只有 rules 里的 `jg-planner-first.mdc` 文本约束与 agent NON-GOALS 的自然语言。

**弱点 2：`check_implement` 的 scope_extra 检查依赖 `affected_files` 的完备性，且豁免了 `.pipeline/`。** 代码原文：

```python
extra = all_changed - affected
for changed_file in sorted(extra):
    if changed_file.startswith(".pipeline/"):
        continue
    violations.append(InvariantViolation("scope_extra", f"File changed but not in plan affected_files: {changed_file}"))
```

豁免 `.pipeline/` 是 necessary（artifact 本身不该算越界），但这也意味着**任何写进 `.pipeline/` 的东西都不受范围约束**。

**弱点 3：`lint-result.json` 处于校验盲区。** AGENTS.md 与 `docs/reference/agents.md` 都把 `team-linter` 列为写 `lint-result.json` 的一环（pipeline 第 3.5 步），但 `REQUIRED_KEYS` 里**没有这个键**——我实测 `schema.py --validate lint-result.json` 返回 `Unknown artifact: lint-result.json` 且 exit 1。因此**唯一没有可校验契约的产物恰恰是链路上的一个门槛阶段**。同时 `check.py` 也没有 lint 相关 stage。

---

## 8. 可直接复用的设计要点清单

### 8.1 强烈建议借鉴（高价值 / 低适配成本）

1. **`ROLE → PRIMARY OBJECTIVE → CORE RESPONSIBILITIES → NON-GOALS` 四节骨架**。8/8 agent 一致，且 `NON-GOALS` 用互斥矩阵划边界——这是**不用 `tools` 白名单也能约束 agent 行为**的最实用手法。直接抄。
2. **frontmatter 极简主义：只留 `name` / `model` / `description` / `readonly`**。`description` 统一 "做什么 + Use when…" 两段式，同时承担**自动路由触发面**。字段越少越不容易漂移。
3. **"单写者 + 磁盘文件"的 artifact 契约**：每个 agent 恰好写一个 JSON，读上游只读文件路径（**明确反模式："Do not pass full artifact content in the prompt; pass the file path"**）。这让每步可独立校验、可续跑、可事后取证。
4. **双向的 plan↔改动一致性不变量**（`file_has_step` + `step_in_affected` + `scope_extra`）。用机器校验把"plan 与实现漂移"这种最常见的多 agent 失效模式变成硬错误，而不是靠 reviewer 肉眼抓。这是我见过最值得直接搬迁的 check。
5. **`phase_2_gated`：Phase 1 有 FAIL 就不许有 phase_2**。把"不要越过失败往下跑"变成不变量，而不是提示词劝告。
6. **`verdict_consistent`：`verdict == "PASS"` 时 `blockers` 必须为空**。一行代码消灭"嘴上通过、账上有 blocker"的经典不一致。
7. **`InvariantViolation` 的 error/warning 两级 + 三段式退出码**（0 通过 / 1 有 error / 2 环境错）。既保留硬门槛，又不让"计划列了没改"这种软问题阻塞流水线。
8. **纯静态的表驱动校验器**（`load_artifact` 按文件名分派 + `REQUIRED_KEYS` 字典 + `STAGE_CHECKERS` 字典）。新增 artifact / 新增 stage 都是加一行，无框架依赖，无第三方库（只用 `json` / `pathlib` / `argparse` / `subprocess`）。
9. **分层"薄壳继承"模式**：expert 的 `check.py` 用 `as base_check_implement` 包装而非重写，新增 tier 不变量时基类逻辑零改动。**扩展点收敛、上游修复可继承**——比 fork 一份改要健康得多。
10. **`escalation_tier_progression` 不变量**（升级只能向上，`from_tier < to_tier`）。把"防止 agent 在档位间来回弹跳"这种隐性成本泄漏做成可校验约束。
11. **升级不计入重试 + 鼓励 fast 档主动 escalate**（配 expert README 的 "escalation is cheap and expected"）。这是**成本控制里最反直觉但最正确的一条**：便宜模型硬做题的返工成本远高于一次升级。
12. **`state.yaml` 的续跑锚点设计**：`current_stage` 枚举 + AC 三态（pending/implemented/verified）+ `stages.*.artifact_path` 指针 + `routing_decisions` 审计痕迹。用几十行 YAML 换来跨 session 可恢复。
13. **`lessons.yaml` 的容量上限（~50 条 + 淘汰最旧）+ `frequency` 计数字段**。跨运行经验沉淀最容易失控的就是无界增长，这个上限是必要的自我约束。
14. **`jg-planner-first.mdc` 的 Pre-Action Gate 写法**：引用块 + `**STOP.**` + 明确的 tool-call 优先级 + **"If you cannot justify a Trivial classification, you must not proceed directly"**（把举证责任放在"允许直接做"一侧）+ 独立的 `## Exempt` 节。这是让"必须先编排"真正生效的关键句式。
15. **把支撑型 agent 与流水线阶段显式区分**（"jg-benchmarker is a support agent (on-demand), not a pipeline stage"），并在 pipeline order 里用 `3.5` 号插入可选阶段——不破坏主编号语义。
16. **`templates/` 与校验器/文档的强制联动**：`agent.md` 模板末句原文 "Add the new artifact to pipeline/README.md and pipeline/schema.py REQUIRED if you add a new artifact type."，`templates/README.md` 也重复了一遍。**在模板里写"改完要同步哪两个文件"**，是防止契约漂移的低成本手段。
17. **`jg-benchmark-ops` 的五级量化判定表**（Excellent / Correct / Monitor / Tune / Upgrade + 明确的 ~5% / ~5–15% 阈值）。把"模型选型"从争论变成流程，且每条分数强制带 source URL + 日期、缺数据记 null **禁止估算**。
18. **命名空间前缀约定**（`jg-*` = 共享不可改，`<team>-*` = 团队约定，无前缀 = 个人）+ 升级时"diff before overwriting"。让模板可升级而不被本地改动卡死。
19. **PR 审阅的固定 body 模板 + "禁止带条件 approve"**（"Do not post APPROVE with conditions"）。消灭 "LGTM after you fix X" 这种无法审计的中间态。

### 8.2 建议简化或不采纳（复杂度不划算 / 已知缺陷）

1. **`lib/` 与 `.cursor-*/pipeline/` 的跨目录依赖** ❌ **必须改**。当前 `parents[2] / "lib"` 的布局使得按 README 推荐方式 `cp -r .cursor-practitioner/* your-project/.cursor/` 之后，`schema.py` / `check.py` **直接 ImportError**。复用时要么把公共代码内联进每个 tier，要么把 `lib/` 一起打包并调整路径解析。
2. **同一张 tier routing 表在三处重复**（`rules/jg-tier-routing.mdc`、`AGENTS.md`、`agents/jg-planner.md`）——典型的多源真相。建议**单一源 + 其余引用**（例如只留 rule，agent 文件写 "see jg-tier-routing.mdc"）。
3. **`readonly` 不做运行时强制**：要么老实承认它是注释（并在文档里这么写），要么在 `check.py` 里真的加一条"本 stage 的写入者必须是 X"的断言。当前的中间态会给使用者**虚假的安全感**。
4. **`lint-result.json` 无契约**：如果保留 team-linter 这个 3.5 阶段，就该把它加进 `REQUIRED_KEYS` 并补一个 `check_lint`；否则应从 pipeline order 里降级为"可选人工步骤"，避免文档承诺了校验却兑现不了。
5. **`schema.py` 只查键存在、不查类型**：`steps` 传字符串也能过。若追求契约强度，值得加轻量类型/shape 校验（不必上 jsonschema，几十行手写即可）。**当前设计"故意宽松"可以接受，但要明确知道它挡不住什么**。
6. **`test-result.json` / `review-result.json` 的 `nits` 不校验 file/line 而 `blockers`/`concerns` 校验**：这个不对称没有明显理由，建议统一（nits 也带位置，便于直接跳转）。
7. **`state.yaml` 模板与 walkthrough 样例字段漂移**（`text` vs `description`、`retries` 列表 vs 整数、结果大小写）：既然"project-defined 不校验"，就该在模板里**固化一种并删掉另一种**，否则每个采用者都会分叉。
8. **`rules/README.md` 标注与 `jg-planner-first.mdc` 实际 `alwaysApply` 不一致**：文档不可信会让"该不该开总闸门"这个最关键的决策失去依据。
9. **`globs` 能力文档化但零使用**：如果团队没有按文件类型触发的规则需求，**从 README 的 frontmatter 说明里降级为"可选能力"注解**即可，避免读者以为必须填。
10. **`docs/reference/agents.md` 与 `AGENTS.md` 的表格列不一致**（一个有 `Tier` 列一个没有）：同一份注册表维护两份，容易漂。建议 reference 版做单向生成或直接指向 AGENTS.md。
11. **规模适配**：8 个 agent / 15 个 agent 的完整分层路由，对**小团队或个人项目是过度设计**。可简化为：先上 practitioner 的 5 步主干（planner → worker → tester → reviewer → git），**把 tier 变体、benchmarker、team-linter、lessons.yaml 全部砍掉**；只保留 3 个最划算的机制——**artifact 契约 + plan/改动双向一致性 check + NON-GOALS 互斥矩阵**。
12. **重试上限（2 次）与评分阈值（~5%/~15%）都是硬编码的魔法数字**，未见出处或校准记录。**复用时应视为待调参的初始值，而非经验结论**。

---

## 9. 审计结论一句话版

这套仓库的核心价值**不在 agent 提示词本身**（提示词相当朴素），而在于**用最小依赖的静态校验器（`lib/*_common.py`，共 231 行）把多 agent 协作的三类经典失效——计划与实现漂移、越过失败继续跑、verdict 与 finding 不一致——变成了可执行的不变量**；其分层路由与 `lessons.yaml` 则分别提供了成本杠杆与跨 session 记忆。最需要在复用时修正的是 **`lib/` 的跨目录依赖布局**（会让模板按官方方式复制后直接不可用）与 **文档承诺/实际强制的落差**（`readonly`、`globs`、`lint-result.json`）。
