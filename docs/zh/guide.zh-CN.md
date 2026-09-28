# Rgents 使用说明（中文）

> 面向「框架部署、搭建任务、执行校验门禁」的操作手册。  
> 版本：`1.0.4`（见仓库根目录 `VERSION` 与 `.agent/framework-manifest.yaml → release`）  
> 概念总览见 [`README.zh-CN.md`](./README.zh-CN.md)；角色细节见 [`roles.zh-CN.md`](./roles.zh-CN.md)；工作流与状态机见 [`workflow.zh-CN.md`](./workflow.zh-CN.md)。

---

## 一、框架特性说明

1. **协调者是主线程扮演的角色，不是 `Task(subagent_type="orchestrator")`**  
   斜杠命令（`/spec`、`/build`…）会把主 agent 变成协调者；用 Task 工具去派发 `orchestrator` 会直接报 `not available`。

2. **Agent 之间只产出文件，不传对话**  
   交接物在 `tasks/<TASK-ID>/` 下，形状由 `.agent/schemas/` 约束，由 `validate.py` 检查。

3. **任务分目录存放，做完就挪走**  
   - `tasks/active/`：正在做的任务（勿长期堆 blocked）  
   - `tasks/completed/`：正常完成（本仓示例：`TASK-002`）  
   - `tasks/archive/`：中止、废弃、被 supersede 等（本仓示例：`TASK-004`）  
   - `tasks/fixtures/`：**仅框架仓**用来考校验器的已知病灶样例（如 `TASK-900`），不是活任务，勿挪到 `active/`

---

## 二、使用前应当检测框架完整性

在 **非 `base` 的 conda 环境**（或任意 Python 3.8+）中：

```bash
python .agent/tools/validate.py --selftest
python .agent/tools/validate.py --fixtures
python .agent/tools/validate.py --check-setup
python .agent/tools/validate.py --task TASK-002 --all
```

| 命令 | 含义 |
|---|---|
| `--selftest` | 用代码内临时样例证明各条不变量会报警（单元级 canary） |
| `--fixtures` | 用 `tasks/fixtures/` 里已知有问题的任务样例考校验器（如 TASK-900 必须报 `step_target_missing`）；框架仓自带样例，不是「默认空目录」 |
| `--check-setup` | 角色注册、工作流引用、可移植性等配置自洽 |
| `--task … --all` | 按该任务的复杂度/风险，跑适用阶段 |
| `--task … --stage X` | **仅**跑阶段 X；成功时会标注 `stage-only`（不等于全任务通过） |

返回：`0` 通过（可有 warning）；`1` 有 error；`2` 环境/路径/JSON 问题。

**Windows / conda 注意：** 不要用 `conda run -n <env> python …` 来**看** validate / selftest 的控制台输出——`conda run` 在 Windows 上常把管道设成系统默认代码页（如 GBK），非 ASCII 一打印就 `UnicodeEncodeError`。优先：

1. 先激活conda环境（**不建议**用 conda `base`），再运行 `python .agent/tools/validate.py …`；或  
2. 直接调取环境python解释器，例如  
   `path/to/envs/<your-env>/python.exe .agent/tools/validate.py …`（路径因机器而异，**勿把本机绝对路径写进仓库文档**）。

框架门禁本身只需 **PATH 上的 Python 3.8+（stdlib）**；conda/venv 是贡献者本机选择，不是框架公共依赖。

---

## 三、部署至项目（推荐：seed）

框架 checkout 与产品仓库是**两边**：种子/升级脚本留在框架侧，不会把 `seed_framework.py` 装进产品。

### 新建（目标目录必须为空）

在框架仓库根目录：

```bash
python .agent/tools/seed_framework.py create --target <产品目录绝对或相对路径>
# 可选：顺带搭最小产品骨架
python .agent/tools/seed_framework.py create --target <路径> --with-product-skeleton
```

会写入 `AGENTS.md`、`.cursor/`、`.agent/`、`docs/agents`、以及从**模板**脚手架的 `docs/knowledge/` 与可选的 `docs/architecture/`（后两者为产品自有，upgrade 不覆盖）、轻量 CI 等工作面，并记下 `.agent/seeded-from.yaml`（release + 当时框架 git HEAD）。**不会**替你 `git commit` 或加 remote。框架仓自己的架构自述**不会**被拷进产品仓。

### 更新项目

```bash
python .agent/tools/seed_framework.py upgrade --target <路径> --dry-run   # 先看计划
python .agent/tools/seed_framework.py upgrade --target <路径> --yes       # 确认后执行
```

- **会被替换（框架拥有）**：agent 定义、规则、schemas、workflows、`validate.py`、`VERSION` 等（见 manifest 的 `replaceable`）。  
- **永不覆盖（产品拥有）**：`project-baseline.yaml`、`docs/knowledge/**`、`docs/architecture/**`、`tasks/**`、**`.gitignore`**、模型目录里的 `available.yaml` 等。  
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

`init_project` 可 `git init`，但**不会**加 remote、**不会**做首次提交。环境（栈、环境管理器、权威命令）写在 `.agent/project-baseline.yaml`，由人类 + product + tech-lead 在项目级 spec/design 里确立，`status: established` 后机器才认。

---

## 四、新建任务（Cursor）

```
/spec    "业务请求"
/design  TASK-NNN
/build   TASK-NNN
/verify  TASK-NNN
/review-code TASK-NNN
/ship    TASK-NNN
```

| 命令 | 阶段 |
|---|---|
| `/spec` | 分类 + 规格（product）；agent判断为trivial时，需用户进行确认 |
| `/design` | 技术设计 + 计划（tech-lead；高风险并入相关专家） |
| `/build` | 实现（developer） |
| `/verify` | QA + 已激活专家门禁 |
| `/review-code` | 最终工程质量门禁 |
| `/ship` | 交付就绪（若需要）+ 闭环 |
| `/triage` | 处理冲突需求 |

### 复杂度与门禁（摘要）

| 复杂度 | 实例任务 | 设计/计划/评审 |
|---|---|---|
| `trivial` | 1–2 文件、单层、无新抽象、无接口变化 | 可省略 design/plan/review；**须人类确认 trivial 标签**（S1：确认后可无 `plan.json`） |
| `standard` | 跨模块或需跨层测试 | 全要 |
| `complex` | 新抽象、架构变更、并发主题、安全关键路径 | 全要 + 人类签核 |

风险决定**阻断门禁**：`low` → QA；`medium` → QA + review；`high` → 再加 security 等（以 `.agent/config.yaml` 为准）。

### 任务目录

```
tasks/
  active/       # 正在做；/ship 后应离开此目录
  completed/    # 正常完成（本仓示例：TASK-002）
  archive/      # 中止 / 废弃 / 被 supersede（本仓示例：TASK-004）
  fixtures/     # 框架自检样例（本仓：TASK-900）；产品 seed 默认不建此目录
```

- 日常用 `/spec` 在 `active/` 下建任务即可。  
- 若必须手工起任务：按 `.agent/templates/task/README.md` 在 `tasks/active/<TASK-ID>/` 落产物（仓库里**没有** `tasks/_template/` 目录）。  
- `fixtures/` 只服务 `validate.py --fixtures`，不要当业务任务使用或搬进 `active/`。

任一门禁失败 → 回到实现，并从 **QA 起整条门禁链重跑**（不能只重跑失败那一环）。

### 多 active 任务（S6）

任务实现时，会按照该任务的 `plan.affected_files` / trivial 的 worker 声明过滤 scope（S2），但多任务同时执行仍旧可能引发问题：

1. **优先串行**：一个任务 `/ship` 并 commit 产品文件后，再 `/build` 下一个。

2. **必须并行**：保证各任务 `affected_files` 不交集；或使用 `.agent/tools/parallel_worktree.py` 按任务分 worktree。

3. **不要**刻意扩大 `SCOPE_EXEMPT` 的范围或把无关文件塞进任务计划。

4. 临时脚本（`_qa_*.py`、`_score_*.py`）放在 `tasks/<ID>/` 下或删除。

### 归档（`/ship`）

必须用工具(直接让agent运行 `/ship` 即可)，不要「只复制不删」：

```bash
python .agent/tools/archive_task.py TASK-NNN
```

若 `tasks/active/<ID>/` 与 `tasks/completed/<ID>/` 同时存在，`--stage completion` 报 `archive_active_residual`。删除 active 若被环境拦截，须人类批准后再跑工具；**不得**在 active 仍在时宣称 ship 完成。

---

## 五、校验与 CI

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
2. `validate.py --fixtures`  
3. `validate.py --check-setup`  
4. regenerate governance docs + `git diff --exit-code`  
5. `validate.py --ci-changed`（仅变更触及的 `tasks/active`）

---


## 六、添加新的 Agent

1. 复制 `.agent/templates/agent.md`，写入 `.cursor/agents/`  
2. 登记到 `.agent/config.yaml`  
3. 若写产物：加入 `validate.py` 的 `ARTIFACT_WRITERS` 与对应 schema  
4. `python .agent/tools/validate.py --check-setup`  
5. 改完 agent 定义后跑 `.agent/regenerate-governance-docs.py`（若仓库提供）以刷新职责/权限矩阵  

**不要**给需要写产物的角色设 `readonly: true`——Cursor 的该标志会拿掉全部写工具，角色会在第一次写文件时失败。

---

## 七、说明文档

| 文档 | 内容 |
|---|---|
| [`README.zh-CN.md`](./README.zh-CN.md) | 框架设计、团队构成、门禁一览 |
| [`roles.zh-CN.md`](./roles.zh-CN.md) | 12 角色职责与 NON-GOALS |
| [`workflow.zh-CN.md`](./workflow.zh-CN.md) | 工作流、重复需求裁决、返工、校验速查 |
| **本文 `guide.zh-CN.md`** | 种子化 / 日常命令 / 环境 / CI 操作说明 |
| 仓库根 `AGENTS.md` / `README.md` | 英文宪法与总览（Agent 默认先读英文） |

框架维护者本地的架构备忘（`docs/architecture/`）**不发布到 GitHub**（gitignore）。产品仓可在 seed 时从 `.agent/templates/architecture/` 得到空白模板，之后完全自有，upgrade 不覆盖。
