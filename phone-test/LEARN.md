# 手机APP自动化测试系统 — 项目学习指南

> 目标读者：有 React / Python 基础，希望快速理解项目全貌后继续开发的同学。

---

## 目录

1. [项目是什么](#1-项目是什么)
2. [整体架构图](#2-整体架构图)
3. [硬件层原理](#3-硬件层原理)
4. [后端结构与逐层讲解](#4-后端结构与逐层讲解)
5. [前端结构与逐层讲解](#5-前端结构与逐层讲解)
6. [数据流转全流程](#6-数据流转全流程)
7. [核心算法详解](#7-核心算法详解)
8. [API 速查表](#8-api-速查表)
9. [状态管理（Zustand Stores）](#9-状态管理zustand-stores)
10. [本地开发环境启动](#10-本地开发环境启动)
11. [关键配置项](#11-关键配置项)
12. [待完成的功能清单](#12-待完成的功能清单)
13. [开发约定 & 容易踩的坑](#13-开发约定--容易踩的坑)

---

## 1. 项目是什么

这是一套**物理机械臂驱动真实手机完成 APP 自动化测试**的系统。

区别于传统模拟器测试：

| 对比维度 | 传统方案（Appium/UI Automator） | 本系统 |
|---|---|---|
| 执行方式 | 软件注入指令 | 物理机械手指触摸真实屏幕 |
| 覆盖范围 | 仅限已适配的 APP | 任意 APP，包括加固、游戏 |
| 视觉识别 | AccessibilityService 读取结构 | 截图 + 视觉大模型推理 |
| 硬件要求 | PC | N1 miniPC × 22 + CoreXY 机械台 × 22 |

### 核心能力

- 22 台设备**并发、独立**地执行测试脚本
- 支持 **YAML 脚本**和**自然语言指令**两种驱动方式
- 视觉模型（GUI-Owl / GPT-4o / Claude）识别页面元素、判断状态
- 实时 WebSocket 推送设备状态和任务进度
- 全局紧急停止（ESTOP）保护硬件安全

---

## 2. 整体架构图

```
┌─────────────────────────────────────────────────────────┐
│                   浏览器前端 (React)                     │
│   ControlCenter  DevTools  GroupControl  Calibration     │
│   Settings                                               │
│                ↕ HTTP / WebSocket                        │
├─────────────────────────────────────────────────────────┤
│              总控服务器  192.168.1.100:8080               │
│                    FastAPI (Python 3.9)                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐  │
│  │ 设备管理  │ │ 任务调度  │ │ 视觉推理  │ │ 坐标映射  │  │
│  │DevManager│ │Scheduler │ │VisionMgr │ │CoordMapper│  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────┘  │
│         ↕ Moonraker HTTP API (7125端口)                   │
├─────────────────────────────────────────────────────────┤
│  N1-01  N1-02  N1-03  …  N1-22   (192.168.1.101~122)   │
│  每台运行 Klipper + Moonraker                            │
│  控制 CoreXY 机械台实现 XYZ 三轴运动                     │
│         ↕ 物理触摸                                       │
└─────────────────────────────────────────────────────────┘
         手机屏幕（实体）  ←→  go2rtc 摄像头推流 (1984端口)
```

---

## 3. 硬件层原理

### 3.1 N1 miniPC

- 每台 N1 miniPC 通过 **Klipper 固件** 控制步进电机（CoreXY 结构）
- Klipper 接受 G-Code 指令，**Moonraker** 是 Klipper 的 HTTP/WebSocket API 网关
- 端口：默认 `7125`

### 3.2 CoreXY 运动学

CoreXY 是 3D 打印机常用结构，两个电机同时参与 X/Y 运动：

- 机械坐标范围：X: 0~150mm，Y: 0~150mm，Z: 0~50mm
- Z 轴离开时高度（Z_SAFE = 30mm）防止拖动

### 3.3 G-Code 指令含义（在 `motion.py` 中）

```gcode
G28          ; 归零（回原点）
G1 Z30 F3000 ; Z轴先抬起（安全移动）
G1 X75 Y60 F6000 ; XY 移到目标位置
G1 Z0 F3000  ; Z轴下压（触摸屏幕）
G4 P1000     ; 等待 1000ms（长按）
```

### 3.4 截图来源

每台 N1 上还运行 **go2rtc** 服务（端口 `1984`），通过摄像头拍摄手机屏幕。

截图 URL：`http://{设备IP}:1984/api/streams/camera0.jpg`

期望分辨率：**1280 × 720**

---

## 4. 后端结构与逐层讲解

```
backend/app/
├── main.py              # FastAPI 入口、路由注册、生命周期
├── config.py            # 所有配置项（读取 .env）
├── database.py          # SQLAlchemy 异步引擎 + session 工厂
├── auth.py              # JWT 鉴权（Bearer token）
├── ws_manager.py        # WebSocket 连接池 + broadcast
│
├── models/              # SQLAlchemy ORM 模型（数据库表）
│   ├── device.py        # Device 表（id, ip, hostname, status…）
│   ├── task.py          # TaskExecution 表（任务执行记录）
│   ├── template.py      # Template 表（YAML脚本模板）
│   └── calibration.py   # CalibrationData 表（标定数据）
│
├── schemas/             # Pydantic 请求/响应 Schema
│
├── api/                 # HTTP 路由（FastAPI Router）
│   ├── auth.py          # POST /api/v1/token → 获取 JWT
│   ├── devices.py       # GET/POST /api/v1/devices/…
│   ├── tasks.py         # POST /api/v1/devices/{id}/execute 等
│   ├── templates.py     # CRUD /api/v1/templates
│   ├── calibration.py   # POST /api/v1/devices/{id}/calibrate
│   ├── emergency.py     # POST /api/v1/emergency_stop
│   └── ws.py            # WebSocket /api/v1/ws/status
│
├── services/            # 核心业务逻辑
│   ├── device_manager.py  # 设备注册 + 心跳状态机
│   ├── moonraker_client.py# 向 N1 发送 G-Code
│   ├── motion.py          # 物理动作（tap/swipe/long_press）
│   ├── screenshot.py      # 从 go2rtc 抓屏
│   ├── coordinate.py      # 像素坐标 → 机械坐标转换
│   ├── flow_engine.py     # YAML 脚本步骤执行引擎
│   ├── scheduler.py       # 任务队列调度（最多22并发）
│   └── device_lock.py     # 设备锁（防止同时执行多任务）
│
├── vision/              # 视觉推理层
│   ├── adapter.py       # 抽象基类 VisionAdapter（接口定义）
│   ├── guiowl.py        # GUI-Owl（本地 vLLM，主用）
│   ├── api_vision.py    # OpenAI / Anthropic（Fallback）
│   └── manager.py       # 选择适配器，统一入口
│
└── nlp/
    └── intent.py        # 自然语言 → YAML 脚本转换
```

### 4.1 启动流程（main.py lifespan）

```python
1. 创建数据库表（Base.metadata.create_all）
2. device_manager.init_devices()
   → 若数据库无设备，自动注册 192.168.1.101~122 共 22 台
3. device_manager.start_heartbeat()
   → 每 5 秒并发检测所有设备存活状态
4. 服务就绪
```

### 4.2 设备状态机（device_manager.py）

```
          首次响应
OFFLINE ──────────→ RECOVERING
           ↑连续2次成功
RECOVERING ────────→ ONLINE
           ↑失联1次
ONLINE ────────────→ SUSPECT
           ↑失联3次
SUSPECT ───────────→ OFFLINE
           ↑紧急停止按钮
任意状态 ──────────→ ESTOP（不再参与心跳检测）
```

心跳阈值常量：
```python
HEARTBEAT_INTERVAL = 5   # 秒
SUSPECT_THRESHOLD  = 1   # 失联 N 次变 SUSPECT
OFFLINE_THRESHOLD  = 3   # 失联 N 次变 OFFLINE
RECOVER_THRESHOLD  = 2   # 连续成功 N 次变 ONLINE
```

### 4.3 任务调度流程（scheduler.py）

```
API 请求 dispatch_task(device_id, yaml)
  ↓
验证设备 ONLINE
  ↓
写入 TaskExecution 记录（PENDING）
  ↓
asyncio.create_task(_run_task)  ← 异步后台运行
  ↓
device_lock_manager.acquire(device_id)  ← 设备锁
  ↓
Semaphore(22)  ← 全局最大并发控制
  ↓
FlowEngine.execute_yaml(yaml)  ← 逐步执行
  ↓
更新 TaskExecution 状态（DONE / FAILED）
  ↓
device_lock_manager.release
```

### 4.4 视觉推理层（vision/）

```python
# 抽象接口（adapter.py）
class VisionAdapter(ABC):
    async def find_icon(screenshot, icon_name) → (x, y) | None
    async def find_element(screenshot, desc) → (x, y) | None
    async def detect_page_state(screenshot, desc) → bool
    async def verify_action(before, after, desc) → bool
    async def read_text(screenshot, region) → [TextResult]
    async def detect_anomaly(screenshot) → str | None
    async def plan_actions(screenshot, task) → [ActionStep]
```

优先级：**GUI-Owl（本地 vLLM）→ GPT-4o → Claude**

---

## 5. 前端结构与逐层讲解

```
frontend/src/
├── main.tsx             # React 渲染入口
├── App.tsx              # 路由配置（BrowserRouter）
├── theme.ts             # MUI 深色主题 + 颜色常量
│
├── pages/               # 5个页面
│   ├── ControlCenter.tsx  # 总控中心（首页）
│   ├── DevTools.tsx       # 开发者工具（单设备调试）
│   ├── GroupControl.tsx   # 群控（多设备批量执行）
│   ├── Calibration.tsx    # 标定页面
│   └── Settings.tsx       # 系统设置
│
├── components/
│   ├── DevTools/          # DevTools 页面的子组件（共10个）
│   │   ├── DeviceToolbar.tsx   # 顶部设备选择工具栏
│   │   ├── PhonePreview.tsx    # 手机截图预览区域
│   │   ├── DeviceControls.tsx  # 归零/截图/手动控制按钮
│   │   ├── LogPanel.tsx        # 日志输出面板（5行高度固定）
│   │   ├── ScriptToolbar.tsx   # 脚本工具栏（运行/停止/保存）
│   │   ├── RuleCard.tsx        # 规则卡片（展开/折叠）
│   │   ├── RuleParams.tsx      # 规则参数表单
│   │   ├── SubActionQueue.tsx  # 子动作队列容器（DnD）
│   │   ├── SubActionRow.tsx    # 单条子动作行（可拖拽排序）
│   │   └── DetectArea.tsx      # 视觉检测区域绘制
│   └── common/
│       ├── StatusIndicator.tsx # 状态圆点指示器
│       └── EmergencyStop.tsx   # 全局紧急停止悬浮按钮
│
├── stores/              # Zustand 全局状态
│   ├── deviceStore.ts   # 设备列表 + 选中设备
│   ├── ruleStore.ts     # 规则列表 CRUD + 子动作管理
│   └── logStore.ts      # 日志环形缓冲（最多200条）
│
├── api/                 # HTTP 请求封装
│   ├── client.ts        # axios 实例 + 自动注入 Token
│   ├── devices.ts       # devicesApi / templatesApi / tasksApi
│   └── ws.ts            # WebSocket 客户端（自动重连）
│
└── types/               # TypeScript 类型定义
    ├── device.ts        # Device, DeviceStatus
    └── rule.ts          # Rule, SubAction, ActionType, Template
```

### 5.1 路由结构

```
/              → ControlCenter（总控中心）
/devtools      → DevTools（单设备开发调试）
/group         → GroupControl（群控执行）
/calibration   → Calibration（坐标标定）
/settings      → Settings（系统配置）
```

### 5.2 DevTools 页面布局（devtools）

```
┌──────────────────────────────────────────────────────────┐
│   左侧面板 (460px 固定宽)       │  右侧面板 (flex: 1)    │
│                                 │                        │
│ ┌─────────────────────────────┐ │  ScriptToolbar          │
│ │ DeviceToolbar               │ │  ─────────────────────  │
│ │ (设备选择下拉 + 连接按钮)   │ │  RuleCard × N           │
│ └─────────────────────────────┘ │  (可拖拽的规则卡片列表) │
│ ┌─────────────────────────────┐ │                        │
│ │ PhonePreview                │ │                        │
│ │ flex: 1 (占剩余高度)        │ │                        │
│ │ 手机截图 / 检测区域绘制     │ │                        │
│ └─────────────────────────────┘ │                        │
│ ┌─────────────────────────────┐ │                        │
│ │ DeviceControls (归零/截图)  │ │                        │
│ └─────────────────────────────┘ │                        │
│ ┌─────────────────────────────┐ │                        │
│ │ LogPanel  height: 106px     │ │                        │
│ │ 固定5行日志显示             │ │                        │
│ └─────────────────────────────┘ │                        │
└──────────────────────────────────────────────────────────┘
```

### 5.3 GroupControl 页面布局

```
┌───────────────────────────────────────────────────────────┐
│ 左侧边栏 (210px)             │  主内容区 (flex: 1)        │
│                              │                            │
│ 设备勾选列表                 │  顶部工具栏                 │
│ ─────────────────            │  (脚本选择/全选/运行/停止) │
│ 全局控制                     │  ──────────────────────   │
│ [全选] [取消]                 │  设备卡片 Grid             │
│                              │  (150~420px 响应式宽度)    │
│ 脚本选择下拉                 │  每卡片：IP + 手机截图      │
│                              │  ──────────────────────   │
│ [▶ 全部运行]                 │  分页 (10/20/50/100 per页) │
│ [■ 全部停止]                 │                            │
└───────────────────────────────────────────────────────────┘
```

---

## 6. 数据流转全流程

以"点击手机图标"为例，完整流程：

```
用户在 DevTools 点击 PhonePreview 上的坐标
      ↓
ruleStore.setCoordinate(x, y)  ← 发送到选中规则
      ↓
用户点击 ScriptToolbar [运行]
      ↓
前端: tasksApi.execute(deviceId, { action: 'tap', params: { screen_percent: [x%, y%] } })
      ↓
后端 API: POST /api/v1/devices/{id}/execute
      ↓
scheduler.dispatch_task(device_id, yaml_content)
      ↓
FlowEngine._execute_step({ action: 'tap_icon', icon: '...' })
      ↓
screenshot.capture_screenshot(device_ip)  ← 从 go2rtc 抓图
      ↓
vision_manager.find_icon(screenshot, icon_name)  ← 大模型推理 → (px_x, px_y)
      ↓
coord_mapper.pixel_to_mech(px_x, px_y)  ← 坐标转换 → (mech_x, mech_y)
      ↓
motion.tap(mech_x, mech_y)
      ↓
moonraker_client.send_gcode("G1 Z30 F3000\nG1 X75 Y60 F6000\nG1 Z0 F3000\nG1 Z30 F3000")
      ↓
N1 miniPC Klipper 执行 G-Code → 机械手指物理点击手机屏幕
      ↓
ws_manager.broadcast("task_progress", {...})
      ↓
前端 wsClient 收到事件 → logStore.addLog(…)  → LogPanel 显示
```

---

## 7. 核心算法详解

### 7.1 坐标映射（coordinate.py）

将**截图像素坐标**映射到**机械坐标**（mm）：

**标定前（默认线性比例）：**
```
mech_x = (pixel_x / 1280) × 150
mech_y = (pixel_y / 720)  × 150
```

**标定后（四点仿射变换）：**
通过 Calibration 页面选取4个对应点对，计算线性插值：
```python
mx = mx_tl + (px - px_tl[0]) / px_w * mx_w + offset_x
my = my_tl + (py - px_tl[1]) / px_h * mx_h + offset_y
```
最终结果在 [0, 150] 范围内 clamp。

### 7.2 安全运动原则（motion.py）

每次 XY 移动都**先抬 Z 轴**，防止拖拽划伤手机：
```
当前位置 → Z 抬至 30mm → XY 移动 → Z 下压到目标高度
```

速度限制：
- XY 最大 F9000（150mm/s）
- Z 最大 F4800（80mm/s）

### 7.3 SubAction 拖拽排序（@dnd-kit）

`SubActionQueue.tsx` 使用 `@dnd-kit/sortable`：
```tsx
<DndContext onDragEnd={handleDragEnd}>
  <SortableContext items={subActions.map(s => s.id)}>
    {subActions.map(s => <SubActionRow key={s.id} ... />)}
  </SortableContext>
</DndContext>
```
拖拽完成后调用 `ruleStore.reorderSubActions(ruleId, fromIndex, toIndex)`。

### 7.4 WebSocket 自动重连（ws.ts）

```typescript
ws.onclose = () => {
  setTimeout(() => this.connect(), 3000)  // 3秒后重连
}
// 每30秒发送 ping 保活
setInterval(() => ws.send('ping'), 30000)
```

---

## 8. API 速查表

所有 API 路径前缀：`/api/v1`，需要 Bearer Token 鉴权（除 `/token` 外）。

### 认证

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/token` | 获取 JWT，存入 localStorage |

### 设备

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/devices` | 列出所有设备（含状态） |
| GET | `/devices/{id}/status` | 获取单台设备状态 |
| GET | `/devices/{id}/screenshot` | 返回 JPEG 截图 |
| POST | `/devices/{id}/home` | 归零（G28） |
| POST | `/devices/{id}/reset` | 从 ESTOP 恢复 |
| POST | `/devices/{id}/execute` | 执行单步动作 |
| POST | `/devices/{id}/stop` | 停止当前任务 |
| POST | `/devices/{id}/calibrate` | 保存标定数据 |

### 视觉模型

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/vision/health` | 检查 vLLM / OpenAI / Anthropic 连通性及已加载模型 |
| POST | `/vision/test` | 运行推理测试（ping 或图像推理，需传 device_id） |

### 任务

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/tasks/natural` | 自然语言指令执行 |
| GET | `/tasks/{id}` | 查询任务状态 |

### 模板

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/templates` | 列出所有 YAML 模板 |
| POST | `/templates` | 创建模板 |
| PUT | `/templates/{id}` | 更新模板 |
| DELETE | `/templates/{id}` | 删除模板 |

### WebSocket

| 路径 | 事件 | 数据格式 |
|------|------|------|
| `/ws/status` | `device_status` | `{ device_id, status, ip }` |
| `/ws/status` | `task_progress` | `{ device_id, step, total, action }` |

---

## 9. 状态管理（Zustand Stores）

### deviceStore.ts

```typescript
{
  devices: Device[]             // 所有22台设备
  selectedDeviceId: number|null // 当前选中的设备
  
  fetchDevices()          // GET /devices → 更新 devices
  updateDeviceStatus()    // WebSocket 推送时调用
  selectDevice(id)        // 切换选中设备
  selectedDevice()        // 返回选中设备对象
}
```

### ruleStore.ts

```typescript
{
  rules: Rule[]            // 当前脚本的所有规则
  selectedRuleId: string   // 当前选中的规则

  addRule(afterId?)        // 在指定规则后插入新规则
  removeRule(id)           // 删除规则
  duplicateRule(id)        // 复制规则（含所有子动作）
  updateRule(id, partial)  // 修改规则字段
  
  addSubAction(ruleId)         // 添加子动作
  removeSubAction(ruleId, id)  // 删除子动作
  updateSubAction(...)         // 修改子动作
  reorderSubActions(...)       // 拖拽排序
  
  setCoordinate(x, y)      // 点击 PhonePreview 时设置坐标
  clearAll()               // 清空脚本
  loadRules(rules)         // 从模板加载规则
}
```

### logStore.ts

```typescript
{
  logs: LogEntry[]   // 最近200条日志（环形缓冲）
  
  addLog(message, level)  // 添加日志（level: info/error/success/warn）
  clear()                 // 清空日志
}

// LogEntry 结构
{ id: number, time: 'HH:mm:ss', message: string, level }
```

**颜色映射：**
- `info` → `#aaaaaa`（灰色）
- `success` → `#4caf50`（绿色）
- `warn` → `#ff9800`（橙色）
- `error` → `#f44336`（红色）

---

## 10. 本地开发环境启动

### 环境要求

- Python 3.9（不支持 3.10+，部分语法已做兼容处理）
- Node.js 18+

### 后端启动

```bash
cd backend
pip3 install -r requirements.txt
pip3 install greenlet  # 必须！SQLAlchemy async 依赖

# 复制并修改配置（主要改 database_url 为 sqlite）
cp ../.env.example .env
# 编辑 .env 添加：
# DATABASE_URL=sqlite+aiosqlite:///./test.db

uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

验证：`curl http://localhost:8080/health` → `{"status":"ok"}`

API 文档：`http://localhost:8080/docs`

### 前端启动

```bash
cd frontend
npm install
npm run dev
# 访问 http://127.0.0.1:5173
```

Vite 代理配置（`vite.config.ts`）将 `/api` 转发到 `localhost:8080`。

---

## 11. 关键配置项

配置文件：`backend/.env`（空时使用 `config.py` 默认值）

```env
# 数据库（本地用 SQLite，生产用 MySQL）
DATABASE_URL=sqlite+aiosqlite:///./test.db
# DATABASE_URL=mysql+aiomysql://root:password@localhost:3306/phonetest

# JWT 密钥（生产必须修改！）
JWT_SECRET_KEY=change-this-to-a-random-secret-key
JWT_EXPIRE_MINUTES=1440  # 24小时

# 设备 IP 范围
DEVICE_IP_START=192.168.1.101
DEVICE_IP_END=192.168.1.122
DEVICE_MOONRAKER_PORT=7125
DEVICE_GO2RTC_PORT=1984

# 视觉模型（本地 vLLM）
VLLM_BASE_URL=http://localhost:8000/v1

# 视觉模型（云端 Fallback）
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# vLLM 模型名（必须与 vllm serve 的模型 ID 一致）
VLLM_MODEL=mPLUG/GUI-Owl-1.5-8B-Instruct

# Ollama（macOS 开发阶段，GUI-Owl-7B 本地模型别名）
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gui-owl-7b
```

---

## 11.1 macOS 开发环境视觉模型安装

> GUI-Owl-1.5 使用 qwen3_vl 架构，当前 Ollama 0.20.x 的 llama.cpp 后端尚不支持，
> 因此开发阶段使用 GUI-Owl-7B（基于 qwen2.5vl，GUI-Owl 系列前代版本，API 格式完全相同）。

### 一次性安装步骤

```bash
# 1. 安装 Ollama（已完成）
curl -fsSL https://ollama.com/install.sh | sh

# 2. 拉取 GUI-Owl-7B GGUF（Q4_K_M 量化，约 4.7GB + 视觉投影 729MB）
ollama pull hf.co/mradermacher/GUI-Owl-7B-GGUF:Q4_K_M

# 3. 创建带正确 chat template 的本地模型别名（Qwen2.5-VL 格式）
cat > /tmp/Modelfile-guiowl <<'EOF'
FROM hf.co/mradermacher/GUI-Owl-7B-GGUF:Q4_K_M

TEMPLATE """{{ if .System }}<|im_start|>system
{{ .System }}<|im_end|>
{{ end }}{{ range .Messages }}<|im_start|>{{ .Role }}
{{ .Content }}<|im_end|>
{{ end }}<|im_start|>assistant
"""

PARAMETER stop "<|im_end|>"
PARAMETER stop "<|im_start|>"
PARAMETER temperature 0.1
EOF
ollama create gui-owl-7b -f /tmp/Modelfile-guiowl

# 4. 验证
curl -s http://localhost:11434/api/chat -d '{
  "model": "gui-owl-7b",
  "messages": [{"role":"user","content":"reply: ok"}],
  "stream": false
}' | python3 -c "import sys,json; print(json.load(sys.stdin)['message']['content'])"
# 预期输出: ok
```

### Ollama 服务管理

```bash
ollama serve          # 手动启动（安装后自动启动，重启后需手动执行）
ollama list           # 查看已安装模型
ollama ps             # 查看已加载到内存的模型
```

---

## 11.2 切换到 NVIDIA GPU / vLLM 生产部署

> 当前阶段在 Apple M4 上用 Ollama 进行开发调试。
> 后期迁移到 NVIDIA 显卡服务器（CUDA）时，按以下步骤操作。

### 硬件 & 系统要求

| 项目 | 要求 |
|------|------|
| GPU | NVIDIA 显卡（3050 / 3080 / 4090 均可，显存 ≥ 8GB） |
| 系统 | Linux（Ubuntu 20.04 / 22.04 推荐） |
| CUDA | 12.1+（`nvidia-smi` 验证） |
| Python | 3.9 ~ 3.11 |
| 显存参考 | GUI-Owl-1.5-8B ≈ 10GB；GUI-Owl-1.5-2B ≈ 4GB（3050 8GB 推荐用 2B） |

### 步骤 1：在 NVIDIA 服务器安装 vLLM

```bash
# Ubuntu 服务器上执行
pip install vllm

# 验证 CUDA 可用
python -c "import torch; print(torch.cuda.is_available())"
```

### 步骤 2：启动 vLLM 推理服务（部署 GUI-Owl-1.5）

```bash
# GUI-Owl-1.5-8B-Instruct（8B，约需 10GB 显存，3050 8GB 较紧，建议量化）
python -m vllm.entrypoints.openai.api_server \
  --model mPLUG/GUI-Owl-1.5-8B-Instruct \
  --host 0.0.0.0 \
  --port 8000 \
  --dtype auto \
  --max-model-len 32768 \
  --mm-processor-kwargs '{"size": {"longest_edge": 3072000, "shortest_edge": 65536}}' \
  --limit-mm-per-prompt 'image=5'

# 显存不够（3050 8GB）时改用更小的 2B 版本：
python -m vllm.entrypoints.openai.api_server \
  --model mPLUG/GUI-Owl-1.5-2B-Instruct \
  --host 0.0.0.0 \
  --port 8000
# 同时在 .env 中改：VLLM_MODEL=mPLUG/GUI-Owl-1.5-2B-Instruct
```

验证：`curl http://服务器IP:8000/v1/models` 应返回 `mPLUG/GUI-Owl-1.5-8B-Instruct`。

### 步骤 3：修改后端 .env

```env
VLLM_BASE_URL=http://192.168.1.200:8000/v1
VLLM_MODEL=mPLUG/GUI-Owl-1.5-8B-Instruct   # 与 vllm serve 的 --model 参数一致
```

不需要改其他任何配置。

### 步骤 4：调整视觉适配器优先级

默认代码优先级是 **Ollama → vLLM**，切换到生产后把 vLLM 调到第一位：

编辑 `backend/app/vision/manager.py`：

```python
# 生产环境：vLLM 优先，Ollama 关掉
# self._adapters.append(OllamaAdapter())   ← 注释掉或删除
self._adapters.append(GUIOwlAdapter())     # 1st — NVIDIA vLLM
# OpenAI / Anthropic fallback 保持不变
```

### 步骤 5：重启后端验证

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

访问 `http://127.0.0.1:5173/vision-test` → 点「全部检查」：
- vLLM 行应显示绿色 ✅
- Ollama 行变红（因为本机没跑 Ollama，属于正常）

### 各方案对比

| 方案 | 硬件 | 速度 | 成本 | 场景 |
|------|------|------|------|------|
| Ollama | Apple M4 (Metal) | 中 | 0（已有设备） | 开发调试（GUI-Owl-7B GGUF，4.7GB，qwen2.5vl 架构） |
| vLLM + GUI-Owl-1.5 | NVIDIA 3050 8GB | 快 | 低（N 卡便宜） | 生产部署（2B 版可跑 8GB 显存） |
| OpenAI API | 云端 | 最快 | 按 token 计费 | 兜底 fallback |
| Anthropic API | 云端 | 快 | 按 token 计费 | 兜底 fallback |

---

## 12. 待完成的功能清单

### 高优先级

- [x] **ControlCenter 页面**：已实现设备状态统计面板 + 自然语言指令输入 + 导航卡片
- [x] **WebSocket 接入前端**：`App.tsx` 全局连接 WS，监听 `device_status` / `task_progress` / `task_complete`，实时更新 deviceStore
- [x] **DeviceToolbar 设备切换**：挂载时自动扫描 + 选中第一台；Refresh 按钮已绑定 `handleScan`
- [x] **ScriptToolbar 运行/停止逻辑**：▶ 调用 `tasksApi.runYaml`；■ 调用 `tasksApi.stop`；保存/加载模板已接入 `/templates` API；导出 YAML 按钮下载文件
- [x] **Settings 页面**：服务器配置 + vLLM 地址 + API 密钥（OpenAI/Anthropic，带显示/隐藏切换）+ Moonraker/go2rtc 端口；localStorage 持久化

### 中优先级

- [x] **Calibration 页面**：4点标定交互（点击预览图自动填充坐标）+ 挂载时自动加载设备已有标定数据
- [x] **自然语言输入框**：ControlCenter 和 DeviceControls 均已接入 `/tasks/natural` API
- [x] **GroupControl 执行状态回显**：设备卡片显示 WS 驱动的运行中转圈 / 成功绿色 / 失败红色状态
- [x] **模板保存/加载**：ScriptToolbar 的保存/加载按钮已关联 `/templates` API

### 低优先级（需硬件）

- [x] go2rtc 视频流接入：后端新增 `GET /devices/{id}/stream` MJPEG 代理端点；PhonePreview 优先使用 MJPEG 流，失败时降级 JPEG 轮询（500ms）
- [x] 视觉模型 vLLM 部署测试：新增 `GET /api/v1/vision/health`（检查所有 Provider 连通性）+ `POST /api/v1/vision/test`（Ping 及图像推理测试）；新增模型管理 API（列表/拉取流式进度/删除）；前端 `/vision-test` 页面含「模型管理」（下载进度条、已加载模型、删除）+ 连接检查 + 推理测试三块；可从总控中心导航卡或设置页跳转
- [ ] 实际 N1 节点联调测试

---

## 13. 开发约定 & 容易踩的坑

### Python 3.9 兼容性

❌ **禁止使用 3.10+ 语法：**
```python
# 禁止
def foo(x: str | None): ...
async with asyncio.timeout(5): ...
list[str]  # 作为运行时注解

# 正确写法
from typing import Optional, List
def foo(x: Optional[str]): ...
client_timeout = aiohttp.ClientTimeout(total=5)
List[str]
```

### 前端 Token 机制

前端使用**匿名 token**（调用 `POST /token` 不需要用户名密码），token 存入 `localStorage['token']`，`client.ts` 拦截器自动带入。

找不到 token 时先调用 `ensureToken()` 再发请求。

### 截图刷新策略

GroupControl 中的设备卡片每 1000ms 重新 `setImgSrc` 强制刷新（URL 带时间戳参数）：
```typescript
setImgSrc(devicesApi.screenshot(device.id))  // 包含 ?t=Date.now()
```

### MUI 深色主题颜色常量

```typescript
// theme.ts 中定义
colors.bg        = '#1a1a2e'  // 页面背景
colors.surface   = '#16213e'  // 卡片背景
colors.border    = '#333333'  // 边框
colors.textPrim  = '#e0e0e0'  // 主文字
colors.textSec   = '#aaaaaa'  // 次要文字
colors.primary   = '#2196f3'  // 蓝色强调
```

### 设备 ID 与 IP 对应关系

```
设备数据库 ID 1  → 192.168.1.101 → hostname: nb-01
设备数据库 ID 2  → 192.168.1.102 → hostname: nb-02
…
设备数据库 ID 22 → 192.168.1.122 → hostname: nb-22
```

初始化由 `device_manager.init_devices()` 在首次启动时自动完成。

---

*文档生成于 2026-04-09，对应项目当前开发状态*
