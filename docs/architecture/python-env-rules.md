# 环境使用规范吸引子

> **文档定位：** 架构级约束文档，规范 Python 运行环境的使用方式，确保所有脚本、回测、实盘程序在统一、可复现的环境中运行。

---

## 1. 核心原则

本项目的 Python 环境**统一使用系统级 Python 派生的 venv 虚拟环境**，禁止使用 Conda、pyenv-virtualenv、Poetry 等第三方环境管理工具。

| 约束项 | 规范 |
|:---|:---|
| **Python 解释器** | 系统目录安装的 Python（当前为 `C:\Users\Rusz\AppData\Local\Programs\Python\Python311\python.exe`） |
| **虚拟环境** | 基于系统 Python 创建的标准 `venv`，位于项目根目录 `./venv/` |
| **包管理器** | venv 内置的 `pip`，依赖声明统一使用 `requirements.txt` |
| **禁止的工具** | Conda、pyenv、Poetry、PDM、uv、pipenv 等第三方环境/包管理工具 |

---

## 2. 环境创建与激活

### 2.1 首次创建

```powershell
# 使用系统 Python 创建 venv（仅首次）
C:\Users\Rusz\AppData\Local\Programs\Python\Python311\python.exe -m venv ./venv

# 激活
./venv/Scripts/Activate.ps1

# 安装依赖
pip install -r requirements.txt
```

### 2.2 日常使用

```powershell
# 激活 venv
./venv/Scripts/Activate.ps1

# 运行脚本
python scripts/run_live_echo.py
```

### 2.3 显式调用（不激活 venv 时）

```powershell
# 直接使用 venv 的 Python 解释器
./venv/Scripts/python.exe -m src.backtest.run
./venv/Scripts/python.exe -m pip install <package>
```

---

## 3. 强制规则

### 3.1 解释器约束

- ✅ 必须使用 `./venv/Scripts/python.exe` 或激活 venv 后的 `python`
- ❌ 禁止使用系统全局 Python（`C:\Users\Rusz\AppData\Local\Programs\Python\Python311\python.exe`）直接运行脚本
- ❌ 禁止使用其他 Python 安装（如 `C:\Users\Rusz\AppData\Local\Python\bin\python.exe`）
- ❌ 禁止使用 `py` launcher 隐式选择解释器

### 3.2 包管理约束

- ✅ 必须使用 venv 内的 `pip` 安装依赖
- ✅ 新增依赖必须同步更新 `requirements.txt`
- ❌ 禁止使用 `pip install --user`（会污染用户级 site-packages）
- ❌ 禁止使用 `sudo pip install` 或全局 `pip install`
- ❌ 禁止在 venv 外安装项目运行所需的依赖

### 3.3 环境隔离约束

- ✅ venv 目录 `./venv/` 应加入 `.gitignore`，不纳入版本控制
- ✅ `requirements.txt` 必须纳入版本控制，作为环境的唯一声明
- ❌ 禁止在脚本中硬编码 Python 解释器的绝对路径
- ❌ 禁止在脚本中动态创建或切换虚拟环境

---

## 4. 依赖管理

### 4.1 requirements.txt 规范

```
# 运行时依赖
websockets>=12.0
aiohttp>=3.9.0
python-dotenv>=1.0.0
numpy>=1.26.0

# 回测工具链
httpx>=0.27.0
pandas>=2.2.0
pyarrow>=15.0.0
tqdm>=4.66.0
```

- 使用 `>=` 指定最低版本，避免过度锁定
- 按用途分组，补充注释说明
- 新增依赖时注明用途

### 4.2 依赖安装流程

```powershell
# 1. 激活 venv
./venv/Scripts/Activate.ps1

# 2. 安装新依赖
pip install <package>

# 3. 冻结到 requirements.txt
pip freeze > requirements.txt
# 或手动编辑 requirements.txt，仅追加新增项
```

---

## 5. 口径一致性：代码与 requirements.txt 强制同步

> **问题背景：** 做方案或写代码时引用了某个 Python 库，但未同步维护进 `requirements.txt` 并安装到 venv，导致代码在运行时 `ImportError`，或其他人无法复现环境。

### 5.1 强制同步规则

| 场景 | 必须执行的动作 |
|:---|:---|
| 方案/设计文档中引用了新库 | 立即将库名+最低版本写入 `requirements.txt`，并执行 `pip install` |
| 代码中 `import` 了新库 | 同上，且必须在提交代码前完成 |
| 发现代码依赖未在 `requirements.txt` 中声明 | 立即补写并安装，不得拖延 |
| 升级了库的版本 | 同步更新 `requirements.txt` 中的版本约束 |

### 5.2 禁止行为

- ❌ 禁止在方案中引用未安装的库，即使"理论上可用"
- ❌ 禁止在代码中 `import` 未写入 `requirements.txt` 的库
- ❌ 禁止"先代码后补 requirements"——必须在代码运行前完成同步
- ❌ 禁止在 `requirements.txt` 中声明了某版本但 venv 中实际安装的是另一版本

### 5.3 自检命令

每次提交前，在 venv 中执行以下命令验证一致性：

```powershell
# 1. 激活 venv
./venv/Scripts/Activate.ps1

# 2. 检查代码中实际 import 的库是否都在 requirements.txt 中
pip install pipreqs -q
pipreqs . --force --savepath requirements.txt.check
diff requirements.txt requirements.txt.check

# 3. 检查 venv 中已安装库是否与 requirements.txt 一致
pip check
```

---

## 6. 审计检查清单

在提交新脚本或修改环境配置前，逐项检查：

- [ ] 是否使用 `./venv/Scripts/python.exe` 或激活的 venv 运行？
- [ ] 是否避免了使用系统全局 Python？
- [ ] 新增依赖是否已写入 `requirements.txt`？
- [ ] 是否避免了硬编码解释器路径？
- [ ] 是否避免了使用 Conda / Poetry / pyenv 等工具？
- [ ] 代码中引用的所有库是否已写入 `requirements.txt` 并安装到 venv？

---

## 相关文档

- [okx-sdk-rules.md](./okx-sdk-rules.md) — OKX SDK 使用规范
- [sys-proxy-rules.md](./sys-proxy-rules.md) — 本地代理规范
- [strategy-and-factor-constraints.md](./strategy-and-factor-constraints.md) — 策略与因子约束吸引子
