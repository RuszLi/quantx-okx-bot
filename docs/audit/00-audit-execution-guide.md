# 审核执行指南

## 目的

本指南定义应用层开发的默认审核检查点（audit checkpoints）。

对于已创建的方案，独立草稿审核（draft review）和结案审核（closure audit）是强制要求。

每个已创建的方案必须在至少一处记录持久的审核证据。默认做法：将草稿审核证据作为简短的 `Draft Review Record` 笔记记录在方案本身，将结案证据记录在方案的 `## Closure` 部分，仅当需要额外可追溯性（traceability）时才使用每日日志或 `docs/audits/` 下的文件。不得将审核结果仅保留在聊天中。

冷回放（cold replay）不是第二审核者，不能单方面批准方案创建、方案关闭或受保护区域的范围变更。

## 三种默认审核

1. 文档审核（document audit）
2. 草稿审核（draft review）
3. 结案审核（closure audit）

这些是审核对象（audit objects）。

项目也可以在这些对象上应用审核风格（audit styles）：

- 多维度审核（multi-dimensional audit）—— 同时在多个维度上质疑工作成果
- 开放式审核（open-ended audit）—— 在标准检查清单之外搜索隐藏问题

示例：

- 多维度草稿审核
- 开放式结案审核

模板在 `docs/skills/` 下为这些风格提供通用默认提示词。复制的项目应根据自己的所有者文档（owner docs）、受保护区域（protected areas）、验证栈（verification stack）和已知故障模式调整这些提示词。

## 文档审核

在需求/设计更新之后、大规模实现工作之前执行。

对于高风险、跨模块或跨文档的工作，考虑在普通文档审核之上叠加 `multi-dimensional-audit-prompt.md`。

检查项：

- 缺失的范围边界（scope boundaries）
- 伪装成已解决需求的未解决问题
- 原始输入与综合需求之间的不匹配
- 需求与所有者文档之间的不匹配

## 草稿审核

在方案编写完成后、实施前执行。

如果方案跨越多个所有者文档边界、受保护区域或验证面（verification surfaces），添加 `multi-dimensional-audit-prompt.md`。

检查项：

- 不诚实的关闭门槛（dishonest closure gates）
- 隐藏依赖
- 无人认领的遗留项（unowned leftovers）
- 方案范围仍依赖于未解决的需求
- 每个验收标准（acceptance criterion）缺少证明策略
- 方案中任务路由和技能选择理由缺失或薄弱

## 结案审核

在每个已创建方案的实施和验证完成后执行。

如果正常结案检查持续通过，但后续仍出现隐藏回归或薄弱证明，添加 `open-ended-audit-prompt.md`。

结案审核必须是独立的、由独立子代理（subagent）或审核者执行的独立审核阶段。自我审核、自我审计或自我记录的结案证据不能作为判定 `Plan Status: completed` 的依据。

检查项：

- 实时行为（live behavior）是否真正落地
- 文档是否对齐
- 声称的证据是否真实存在
- 方案关闭门槛是否真正满足
- 是否有范围内事项被降级为模糊的后续跟进
- 验证失败是否被当作非阻断项处理，且未经明确裁决

草稿审核发现应直接修订方案。不要求每个方案都有正式的 `## Plan Audit` 部分。

最低限度的持久草稿审核证据：

- 审核者 / 智能体（agent）
- 结论（verdict）
- 简明修订摘要或最终形态的论证

默认情况下，将此证据保留在方案内的简短 `Draft Review Record` 部分。仅当审核存在争议、可复用或可能后续重要时，才升级到 `docs/logs/` 或 `docs/audits/`。方案处于 `draft`、`active` 和 `completed` 状态的规范期望属于方案指南的内容。

## 输出规则

审核结果必须为每个已创建的方案持久记录。当审核存在争议、可复用或可能后续重要时，使用单独文件。

可复用提示词模板使用 `docs/skills/`，附加到每日执行的小型审核笔记使用 `docs/logs/`。

## 文件名指引

审核记录优先使用日期命名：

- `docs/audits/YYYY-MM-DD-HHmm-document-audit-topic.md`
- `docs/audits/YYYY-MM-DD-HHmm-draft-review-topic.md`
- `docs/audits/YYYY-MM-DD-HHmm-closure-audit-topic.md`
