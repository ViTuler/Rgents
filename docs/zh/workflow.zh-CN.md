# 工作流、门禁与状态机

本文说明任务如何在团队中流动、门禁如何判定、失败如何路由，以及状态如何被记录和续跑。

---

## 一、四条工作流

工作流是**声明式**的，定义在 `.agent/workflows/*.yaml`。协调者读取它决定阶段顺序。
阶段顺序是权威的，**到达的门禁不是可选项**。

选择哪条工作流由 `intake.json → type` 决定。

| 工作流 | 用于 | 优化目标 | 特殊之处 |
|---|---|---|---|
| `feature` | 新能力、用户可见改动 | 正确性 | 标准五阶段全流程 |
| `bugfix` | 恢复**已被规定**但当前错误的行为 | 定位根因 | 先复现再修；**每个修复必须带回归测试** |
| `refactor` | 改结构，不改可观测行为 | 行为等价 | 先做**特征化基线**；行为变化必须申报 |
| `incident` | 生产降级或不可用 | **恢复时间** | 顺序刻意反转：先止血，后理解，最后复盘 |

### `feature`

```
intake → specification → design → planning → [ux] → implementation
       → [database] → qa → [security] → [performance] → [data]
       → review → [devops] → completion
```

`[...]` 表示按条件激活。

### `bugfix`

```
intake → reproduction(先复现) → [diagnosis] → implementation
       → [database] → qa → [security] → review → [devops] → completion
```

关键规则：

- **无法复现的缺陷还没有被理解**，不要据此猜测实现
- **修因不修果**。在调用点加一个守卫不是根因修复
- **没有回归测试的修复一定会再退化**
- 如果观察到的行为**符合需求规定**，这就不是 bugfix——按 feature 或需求变更路由

### `refactor`

```
intake → baseline(先做特征化) → design → planning → implementation
       → [database] → [performance] → qa → review → completion
```

关键规则：

- **行为要变就不是重构**，是 feature 或 bugfix。误分类的重构是"小清理"上线回归事故的根源
- **没有先捕获行为，就无法证明行为被保留**
- 一个让复杂度上升的重构是失败的
- 被迫改变的行为必须申报，**不能夹带**

### `incident`

```
intake → triage_evidence(先取证) → mitigation(先止血)
       → [security] → qa → [database] → review
       → postmortem → prevention_verification
```

关键规则：

- **恢复优先于流程**。证据采集是强制的，但**绝不能延迟止血**
- **改动前先捕获状态**。止血之后再取证只能靠猜
- **优先回滚或关闭开关**，而不是在压力下向前修
- 复盘没有产出后续任务和经验条目，就等于没有复盘
- 预防工作**成为新任务**，绝不追加到本次事件的范围里

---

## 二、门禁

### 门禁顺序（固定）

```
qa → security → performance → ux → database → data → review → devops
```

- `security` 可以在计划声明安全时**与 `qa` 并行**运行
- `review` **始终等待** QA 与所有已激活的专家门禁
- `devops` 在 `review` 之后

### 通过条件

| 门禁 | 产物 | 通过条件 |
|---|---|---|
| `qa` | `qa-report.json` | `verdict == PASS`，每条验收标准都有结论，无未决 critical/major 发现 |
| `security` | `security-report.json` | `verdict == PASS`，无未决 critical/high 发现 |
| `performance` | `perf-report.json` | `verdict == PASS` 或被合理说明的 `SKIP` |
| `ux` | `ux-report.json` | `verdict == PASS` 或被合理说明的 `SKIP` |
| `database` | `db-report.json` | `verdict == PASS` 或被合理说明的 `SKIP` |
| `data` | `data-report.json` | `verdict == PASS` 或被合理说明的 `SKIP` |
| `review` | `review-report.json` | `verdict == PASS` 且 `blockers` 与 `concerns` **都为空** |
| `devops` | `delivery-report.json` | `verdict == PASS` 或被合理说明的 `SKIP` |

### 三条最重要的门禁规则

1. **没有产物 = 门禁没跑，绝不推断为通过。**
   不得从门禁的口头总结、从缺失的报告、或从实现者的信心推断通过。
   校验器对此报 `gate_not_run`。

2. **阻断性发现不可协商。**
   `security` / `database` / `performance` / `devops` 提出的阻断项，
   `developer`、`tech-lead`、`orchestrator` **都不能降级或豁免**。
   只有提出它的专家能用证据解除它。

3. **`PASS` 不能夹带阻断物料。**
   `verdict == PASS` 时，`blockers`、`concerns`、失败的验收标准、未决的 critical/high 发现
   **都必须为空**。校验器报 `verdict_consistent`。

### 条件门禁：按风险定流程

门禁**不是仪式**。按 `complexity` 与 `risk` 决定激活哪些。

| 复杂度 | 定义 | 必需角色 | design | plan | review |
|---|---|---|---|---|---|
| `trivial` | 1–2 文件、单层、无新抽象、无接口变更 | developer, qa | ✗ | ✗ | ✗ |
| `standard` | 3+ 文件，或跨层，或需要跨模块测试 | product, tech-lead, developer, qa, reviewer | ✓ | ✓ | ✓ |
| `complex` | 新抽象、架构变更、并发、安全关键路径 | 同上 + 人类签核 | ✓ | ✓ | ✓ |

| 风险 | 定义 | 阻断门禁 |
|---|---|---|
| `low` | 无用户可见、安全、数据完整性或可用性影响 | qa |
| `medium` | 用户可见行为变化，但可逆且不敏感 | qa, review |
| `high` | 触及认证授权、密钥、支付、个人数据、不可逆数据操作、生产运行时 | qa, **security**, review |

**分类必须可审计**：`intake.json → classification_rationale` 要求说明为什么是这个复杂度和风险，
引用 `.agent/config.yaml` 里的定义。**如果你无法论证一个 `trivial` 分类，它就不是 trivial。**

### 专家激活

| 专家 | 触发条件（节选） |
|---|---|
| `ux` | 新的用户界面/页面/弹窗/流程；用户可见的文案或布局；交互或状态变化 |
| `security` | 认证授权；用户输入到达持久化或 shell；密钥凭据；支付金融流；个人敏感数据；新外部依赖；新公开端点 |
| `database` | 表结构变更；新增迁移；大表上的新查询；事务或隔离语义；索引或约束变更；数据回填 |
| `performance` | 声明了延迟/吞吐预算；热路径改动；无界输入上的新循环；N+1 或全表扫描风险；大载荷或流式；引入缓存或并发 |
| `data` | 新增/变更分析事件；指标或看板依赖；ETL/ELT 变更；实验或特性开关度量 |
| `devops` | 构建或 CI 变更；交付面变化（Dockerfile、IaC、环境变量、entrypoint）；新运行时依赖或服务；配置或密钥处理变更；可观测性或健康检查变更 |

**跳过必须记录原因。** `intake.json → skipped_specialists` 是一个 `{specialist, reason}` 数组。
静默跳过专家是这套流水线产出"自信的错结果"最常见的方式，因此它是一个协议违规。

---

## 三、任务状态机

```
                          ┌─────────────────┐
                          │   CLASSIFIED    │  intake.json 写入
                          │                 │  ★ 含重复需求比对
                          └────────┬────────┘
                                   ↓
                     ┌─────────────────────────┐
                     │  重复需求裁决（强制）      │
                     │  命中 → 人类决定          │
                     │  new / reuse / supersede │
                     └────────────┬────────────┘
                                  ↓
                          ┌─────────────┐
                          │ SPECIFIED   │  requirements.json
                          └──────┬──────┘   ← open_questions 非空则停下问人类
                                 ↓
                          ┌─────────────┐
                          │  DESIGNED   │  design.json
                          └──────┬──────┘
                                 ↓
                          ┌─────────────┐
                          │  PLANNED    │  plan.json
                          └──────┬──────┘
                                 ↓
                          ┌─────────────┐
                          │IMPLEMENTING │  worker-result.json
                          └──────┬──────┘
                                 ↓
              ┌──────────────────┴──────────────────┐
              │           GATE CHAIN                │
              │  qa → security → database → ...     │
              │           → review → devops         │
              └──────────────────┬──────────────────┘
                                 │
                    ┌────────────┴────────────┐
                    ↓                         ↓
              ┌───────────┐            ┌───────────┐
              │  FAILED   │            │  PASSED   │
              └─────┬─────┘            └─────┬─────┘
                    │                        ↓
                    │                  ┌───────────┐
                    │                  │  SIGN-OFF │  (complex 或 high risk)
                    │                  └─────┬─────┘
                    │                        ↓
                    │                  ┌───────────┐
                    │                  │COMPLETED  │
                    │                  └───────────┘
                    │
                    ↓
        路由给缺陷拥有者 → IMPLEMENTING
        （整条门禁链从 qa 重跑）
```

`task.yaml` 是续跑锚点：

| 字段 | 用途 |
|---|---|
| `status` | `in_progress` / `blocked` / `completed` / `failed` / `paused` |
| `current_stage` | 从这里继续 |
| `acceptance_criteria[].status` | 三态：`pending` → `implemented` → `verified` |
| `stages.<stage>.artifact_path` | 指针而非内联内容 |
| `retries` / `routing_decisions` | 为什么任务在现在这个位置 |
| `blocking_items` | 当前阻断项 + 修复清单 |

**任何人——Agent 或人类——都必须能仅凭产物从 `task.yaml` 续跑。**
不要在续跑时从对话重新推导之前阶段，也不要重跑输入未变的阶段。

---

## 四、返工与升级

### 返工路由

失败**总是路由给缺陷的拥有者**，而不是绕过门禁。
归属错误是最贵的路由错误，因为它把修复送给了做不到的 Agent。

| 缺陷类别 | 症状 | 路由给 |
|---|---|---|
| `implementation_defect` | 行为与设计或验收标准不符 | `developer` |
| `requirement_defect` | 验收标准本身错了、含糊、矛盾 | `product` |
| `design_defect` | 接口或计划无法满足需求 | `tech-lead` |
| `test_defect` | 断言写错，或测试脚手架坏了 | `qa` |
| `unclear_scope` | 无法确定什么在工作范围内 | `orchestrator`（重新分类） |

### 重跑规则

**失败返回门禁链的起点，不是局部打补丁。**

修复会使之前的验证失效：QA 在改动前通过，不代表改动后通过。
因此任务从 `qa` **重新进入**，走完整条链。局部重跑不是一个可用选项。

### 预算

| 预算 | 值 | 超出后 |
|---|---|---|
| 每阶段重试 | 2 | 升级到人类 |
| 总循环 | 3（`incident` 为 5） | 升级到人类 |
| 升级次数 | **不计入重试预算** | — |

### 升级是廉价且被鼓励的

> 一个不确定的 Agent 应当升级，而不是猜测。**猜测是错误的昂贵路径。**

**升级给技术经理**：

- 设计含糊或内部不一致
- 完成任务需要改架构
- 专家发现与已批准的设计冲突

**升级给人类**：

- 需求含糊或产品决策未决
- 改动不可逆
- 安全 `critical` 发现无法在本次范围内修复
- 同一阶段失败三次
- 需要改治理面（`.cursor/**`、`.agent/**`、`AGENTS.md`、`docs/agents/**`）
- 风险为 `high` 且任务已就绪待完成

---

## 五、并行执行

**默认顺序执行。** 只有同时满足以下全部条件才允许并行：

- 计划把它们声明在同一个 `parallel_group`
- 各工作流写入**不相交的文件集**
- 没有工作流消费另一个仍在定义的接口
- 没有工作流触及共享的 schema、迁移或公开契约

**无条件禁止**：

- 两个 Agent 编辑同一个文件
- 前端消费仍在设计中的 API 契约
- 计划标记为有依赖的步骤并行执行

不满足并行安全条件时，顺序执行是默认值，**不是失败**。

---

## 六、重复需求裁决（强制）

**问题**：流水线原有的不变量都是"任务对自己"的检查（计划 vs 自己的 diff）。**没有任何检查能发现两个
active 任务在描述同一需求**——结果是两套分歧的需求都看起来权威。这个缺口是真实发生过的：
历史上 TASK-003 与 TASK-004 由同一句请求创建（两任务均已从本仓库示例中移除或归档），当时谁都没发现。

**做法**：在分配任务 ID 之前，把请求与每个 active 任务比对，结果写进 `intake.json → overlap_check`。

### 比对方式：两种取最大值

| 方式 | 语料 | 擅长捕获 |
|---|---|---|
| `request_narrow` | 仅标题 + 请求原文 | **近乎逐字重复**——同一句话会打到约 1.0 |
| `document_broad` | 标题 + 请求 + 目标 + 全部验收标准 | **换一种说法描述的同一功能**，包括跨语言 |

单一方法都不够：只看标题请求会**完全漏掉**换语言重述的情况（实测 0.0）；只看全文档会把同一请求
稀释到 0.29。所以取两者最大值。

### 阈值是实测校准的，不是拍的

以本仓库早期示例任务为样本（TASK-001 / TASK-003 已从仓库移除，数字仍作阈值校准依据），**应用停用词与别名之后**的实测值：

```
TASK-004 vs TASK-003  同一请求，逐字重述     1.0000   (narrow)
TASK-003 vs TASK-001  同一功能，措辞不同     0.3714   (broad)
TASK-004 vs TASK-001  同一功能，措辞不同     0.2745   (broad)
任一任务 vs TASK-002  无关（改文案）         0.0000 ~ 0.0096
```

0.01 到 0.27 之间是一条**很宽的空带**。阈值设在空带里：`likely: 0.24`、`possible: 0.12`，
再用 `min_shared_tokens` 过滤掉最后一点噪声。

**为什么必须做跨语言别名映射**：纯词面比对看不出 `邀请同事` 和 `invite a colleague` 是同一件事。
实测中这一条把"同一请求"与"无关任务"的差距从 9 倍拉到 **28 倍**，共享词从 45 个（大半是
`the` `to` `is` 这类噪声）降到 32 个实义词。

### 裁决由人类做，不由协调者做

命中 `likely` 时，**协调者可以跑比对，但不得拍板**：

- 选 `new` 会把已在推进的工作**静默分叉**成两套需求
- 选 `reuse` 会**丢弃请求者真正要的东西**

两者都是人类的决定。协调者的职责是把分值和共享词摆到人面前，并记录 `decision.decided_by: human`。

| 裁决 | 含义 | 强制检查 |
|---|---|---|
| `new` | 作为独立任务推进 | 存在匹配时必须给 `rationale` |
| `reuse` | 复用既有任务 | **不应存在新任务目录**——存在即报错 |
| `supersede` | 本任务取代指定任务 | 被取代的任务**必须已归档**——仍在 `active/` 即报错 |
| `no_overlap` | 无匹配达到阈值 | 仍须显式记录 |

### 两条容易忽略的规则

1. **即使什么都没匹配到，也必须记录 `no_overlap`**。一条未记录的"没找到"和"根本没检查"在产物上
   无法区分。校验器对静默的 intake 报 `overlap_check_missing`。
2. **启发式会漏也会误报，两种情况都走 `override` 且必须给理由**：
   `false_positive`（匹配真实存在但不构成竞争，比如框架自带的示例任务）、
   `missed_match`（真实重叠但打分没抓到）。**没有理由的 override 是错误。**

### 验证

```bash
python .agent/tools/validate.py --task <TASK-ID> --stage duplicate_check
```

## 七、开发环境确认门禁（强制，先于一切命令）

**规则**：在跑任何 build / lint / typecheck / test 命令之前，环境必须与人类确认。

### 为什么这不是流程表演

环境不对时，`npm test` 或 `pytest` 会报 `command not found`、`ModuleNotFoundError`、或版本不匹配的错误。
**这些输出看起来和"测试失败"一模一样。** 于是：

```
错误环境 → 命令报错 → 被读成测试失败 → 被当成实现缺陷
        → 路由给 developer → 一整轮错误的返工
```

而问题从来不在代码里。**确认花一条消息，不确认花一个完整返工周期。**

### 要探测并报告什么

不要自己默默选一个，**探测后报告，让人确认**：

| 项 | 去哪里看 |
|---|---|
| 语言运行时与版本 | `.nvmrc`、`.python-version`、`package.json` 的 `engines`、`requires-python` |
| 环境管理器 | `environment.yml`、`conda*.yaml`、`pyproject.toml`、`venv`、`Dockerfile` |
| 包管理器与锁文件 | `package-lock.json` / `pnpm-lock.yaml` / `poetry.lock` / `uv.lock` |
| **机器上实际有哪些环境** | 如 `conda env list`，以及**当前激活的是哪一个** |
| 需要的服务 | 数据库、缓存、队列、邮件捕获、对象存储 |
| 需要的配置 | 文档或 `.env.example` 里列出的环境变量 |
| 安装/迁移/填充命令 | 项目自己文档化的那套 |
| **改动前的基线状态** | 改动前测试套件是否通过——这条把"新增失败"和"既有失败"分开 |

### 要问人类什么（一次问完）

1. 用哪个环境（确切名称/版本）？
2. install / lint / typecheck / test 的权威命令分别是什么？
3. 需要哪些服务在跑？已经跑了吗？
4. 需要哪些配置值？
5. 改动前套件在当前版本上是通过的吗？

**人类没回答就停下等**。不要猜，也不要退回到"默认激活的那个"。

### 确认之后

- 严格用确认过的环境和命令，**不要自己换一套**
- 把确认结果记进 `worker-result.json → environment`，含 `confirmed_by_user: true`
- **校验器会拒绝没有环境确认的实现报告**（`environment_unconfirmed`）

### 环境失败 ≠ 代码缺陷

如果命令失败，记录**真实输出**。由环境导致的失败是**环境问题**，不是实现缺陷——但**也不能拿它当跳过验证的借口**。
先把环境修好，再重跑。

### 绝不做

- 未经确认就对某个环境执行**变更性命令**
- 不说一声就 `conda activate` / `nvm use` / 全局装包
- 实际输出是 `command not found` 却报告"测试失败"
- 运行中途静默切换环境
- 把缺失的工具当成代码缺陷——那是环境发现

### 既有失败

**改动前先建立基线。** 一个本来就部分失败的套件必须被记录为如此，否则每个既有失败都会被算到本次改动头上——
这是自动化流水线里最常见、也最浪费的返工来源。

### 验证

```bash
python .agent/tools/validate.py --artifact tasks/active/<TASK-ID>/worker-result.json
```

`environment.confirmed_by_user` 不为 `true` 即报错。

## 八、人类的介入点

团队在以下情况必须停下并问人类：

| # | 情形 |
|---|---|
| 1 | 需求含糊，或存在未决的产品决策（`open_questions` 非空） |
| 2 | 改动不可逆（存量数据上的 schema 迁移、删除、凭据轮换） |
| 3 | 安全 `critical` 发现无法在本次范围内修复 |
| 4 | 同一阶段失败三次 |
| 5 | 需要修改治理面 |
| 6 | 风险为 `high` 且任务待完成（最终人类签核） |

> **问一次花一条消息。猜错花一个完整返工周期。**

### 人类独占的操作

Agent **永不执行**，也永不变通执行：

- 合并 PR
- force push
- 推送到受保护分支
- `git commit --no-verify` 或任何跳过钩子的标志
- 删除或清空生产数据
- 轮换、泄露或提交凭据
- 对共享或生产系统执行破坏性命令
- 对生产执行部署或迁移

`/ship` 只是**确认就绪并闭环任务**；合并与部署由**人类**执行。

---

## 九、治理面：人类所有

Agent 可以**读**，但绝不能**写**：

- `AGENTS.md`
- `.cursor/rules/**`、`.cursor/agents/**`、`.cursor/skills/**`、`.cursor/commands/**`
- `.agent/**`
- `docs/agents/**`

需要变更治理时，Agent 应当：

1. 在自己的报告产物里写出提案，指明**确切文件**与**确切改动**
2. 说明它解决的具体问题，以及没有它时出了什么错
3. 经协调者升级给人类

**由人类实施。**

这个边界是刻意的：**如果 Agent 可以改写自己的约束，那么每一条约束都会侵蚀成当时最方便的那一条。**

---

## 十、命令速查

| 命令 | 作用 |
|---|---|
| `/spec <请求>` | 分类 + 产出可测试需求 |
| `/design <任务ID>` | 技术设计与实现计划 |
| `/build <任务ID>` | 实现 |
| `/verify <任务ID>` | 功能验证 + 已激活的专家评估 |
| `/review-code <任务ID>` | 最终工程质量门禁（命令名带 `-code` 是为了避开 Cursor 内置的 `/review`） |
| `/ship <任务ID>` | 交付就绪确认 + 闭环 |
| `/triage [请求\|失败任务]` | 分类新请求，或把失败路由给缺陷拥有者 |

每个命令都会委派给 `orchestrator`。**不要在主线程里自己做分类。**

## 十一、校验命令速查

```bash
# 证明不变量的确会报警（17 项 canary）
python .agent/tools/validate.py --selftest

# 校验框架自身配置的一致性
python .agent/tools/validate.py --check-setup

# 校验单个产物
python .agent/tools/validate.py --artifact tasks/completed/TASK-002/qa-report.json

# 校验某个阶段的不变量
python .agent/tools/validate.py --task TASK-002 --stage duplicate_check
python .agent/tools/validate.py --task TASK-002 --stage qa
python .agent/tools/validate.py --task TASK-002 --stage completion

# 跑该任务适用的全部阶段（按分类自动跳过不适用的阶段）
python .agent/tools/validate.py --task TASK-002 --all
```

退出码：`0` 全部通过（允许 warning）；`1` 有 error（门禁未通过）；`2` 环境错误（路径、文件、JSON 问题）。
