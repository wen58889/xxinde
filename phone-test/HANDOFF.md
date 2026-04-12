# 手机APP自动化测试系统 — 开发交接文档

> **文档版本**：2026-04-12 | **状态**：Phase 1 单机闭环基本完成，Phase 2 WEB界面基本完成
> **本文档目标**：下一位AI程序员/开发者读完即可独立继续开发、维护、修Bug。

---

## 1. 项目概述

**一句话**：用机械臂（CoreXY）+ 摄像头 + OpenCV/OCR 模拟真实手指触碰手机屏幕，自动化测试APP性能。

**核心约束**：
- 必须物理触碰屏幕（不用ADB），Android/iOS 都要支持
- 当前规模：3台样机（N1盒子 + CoreXY机械臂 + RP2040下位机 + C270摄像头）
- 远期目标：22台并发 → 10万台
- 视觉系统：**不用AI大模型**，只用 OpenCV 模板匹配 + PaddleOCR（确定性、可重复）

**硬件拓扑**：
```
总控服务器 (macOS, Python 3.12, 3060显卡)
  ├── HTTP/WS ←→ N1盒子-01 (192.168.5.101, Armbian, Klipper+Moonraker+go2rtc)
  ├── HTTP/WS ←→ N1盒子-02 (192.168.5.102)
  └── HTTP/WS ←→ N1盒子-03 (192.168.5.103)
                     ↓
               RP2040下位机 (USB串口 → 步进电机)
                     ↓
               CoreXY机械臂 (X/Y/Z 轴) → 电容笔 → 手机屏幕
                     ↓
               C270摄像头 (USB → go2rtc → JPEG快照)
```

---

## 2. 快速启动

### 2.1 环境要求

| 组件 | 版本 | 说明 |
|------|------|------|
| Python | 3.12 | `/Library/Frameworks/Python.framework/Versions/3.12/bin/python3` |
| Node.js | 18+ | 前端构建 |
| SQLite | 内置 | 开发数据库（生产可切MySQL） |

### 2.2 后端启动

```bash
cd /Users/yu/Projects/phone-test

# 安装依赖（首次）
pip3 install -r backend/requirements.txt
pip3 install paddlepaddle paddleocr  # OCR 必须单独装

# 启动
bash start_backend.sh
# 等价于: cd backend && python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

后端跑在 `http://localhost:8080`，带 `--reload` 热更新。

### 2.3 前端启动

```bash
cd frontend
npm install   # 首次
npm run dev   # http://localhost:5173
```

Vite 自动代理 `/api` → `http://localhost:8080`。

### 2.4 验证

```bash
# 健康检查
curl http://localhost:8080/health
# => {"status":"ok"}

# 获取 Token（无密码，直接发放）
curl -X POST http://localhost:8080/api/v1/token
# => {"access_token":"eyJ..."}

# 视觉系统健康
curl -H "Authorization: Bearer <token>" http://localhost:8080/api/v1/vision/health
```

---

## 3. 项目结构

```
phone-test/
├── CLAUDE.md              # AI助手总纲（系统架构、页面设计、交付计划）
├── HANDOFF.md             # ← 本文档
├── start_backend.sh       # 一键启动后端
├── docker-compose.yml     # MySQL（开发用SQLite可忽略）
├── backend/
│   ├── .env               # ★ 运行时配置（IP范围、裁剪区域、阈值等）
│   ├── requirements.txt   # Python依赖
│   ├── test.db            # SQLite数据库（自动生成）
│   ├── app/
│   │   ├── main.py        # FastAPI入口 + lifespan + 路由挂载
│   │   ├── config.py      # Pydantic Settings（读.env）
│   │   ├── database.py    # SQLAlchemy async engine + session
│   │   ├── auth.py        # JWT生成/验证（无用户名密码，直接发token）
│   │   ├── ws_manager.py  # WebSocket广播管理
│   │   ├── api/           # API路由层
│   │   │   ├── auth.py           # POST /token
│   │   │   ├── devices.py        # ★ 设备CRUD、扫描、视觉、移动、快照
│   │   │   ├── tasks.py          # 任务执行、批量运行、自然语言
│   │   │   ├── templates.py      # YAML模板CRUD
│   │   │   ├── templates_icons.py # 模板图标上传/裁剪/列表
│   │   │   ├── calibration.py    # 4点标定
│   │   │   ├── emergency.py      # 全局急停
│   │   │   ├── vision_test.py    # 视觉测试（匹配测试、OCR测试、健康检查）
│   │   │   ├── settings_api.py   # 运行时设置修改
│   │   │   └── ws.py             # WebSocket /ws/status
│   │   ├── models/        # SQLAlchemy ORM
│   │   │   ├── device.py         # Device + DeviceStatus枚举
│   │   │   ├── calibration.py    # CalibrationData（标定点、偏移量）
│   │   │   ├── task.py           # TaskExecution + TaskStatus枚举
│   │   │   └── template.py       # Template（YAML模板存储）
│   │   ├── schemas/       # Pydantic请求/响应模型
│   │   │   └── __init__.py       # DeviceOut, TaskOut, VisionRequest等
│   │   ├── services/      # ★ 核心业务逻辑
│   │   │   ├── moonraker_client.py  # Moonraker HTTP客户端（全局共享session）
│   │   │   ├── device_manager.py    # 设备生命周期 + 心跳监控
│   │   │   ├── motion.py           # 机械臂安全运动控制（G-code）
│   │   │   ├── screenshot.py       # go2rtc截图 + 旋转
│   │   │   ├── coordinate.py       # 像素→机械坐标映射（4点标定）
│   │   │   ├── flow_engine.py      # YAML流程引擎
│   │   │   ├── scheduler.py        # 多设备并发调度
│   │   │   └── device_lock.py      # 设备独占锁
│   │   ├── vision/        # ★ 视觉系统
│   │   │   ├── adapter.py              # 抽象接口（VisionAdapter）
│   │   │   ├── template_match_adapter.py # 实现：OpenCV + OCR
│   │   │   ├── opencv_matcher.py        # OpenCV TM_CCOEFF_NORMED封装
│   │   │   ├── ocr_service.py           # PaddleOCR 3.4.0 封装（单例）
│   │   │   └── manager.py              # VisionManager门面
│   │   └── nlp/
│   │       └── intent.py          # 自然语言→YAML（规则匹配，非AI）
│   └── tests/             # （空，待补充）
├── frontend/
│   ├── package.json       # React 18 + MUI 6 + Zustand 4
│   ├── vite.config.ts     # Vite + proxy配置
│   ├── src/
│   │   ├── App.tsx        # 路由定义 + WS连接 + Token自动获取
│   │   ├── theme.ts       # MUI暗色主题
│   │   ├── api/
│   │   │   ├── client.ts       # Axios实例 + 拦截器 + Token刷新
│   │   │   ├── devices.ts      # 所有API函数封装
│   │   │   └── ws.ts           # WebSocket客户端（自动重连）
│   │   ├── pages/
│   │   │   ├── ControlCenter.tsx    # / 控制中心入口
│   │   │   ├── DevTools.tsx         # /devtools 开发者工具（主页面）
│   │   │   ├── GroupControl.tsx     # /group 投屏群控
│   │   │   ├── Calibration.tsx      # /calibration 标定页
│   │   │   ├── Settings.tsx         # /settings 参数页
│   │   │   └── VisionTest.tsx       # /vision-test 视觉测试
│   │   ├── components/
│   │   │   ├── DevTools/            # 开发者工具子组件
│   │   │   │   ├── PhonePreview.tsx      # 手机屏幕预览（点击取坐标 + 机械臂联动）
│   │   │   │   ├── RuleCard.tsx          # 规则卡片
│   │   │   │   ├── RuleParams.tsx        # 规则参数行
│   │   │   │   ├── SubActionQueue.tsx    # 子动作队列
│   │   │   │   ├── SubActionRow.tsx      # 单条子动作
│   │   │   │   ├── ScriptToolbar.tsx     # 脚本工具栏
│   │   │   │   ├── DeviceToolbar.tsx     # 设备选择栏
│   │   │   │   ├── DeviceControls.tsx    # 底部控制栏（识图/识字/复位等）
│   │   │   │   ├── LogPanel.tsx          # 日志面板
│   │   │   │   └── DetectArea.tsx        # 探测区域
│   │   │   └── common/
│   │   │       ├── EmergencyStop.tsx     # 全局急停浮动按钮
│   │   │       └── StatusIndicator.tsx   # 设备状态指示灯
│   │   ├── stores/
│   │   │   ├── deviceStore.ts    # 设备列表 + 视觉目标 + 机械臂联动开关
│   │   │   ├── ruleStore.ts      # 规则编辑器状态
│   │   │   └── logStore.ts       # 日志存储
│   │   ├── types/
│   │   │   ├── device.ts         # Device, DeviceStatus
│   │   │   └── rule.ts           # Rule, SubAction, ActionType
│   │   └── utils/
│   │       ├── rulesYaml.ts      # 规则 ↔ YAML 转换
│   │       └── localVision.ts    # 前端本地视觉辅助
├── templates/
│   ├── douyin.yaml        # 抖音测试模板
│   ├── wechat.yaml        # 微信测试模板
│   └── icons/             # 模板图标图片
│       ├── _common/       # 通用图标（如 支付宝.jpg）
│       ├── 微信/          # 微信专属图标
│       └── 抖音/          # 抖音专属图标
├── deploy/
│   ├── install_n1.sh      # N1节点安装脚本
│   ├── harden_n1.sh       # N1加固脚本
│   ├── batch_deploy.sh    # 批量部署
│   ├── go2rtc.yaml        # go2rtc配置模板
│   └── start_guiowl.sh    # (已废弃，GUI-Owl已移除)
└── n1/
    └── camera_server.py   # (旧版，已用go2rtc替代)
```

---

## 4. 核心配置文件

### 4.1 backend/.env（★必读）

```env
DATABASE_URL=sqlite+aiosqlite:///./test.db
JWT_SECRET_KEY=dev-secret-key-change-in-production

# ★ 设备IP范围 — 只扫描实际存在的N1，太大会打坏macOS网络栈（ARP风暴）
DEVICE_IP_START=192.168.5.101
DEVICE_IP_END=192.168.5.103

# ★ 手机屏幕裁剪区域 — 相机图旋转后720×1280坐标系中的手机屏幕矩形
SCREEN_CROP=129,127,663,1272

# OpenCV模板匹配阈值
TEMPLATE_MATCH_THRESHOLD=0.85

# 模板图标目录（相对于backend/）
TEMPLATE_ICONS_DIR=../templates/icons

# PaddleOCR语言
OCR_LANG=ch
```

**关键注意**：`DEVICE_IP_START` 和 `DEVICE_IP_END` 范围不要超过实际设备数量。扫描不存在的IP会导致：
1. macOS ARP表填满 REJECT 路由
2. 整个局域网不可达（包括网关）
3. 需要手动 `sudo arp -a -d` 清理

### 4.2 前端代理 vite.config.ts

```ts
server: {
  port: 5173,
  proxy: {
    '/api': { target: 'http://localhost:8080', changeOrigin: true },
  },
},
```

---

## 5. 后端架构详解

### 5.1 请求生命周期

```
HTTP Request → FastAPI Router → verify_token (JWT)
  → API Handler → Service Layer → Moonraker/Vision/DB
  → JSON Response
```

### 5.2 认证系统

**极简设计**：无用户名密码，`POST /api/v1/token` 直接返回JWT。前端启动时自动获取。

```python
# backend/app/api/auth.py
@router.post("/token")
async def get_token():
    token = create_access_token({"sub": "admin"})
    return {"access_token": token}
```

所有其他API都需要 `Authorization: Bearer <token>` 头。

### 5.3 设备管理（★核心）

**状态机**：
```
ONLINE ←→ SUSPECT ←→ OFFLINE → RECOVERING → ONLINE
                                ESTOP（需手动复位）
```

**心跳参数**（`device_manager.py`）：
| 参数 | 值 | 说明 |
|------|-----|------|
| `HEARTBEAT_INTERVAL` | 10s | 心跳轮询间隔 |
| `MAX_CONCURRENT_CHECKS` | 15 | 最多15台设备同时探测 |
| `OFFLINE_CHECK_INTERVAL` | 6轮 | 已离线设备约60s检查一次 |
| `SUSPECT_THRESHOLD` | 1次 | 1次心跳失败 → SUSPECT |
| `OFFLINE_THRESHOLD` | 3次 | 3次失败 → OFFLINE |
| `RECOVER_THRESHOLD` | 2次 | 连续2次成功 → ONLINE |

**网络层**（`moonraker_client.py`）：
- 全局共享 `aiohttp.ClientSession`，`TCPConnector(limit=30, limit_per_host=2)`
- `trust_env=False` — **必须**，否则 ClashX 代理会劫持内网请求
- `is_alive()` 使用 1次尝试 × 2s超时（不重试），快速判断
- `_request()` 使用 3次重试 × 5s超时（常规API调用）
- `close_shared_session()` 在应用关闭时调用

**扫描流程**（`devices.py:scan_devices`）：
1. 从 `.env` 读取IP范围
2. `asyncio.Semaphore(15)` 并发探测每个IP的Moonraker `/server/info`
3. **只为在线设备创建数据库记录**（不创建离线幽灵设备）
4. 为新设备创建 `MoonrakerClient` 并注册到 `device_manager`

### 5.4 运动控制（★核心）

**安全规范**（`motion.py`）：

| 参数 | 值 |
|------|-----|
| CoreXY行程 | X 0-150mm, Y 0-150mm, Z 0-50mm |
| 安全高度 | Z=30mm |
| XY最大速度 | F9000 (150mm/s) |
| Z最大速度 | F4800 (80mm/s) |
| 默认XY速度 | F6000 |
| 触碰高度 | Z=0mm |

**安全移动序列**（`_safe_move_xy`）：
```
G90                    # 绝对坐标模式
G1 Z30 F3000           # 先升至安全高度
  ↓ 如果报错 "out of range" 或 "must home"
  G28                  # 自动归位（解决Klipper未归位状态）
  G1 Z30 F3000         # 重试升Z
G1 X{x} Y{y} F6000    # 走XY
```

**所有坐标和速度都有范围校验**，超出会抛 `ValueError`。

**G-code 参考**：
| G-code | 功能 |
|--------|------|
| `G28` | 全轴归位 |
| `G90` | 绝对坐标模式 |
| `G1 X{x} Y{y} Z{z} F{feed}` | 直线移动 |
| `G4 P{ms}` | 延时（毫秒） |

### 5.5 截图系统

**截图流程**（`screenshot.py`）：
```
go2rtc HTTP API → GET /api/frame.jpeg?src=camera0
  → JPEG 1280×720（摄像头横装）
  → PIL.Image.rotate(-90°)  # 顺时针90°旋转
  → JPEG 720×1280（竖屏）
  → bytes
```

- 3次重试，502时等0.8s后重试（go2rtc流未就绪）
- 使用全局共享 `aiohttp.ClientSession`

### 5.6 坐标转换

**4点标定**（`coordinate.py`）：
- 存储4个像素点和对应的机械臂坐标
- 用第1、3个点（左上、右下）做线性插值
- 支持人工微调偏移量 `offset_x/y`
- **回退**：未标定时用比例映射 `px/1280 * 150`, `py/720 * 150`
- 所有输出 clamp 到 `[0, 150]`

### 5.7 视觉系统

**架构分层**：
```
VisionManager (manager.py)              # 门面，对外API
  └── TemplateMatchAdapter              # OpenCV + OCR 实现
        ├── OpenCVMatcher               # cv2.TM_CCOEFF_NORMED
        └── OCRService                  # PaddleOCR 3.4.0 (单例, 懒加载)
```

**VisionAdapter 接口**（`adapter.py`）：
| 方法 | 输入 | 返回 |
|------|------|------|
| `find_icon(screenshot, template_name)` | bytes, str | `(x,y)` or None |
| `find_element(screenshot, template_name)` | bytes, str | `(x,y)` or None |
| `detect_page_state(screenshot, templates, ocr_keywords)` | bytes, list, list | bool |
| `verify_action(before, after)` | bytes, bytes | float (SSIM) |
| `read_text(screenshot, region?)` | bytes, tuple? | `list[TextResult]` |
| `detect_anomaly(screenshot)` | bytes | str or None |
| `detect_targets(screenshot)` | bytes | `list[VisionTarget]` |

**模板搜索顺序**：
1. `templates/icons/{app_name}/{template_name}.jpg`
2. `templates/icons/{app_name}/{template_name}.png`
3. `templates/icons/_common/{template_name}.jpg`
4. `templates/icons/_common/{template_name}.png`

**PaddleOCR 3.4.0 注意**（`ocr_service.py`）：
- **版本**：paddleocr 3.4.0 + paddlepaddle 3.3.1
- **新API**：使用 `ocr.predict(img)` 而非旧版 `.ocr(cls=True)`
- **初始化参数**：`PaddleOCR(lang='ch', use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False)`
- 旧参数 `use_gpu`, `enable_mkldnn`, `use_angle_cls`, `show_log` **已移除，不可使用**
- 结果结构：`result['rec_texts']`, `result['rec_scores']`, `result['rec_polys']`
- 首次加载会下载模型到 `~/.paddlex/official_models/PP-OCRv5_server_*/`

### 5.8 YAML流程引擎

**模板格式**：
```yaml
app: 抖音
name: 刷视频测试
steps:
  - action: tap_icon
    template: 抖音          # 对应 templates/icons/ 下的图片
    threshold: 0.85
    wait: 3
  - action: detect_state
    ocr_keywords: [推荐, 关注]
    timeout: 10
  - action: swipe
    direction: up
    duration: 0.5
    repeat: 3
    wait: [2, 4]           # [min, max] 随机
```

**支持的action类型**（`flow_engine.py`）：

| action | 参数 | 说明 |
|--------|------|------|
| `tap_icon` | template, threshold | 视觉定位图标并点击 |
| `tap` | screen_percent: [x%, y%] | 按百分比坐标点击 |
| `detect_state` | templates[], ocr_keywords[], timeout | 检测页面状态 |
| `swipe`/`swipe_up`/`swipe_down`/`swipe_left`/`swipe_right` | direction, duration, repeat | 滑动 |
| `long_press` | screen_percent, seconds | 长按 |
| `detect_anomaly` | - | 检测异常 |
| `verify_action` | - | 验证操作结果（SSIM） |

**安全机制**：任何步骤报错后自动 `G1 Z30 F3000` 抬升Z轴。

### 5.9 WebSocket实时推送

```
前端 wsClient.connect()
  → WS /api/v1/ws/status
  → 后端 ws_manager.broadcast(event, data)
  → 前端回调处理
```

事件类型：
| event | data | 触发时机 |
|-------|------|---------|
| `device_status` | `{device_id, status}` | 设备状态变化 |
| `task_progress` | `{device_id, step, total, action}` | 任务步骤进度 |

---

## 6. API 完整参考

### 6.1 认证
| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/api/v1/token` | 获取JWT（无需凭据） |

### 6.2 设备
| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/v1/devices` | 设备列表 |
| POST | `/api/v1/devices/scan` | 扫描局域网设备 |
| GET | `/api/v1/devices/{id}/status` | 设备状态 |
| POST | `/api/v1/devices/{id}/home` | G28归位 |
| POST | `/api/v1/devices/{id}/reset` | 从ESTOP恢复 |
| POST | `/api/v1/devices/{id}/firmware_restart` | 固件重启 |
| POST | `/api/v1/devices/{id}/estop` | 急停 |
| POST | `/api/v1/devices/{id}/stop` | 停止当前任务 |
| GET | `/api/v1/devices/{id}/position` | 读取XYZ位置 |
| GET | `/api/v1/devices/{id}/snapshot` | 截图（返回JPEG） |
| POST | `/api/v1/devices/{id}/move_to_pixel` | 像素坐标→机械臂移动 |
| POST | `/api/v1/devices/{id}/vision` | 视觉操作（find_icon/read_text/detect_targets） |
| POST | `/api/v1/devices/{id}/execute` | 执行单步动作 |
| POST | `/api/v1/devices/{id}/run_yaml` | 运行YAML流程 |
| POST | `/api/v1/devices/{id}/calibrate` | 保存标定数据 |
| GET | `/api/v1/devices/{id}/calibration` | 读取标定数据 |

### 6.3 任务
| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/api/v1/tasks/batch_run` | 多设备批量执行 |
| POST | `/api/v1/tasks/natural` | 自然语言指令 |

### 6.4 模板
| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/v1/templates` | 模板列表 |
| POST | `/api/v1/templates` | 创建模板 |
| GET/PUT/DELETE | `/api/v1/templates/{id}` | 模板CRUD |
| GET | `/api/v1/templates/icons` | 图标列表 |
| POST | `/api/v1/templates/icons/{app}/{name}` | 上传图标 |
| POST | `/api/v1/templates/icons/crop` | 从设备截图裁剪图标 |
| POST | `/api/v1/templates/icons/crop_base64` | 从base64裁剪图标 |
| DELETE | `/api/v1/templates/icons/{app}/{name}` | 删除图标 |

### 6.5 其他
| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/api/v1/emergency_stop` | 全局急停 |
| GET | `/api/v1/vision/health` | 视觉系统状态 |
| POST | `/api/v1/vision/match_test` | 模板匹配测试 |
| POST | `/api/v1/vision/ocr_test` | OCR测试 |
| POST | `/api/v1/settings/vision` | 保存视觉设置 |
| POST | `/api/v1/settings/screen_crop` | 修改裁剪区域 |
| WS | `/api/v1/ws/status` | WebSocket状态推送 |

### 6.6 关键请求/响应示例

**move_to_pixel**:
```json
// POST /api/v1/devices/1/move_to_pixel
// Request:
{"px": 360, "py": 640}
// Response:
{
  "pixel": {"x": 360, "y": 640},
  "mech": {"x": 64.99, "y": 73.11},
  "calibrated": true,
  "moved": true,           // false = 设备离线，但坐标转换成功
  "move_error": null,      // 非null = 移动失败原因
  "message": "pixel(360,640) → mech(64.99,73.11)mm"
}
```

**vision (read_text)**:
```json
// POST /api/v1/devices/1/vision
// Request:
{"method": "read_text", "params": {}}
// Response:
{
  "method": "read_text",
  "result": [
    {"text": "推荐", "x": 120.5, "y": 45.0, "w": 60.0, "h": 25.0, "confidence": 0.95}
  ]
}
```

---

## 7. 前端架构详解

### 7.1 技术栈

| 库 | 版本 | 用途 |
|-----|------|------|
| React | 18.3 | UI框架 |
| MUI | 6.0 | Material UI组件库 |
| Zustand | 4.5 | 状态管理（3个store） |
| React Router | 6.26 | 路由 |
| Axios | 1.7 | HTTP客户端 |
| dnd-kit | 6.1 | 拖拽排序（子动作队列） |

### 7.2 页面路由

| 路由 | 页面 | 状态 |
|------|------|------|
| `/` | ControlCenter | ✅ 已实现 |
| `/devtools` | DevTools（主页面） | ✅ 已实现 |
| `/group` | GroupControl | ✅ 基础框架 |
| `/calibration` | Calibration | ✅ 已实现 |
| `/settings` | Settings | ✅ 已实现 |
| `/vision-test` | VisionTest | ✅ 已实现 |

### 7.3 状态管理

**deviceStore**（全局设备状态）：
| 字段 | 类型 | 说明 |
|------|------|------|
| `devices` | Device[] | 设备列表 |
| `selectedDeviceId` | number \| null | 当前选中设备 |
| `visionTargets` | VisionTarget[] | 视觉识别结果叠加层 |
| `currentFrameBlob` | Blob \| null | 当前截图Blob（用于裁剪） |
| `armLinkEnabled` | boolean | 机械臂联动开关 |

**ruleStore**（规则编辑器）：
- `rules: Rule[]` — 可折叠的规则卡片列表
- `addRule / removeRule / duplicateRule / updateRule`
- `addSubAction / removeSubAction / updateSubAction / reorderSubActions`
- `setCoordinate(x, y)` — 从预览区点击填入坐标

**logStore**（日志）：
- 带时间戳、颜色分级的日志条目

### 7.4 暗色主题

```ts
// theme.ts 核心色值
background:  '#1a1a2e'     // 页面背景
paper:       '#16213e'     // 卡片/面板
primary:     '#0096ff'     // 高亮/选中
success:     '#00c853'     // 运行/保存
error:       '#ff1744'     // 停止/删除
warning:     '#ff9100'     // 打版/警告
text:        '#e0e0e0'     // 主文字
```

### 7.5 Token流程

1. `App.tsx` 挂载时调用 `ensureToken()`
2. `ensureToken()` → `POST /api/v1/token` → 存入 `localStorage`
3. Axios拦截器自动附加 `Authorization: Bearer <token>`
4. 401时自动刷新token并重试

---

## 8. N1盒子（边缘设备）

### 8.1 软件栈

| 软件 | 端口 | 用途 |
|------|------|------|
| Klipper | - | 3D打印固件，驱动RP2040 |
| Moonraker | 7125 | Klipper HTTP API |
| go2rtc | 1984 | 摄像头JPEG快照 |

### 8.2 关键API

```bash
# Moonraker — 发送G-code
POST http://192.168.5.101:7125/printer/gcode/script    {"script": "G28"}

# Moonraker — 查询状态
GET  http://192.168.5.101:7125/printer/objects/query?print_stats&toolhead&gcode_move

# Moonraker — 急停
POST http://192.168.5.101:7125/printer/emergency_stop

# Moonraker — 固件重启
POST http://192.168.5.101:7125/printer/firmware_restart

# go2rtc — 截图
GET  http://192.168.5.101:1984/api/frame.jpeg?src=camera0
```

### 8.3 部署

```bash
# 单节点安装
scp deploy/install_n1.sh root@192.168.5.101:~
ssh root@192.168.5.101 'bash install_n1.sh'

# 加固
scp deploy/harden_n1.sh root@192.168.5.101:~
ssh root@192.168.5.101 'bash harden_n1.sh'
```

---

## 9. 已知问题与踩坑记录

### 9.1 macOS网络栈 ARP 风暴（★致命）

**现象**：扫描大IP范围（如100+IP）后，整个局域网不可达。
**原因**：不存在的IP在ARP表中产生REJECT条目，连网关都ping不通。
**解决**：
1. `.env` 中 `DEVICE_IP_END` 不要超过实际设备数
2. 只为在线设备创建DB记录
3. 如果已中招：`sudo arp -a -d` 清理ARP缓存

### 9.2 代理劫持内网请求

**现象**：ClashX/代理软件运行时，内网设备请求超时。
**解决**：`aiohttp.ClientSession` 必须设置 `trust_env=False`，否则会读系统代理。

### 9.3 Klipper未归位导致移动失败

**现象**：`Move out of range: 0.000 0.000 30.000`
**原因**：Klipper开机/固件重启后处于unhomed状态，拒绝所有绝对移动。
**解决**：`motion.py:_safe_move_xy()` 检测错误后自动 `G28` 归位再重试。

### 9.4 PaddleOCR 3.x API 不兼容

**现象**：`ValueError: Unknown argument: use_gpu`
**原因**：PaddleOCR 3.4.0 移除了 `use_gpu`, `enable_mkldnn`, `use_angle_cls`, `show_log` 等旧参数。
**解决**：改用新构造函数和 `.predict()` 方法（不是 `.ocr()`），已修复。

### 9.5 go2rtc 首次取帧 502

**现象**：设备刚上线时截图返回502。
**原因**：go2rtc需要时间启动MJPEG流。
**解决**：`screenshot.py` 有3次重试，502时等0.8s。

### 9.6 相机图旋转

摄像头横装拍竖向手机，原始图 `1280×720`，需顺时针旋转90°变 `720×1280`。
`screenshot.py` 使用 `PIL.Image.rotate(-90, expand=True)` 处理。

### 9.7 路由前缀冲突

`templates_icons.router`（`/api/v1/templates/icons/...`）必须在 `templates.router`（`/api/v1/templates/...`）**之前**挂载，否则 `icons` 被当作模板ID。

---

## 10. 开发约定

### 10.1 代码规范

- **异步优先**：所有IO操作使用 `async/await`
- **HTTP库**：只用 `aiohttp`（禁止 `requests`）
- **共享Session**：通过 `_get_shared_session()` 获取，不要自己创建 `ClientSession`
- **日志**：`logger = logging.getLogger(__name__)`，包含设备ID、动作、结果
- **安全移动**：任何机械臂操作必须先抬Z到安全高度
- **坐标校验**：所有坐标/速度必须范围校验后再发送

### 10.2 添加新API

1. 在 `backend/app/api/` 下写路由
2. 在 `backend/app/main.py` 挂载 `app.include_router(xxx.router)`
3. 请求/响应模型放 `backend/app/schemas/__init__.py`
4. 前端API函数加到 `frontend/src/api/devices.ts`

### 10.3 添加新视觉能力

1. 在 `VisionAdapter`（`adapter.py`）定义抽象方法
2. 在 `TemplateMatchAdapter`（`template_match_adapter.py`）实现
3. 在 `VisionManager`（`manager.py`）暴露接口
4. 在 `devices.py:vision_action` 加分支处理

### 10.4 添加新YAML动作

1. 在 `flow_engine.py:_execute_step()` 加 `elif action == "xxx"`
2. 实现对应的 `_xxx()` 方法
3. 更新模板文档

---

## 11. 数据库模型

| 表 | 说明 | 关键字段 |
|-----|------|---------|
| `devices` | 设备列表 | id, ip, hostname, status(枚举), missed_heartbeats |
| `calibrations` | 标定数据 | device_id(FK), pixel_points(JSON), mech_points(JSON), offset_x/y |
| `task_executions` | 任务记录 | device_id(FK), status(枚举), current_step, error, log_text |
| `templates` | YAML模板 | app_name, name, yaml_content, version |

使用 SQLAlchemy 2.0 异步 ORM，启动时自动 `create_all()`（无需手动迁移）。

---

## 12. 交付进度与待办

### ✅ 已完成

- [x] Moonraker API通信 + 全局共享session
- [x] go2rtc截图获取 + 旋转
- [x] OpenCV模板匹配（TM_CCOEFF_NORMED）
- [x] PaddleOCR 3.4.0 文字识别
- [x] 4点标定 + 坐标转换
- [x] 机械臂安全运动控制（含自动G28归位）
- [x] 设备状态管理（心跳 + 状态机 + 降频）
- [x] 设备扫描（并发探测 + 只入库在线设备）
- [x] YAML流程引擎（模板解析 → 逐步执行）
- [x] 多设备并发调度 + 设备锁
- [x] Web界面（React + MUI暗色主题）
- [x] 开发者工具双栏布局（预览 + 规则编辑器 + 日志）
- [x] 点击预览取坐标 + 机械臂联动
- [x] 模板图标管理（上传/裁剪/删除）
- [x] WebSocket实时推送
- [x] 控制中心入口页 + 群控页框架

### 🔧 需要完善

- [ ] **前端规则 ↔ YAML双向转换**：`utils/rulesYaml.ts` 存在但未完全测试
- [ ] **自然语言→YAML**：`nlp/intent.py` 是规则匹配，覆盖面有限
- [ ] **VisionAdapter降级策略**：`api_vision.py` 和 `guiowl.py` 已存在但当前未使用（全用OpenCV）
- [ ] **标定页精度验证**：标定后应有自动验证流程（多点随机点击对比偏差）
- [ ] **投屏群控页**：框架已有，监控墙和分组功能待实现
- [ ] **错误处理增强**：部分异常场景缺少用户友好的前端提示
- [ ] **N1批量部署脚本**：`deploy/batch_deploy.sh` 待测试
- [ ] **日志持久化**：当前日志只在前端内存和后端stdout，无持久化
- [ ] **单元测试**：`backend/tests/` 为空

### 🚫 已废弃/已移除

- `deploy/start_guiowl.sh` — GUI-Owl模型已移除，改用OpenCV
- `backend/app/vision/guiowl.py` — 保留文件但未使用
- `backend/app/vision/api_vision.py` — API视觉后备，未接入主流程
- `backend/app/vision/ollama_adapter.py` — Ollama适配器，未使用
- `n1/camera_server.py` — 旧版摄像头服务，已被go2rtc替代

---

## 13. 常用调试命令

```bash
# 查看后端日志
tail -f /tmp/backend.log    # 如果有输出重定向
# 或者直接看终端输出（start_backend.sh 前台运行）

# 手动测试Moonraker连通性
curl -s http://192.168.5.101:7125/server/info | python3 -m json.tool

# 手动截图
curl -o /tmp/test.jpg http://192.168.5.101:1984/api/frame.jpeg?src=camera0

# 手动发G-code
curl -X POST http://192.168.5.101:7125/printer/gcode/script \
  -H 'Content-Type: application/json' -d '{"script":"G28"}'

# 检查设备位置
curl -X POST http://192.168.5.101:7125/printer/objects/query?toolhead

# 清理ARP缓存（macOS网络异常时）
sudo arp -a -d

# 直接TCP测试
nc -z -w 2 192.168.5.101 7125 && echo "OPEN" || echo "CLOSED"

# OCR独立测试
python3 -c "
import os; os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK']='True'
from paddleocr import PaddleOCR
ocr = PaddleOCR(lang='ch', use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False)
for r in ocr.predict('test.jpg'):
    print(r['rec_texts'], r['rec_scores'])
"

# 前端TypeScript检查
cd frontend && npx tsc --noEmit
```

---

## 14. 环境部署清单

### 总控服务器（macOS）

```bash
# 1. Python 3.12 依赖
pip3 install -r backend/requirements.txt
pip3 install paddlepaddle paddleocr

# 2. Node.js 前端
cd frontend && npm install

# 3. 配置 .env（修改IP范围为实际设备）
cp backend/.env.example backend/.env
# 编辑 DEVICE_IP_START, DEVICE_IP_END

# 4. 启动
bash start_backend.sh &          # 后端
cd frontend && npm run dev &     # 前端

# 5. 如果有代理软件（ClashX等），确保不代理内网：
# NO_PROXY=localhost,127.0.0.1,192.168.5.*
# 或者后端代码已设置 trust_env=False，一般不受影响
```

### N1盒子（Armbian）

```bash
# 固定IP: 192.168.5.101（手动配或DHCP保留）
# 主机名: nb-01

# 安装 Klipper + Moonraker
bash deploy/install_n1.sh

# 配置 go2rtc
cp deploy/go2rtc.yaml /etc/go2rtc/go2rtc.yaml
systemctl enable go2rtc && systemctl start go2rtc

# 验证
curl http://localhost:7125/server/info          # Moonraker
curl http://localhost:1984/api/frame.jpeg       # go2rtc
```

---

## 15. FAQ

**Q: 扫描不到设备？**
A: 检查 `.env` 中IP范围是否正确。确认N1的Moonraker端口7125可达：`nc -z -w 2 192.168.5.101 7125`

**Q: 机械臂不动？**
A: 先 `POST /devices/{id}/home` 归位。Klipper必须归位后才能绝对移动。

**Q: 截图返回502？**
A: go2rtc流未就绪，等几秒重试。检查go2rtc服务：`curl http://192.168.5.101:1984/api/streams`

**Q: OCR报错？**
A: 确认 `paddlepaddle` 和 `paddleocr` 已安装。注意是 3.x 版本，API已变更。

**Q: 整个网络断了？**
A: 可能是ARP表被污染。`sudo arp -a -d` 然后 `ping 192.168.5.1`（网关）。缩小 `.env` 中的IP扫描范围。

**Q: 如何添加新APP的测试模板？**
A: 1) 在 `templates/icons/{app_name}/` 放模板图片 2) 写 `templates/{app_name}.yaml` 3) 前端"运行"按钮执行

**Q: 如何切换MySQL数据库？**
A: 改 `.env` 中 `DATABASE_URL=mysql+aiomysql://root:phonetest@localhost:3306/phonetest`，启动 `docker-compose up -d mysql`
