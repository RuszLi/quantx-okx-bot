# 架构文档索引

## 用途

`docs/architecture/` 定义 `okx-bot` 稳定的跨领域技术基线。

- `docs/design/` 负责应用层功能与业务设计。
- `docs/architecture/` 负责横跨多个功能面的技术结构。

***

## 建议阅读顺序

1. [project-vision.md](./project-vision.md) — 产品与系统意图
2. [strategy-and-factor-constraints.md](./strategy-and-factor-constraints.md) — 策略与因子的允许/禁止边界
3. [okx-sdk-rules.md](./okx-sdk-rules.md) — OKX SDK 使用规范
4. [sys-proxy-rules.md](./sys-proxy-rules.md) — 本地代理规范
5. [python-env-rules.md](./python-env-rules.md) — Python 运行环境规范
6. [2026-06-27-strategy-v3-execution-architecture.md](./2026-06-27-strategy-v3-execution-architecture.md) — V3 策略执行架构
7. [backtest-exit-klines-alignment-checklist.md](./backtest-exit-klines-alignment-checklist.md) — 回测退出 K 线对齐检查清单
8. 随项目演进，继续补充更具体的归属文档

***

## 归属文档规则

- 一份文档只负责一个稳定主题
- 解释当前的决策依据与约束，而非按时间顺序的演进历史
- 当实现改变受支持的架构时，应在同一次变更中更新归属文档
- 把被否决的方案与探索性记录迁到 `docs/analysis/`
- 当技术规则是为支撑某个具体产品行为而存在时，请引用 `docs/design/` 下对应的应用层归属文档

***

## 优先级边界

- `docs/design/` 归属应用行为与功能语义
- `docs/architecture/` 归属技术结构与跨领域实现规则
- 当问题涉及持久化或 schema 真值时，模型/schema 文件本身是权威来源

***

## 初始归属文档

- [project-vision.md](./project-vision.md) — 产品与系统意图
- [strategy-and-factor-constraints.md](./strategy-and-factor-constraints.md) — 策略与因子挖掘的允许/禁止约束
- [okx-sdk-rules.md](./okx-sdk-rules.md) — OKX SDK 使用规范
- [sys-proxy-rules.md](./sys-proxy-rules.md) — 本地代理规范
- [python-env-rules.md](./python-env-rules.md) — Python 运行环境规范
- [2026-06-27-strategy-v3-execution-architecture.md](./2026-06-27-strategy-v3-execution-architecture.md) — V3 策略执行架构
- [backtest-exit-klines-alignment-checklist.md](./backtest-exit-klines-alignment-checklist.md) — 回测退出 K 线对齐检查清单

***

# 架构文档写作规范

> 本节定义 `docs/architecture/` 目录下所有架构文档的命名规范、内容格式规范和写作指引。

## 1. 文件命名规范

### 1.1 命名格式

架构文档采用 **kebab-case**（短横线分隔）命名，格式为：

```
<scope>-<subject>[-rules|-constraints|-guide].md
```

### 1.2 命名模式

| 模式      | 格式                         | 示例                                      |
| :------ | :------------------------- | :-------------------------------------- |
| **规则型** | `<subject>-rules.md`       | `okx-sdk-rules.md`、`sys-proxy-rules.md` |
| **约束型** | `<subject>-constraints.md` | `strategy-and-factor-constraints.md`    |
| **指南型** | `<subject>-guide.md`       | `deployment-guide.md`                   |
| **规范型** | `<subject>-spec.md`        | `api-spec.md`                           |

### 1.3 命名原则

- **简洁明确**：文件名应直接反映文档的核心主题，避免冗余词汇
- **范围前缀**：若文档涉及特定系统或模块，加范围前缀区分命名空间（如 `okx-`、`sys-`）
- **统一后缀**：同一类型的文档使用统一后缀，便于识别和检索
- **禁止中文命名**：文件名统一使用英文，避免编码和跨平台兼容问题

### 1.4 现有文件清单

| 文件                                                 | 类型  | 主题             |
| :------------------------------------------------- | :-- | :------------- |
| `project-vision.md`                                | 愿景型 | 产品与系统意图        |
| `strategy-and-factor-constraints.md`               | 约束型 | 策略与因子挖掘约束      |
| `okx-sdk-rules.md`                                 | 规则型 | OKX SDK 使用规范   |
| `sys-proxy-rules.md`                               | 规则型 | 本地代理规范         |
| `python-env-rules.md`                              | 规则型 | Python 运行环境规范  |
| `2026-06-27-strategy-v3-execution-architecture.md` | 架构型 | V3 策略执行架构      |
| `backtest-exit-klines-alignment-checklist.md`      | 检查型 | 回测退出 K 线对齐检查清单 |

***

## 2. 内容格式规范

### 2.1 文档结构

每个架构文档应包含以下标准结构：

```markdown
# <文档标题>

> **文档定位：** 一句话说明本文档的架构级角色和目的。

---

## 1. 核心原则 / 核心目标 / 背景

> 说明文档所定义的核心约束、目标或背景信息。

---

## 2. 具体规则 / 规范内容

> 分章节详细描述各项规则、约束或规范。

---

## 3. 强制规则 / 禁止行为（如适用）

> 明确列出必须遵守和严格禁止的行为。

---

## 4. 审计检查清单（如适用）

> 提交前逐项检查的清单。

---

## 相关文档

> 链接到其他关联的架构、设计或需求文档。
```

### 2.2 标题规范

- **一级标题（H1）**：文档标题，每个文件只有一个
- **二级标题（H2）**：主要章节
- **三级标题（H3）**：子章节
- **四级标题（H4）**：细分内容
- 标题前后各留一个空行

### 2.3 内容格式

| 元素     | 格式           | 示例           |
| :----- | :----------- | :----------- |
| **加粗** | `**文本**`     | 用于强调关键术语或参数名 |
| *斜体*   | `*文本*`       | 用于引用或注释      |
| `行内代码` | `` `代码` ``   | 用于命令、文件名、变量名 |
| 代码块    | 三个反引号 + 语言标识 | 用于多行代码示例     |
| 表格     | Markdown 表格  | 用于结构化数据展示    |
| 有序列表   | `1. 2. 3.`   | 用于步骤或优先级     |
| 无序列表   | `- `         | 用于枚举项        |
| 复选框    | `- [ ]`      | 用于检查清单       |

### 2.4 链接规范

- 内部链接使用相对路径：`[okx-sdk-rules.md](./okx-sdk-rules.md)`
- 外部链接使用完整 URL：`[官方文档](https://okx.com/docs-v5/)`
- 链接前后各留一个空格（中文排版规范）

***

## 3. 吸引子文档写作指引

### 3.1 什么是吸引子（Attractor）

吸引子是架构级约束文档，用于：

- **限定边界**：明确什么可以做、什么禁止做
- **对齐认知**：确保所有开发者对架构决策有一致理解
- **防止漂移**：避免代码实现偏离架构意图

### 3.2 写作要点

1. **定位清晰**：开头用 `> **文档定位：**` 一句话说明文档的架构级角色
2. **原则先行**：先写核心原则，再写具体规则
3. **正反对比**：用 ✅/❌ 或表格明确「必须做」和「禁止做」
4. **可审计**：结尾附检查清单，便于提交前自查
5. **关联引用**：用「相关文档」章节链接到其他关联文档

### 3.3 常见吸引子类型

| 类型                   | 用途          | 示例            |
| :------------------- | :---------- | :------------ |
| **规则型（Rules）**       | 规定必须遵守的行为规范 | SDK 使用规范、代理规范 |
| **约束型（Constraints）** | 限定边界和禁止行为   | 策略与因子约束       |
| **指南型（Guide）**       | 提供实施指引      | 部署指南、接入指南     |

***

## 4. 审计检查清单

在创建或修改架构文档时，逐项检查：

- [ ] 文件名是否符合 kebab-case 命名规范？
- [ ] 是否包含文档定位说明？
- [ ] 是否包含核心原则/目标章节？
- [ ] 规则描述是否明确，无歧义？
- [ ] 是否包含「必须做」和「禁止做」的对比？
- [ ] 是否包含审计检查清单？
- [ ] 是否包含相关文档链接？
- [ ] 是否遵循中文排版规范（中英文空格、全角标点）？

***

## 相关文档

- [project-vision.md](./project-vision.md) — 产品与系统意图
- [strategy-and-factor-constraints.md](./strategy-and-factor-constraints.md) — 策略与因子约束吸引子
- [okx-sdk-rules.md](./okx-sdk-rules.md) — OKX SDK 使用规范
- [sys-proxy-rules.md](./sys-proxy-rules.md) — 本地代理规范
- [python-env-rules.md](./python-env-rules.md) — Python 运行环境规范
- [backtest-exit-klines-alignment-checklist.md](./backtest-exit-klines-alignment-checklist.md) — 回测退出 K 线对齐检查清单

