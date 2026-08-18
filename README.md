# 光储充管理系统

## 1. 项目简介

本项目是一个基于 **Python、FastAPI、SQLite、HTML、CSS 和 JavaScript** 构建的光储充系统示例应用。

系统以光伏、负载和储能三个对象为基础，通过 Python 生成动态运行数据，使用独立策略模块计算储能控制结果，将系统状态和控制记录保存到 SQLite 数据库，再由 FastAPI 向浏览器提供页面和数据接口。

项目启动后，可以在浏览器中查看：

- 光伏实时功率；
- 负载实时功率；
- 储能充放电功率；
- 储能剩余电量 SOC；
- 当前策略动作及判断说明；
- 最近一段时间的功率变化曲线；
- 最近生成的控制命令；
- 数据库中保存的历史运行记录。

项目代码按照设备层、策略层、业务服务层、数据库层、接口层和前端展示层进行组织。各模块之间使用固定的数据结构和接口进行通信，便于后续在现有结构上增加设备、页面、业务功能和控制算法。

---

## 2. 项目运行链路

当前项目的完整运行链路如下：

```text
模拟设备生成光伏、负载和储能状态
                ↓
设备适配器返回统一系统状态
                ↓
业务服务调用储能控制策略
                ↓
策略模块生成控制决策
                ↓
设备适配器执行储能控制命令
                ↓
更新储能功率和储能 SOC
                ↓
SQLAlchemy 将状态和控制记录写入 SQLite
                ↓
FastAPI 提供状态、历史和控制记录 API
                ↓
浏览器通过 JavaScript 定时请求 API
                ↓
HTML 页面更新指标、曲线和控制记录
```

后台模拟任务与浏览器页面相互独立：

- FastAPI 后台任务按照固定周期持续推进系统状态；
- 浏览器按照固定周期读取后端数据；
- 页面关闭后，后端模拟任务仍会继续运行；
- 页面重新打开后，会读取数据库和后端中的最新状态。

---

## 3. 完整光储充项目的业务链路

在完整的光储充一体化智能充电站项目中，系统链路可以扩展为：

```text
光伏逆变器、储能 PCS/BMS、充电桩、电表等现场设备
                        ↓
Modbus、MQTT、OCPP 等设备通信协议
                        ↓
设备通信网关与数据标准化
                        ↓
实时状态管理与历史数据存储
                        ↓
规则策略、预测模型和优化调度算法
                        ↓
生成储能充放电、充电功率等控制目标
                        ↓
控制命令校验与设备指令下发
                        ↓
现场设备执行并反馈实际运行状态
                        ↓
前端平台展示、参数配置、运行分析和历史查询
```

本项目中的 `DeviceAdapter`、`EnergyStrategy`、`EMSService`、数据库模型和 API 层，分别对应完整项目中的设备接入、策略计算、业务编排、数据存储和人机交互基础结构。

---

## 4. Web 开发中的前端、后端和数据库

一个典型 Web 应用可以分为前端、后端和数据库三个主要部分。

### 4.1 前端

前端是用户在浏览器中看到和操作的页面。

本项目的前端使用：

- **HTML**：定义页面结构；
- **CSS**：设置页面布局、颜色、卡片和表格样式；
- **JavaScript**：调用后端 API，并将返回的数据更新到页面；
- **Canvas**：绘制历史功率曲线。

前端文件位于：

```text
app/templates/
app/static/
```

### 4.2 后端

后端负责接收浏览器请求、执行业务逻辑、调用数据库并返回数据。

本项目后端使用 FastAPI，主要负责：

- 启动 Web 服务；
- 托管前端页面和静态文件；
- 提供 REST API；
- 管理后台模拟任务；
- 调用策略和设备模块；
- 查询数据库并返回结果。

### 4.3 数据库

数据库用于保存系统运行数据。

本项目使用 SQLite 保存：

- 每个运行周期的系统历史状态；
- 每次策略计算生成的控制命令。

前端不会直接访问数据库，而是通过 FastAPI 提供的 API 获取数据。

---

## 5. 使用的主要工具

### 5.1 Python

Python 是本项目的主要开发语言，用于：

- 编写 FastAPI 后端；
- 生成模拟数据；
- 编写控制策略；
- 操作数据库；
- 管理后台任务；
- 编写自动化测试。

### 5.2 FastAPI

FastAPI 是一个 Python Web 开发框架。

本项目使用 FastAPI：

- 创建后端应用；
- 定义 API 路由；
- 返回 HTML 页面；
- 托管 CSS 和 JavaScript；
- 管理应用启动和关闭过程；
- 启动后台循环任务；
- 自动生成接口文档。

### 5.3 Uvicorn

Uvicorn 是运行 FastAPI 应用的 ASGI 服务器。

执行 `python run.py` 后，项目通过 Uvicorn 在本地启动 Web 服务。

### 5.4 SQLite

SQLite 是一个轻量级关系型数据库。

它将所有数据保存在一个本地文件中，不需要单独安装或启动数据库服务器。数据库文件默认生成在：

```text
data/demo.db
```

### 5.5 SQLAlchemy

SQLAlchemy 是 Python 中常用的数据库工具。

本项目使用 SQLAlchemy：

- 创建数据库连接；
- 定义数据库表；
- 将 Python 对象写入 SQLite；
- 查询历史数据和控制记录；
- 管理数据库会话和事务。

### 5.6 Pydantic

Pydantic 用于定义和校验数据结构。

本项目通过 Pydantic 明确规定：

- 设备状态包含哪些字段；
- 策略返回哪些控制结果；
- API 返回哪些数据；
- 每个字段采用什么数据类型。

### 5.7 Jinja2

Jinja2 是 FastAPI 使用的 HTML 模板工具。

本项目通过 Jinja2 返回 `index.html` 页面，并向页面传递项目名称等基础信息。

### 5.8 HTML、CSS 和 JavaScript

三者共同构成浏览器页面：

- HTML 负责内容结构；
- CSS 负责视觉样式；
- JavaScript 负责调用 API、更新数据和处理按钮事件。

### 5.9 Pytest

Pytest 用于运行自动化测试。

本项目包含策略测试和 API 测试，可以在修改代码后快速检查主要功能是否仍然正常。

---

## 6. 环境要求

建议使用：

```text
Python 3.10 或更高版本
```

可以使用 Conda 或 Python 自带的 `venv` 管理项目环境。

---

## 7. 使用 Conda 安装和启动

### 7.1 创建 Conda 环境

在项目根目录打开终端，执行：

```bash
conda create -n light-storage-demo python=3.11 -y
```

### 7.2 激活环境

```bash
conda activate light-storage-demo
```

### 7.3 安装项目依赖

```bash
python -m pip install -r requirements.txt
```

### 7.4 启动项目

```bash
python run.py
```

终端出现类似以下内容时，说明服务已经启动：

```text
Uvicorn running on http://127.0.0.1:8000
```

### 7.5 打开页面

在浏览器访问：

```text
http://127.0.0.1:8000
```

### 7.6 打开 FastAPI 接口文档

```text
http://127.0.0.1:8000/docs
```

### 7.7 退出环境

```bash
conda deactivate
```

### 7.8 删除 Conda 环境

```bash
conda remove -n light-storage-demo --all -y
```

---

## 8. 使用 venv 安装和启动

### 8.1 创建虚拟环境

```bash
python -m venv .venv
```

### 8.2 激活虚拟环境

Windows PowerShell：

```powershell
.venv\Scripts\Activate.ps1
```

Windows CMD：

```bat
.venv\Scripts\activate.bat
```

macOS 或 Linux：

```bash
source .venv/bin/activate
```

### 8.3 安装依赖

```bash
python -m pip install -r requirements.txt
```

### 8.4 启动项目

```bash
python run.py
```

---

## 9. 停止项目

在启动项目的终端中按下：

```text
Ctrl + C
```

即可停止 FastAPI 服务和后台模拟任务。

---

## 10. 项目目录

```text
mcs-integration/
├── run.py
├── requirements.txt
├── README.md
├── pytest.ini
├── .env.example
│
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── router.py
│   │   ├── system.py
│   │   ├── devices.py
│   │   └── strategies.py
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── system.py
│   │   ├── device.py
│   │   └── strategy.py
│   │
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── common.py
│   │   ├── device.py
│   │   └── strategy.py
│   │
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── device_repository.py
│   │   └── strategy_repository.py
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── system_service.py
│   │   ├── device_service.py
│   │   └── strategy_service.py
│   │
│   ├── devices/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   └── simulator.py
│   │
│   ├── strategies/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   └── fixed_rule.py
│   │
│   ├── templates/
│   │   ├── base.html
│   │   ├── index.html
│   │   ├── devices.html
│   │   └── strategy.html
│   │
│   └── static/
│       ├── styles.css
│       ├── app.js
│       └── js/
│           ├── devices.js
│           └── strategy.js
│
├── data/
│   └── demo.db
│
└── tests/
    ├── __init__.py
    ├── test_api.py
    ├── test_strategy.py
    ├── test_devices.py
    └── test_integration.py

`data/demo.db` 会在项目首次运行时自动创建，因此刚解压项目时可能只看到 `data/.gitkeep`。

---

## 11. 根目录文件说明

### 11.1 `run.py`

项目启动入口。

文件完成两项工作：

1. 调用 `create_app()` 创建 FastAPI 应用；
2. 使用 Uvicorn 启动本地 Web 服务。

需要修改服务监听地址、端口或 Uvicorn 启动参数时，可以修改该文件。

### 11.2 `requirements.txt`

记录项目运行和测试所需的 Python 第三方依赖。

新增 Python 工具后，应同步更新此文件。

### 11.3 `README.md`

项目说明文档，包含系统介绍、安装方法、目录结构、文件作用、API 和扩展方法。

### 11.4 `pytest.ini`

Pytest 配置文件。

它指定：

- 测试目录为 `tests`；
- 项目根目录加入 Python 模块搜索路径。

### 11.5 `.env.example`

环境变量示例文件，列出可以配置的项目参数：

```text
EMS_DATABASE_URL
EMS_LOOP_SECONDS
EMS_HISTORY_LIMIT
```

当前程序通过操作系统环境变量读取这些配置。

Windows PowerShell 示例：

```powershell
$env:EMS_LOOP_SECONDS="5"
python run.py
```

macOS 或 Linux 示例：

```bash
export EMS_LOOP_SECONDS=5
python run.py
```

---

## 12. 后端核心文件说明

### 12.1 `app/main.py`

FastAPI 应用的核心入口。

该文件负责：

- 创建 FastAPI 实例；
- 初始化数据库、模拟设备和策略；
- 创建 `EMSService`；
- 管理应用生命周期；
- 启动和停止后台任务；
- 挂载 `/static` 静态文件目录；
- 返回首页；
- 提供 API 路由。

当前 API 集中定义在该文件中。后续接口数量增加后，可以新建：

```text
app/api/
```

并将状态、历史、设备、策略等路由拆分为独立文件。

### 12.2 `app/config.py`

集中管理项目配置。

当前配置包括：

- SQLite 数据库地址；
- 后台循环周期；
- 历史数据返回数量。

默认值可以直接在 `Settings.from_env()` 中调整，也可以通过系统环境变量覆盖。

### 12.3 `app/database.py`

负责数据库连接和会话管理。

主要内容包括：

- SQLAlchemy 基类 `Base`；
- 数据库引擎；
- 数据库会话工厂；
- 自动创建数据表；
- 数据库事务提交与回滚。

将 SQLite 替换为 PostgreSQL 时，主要修改数据库连接地址和对应数据库驱动。

### 12.4 `app/models.py`

定义数据库表。

当前包含两张表。

#### `SystemHistory`

保存系统历史状态：

- 光伏功率；
- 负载功率；
- 储能功率；
- 储能 SOC；
- 创建时间。

#### `ControlCommand`

保存策略生成的控制记录：

- 控制功率；
- 动作类型；
- 策略说明；
- 执行结果；
- 创建时间。

需要增加设备、用户、参数、告警或预测结果时，可以在该文件中增加新的 SQLAlchemy 模型。

开发阶段修改模型后，可以删除旧的 `data/demo.db`，再重新启动项目生成新表。正式项目建议使用 Alembic 管理数据库迁移。

### 12.5 `app/schemas.py`

定义模块之间和 API 中使用的数据结构。

当前包含：

- `SystemState`：设备向策略提供的系统状态；
- `ControlDecision`：策略向执行层提供的控制决策；
- `StatusResponse`：实时状态接口返回值；
- `HistoryItem`：历史记录接口返回值；
- `CommandItem`：控制记录接口返回值；
- `ResetResponse`：重置接口返回值。

增加字段时，需要同步检查设备适配器、策略模块、业务服务、数据库模型、API 和前端 JavaScript。

### 12.6 `app/service.py`

项目的业务流程组织者。

`EMSService` 将不同模块串联起来：

```text
读取设备状态
→ 调用策略
→ 执行控制
→ 保存历史状态
→ 保存控制记录
```

该文件还负责：

- 启动后台循环；
- 停止后台循环；
- 返回实时状态；
- 查询历史数据；
- 查询控制命令；
- 重置系统。

新增业务功能时，优先在服务层组织流程，不建议将大量业务逻辑直接写在 API 路由中。

---

## 13. 设备模块说明

### 13.1 `app/devices/base.py`

定义统一设备接口 `DeviceAdapter`。

所有设备实现都需要提供：

```python
read_state()
execute_command()
reset()
```

业务服务只调用统一接口，不需要知道底层数据来自模拟器、Modbus、MQTT 或其他系统。

### 13.2 `app/devices/simulator.py`

实现模拟设备。

当前模拟器负责：

- 推进模拟时间；
- 生成光伏功率；
- 生成负载功率；
- 保存储能状态；
- 执行充放电命令；
- 更新储能 SOC；
- 重置模拟数据。

光伏功率采用白天正弦变化曲线，并加入少量随机波动；负载功率采用周期变化和随机扰动。

需要修改模拟数据规律时，可以调整：

- `_next_environment()`；
- `_storage_capacity_kwh`；
- `_simulation_step_hours`；
- `_initial_state()`。

### 13.3 接入真实设备

接入真实设备时，可以新增文件，例如：

```text
app/devices/modbus_adapter.py
```

并实现 `DeviceAdapter` 接口：

```python
class ModbusDeviceAdapter(DeviceAdapter):
    def read_state(self):
        ...

    def execute_command(self, decision):
        ...

    def reset(self):
        ...
```

然后在 `app/main.py` 中，将：

```python
device = SimulatorAdapter()
```

替换为真实设备适配器实例。

---

## 14. 策略模块说明

### 14.1 `app/strategies/base.py`

定义统一策略接口 `EnergyStrategy`。

策略必须实现：

```python
calculate(state)
```

输入为 `SystemState`，输出为 `ControlDecision`。

因此，后续更换控制算法时，不需要修改设备适配器、数据库模型和前端接口。

### 14.2 `app/strategies/fixed_rule.py`

实现当前储能控制策略 `FixedRuleStrategy`。

策略根据以下输入计算储能目标功率：

- 光伏功率；
- 负载功率；
- 储能 SOC。

策略输出：

- 储能目标功率；
- 充电、放电或待机动作；
- 策略说明；
- 决策时间。

需要修改当前策略时，可以调整：

```python
CHARGE_POWER
DISCHARGE_POWER
SOC_MIN
SOC_MAX
```

也可以直接修改：

```python
calculate()
```

中的判断逻辑。

需要新增另一套策略时，可以新建：

```text
app/strategies/new_strategy.py
```

并继承 `EnergyStrategy`。完成后，在 `app/main.py` 中替换：

```python
strategy = FixedRuleStrategy()
```

即可切换策略。

---

## 15. 前端文件说明

### 15.1 `app/templates/index.html`

定义页面结构。

页面包含：

- 项目标题；
- 实时状态卡片；
- 当前策略结果；
- SOC 进度条；
- 系统链路说明；
- 历史曲线画布；
- 控制记录表格；
- 重置按钮。

需要增加新的页面区域时，可以在该文件中添加对应 HTML 结构。

如果后续页面数量较多，可以继续增加：

```text
app/templates/devices.html
app/templates/strategy.html
app/templates/history.html
```

并在 FastAPI 中增加对应页面路由。

### 15.2 `app/static/styles.css`

负责页面样式。

文件包含：

- 页面背景；
- 顶部标题区域；
- 实时数据卡片；
- 面板；
- 策略状态标签；
- SOC 进度条；
- 系统链路；
- 表格；
- 响应式布局；
- 提示消息。

需要调整页面颜色、尺寸、间距或移动端效果时，可以修改该文件。

### 15.3 `app/static/app.js`

负责前端交互和数据刷新。

主要功能包括：

- 请求 `/api/status`；
- 请求 `/api/history`；
- 请求 `/api/commands`；
- 更新实时状态卡片；
- 更新策略说明；
- 更新 SOC 进度条；
- 使用 Canvas 绘制历史曲线；
- 更新控制记录表格；
- 调用 `/api/reset`；
- 定时刷新页面。

需要调整页面刷新周期时，可以修改：

```javascript
const REFRESH_MS = 3000;
```

新增 API 后，可以继续使用 `requestJson()` 统一发送请求。

---

## 16. 数据目录

### `data/demo.db`

SQLite 数据库文件。

项目首次启动时，程序会自动：

1. 创建 `data` 目录；
2. 创建 `demo.db`；
3. 创建数据库表；
4. 写入第一条系统状态和控制记录。

可以使用 SQLite 可视化工具打开该文件，例如：

- DB Browser for SQLite；
- SQLiteStudio；
- VS Code SQLite 插件。

开发期间如需清空全部数据，可以停止项目后删除：

```text
data/demo.db
```

再次启动时，数据库会重新创建。

---

## 17. 测试文件说明

### 17.1 `tests/test_strategy.py`

测试固定策略的主要逻辑：

- 光伏功率高于负载时执行充电；
- 光伏功率低于负载时执行放电；
- SOC 达到上限时停止充电；
- SOC 达到下限时停止放电。

修改策略后，可以同步增加或修改对应测试。

### 17.2 `tests/test_api.py`

测试：

- 首页是否能够访问；
- `/api/status` 是否返回完整字段；
- `/api/history` 是否返回历史记录；
- `/api/reset` 是否能够正常执行。

---

## 18. 运行测试

激活项目环境后，在项目根目录执行：

```bash
pytest
```

查看更详细的测试输出：

```bash
pytest -v
```

只运行策略测试：

```bash
pytest tests/test_strategy.py -v
```

只运行 API 测试：

```bash
pytest tests/test_api.py -v
```

---

## 19. API 说明

### 19.1 获取当前状态

```http
GET /api/status
```

返回示例：

```json
{
  "pv_power": 65.2,
  "load_power": 82.5,
  "storage_power": 10.0,
  "storage_soc": 54.8,
  "action": "discharge",
  "strategy_message": "光伏功率低于负载，储能执行固定功率放电。",
  "updated_at": "2026-07-20T16:30:00"
}
```

### 19.2 获取历史数据

```http
GET /api/history
```

返回最近若干条系统历史状态，用于绘制功率曲线。

返回数量由以下配置决定：

```text
EMS_HISTORY_LIMIT
```

### 19.3 获取控制记录

```http
GET /api/commands
```

返回最近 10 条控制命令。

### 19.4 重置系统

```http
POST /api/reset
```

该接口会：

- 重置模拟设备；
- 清空历史状态；
- 清空控制记录；
- 重新执行一个完整周期；
- 生成新的初始记录。

---

## 20. 页面功能说明

### 20.1 实时状态卡片

页面顶部展示：

- 光伏功率；
- 负载功率；
- 储能功率；
- 储能 SOC。

数据来自：

```http
GET /api/status
```

### 20.2 当前策略结果

页面显示：

- 当前动作；
- 策略判断说明；
- 最近更新时间；
- SOC 进度条。

修改策略判断文字时，可以修改：

```text
app/strategies/fixed_rule.py
```

中的 `message`。

### 20.3 历史功率曲线

前端调用：

```http
GET /api/history
```

并使用 Canvas 绘制：

- 光伏功率；
- 负载功率；
- 储能功率。

如需增加 SOC 曲线，可以在：

```text
app/static/app.js
```

的 `drawChart()` 中增加新的数据序列，或在 `index.html` 中增加第二个画布。

### 20.4 控制记录

页面调用：

```http
GET /api/commands
```

显示最近控制动作、功率、策略说明和执行结果。

数据库记录结构定义在：

```text
app/models.py
```

### 20.5 重置演示

点击“重置演示”按钮后，前端调用：

```http
POST /api/reset
```

按钮事件位于：

```text
app/static/app.js
```

---

## 21. 常见修改方法

### 21.1 修改储能控制规则

修改：

```text
app/strategies/fixed_rule.py
```

主要调整：

```python
FixedRuleStrategy.calculate()
```

修改后建议运行：

```bash
pytest tests/test_strategy.py -v
```

### 21.2 修改模拟光伏和负载数据

修改：

```text
app/devices/simulator.py
```

主要调整：

```python
_next_environment()
```

### 21.3 修改初始 SOC

修改 `app/devices/simulator.py` 中的：

```python
storage_soc=50.0
```

### 21.4 修改后台运行周期

Windows PowerShell：

```powershell
$env:EMS_LOOP_SECONDS="5"
python run.py
```

macOS 或 Linux：

```bash
export EMS_LOOP_SECONDS=5
python run.py
```

也可以修改 `app/config.py` 中的默认值。

### 21.5 修改前端刷新周期

修改 `app/static/app.js` 中的：

```javascript
const REFRESH_MS = 3000;
```

### 21.6 增加数据库字段

通常需要同步修改：

```text
app/models.py
app/schemas.py
app/service.py
app/static/app.js
app/templates/index.html
```

### 21.7 增加新的 API

可以先在 `app/main.py` 中增加新路由。

接口较多后，建议创建：

```text
app/api/
```

并按照功能拆分路由。

### 21.8 增加新的页面

新增 HTML 模板后，需要：

1. 在 `app/templates/` 中创建页面；
2. 在 `app/main.py` 中增加页面路由；
3. 在 `app/static/` 中增加对应样式和脚本；
4. 在页面中调用已有或新增 API。

### 21.9 接入真实设备

新增设备适配器并实现：

```python
DeviceAdapter
```

然后在 `app/main.py` 中替换当前的：

```python
SimulatorAdapter
```

### 21.10 接入新的控制算法

新增策略类并实现：

```python
EnergyStrategy
```

然后在 `app/main.py` 中替换当前的：

```python
FixedRuleStrategy
```

---

## 22. 建议的扩展方向

可以在当前代码基础上逐步增加以下内容。

### 22.1 数据与设备

- 多个光伏设备；
- 多组储能设备；
- 多个充电桩；
- 设备在线状态；
- 设备通信日志；
- Modbus 或 MQTT 接入。

### 22.2 策略与算法

- 可配置规则；
- 多套策略切换；
- 光伏预测；
- 负载预测；
- 储能优化调度；
- Pyomo 优化模型。

### 22.3 后端

- 用户和权限；
- 告警管理；
- 参数配置；
- 日志管理；
- WebSocket；
- 定时任务管理；
- PostgreSQL；
- Redis。

### 22.4 前端

- 多页面导航；
- 设备管理；
- 策略配置；
- 历史数据筛选；
- 报表导出；
- Vue 或 React 前端工程；
- 更完整的图表和能量流展示。

### 22.5 工程部署

- 配置文件管理；
- Docker；
- HTTPS；
- Linux 服务部署；
- 日志轮转；
- 数据备份；
- 自动化测试和持续集成。

---

## 23. 开发建议

在现有项目上继续开发时，建议遵循以下原则：

1. 设备模块只负责读取状态和执行命令；
2. 策略模块只负责根据状态生成控制决策；
3. 业务服务负责组织完整流程；
4. API 负责接收请求和返回结果；
5. 数据库负责保存业务数据；
6. 前端通过 API 获取数据，不直接访问数据库；
7. 新增功能后同步增加测试；
8. 修改公共字段时同步检查前后端和数据库；
9. 保持 `SystemState`、`ControlDecision` 和设备接口稳定；
10. 先使用模拟设备完成闭环，再接入真实设备。

---

## 24. 项目访问地址汇总

系统首页：

```text
http://127.0.0.1:8000
```

FastAPI Swagger 接口文档：

```text
http://127.0.0.1:8000/docs
```

FastAPI ReDoc 接口文档：

```text
http://127.0.0.1:8000/redoc
```

实时状态接口：

```text
http://127.0.0.1:8000/api/status
```

历史数据接口：

```text
http://127.0.0.1:8000/api/history
```

控制记录接口：

```text
http://127.0.0.1:8000/api/commands
```

| v1.5 | `ems-v1.5` | 完整 Simulator EMS 验收（页面风格统一、全量测试通过、故障链验证） |
