# AGENTS.md

## Project Intent

`okx-bot` 是一个研究、挖掘加密货币交易策略、因子的工程，交付多个独立的算法脚本与独立形态，在 okx 交易所上自动化算法交易。

本仓库为应用层产品形态（交付为多个独立算法脚本：backtest、paper、live 三类 runner，加上 strategies 因子与 reports 产出物），非框架核心项目。

仓库是事实的来源（source of truth，简称 SoT），聊天会话只是临时的工作面。

## 语言偏好

请使用简体中文表达，避免 AI 翻译腔（AI味）和机翻硬翻，可保留英语术语，并在旁用简中一句话简单解释术语。在编写文档时必须调用 skills `.agents/skills/chinese-documentation/SKILL.md`。

## 基本准则

- 写文档的时候，先调用 `.agents/skills/chinese-documentation/SKILL.md` 中的技能规范，再根据规范编写文档。
- 文档尽可能保持采用简体中文本土习惯表达；如果一定要用英文术语，要在英文术语附近补充对应的中文含义理解（注解）。

## Read This First

开始任何非琐碎工作前，AI 必须先快速扫读以下文件，确认任务路由和当前基线：

- `docs/requirements/product-scope.md` —— 当前产品范围、目标用户、边界
- `docs/requirements/` 下文件名带最新日期的文档 —— 现行需求基线
- `docs/design/app-overview.md` 与 `docs/design/feature-inventory.md` —— 应用层设计基线
- `docs/architecture/project-vision.md` —— 高层架构与工程吸引子
- `docs/architecture/strategy-and-factor-constraints.md` —— 策略与因子硬约束
- `docs/plans/` 下文件名带最新日期、未结案的文档 —— 当前进行中的方案
- `docs/logs/{year}/{month}-{day}.md` 中最近 1 至 3 天的日志 —— 近期变更基线
- `docs/strategies/00-strategy-template.md` 与 `docs/strategies/00-strategy-review-checklist.md` —— 策略模板与评审清单
- `docs/input/` 中文件名带最新日期的 PM 原始输入 —— 需求溯源

按需补充阅读：

- `docs/architecture/okx-sdk-rules.md`、`docs/architecture/python-env-rules.md`、`docs/architecture/sys-proxy-rules.md` —— 技术栈细节
- `docs/architecture/backtest-exit-klines-alignment-checklist.md` —— 回测/实盘对齐检查
- `docs/discussions/` —— 历史决策与未决问题
- `docs/bugs/` —— 已知的非显而易见退化
- `docs/retrospectives/` —— 历史实现与原型偏差
- `docs/audit/00-audit-execution-guide.md` —— 审计流程规范
- `docs/plans/00-plan-authoring-and-execution-guide.md` —— 方案编写与执行规范
- `docs/logs/00-log-writing-guide.md` —— 日志格式规范
- `docs/requirements/00-requirement-synthesis-guide.md` —— 需求合成规范
- `docs/input/00-input-processing-guide.md` —— 原始资料录入规范

## Task Routing

动手前必须先给任务分类，再决定后续动作：

1. 判断任务类型（六选一，可多选但需声明主次）：
   - requirement clarification（需求澄清）→ 主要读写 `docs/discussions/`、`docs/requirements/`
   - app-layer design change（应用层设计变更）→ 主要读写 `docs/design/`
   - architecture change（架构变更）→ 主要读写 `docs/architecture/`
   - implementation-only change（纯实现变更）→ 仍须确认 `docs/requirements/`、`docs/design/` 是否需要同步
   - bug investigation（缺陷调查）→ 读 `docs/bugs/`，必要时新建
   - verification or audit work（验证或审计）→ 读 `docs/audit/00-audit-execution-guide.md`
2. 用 `docs/skills/README.md` 检索候选可复用技能，确认调用前置条件满足
3. 触发方案编写条件时（非琐碎），先在 `docs/plans/` 编写或更新方案，并在方案中记录每个阶段或条目引用的 `Skill: <名称>` 或 `Skill: none`
4. 实施前对方案进行自审或冷回放审查；结案前进行结案审核
5. 不得从单个功能列表直接跳到代码，除非活动需求文档和归属文档已给出明确路由

## 运行守则

1. 优先采用 "文件输入、文件输出" 的协作模式。
2. 不要把聊天会话记录当作项目长期存档资料。
3. 在项目范围尚不明确时，禁止直接根据产品经理口述内容或原型截图编写代码。
4. 输入信息存在歧义时，先在 `docs/discussions/` 或 `docs/requirements/` 新建或更新文档固化疑问。
5. 满足下文的方案编写触发条件时，必须先制定 / 更新执行方案，再动手开发。
6. `docs/design/`（设计文档）与 `docs/architecture/`（架构文档）只维护当前正式基线版本，不需要留存历史迁移记录。
7. 日志保持精简、标注日期，仅允许追加内容。每完成一次较大规模代码修改，必须更新每日开发日志：`docs/logs/{year}/{month}-{day}.md`（日志倒序排列，格式规范参考 `docs/logs/00-log-writing-guide.md`）。
8. 把非显而易见的功能退化问题记录在 `docs/bugs/`。
9. 当最终实现和原型出现重大偏差时，把偏差原因记录到 `docs/retrospectives/`，不能直接忽略差异继续推进。
10. 当同类问题反复出现、具备长期复用价值时，才把流程经验沉淀到 `docs/skills/` 或 `docs/audit/`。
11. 创建、修改、执行、评审 `docs/plans/` 下的方案文件时，必须优先阅读并严格遵守 `docs/plans/00-plan-authoring-and-execution-guide.md` 中的流程规范。
12. 代码注释尽量精简。优先编写自解释代码；仅在局部约束极易被误读的场景，才补充少量注释。
13. 找不到指定路径的文档时，先检索 `docs/archive/` 归档目录（若目录尚未建立则视为无归档），再判定文件已删除。归档文件会保留原有相对路径名称；未经人工许可，不得随意把文件移入归档目录。
14. 可重用能力只是执行手段，不能用来替代需求文档、设计文档、架构文档。业务规则必须优先写入归属文档。
15. 同一类缺陷反复出现时，不能只留下文字总结。首先把经验固化为可复用的审计提示词、检查清单、评审手册；如果问题依旧反复发生，再升级为经验脚本、静态检查规则、代码校验规则、CI 门禁或者代码自动修改脚本，并贴合项目自身编码规范，合理控制误报率。

## 文档归属管理

### 核心原则

- 所有文档都必须在 `docs/` 目录下维护，禁止在项目根目录或其他位置散落文档。
- 文档引用优先使用相对路径（`docs/...`），便于跨平台读取。

### 现有目录职责明细

| 目录                     | 职责定位      | 存放内容                            | 维护时机                 |
| :--------------------- | :-------- | :------------------------------ | :------------------- |
| `docs/input/`          | 原始资料入口    | 需求原型、会议纪要、外部参考资料、数据样本等未经加工的原始输入 | 获取第一手资料时立即录入         |
| `docs/discussions/`    | 问题澄清与决策过程 | 待确认的需求歧义、技术选型争议、方案对比讨论记录、决策依据   | 发现信息存在歧义或需要多方讨论时     |
| `docs/requirements/`   | 需求固化      | 经确认的业务需求文档、功能规格说明、验收标准          | 需求澄清后，开发前            |
| `docs/design/`         | 详细设计方案    | 模块级方案设计、接口设计、数据模型设计、算法流程、业务规则   | 需要产出厚方案规划时           |
| `docs/architecture/`   | 高层架构设计    | 系统整体架构、技术选型、核心抽象、工程吸引子、跨模块边界约定  | 涉及底层架构调整或全局工程决策时     |
| `docs/plans/`          | 执行计划      | 任务拆解、里程碑、资源分配、风险预案、技能复用记录       | 触发方案编写条件时，实施前        |
| `docs/audit/`          | 审核与检查     | 代码评审记录、审计清单、检查规则、评审手册、静态检查配置    | 执行审核或沉淀审核经验时         |
| `docs/skills/`         | 可复用能力     | 经验证的通用脚本、工具函数、最佳实践指南、复用模式说明     | 同类问题反复出现且具备长期价值时     |
| `docs/bugs/`           | 缺陷记录      | 非显而易见的功能退化问题、根因分析、修复方案、预防措施     | 发现或修复缺陷时             |
| `docs/retrospectives/` | 复盘与偏差分析   | 最终实现与原型的重大偏差、决策失误复盘、改进建议、重大漂移   | 项目阶段结束或出现重大偏差时       |
| `docs/reports/`        | 产出物归档     | 最终交付报告、分析结论、策略回测结果、性能评估报告       | 任务完成或需要对外输出结论时       |
| `docs/logs/`           | 开发日志      | 每日开发进展、关键决策变更、代码修改摘要（按日期倒序，仅追加） | 每次较大规模代码修改后          |
| `docs/backlog/`        | 待办事项      | 待确认的需求、待确认的技术选型、待确认的任务开始前的准备    | 任务开始前，需求澄清后，技术选型后    |
| `docs/strategies/`     | 策略档案      | 策略评审清单、策略模板、各策略线的归档说明           | 新建/评审策略时，维护策略模板与评审清单 |
| `docs/archive/`        | 历史归档      | 已失效的历史版本文档、废弃方案、迁移前的旧文件         | 文档明确失效且经人工确认后        |

### 未来可扩展目录（按需启用）

| 目录               | 职责定位     | 启用条件                 |
| :--------------- | :------- | :------------------- |
| `docs/context/`  | AI 强制上下文 | 当 AI 路由文档稳定下来后，沉淀强制项 |
| `docs/lessons/`  | 持久经验     | 出现反复失败或重大恢复时         |
| `docs/testing/`  | 手工验证     | 出现需要手工验证或探索性测试时      |
| `docs/analysis/` | 研究与分析    | 出现需要记录权衡或否定方向时       |

## 默认工作流

1. 从 `docs/input/` 录入维护原始输入素材
2. 如需要对原始素材进行讨论和待排版解决的阻断，维护到 `docs/discussions/`
3. 把已澄清的需求合成为可实施的需求文档，维护到 `docs/requirements/`
4. 如果需要额外产出详细的细节（厚方案规划），维护到 `docs/design/`；如果是底层相关、架构相关与整体工程吸引子有关的，维护到 `docs/architecture/`，这一层通常是较为抽象的高层设计
5. 规划任务并选择候选的可重用技能（`docs/skills/README.md` 与 `.agents/skills/`）
6. 当规划触发条件适用时，编写或更新计划，并在相关阶段或条目中记录技能使用情况
7. 在实施前审查计划（自审、冷回放或子代理）
8. 实施最小完整部分
9. 进行验证（按 `docs/context/` 或方案中声明的真实验证命令）
10. 对已创建的计划进行结案审核
11. 记录日志和任何必要的缺陷备注

## 可选工作流层

根据任务复杂度酌情启用。已创建的计划必须进行方案审查与结案审核。

- `docs/audit/` 用于文档审计及非琐碎的审计记录存档
- `docs/testing/`（若已建立）用于手工验证或探索性测试
- `docs/retrospectives/` 用于需求或原型出现重大偏差时的复盘
- `docs/skills/` 用于同类问题反复出现后沉淀的可复用提示词
- `docs/lessons/`（若已建立）用于反复失败或重大恢复后沉淀的持久工程经验

当工作需要从多个维度同时挑战时，使用 `multi-dimensional-audit-prompt.md`。当标准检查清单可能遗漏隐藏风险时，使用 `open-ended-audit-prompt.md`。这两个提示词是通用默认值，复制后必须根据项目的实际归属文档、受保护区域、验证模型和反复出现的失败模式进行定制。

## 方案编写规则

任务具备以下任一特征时，必须编写方案：

- 涉及 API、数据库/模型、鉴权、集成、部署或公开契约行为的变更
- 涉及跨多个功能面的用户可见行为变更
- 触及多个模块并改变共享行为
- 预计需要多个 AI 会话才能完成
- 修改超过 5 个文件或变更行数预计超过 200 行
- 需要分阶段执行或设置显式结案关卡
- 存在不可隐藏在聊天中的产品或技术风险

以下低风险编辑可以跳过正式方案：文案变更、小型样式修复、仅测试清理、有明确现有测试的单文件行为修复，以及不涉及契约、数据/模型、鉴权、权限、集成、部署、跨面行为、文档冲突或未解决产品风险的小型低风险多文件编辑（约 1 至 3 个非生成文件，变更行数不超过 200 行）。

即使没有正式方案，也不得仅凭聊天记忆标记工作完成。必须对照实际 diff 和真实验证命令进行验证，然后记录日志。此冷回放检查同样适用于无方案路径。

### 审查者不可用时的回放策略

当没有第二审查者或子代理可用时，仅针对非受保护且非高风险的计划，可接受单独冷回放审查。方案必须记录使用了单独审查并注明局限性。受保护区域、未解决的产品风险和事实来源冲突仍然需要人类或子代理审查，或保持开放状态。

所有已创建的方案在实施和结案前，必须遵循 `docs/plans/00-plan-authoring-and-execution-guide.md` 中的流程规范。受保护区域、未解决的产品风险和事实来源冲突需要人类/子代理审查或保持开放状态。

## Skill 使用规则

使用可重用技能前，必须确认以下全部条件：

- 任务类型和路径已从需求文档和归属文档中明确
- 技能匹配工作方法，而非仅业务标签相似
- `docs/skills/README.md` 中列出的 required inputs 已就绪
- 预期输出已知且可存放到正确的文档位置

对于非琐碎的方案，每个依赖可复用技能的阶段或条目应记录 `Skill: <名称>` 或 `Skill: none`。

## Agent 提示指南

- 不要从单个功能列表生成完整产品。
- 不要为演示完整性而优化。
- 优先采用小而完整的切片，而非广泛的占位覆盖。
- 优先采用项目现有模式，而非发明新抽象。
- 如果信息缺失，将缺失的假设写入需求、讨论或方案文件，而非静默臆造。
- 除非方案或结案推理需要，否则不要在方案文件中写入代码级实现细节。
- 优先引用现有归属文档，而非在多个文件中重复陈述同一规则。
- 不要将强制规则隐藏在 `docs/references/` 中；如果 AI 必须默认执行，应将其放在 `AGENTS.md` 或 `docs/` 顶层的强制上下文中。
- 使用 `docs/backlog/` 来决定 AI 是否可以在不询问的情况下选择并执行下一个任务。

## 文档维护

完成任何重大代码变更后，必须执行：

1. **更新每日开发日志**，路径为 `docs/logs/{year}/{month}-{day}.md`（倒序排列，格式参考 `docs/logs/00-log-writing-guide.md`）。
2. **更新相关归属文档**，当变更影响应用层行为或技术结构时，同步更新 `docs/design/` 或 `docs/architecture/` 中的对应文档。

当验证完全通过（全绿）时，在日志条目中记录验证状态，并将其包含在 git commit message 中。这为未来的调试提供可靠的已知良好基线。

## Verification Baseline

不要假设任何模板中的示例命令对当前项目有效。

使用方案文件 `docs/plans/<最新未结案方案>.md` 中明确列出的真实验证命令；如果方案中未声明，则使用 `docs/architecture/python-env-rules.md` 与 `docs/architecture/okx-sdk-rules.md` 中登记的脚本与测试入口。

如果验证命令为空白或仍为占位符，必须先填写完整再报告验证成功；不允许在日志中以"已通过"掩盖未执行的验证步骤。
