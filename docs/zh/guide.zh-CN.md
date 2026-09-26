# Rgents 使用说明（中文）

> 面向「把框架接到产品仓库、日常开任务、跑门禁」的操作手册。  
> 版本：`1.0.1`（见仓库根目录 `VERSION` 与 `.agent/framework-manifest.yaml → release`）  
> 概念总览见 [`README.zh-CN.md`](./README.zh-CN.md)；角色细节见 [`roles.zh-CN.md`](./roles.zh-CN.md)；工作流与状态机见 [`workflow.zh-CN.md`](./workflow.zh-CN.md)。

---

## 一、你应该先搞清的三件事

1. **协调者是主线程扮演的角色，不是 `Task(subagent_type="orchestrator")`。**  
   斜杠命令（`/spec`、`/build`…）会把主 agent 变成协调者；用 Task 工具去派发 `orchestrator` 会直接报 `not available`。
2. **Agent 之间只传产物路径，不传对话。**  
   交接物在 `tasks/<TASK-ID>/` 下，形状由 `.agent/schemas/` 约束，由 `validate.py` 检查。
3. **`tasks/active/` 是活任务区，做完就释放。**  
   本仓库不长期挂 blocked 示例任务。对照产物形状请看 `tasks/completed/TASK-002/`（trivial 完成例）或 `tasks/archive/TASK-004/`（高风险 intake 归档）。

---

## 二、在本仓库里先自证框架可用

在 **非 `base` 的 conda 环境**（或任意 Python 3.8+）中：

```bash
python .agent/tools/validate.py --selftest
python .agent/tools/validate.py --check-setup
python .agent/tools/validate.py --task TASK-002 --all
```

| 命令 | 含义 |
|---|---|
| `--selftest` | 用故意造坏的输入证明不变量会报警 |
| `--check-setup` | 角色注册、工作流引用、可移植性等配置自洽 |
| `--task … --all` | 按该任务的复杂度/风险，跑适用阶段 |

退出码：`0` 通过（可有 warning）；`1` 有 error；`2` 环境/路径/JSON 问题。

**Windows / conda 注意：** 不要用 `conda run -n <env> python …` 来**看** validate / selftest 的控制台输出——`conda run` 在 Windows 上常把管道设成系统默认代码页（如 GBK），非 ASCII 一打印就 `UnicodeEncodeError`。优先：

1. 先 `conda activate <env>`（**不要**用 `base`），再直接 `python .agent/tools/validate.py …`；或  
2. 直调解释器，例如 `E:\Conda\envs\vi\python.exe .agent/tools\validate.py …`。

`validate.py` / `archive_task.py` 启动时会尽量把 stdout/stderr 设为 UTF-8，但仍无法修好 `conda run` 自身的包装层。

---

## 三、接到产品仓库（推荐：seed）

框架 checkout 与产品仓库是**两边**：种子/升级脚本留在框架侧，不会把 `seed_framework.py` 装进产品。

### 新建（目标目录必须为空）

在框架仓库根目录：

```bash
python .agent/tools/seed_framework.py create --target <产品目录绝对或相对路径>
# 可选：顺带搭最小产品骨架
python .agent/tools/seed_framework.py create --target <路径> --with-product-skeleton
```

会写入 `AGENTS.md`、`.cursor/`、`.agent/`、`docs/agents|knowledge|architecture`、轻量 CI 等工作面，并记下 `.agent/seeded-from.yaml`（release + 当时框架 git HEAD）。**不会**替你 `git commit` 或加 remote。

### 升级已种子化的产品

```bash
python .agent/tools/seed_framework.py upgrade --target <路径> --dry-run   # 先看计划
python .agent/tools/seed_framework.py upgrade --target <路径> --yes       # 确认后执行
```

- **可替换（框架拥有）**：agent 定义、规则、schemas、workflows、`validate.py`、`VERSION` 等（见 manifest 的 `replaceable`）。  
- **永不覆盖（产品拥有）**：`project-baseline.yaml`、`docs/knowledge/**`、`tasks/**`、**`.gitignore`**、模型目录里的 `available.yaml` 等。  
  - `.gitignore`：`create` 时仍会写入一份起步模板；之后产品可自由加规则（如 `out/`），`upgrade` 不再整文件替换。
- 升级前会在产品侧 `.rgents/upgrade-backups/` 留备份。

### 产品侧初始化

进入产品仓库后：

```bash
python .agent/tools/init_project.py
python .agent/tools/init_project.py --ensure-baseline
python .agent/tools/init_project.py --refresh-models
# 优先：Cursor Agent CLI（`agent models` / `--list-models`）→ 账号下完整可派发目录
# 其次：cursor_sdk / CURSOR_API_KEY（Cloud Agents 推荐子集，常偏窄）并与 seed 并集
# 最后：seed.yaml。密钥永不写入 available.yaml。
# 未装 CLI 时请安装并登录：https://cursor.com/docs/cli/overview → agent login
```

`init_project` 可 `git init`，但**不会**加 remote、**不会**做首次提交。基线（栈、环境管理器、权威命令）写在 `.agent/project-baseline.yaml`，由人类 + product + tech-lead 在项目级 spec/design 里确立，`status: established` 后机器才认。

---

## 四、日常开任务（Cursor）

```
/spec    "一句话业务请求"
/design  TASK-NNN
/build   TASK-NNN
/verify  TASK-NNN
/review-code TASK-NNN
/ship    TASK-NNN
```

| 命令 | 阶段 |
|---|---|
| `/spec` | 分类 + 规格（product）；trivial 需人类确认分类标签 |
| `/design` | 技术设计 + 计划（tech-lead；高风险并入相关专家） |
| `/build` | 实现（developer） |
| `/verify` | QA + 已激活专家门禁 |
| `/review-code` | 最终工程质量门禁（避开 Cursor 内置 `/review`） |
| `/ship` | 交付就绪（若需要）+ 闭环 |
| `/triage` | 新请求分类，或把失败路由回拥有者 |

### 复杂度与门禁（摘要）

| 复杂度 | 典型范围 | 设计/计划/评审 |
|---|---|---|
| `trivial` | 1–2 文件、单层、无新抽象、无接口变化 | 可省略 design/plan/review；**须人类确认 trivial 标签**（S1：确认后可无 `plan.json`） |
| `standard` | 跨模块或需跨层测试 | 全要 |
| `complex` | 新抽象、架构变更、并发主题、安全关键路径 | 全要 + 人类签核 |

风险决定**阻断门禁**：`low`→QA；`medium`→QA+review；`high`→再加 security 等（以 `.agent/config.yaml` 为准）。

### 任务目录

```
tasks/
  active/      # 正在做的任务；测完/做完就移走
  completed/   # 正常完成
  archive/     # 废弃、被 supersede、未跑完等
  _template/   # 手工起任务时可复制
```

任一门禁失败 → 回到实现，并从 **QA 起整条门禁链重跑**（不能只重跑失败那一环）。

### 多 active 任务与工作区卫生（S6）

实现门按**本任务** `plan.affected_files` / trivial 的 worker 声明过滤 scope（S2），但同树多任务仍易乱：

1. **优先串行关闭**：一个任务 `/ship` 并 commit 产品文件后，再 `/build` 下一个。
2. **必须并行时**：保证各任务 `affected_files` 不交集；或使用 `.agent/tools/parallel_worktree.py` 按任务分 worktree。
3. **不要**为过门扩大 `SCOPE_EXEMPT` 或把无关文件塞进本任务 plan。
4. 临时脚本（`_qa_*.py`、`_score_*.py`）放在 `tasks/<ID>/` 下或删除，勿提交到产品树。

### 归档（`/ship`）

必须用工具，禁止「只复制不删」：

```bash
python .agent/tools/archive_task.py TASK-NNN
```

若 `tasks/active/<ID>/` 与 `tasks/completed/<ID>/` 同时存在，`--stage completion` 报 `archive_active_residual`。删除 active 若被环境拦截，须人类批准后再跑工具；**不得**在 active 仍在时宣称 ship 完成。

---

## 五、环境确认（实现前必问）

在跑构建、lint、类型检查或测试命令之前，协调者必须让人类确认：

- 运行时与版本  
- 环境管理器以及**当前激活的环境**（勿在 conda `base` 里装包装包）  
- 权威命令（来自 baseline）  
- 依赖服务是否就绪  
- 当前 revision 上套件是否本就绿  

未确认就猜 → 假缺陷、错路由、整轮返工。记录落在 `worker-result.json → environment`。

---

## 六、校验与 CI

### 本地常用

```bash
# 单产物
python .agent/tools/validate.py --artifact tasks/completed/TASK-002/qa-report.json

# 单阶段
python .agent/tools/validate.py --task TASK-002 --stage qa

# 适用的全部阶段
python .agent/tools/validate.py --task TASK-002 --all

# CI 形态：只对自 --base 以来改动过的 tasks/active/* 做 --all（形状检查，不重跑产品测试）
python .agent/tools/validate.py --ci-changed --base origin/main
```

要点：

- **信任 developer/QA 报告里的测试结果**；框架 CI **不**重放产品测试套件。  
- QA 的 `PASS` 须在 `validate_log_ids` 里引用至少一条成功的 `tasks/<ID>/logs/validate-*.json`（C4）。跑 `--all` 会写出新 log；示例任务只需保留被引用的那份即可。
- **plan 阶段（KI-005）：** 若 `design.json` 有 `data_model` 且 plan 步骤含 DDL，校验 `plan_ddl_nullability`（例如 `TEXT PRIMARY KEY` 无 `NOT NULL` 而设计要求非空 → 失败）。
- **模型目录：** `--refresh-models` 优先 Agent CLI；仅靠 Cloud Agents API 往往拿不到 IDE 里全部第三方模型。

### GitHub Actions

工作流：`.github/workflows/framework-ci.yml`（`framework-ci`）

1. `validate.py --selftest`  
2. `validate.py --check-setup`  
3. `validate.py --ci-changed`（仅变更触及的 `tasks/active`）

---

## 七、人类必须插手的时刻

| 场景 | 为什么 |
|---|---|
| 需求含未决产品决策 | 猜错 = 整轮返工 |
| 新请求与 active 任务可能重复 | 协调者只打分，**裁决**（reuse / supersede / new）归人 |
| 新请求与**已完成**任务 likely 相似 | 可记录分数；**不**强制人裁（S5）；`outcome=new` 仍须 rationale |
| 未确认开发环境 | 见上一节 |
| 不可逆变更（迁移、删数据、轮换密钥） | 人类拥有不可逆操作 |
| security `critical` 无法在本任务内修 | 升级，不绕过 |
| 同一阶段连续失败三次 | 停下来查根因 |
| 要改 `.cursor/**`、`.agent/**`、`AGENTS.md` | 治理面人类拥有；Agent 只能提案 |
| `high` 风险任务收尾 | 最终人类签核 |

---

## 八、扩展团队时（人类操作）

1. 复制 `.agent/templates/agent.md`，写入 `.cursor/agents/`  
2. 登记到 `.agent/config.yaml`  
3. 若写产物：加入 `validate.py` 的 `ARTIFACT_WRITERS` 与对应 schema  
4. `python .agent/tools/validate.py --check-setup`  
5. 改完 agent 定义后跑 `.agent/regenerate-governance-docs.py`（若仓库提供）以刷新职责/权限矩阵  

**不要**给需要写产物的角色设 `readonly: true`——Cursor 的该标志会拿掉全部写工具，角色会在第一次写文件时失败。

---

## 九、文档地图

| 文档 | 内容 |
|---|---|
| [`README.zh-CN.md`](./README.zh-CN.md) | 设计动机、团队构成、门禁一览 |
| [`roles.zh-CN.md`](./roles.zh-CN.md) | 12 角色职责与 NON-GOALS |
| [`workflow.zh-CN.md`](./workflow.zh-CN.md) | 工作流、重复需求裁决、返工、校验速查 |
| **本文 `guide.zh-CN.md`** | 种子化 / 日常命令 / 环境 / CI 操作说明 |
| 仓库根 `AGENTS.md` / `README.md` | 英文宪法与总览（Agent 默认先读英文） |

英文审计与设计笔记仍在 `docs/architecture/`、`refers/`；与本文冲突时，以 `.agent/config.yaml` 与 agent 定义文件为准。
