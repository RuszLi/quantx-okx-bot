# 设计文档索引

## 用途

`docs/design/` 存放稳定的应用层文档。

本目录用于：

- 产品功能基线
- 页面与流程行为
- 角色与权限
- 应用外壳（app-shell）行为

跨领域技术结构请使用 `docs/architecture/`。

## 范围边界

- `docs/requirements/` 负责当前迭代应构建的内容
- `docs/design/` 负责该迭代验收后稳定的应用层基线
- `docs/architecture/` 负责技术设计与跨功能结构

当某个功能同时依赖业务设计和技术设计时，请将两者分文件存放并交叉引用。

## 起始文件

- `app-overview.md`
- `feature-inventory.md`
