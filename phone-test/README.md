# 手机APP自动化测试系统 - 项目说明

## 项目概览

基于物理机械臂的手机屏幕自动化测试系统，使用 CoreXY 机械臂在真实手机屏幕上执行点击、滑动等操作，通过视觉模型识别屏幕内容，实现全自动化测试。

### 系统架构

```
┌─────────────────────────────────────────────────────┐
│                    总控服务器                         │
│        (192.168.1.100, 3060 GPU)                    │
│  ┌──────────┐  ┌───────────┐  ┌──────────────────┐  │
│  │ FastAPI  │  │  React    │  │ GUI-Owl-1.5-8B   │  │
│  │ :8080    │  │  :5173    │  │ vLLM :8000       │  │
│  └────┬─────┘  └─────┬─────┘  └────────┬─────────┘  │
│       └───────────────┼─────────────────┘            │
│                       │ HTTP / WebSocket             │
└───────────────────────┼─────────────────────────────┘
                        │ 局域网
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
  ┌───────────┐   ┌───────────┐   ┌───────────┐
  │ N1 Box    │   │ N1 Box    │   │ N1 Box    │  × 22台
  │ .101      │   │ .102      │   │ .103~.122 │
  │           │   │           │   │           │
  │ Klipper   │   │ Klipper   │   │ Klipper   │
  │ Moonraker │   │ Moonraker │   │ Moonraker │  :7125
  │ go2rtc    │   │ go2rtc    │   │ go2rtc    │  :1984
  │     │     │   │     │     │   │     │     │
  │  RP2040   │   │  RP2040   │   │  RP2040   │
  │  CoreXY   │   │  CoreXY   │   │  CoreXY   │
  │  C270 cam │   │  C270 cam │   │  C270 cam │
  │  📱 手机   │   │  📱 手机   │   │  📱 手机   │
  └───────────┘   └───────────┘   └───────────┘
```

## 技术栈

| 层级 | 技术 | 用途 |
|------|------|------|
| **前端** | React 18 + MUI 6 + TypeScript | 管理界面 |
| **状态管理** | Zustand | 轻量级全局状态 |
| **拖拽** | @dnd-kit | 子动作排序 |
| **构建** | Vite 5 | 开发服务器 + 打包 |
| **后端** | FastAPI + Python | REST API + WebSocket |
| **ORM** | SQLAlchemy 2.0 (async) | 异步数据库操作 |
| **数据库** | MySQL 8.0 / SQLite (dev) | 持久化存储 |
| **视觉模型** | GUI-Owl-1.5-8B (INT8) | 屏幕理解，vLLM 推理 |
| **视觉备选** | GPT-4o / Claude | API 降级方案 |
| **运动控制** | Klipper + Moonraker | G-code 执行 |
| **视频流** | go2rtc | HTTP 截图 API |
| **认证** | JWT Bearer Token | 接口鉴权 |

## 目录结构

```
phone-test/
├── backend/                    # Python 后端
│   ├── app/
│   │   ├── api/                # HTTP 路由
│   │   │   ├── auth.py         # POST /token (JWT)
│   │   │   ├── devices.py      # 设备管理 API
│   │   │   ├── tasks.py        # 任务执行 API
│   │   │   ├── templates.py    # 流程模板 CRUD
│   │   │   ├── calibration.py  # 坐标标定 API
│   │   │   ├── emergency.py    # 紧急停止 API
│   │   │   └── ws.py           # WebSocket 实时状态
│   │   ├── models/             # SQLAlchemy ORM
│   │   │   ├── device.py       # 设备表 (状态机)
│   │   │   ├── task.py         # 任务执行记录
│   │   │   ├── template.py     # 流程模板
│   │   │   └── calibration.py  # 标定数据
│   │   ├── services/           # 业务逻辑
│   │   │   ├── moonraker_client.py  # Moonraker HTTP 客户端
│   │   │   ├── screenshot.py        # go2rtc 截图服务
│   │   │   ├── motion.py            # 运动控制 (安全Z轴)
│   │   │   ├── coordinate.py        # 像素→机械坐标映射
│   │   │   ├── device_lock.py       # 设备互斥锁
│   │   │   ├── device_manager.py    # 设备状态机 + 心跳
│   │   │   ├── flow_engine.py       # YAML 流程执行引擎
│   │   │   └── scheduler.py         # 任务调度 (并发22)
│   │   ├── vision/             # 视觉识别
│   │   │   ├── adapter.py      # 抽象接口 (7个方法)
│   │   │   ├── guiowl.py       # GUI-Owl-1.5-8B 适配器
│   │   │   ├── api_vision.py   # GPT-4o / Claude 适配器
│   │   │   └── manager.py      # 自动降级管理器
│   │   ├── nlp/
│   │   │   └── intent.py       # 自然语言指令解析
│   │   ├── schemas/            # Pydantic 请求/响应模型
│   │   ├── auth.py             # JWT 工具
│   │   ├── config.py           # 配置 (环境变量)
│   │   ├── database.py         # 数据库引擎
│   │   ├── ws_manager.py       # WebSocket 广播管理
│   │   └── main.py             # FastAPI 入口
│   └── requirements.txt
├── frontend/                   # React 前端
│   ├── src/
│   │   ├── api/                # Axios 封装
│   │   │   ├── client.ts       # axios 实例 + JWT 拦截器
│   │   │   ├── devices.ts      # 所有 API 调用
│   │   │   └── ws.ts           # WebSocket 客户端 (自动重连)
│   │   ├── stores/             # Zustand 状态
│   │   │   ├── deviceStore.ts  # 设备列表 + 选中
│   │   │   ├── ruleStore.ts    # 规则编辑 (CRUD + 拖拽)
│   │   │   └── logStore.ts     # 日志缓冲
│   │   ├── components/
│   │   │   ├── DevTools/       # 开发者工具组件
│   │   │   │   ├── DeviceToolbar.tsx   # 顶部：设备选择 + 扫描
│   │   │   │   ├── PhonePreview.tsx    # 手机画面预览 (点击取坐标)
│   │   │   │   ├── DeviceControls.tsx  # 控制栏：复位/TTS/识图/识字
│   │   │   │   ├── LogPanel.tsx        # 日志面板 [HH:MM:SS]
│   │   │   │   ├── ScriptToolbar.tsx   # 脚本操作：保存/运行/停止
│   │   │   │   ├── RuleCard.tsx        # 可折叠规则卡片
│   │   │   │   ├── RuleParams.tsx      # 主规则参数 (单行横排)
│   │   │   │   ├── DetectArea.tsx      # 4点检测区域
│   │   │   │   ├── SubActionQueue.tsx  # 子动作列表 (DnD 排序)
│   │   │   │   └── SubActionRow.tsx    # 单个子动作行
│   │   │   └── common/
│   │   │       ├── EmergencyStop.tsx   # 浮动紧急停止按钮
│   │   │       └── StatusIndicator.tsx # 状态指示灯
│   │   ├── pages/
│   │   │   ├── ControlCenter.tsx  # 首页 - 功能入口
│   │   │   ├── DevTools.tsx       # 开发者工具页 (核心)
│   │   │   ├── GroupControl.tsx   # 群控中心
│   │   │   ├── Calibration.tsx    # 标定工具
│   │   │   └── Settings.tsx       # 系统设置
│   │   ├── types/              # TypeScript 类型
│   │   ├── App.tsx             # 路由
│   │   ├── main.tsx            # React 入口
│   │   └── theme.ts            # MUI 暗色主题
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
├── deploy/                     # 部署脚本
│   ├── install_n1.sh           # N1 节点安装
│   ├── harden_n1.sh            # N1 安全加固
│   ├── batch_deploy.sh         # 批量部署 (101-122)
│   └── go2rtc.yaml             # go2rtc 配置模板
├── templates/                  # 测试流程模板
│   ├── douyin.yaml             # 抖音刷视频流程
│   └── wechat.yaml             # 微信基础功能流程
├── docker-compose.yml          # MySQL 8.0
├── .env.example                # 环境变量模板
└── CLAUDE.md                   # AI 上下文文档
```

## 核心功能

### 1. 设备状态机
```
ONLINE ──(3次心跳丢失)──→ SUSPECT ──(继续丢失)──→ OFFLINE
  ↑                                                   │
  └──────────────(心跳恢复)── RECOVERING ←─────────────┘
  
任意状态 ──(紧急停止)──→ ESTOP
```
- 心跳间隔: 5秒
- 通过 Moonraker `/server/info` 检测存活
- 状态变化实时通过 WebSocket 推送前端

### 2. 运动控制安全机制
- **先升Z轴**: 每次水平移动前先抬升到 Z30（安全高度）
- **坐标校验**: X/Y 范围 0-200, Z 范围 0-50
- **速度限制**: 最大 F6000 (100mm/s)
- **故障抬升**: 流程执行出错时自动抬升 Z 轴

### 3. 视觉识别链
```
GUI-Owl-1.5-8B (本地, 免费, ~9GB VRAM)
       │ 失败
       ▼
GPT-4o / Claude (API, 付费, 高精度)
```
支持7种操作: find_icon, find_element, detect_page_state, read_text, verify_action, detect_anomaly, plan_actions

### 4. 开发者工具页 (DevTools)
```
┌─ 左侧面板 ──────┬─ 右侧面板 ────────────────────┐
│ [设备选择工具栏] │ [保存][打版][⚙][▶运行][■停止] │
│                 │ [+规则][🗑️]                    │
│ ┌─────────────┐ │                                │
│ │  手机画面    │ │ ┌─ 规则卡片 1 ──────────────┐  │
│ │  (实时预览)  │ │ │ [▼] 1. 新规则 1  [📋][🗑] │  │
│ │  点击=取坐标  │ │ │ [点击▾][中心|坐标]        │  │
│ │             │ │ │ X[] Y[] 半径[] 次数[]...   │  │
│ └─────────────┘ │ │ 检测区域: x1 y1 ... [清零] │  │
│                 │ │ ❶ ≡ [点击▾] X Y ... × 删除 │  │
│ [重启][复位]    │ │ ❷ ≡ [滑屏▾] X Y ... × 删除 │  │
│ [□沉思]         │ │ [+ 添加动作]                │  │
│ [混合文字][发送] │ │ └────────────────────────────┘ │
│ [竖屏▾][🟢]    │ │                                │
│ [识图][识字]    │ │ ┌─ 规则卡片 2 ──────────────┐  │
│ [删除图像]      │ │ │ ...                        │  │
│                 │ │ └────────────────────────────┘ │
│ [日志面板]      │ │                                │
│ [10:30:01] 完成 │ │                                │
└─────────────────┴────────────────────────────────┘
                              [■] 紧急停止 (右下角浮动)
```

### 5. 页面路由

| 路径 | 页面 | 功能 |
|------|------|------|
| `/` | 控制中心 | 功能入口（4个卡片导航） |
| `/devtools` | 开发者工具 | 单设备脚本调试（核心页面） |
| `/group` | 群控中心 | 批量任务下发与监控 |
| `/calibration` | 标定工具 | 像素↔机械坐标映射 |
| `/settings` | 系统设置 | 服务器/端口配置 |

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/token` | 获取 JWT Token |
| GET | `/api/v1/devices` | 设备列表 |
| GET | `/api/v1/devices/{id}/status` | 单设备状态 |
| GET | `/api/v1/devices/{id}/screenshot` | 获取截图 |
| POST | `/api/v1/devices/{id}/home` | 机械臂归零 |
| POST | `/api/v1/devices/{id}/execute` | 执行流程模板 |
| POST | `/api/v1/devices/{id}/stop` | 停止任务 |
| POST | `/api/v1/tasks/natural` | 自然语言指令 |
| GET | `/api/v1/tasks/{id}` | 查询任务状态 |
| GET/POST | `/api/v1/templates` | 流程模板 CRUD |
| POST | `/api/v1/devices/{id}/calibrate` | 坐标标定 |
| POST | `/api/v1/emergency_stop` | 全局紧急停止 |
| WS | `/api/v1/ws/status` | 实时状态推送 |
| GET | `/health` | 健康检查 |

## 快速启动

### 方式一：开发环境（SQLite，无需 Docker）

```bash
# 1. 后端
cd backend
pip3 install -r requirements.txt
DATABASE_URL=sqlite+aiosqlite:///./test.db python3 -m uvicorn app.main:app --port 8080

# 2. 前端
cd frontend
npm install
npm run dev
```

### 方式二：生产环境（MySQL + Docker）

```bash
# 1. 启动 MySQL
docker compose up -d

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 填入实际值

# 3. 后端
cd backend
pip3 install -r requirements.txt
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8080

# 4. 前端
cd frontend
npm install && npm run build
# 使用 nginx 部署 dist/ 目录

# 5. 视觉模型 (需要 NVIDIA GPU)
vllm serve GUI-Owl-1.5-8B --quantization awq --dtype float16 --port 8000
```

## 设备网络

| IP 范围 | 用途 | 端口 |
|---------|------|------|
| 192.168.1.100 | 总控服务器 | 8080 (API), 5173 (前端), 8000 (vLLM) |
| 192.168.1.101~122 | N1 节点 ×22 | 7125 (Moonraker), 1984 (go2rtc) |

## 流程模板示例 (YAML)

```yaml
app: 抖音
name: 抖音刷视频测试
steps:
  - action: detect_state
    description: 检测抖音首页
    expect: "抖音首页，底部有推荐、关注等tab"

  - action: swipe
    direction: up
    repeat: 3
    wait: [2, 4]

  - action: tap_icon
    target: "点赞图标（心形）"
```
