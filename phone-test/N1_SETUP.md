# N1 盒子部署手册（Claude 自主执行版）

> 本文档供 Claude AI 独立完成 N1 盒子的全部部署和调试工作。
> 阅读完整文档后，Claude 可以无需人工干预地完成所有步骤。

---

## 0. 背景与目标

**系统架构**

```
macOS 服务器 (:8080)
    │
    ├─ 每 5 秒心跳 ──────── N1:7125   Moonraker HTTP API（G-code 控制机械臂）
    ├─ 发 G-code 指令 ─────  N1:7125   /printer/gcode/script
    └─ 按需拍照 ───────── N1:1984   go2rtc /api/streams/camera0.jpg （1280×720 JPEG）
```

**N1 盒子需要运行的两个服务**

| 服务 | 端口 | 用途 |
|------|------|------|
| Moonraker | 7125 | 接收 G-code，d f控制步进电机（机械臂 XYZ 运动） |
| go2rtc | 1984 | 按需拍照服务，GET /api/streams/camera0.jpg 返回 JPEG |

**机械参数（来自后端代码，切勿修改）**

| 参数 | 值 |
|------|----|
| X 轴行程 | 0 ~ 150 mm |
| Y 轴行程 | 0 ~ 150 mm |
| Z 轴行程 | 0 ~ 50 mm |
| Z 安全高度 | 30 mm（移动前先抬起） |
| 触摸高度 Z | 0 mm |
| XY 最大速度 | F9000（150 mm/s） |
| Z 最大速度 | F4800（80 mm/s） |
| 截图分辨率 | 1280 × 720 px |

**N1 盒子硬件规格（实测）**

| 项目 | 规格 |
|------|------|
| 操作系统 | Armbian 26.2.1 trixie（Debian GNU/Linux 13） |
| 内核 | Linux 6.12.68-ophub aarch64 |
| CPU | ARM Cortex-A53 × 4 核，最高 1512 MHz |
| 架构 | aarch64（64-bit ARMv8） |
| 内存 | 2 GB |
| 存储 | 8 GB eMMC |
| 主机名规则 | n101 ~ n122（对应 IP 末段） |
---

## 1. 前置条件检查

Claude 执行前先确认以下信息（SSH 进入 N1 后运行）：

```bash
# 1. 确认架构（应为 aarch64）
uname -m

# 2. 确认操作系统
cat /etc/os-release | grep -E "^NAME|^VERSION"

# 3. 确认已有网络
ip addr show | grep "inet " | grep -v "127.0.0.1"

# 4. 检查摄像头设备
ls /dev/video* 2>/dev/null || echo "无 USB 摄像头"

# 5. 检查端口占用
ss -tlnp | grep -E "7125|1984"
```

**期望结果**：`aarch64`，`Armbian 26.2.1 trixie (Debian 13)`，有 IP（192.168.5.101~122），摄像头设备存在，端口未占用。

---

## 2. 网络配置（静态 IP）

N1 的 IP 必须在 `192.168.5.101 ~ 192.168.5.122` 范围内（后端硬编码的自动注册范围）。

```bash
# 方法 A：NetworkManager（推荐，Armbian 默认）
CON=$(nmcli -t -f NAME con show --active | head -1)
nmcli con mod "$CON" \
  ipv4.method manual \
  ipv4.addresses "192.168.5.101/24" \
  ipv4.gateway "192.168.5.1" \
  ipv4.dns "8.8.8.8,114.114.114.114"
nmcli con up "$CON"

# 验证
ip addr show | grep "192.168.5."
ping -c 2 192.168.5.1
```

```bash
# 方法 B：直接编辑 /etc/network/interfaces（无 NetworkManager）
cat > /etc/network/interfaces.d/eth0 << 'EOF'
auto eth0
iface eth0 inet static
    address 192.168.5.101
    netmask 255.255.255.0
    gateway 192.168.5.1
    dns-nameservers 8.8.8.8
EOF
systemctl restart networking
```

> **注意**：多台 N1 分别用 .101、.102、.103 … 依次递增，不要重复。

---

## 3. 安装基础依赖

```bash
apt update && apt install -y \
  git python3 python3-pip wget curl \
  libopenblas-dev libatlas-base-dev \
  v4l-utils  # 摄像头工具（可选）
```

---

## 4. 安装 Klipper 固件

Klipper 运行在 N1 上，接收来自 Moonraker（进而来自服务器后端）的 G-code，驱动步进电机。

### 4.1 克隆 Klipper

```bash
cd ~
git clone https://github.com/Klipper3d/klipper.git
```

### 4.2 安装 Python 虚拟环境

```bash
cd ~/klipper
python3 -m venv ~/klippy-env
~/klippy-env/bin/pip install -r scripts/klippy-requirements.txt
```

### 4.3 创建 printer.cfg

根据机械结构填写步进电机参数。以下为**最小可用模板**，需根据实际硬件修改引脚名：

```bash
mkdir -p ~/printer_data/config ~/printer_data/logs
cat > ~/printer_data/config/printer.cfg << 'EOF'
# ============================================================
# N1 手机测试机械臂 - Klipper 配置
# 行程：X=150mm  Y=150mm  Z=50mm
# ============================================================

[printer]
kinematics: cartesian
max_velocity: 150
max_accel: 1000
max_z_velocity: 80
max_z_accel: 200
square_corner_velocity: 5.0

# ---- X 轴（根据实际驱动器接线修改）----
[stepper_x]
step_pin: PB13          # 修改为实际引脚
dir_pin: PB12           # 修改为实际引脚（前缀 ! 表示反向）
enable_pin: !PB14       # 修改为实际引脚
microsteps: 16
rotation_distance: 40   # 丝杆间距×微步数/全步数，实测后校正
endstop_pin: ^PC0       # 修改为限位开关引脚
position_min: 0
position_max: 150
position_endstop: 0
homing_speed: 30

# ---- Y 轴 ----
[stepper_y]
step_pin: PB10
dir_pin: PB2
enable_pin: !PB11
microsteps: 16
rotation_distance: 40
endstop_pin: ^PC1
position_min: 0
position_max: 150
position_endstop: 0
homing_speed: 30

# ---- Z 轴（下压轴，控制触摸力度）----
[stepper_z]
step_pin: PB0
dir_pin: PC5
enable_pin: !PB1
microsteps: 16
rotation_distance: 8    # 丝杆导程（常见 8mm 或 4mm）
endstop_pin: ^PC2
position_min: 0
position_max: 50
position_endstop: 0
homing_speed: 10

# ---- 虚拟加热器（Klipper 要求，不需要实际加热）----
[extruder]
step_pin: PB3
dir_pin: PB4
enable_pin: !PD2
microsteps: 16
rotation_distance: 33.5
nozzle_diameter: 0.4
filament_diameter: 1.75
heater_pin: PC8
sensor_type: EPCOS 100K B57560G104F
sensor_pin: PA0
min_temp: -100
max_temp: 300

[heater_bed]
heater_pin: PC9
sensor_type: EPCOS 100K B57560G104F
sensor_pin: PC3
min_temp: -100
max_temp: 130

[fan]
pin: PC6

# ---- MCU 连接（USB 串口）----
[mcu]
serial: /dev/serial/by-id/usb-Klipper_stm32f103xe_XXXXXXXXX-if00
# 运行 ls /dev/serial/by-id/ 获取实际路径

# ---- 基础 G-code 宏 ----
[gcode_macro SAFE_HOME]
gcode:
    G28
    G1 Z30 F3000

[virtual_sdcard]
path: ~/printer_data/gcodes

[display_status]

[pause_resume]
EOF
```

> **关键步骤**：运行 `ls /dev/serial/by-id/` 找到 MCU 的实际串口路径，替换上面的 `serial:` 行。

### 4.4 创建 Klipper systemd 服务

```bash
cat > /etc/systemd/system/klipper.service << 'EOF'
[Unit]
Description=Klipper 3D Printer Firmware
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root
ExecStart=/root/klippy-env/bin/python /root/klipper/klippy/klippy.py \
    /root/printer_data/config/printer.cfg \
    -l /root/printer_data/logs/klippy.log \
    -a /tmp/klippy_uds
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable klipper
systemctl start klipper
sleep 3
systemctl status klipper --no-pager | tail -10
```

---

## 5. 安装 Moonraker

Moonraker 是 Klipper 的 HTTP API 层，后端通过它发 G-code 指令。

### 5.1 安装

```bash
cd ~
git clone https://github.com/Arksine/moonraker.git
cd moonraker
python3 -m venv ~/moonraker-env
~/moonraker-env/bin/pip install -r scripts/moonraker-requirements.txt
```

### 5.2 配置

```bash
cat > ~/printer_data/config/moonraker.conf << 'EOF'
[server]
host: 0.0.0.0
port: 7125
klippy_uds_address: /tmp/klippy_uds

[authorization]
trusted_clients:
    0.0.0.0/0
    ::1/128
cors_domains:
    *

[octoprint_compat]

[history]

[file_manager]
enable_object_processing: False
EOF
```

### 5.3 创建 systemd 服务

```bash
cat > /etc/systemd/system/moonraker.service << 'EOF'
[Unit]
Description=Moonraker API Server
After=network.target klipper.service
Requires=klipper.service

[Service]
Type=simple
User=root
WorkingDirectory=/root
ExecStart=/root/moonraker-env/bin/python /root/moonraker/moonraker/moonraker.py \
    -c /root/printer_data/config/moonraker.conf \
    -l /root/printer_data/logs/moonraker.log
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable moonraker
systemctl start moonraker
sleep 3
```

### 5.4 验证 Moonraker

```bash
curl -s http://localhost:7125/server/info | python3 -m json.tool | grep -E "klippy_connected|moonraker_version"
# 期望：klippy_connected: true
```

---

## 6. 安装 go2rtc（摄像头快照服务）

go2rtc 是生产级摄像头服务，专门处理摄像头断线重连、格式兼容等边缘情况，单一二进制无外部依赖。
后端调用 `GET /api/streams/camera0.jpg` 按需取帧，无视频推流，资源占用极低。

### 6.1 下载安装

```bash
# arm64 版
wget -O /usr/local/bin/go2rtc \
  https://github.com/AlexxIT/go2rtc/releases/latest/download/go2rtc_linux_arm64
chmod +x /usr/local/bin/go2rtc
go2rtc --version
```

### 6.2 配置摄像头源

```bash
mkdir -p /etc/go2rtc

# USB 摄像头（最常见）
cat > /etc/go2rtc/go2rtc.yaml << 'EOF'
api:
  listen: ":1984"

streams:
  camera0:
    - /dev/video0#width=1280#height=720#input-format=mjpeg
EOF
```

其他摄像头类型：

```yaml
# CSI 摄像头
streams:
  camera0:
    - exec:libcamera-vid -t 0 --width 1280 --height 720 --inline --codec mjpeg -o -

# 已有 RTSP 流
streams:
  camera0:
    - rtsp://localhost:8554/stream
```

### 6.3 测试快照接口

```bash
go2rtc -config /etc/go2rtc/go2rtc.yaml &
sleep 2
curl -o /tmp/test.jpg http://localhost:1984/api/streams/camera0.jpg
python3 -c "
from PIL import Image
img = Image.open('/tmp/test.jpg')
w, h = img.size
print(f'分辨率：{w}×{h}')
assert w == 1280 and h == 720, f'尺寸错误！{w}×{h}'
print('✅ 快照分辨率正确')
"
kill %1 2>/dev/null
```

### 6.4 创建 systemd 服务

```bash
cat > /etc/systemd/system/go2rtc.service << 'EOF'
[Unit]
Description=go2rtc camera snapshot service
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/go2rtc -config /etc/go2rtc/go2rtc.yaml
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable go2rtc
systemctl start go2rtc
sleep 2
systemctl status go2rtc --no-pager | tail -5
```

---

## 7. 全服务验证

```bash
echo "=== 服务状态 ==="
systemctl is-active klipper    && echo "✅ klipper" || echo "❌ klipper"
systemctl is-active moonraker  && echo "✅ moonraker" || echo "❌ moonraker"
systemctl is-active go2rtc      && echo "✅ go2rtc" || echo "❌ go2rtc"

echo ""
echo "=== Moonraker API 心跳 ==="
curl -s http://localhost:7125/server/info | python3 -c "
import sys,json
d=json.load(sys.stdin)
connected=d.get('result',{}).get('klippy_connected',False)
print('✅ Klipper 已连接' if connected else '❌ Klipper 未连接')
"

echo ""
echo "=== 拍照接口（go2rtc）==="
curl -s -o /tmp/shot.jpg http://localhost:1984/api/streams/camera0.jpg
python3 -c "
from PIL import Image
img=Image.open('/tmp/shot.jpg')
w,h=img.size
print(f'✅ 拍照 {w}×{h}' if w==1280 and h==720 else f'❌ 拍照 {w}×{h}（期望 1280×720）')
"

echo ""
echo "=== 本机 IP ==="
ip addr show | grep "inet " | grep -v "127.0.0.1" | awk '{print $2}'
```

---

## 8. 从服务器端验证（在 macOS 服务器上运行）

```bash
N1_IP=192.168.5.101   # 改成实际 N1 的 IP

# 1. Moonraker 心跳
curl -s http://$N1_IP:7125/server/info | python3 -c "
import sys,json
d=json.load(sys.stdin).get('result',{})
print('✅ Moonraker 在线, klippy_connected:', d.get('klippy_connected'))
"

# 2. 截图（保存为 /tmp/n1_shot.jpg，go2rtc 快照接口）
curl -s -o /tmp/n1_shot.jpg http://$N1_IP:1984/api/streams/camera0.jpg
python3 -c "
from PIL import Image
img=Image.open('/tmp/n1_shot.jpg')
w,h=img.size
print(f'✅ 拍照 {w}×{h}' if w==1280 and h==720 else f'❌ 截图 {w}×{h}')
"

# 3. 等待后端检测到设备（约 10 秒后心跳变 ONLINE）
TOKEN=$(curl -s -X POST http://localhost:8080/api/v1/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=admin" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
sleep 10
curl -s http://localhost:8080/api/v1/devices -H "Authorization: Bearer $TOKEN" \
  | python3 -c "
import sys,json
devices=json.load(sys.stdin)
for d in devices:
    ip=d['ip']; status=d['status']
    icon='✅' if status=='ONLINE' else '⚠️'
    print(f'{icon} {ip}  {status}')
"
```

---

## 9. 首次运动测试（G-code 验证）

**在确认一切安全后**，通过 Moonraker 发送归零指令测试电机：

```bash
N1_IP=192.168.5.101

# 步骤 1：发送归零（G28）
curl -s -X POST http://$N1_IP:7125/printer/gcode/script \
  -H "Content-Type: application/json" \
  -d '{"script":"G28"}'

# 步骤 2：抬高 Z 轴到安全高度
curl -s -X POST http://$N1_IP:7125/printer/gcode/script \
  -H "Content-Type: application/json" \
  -d '{"script":"G1 Z30 F3000"}'

# 步骤 3：移动到中心位置
curl -s -X POST http://$N1_IP:7125/printer/gcode/script \
  -H "Content-Type: application/json" \
  -d '{"script":"G1 X75 Y75 F6000"}'

# 步骤 4：测试 Z 轴下压（Z=0 为触摸高度）
curl -s -X POST http://$N1_IP:7125/printer/gcode/script \
  -H "Content-Type: application/json" \
  -d '{"script":"G1 Z5 F3000"}'  # 先用 Z=5 测试，确认安全再用 Z=0

# 步骤 5：归零收架
curl -s -X POST http://$N1_IP:7125/printer/gcode/script \
  -H "Content-Type: application/json" \
  -d '{"script":"G1 Z30 F3000\nG28"}'
```

---

## 10. 坐标标定（Calibration）

机械坐标与像素坐标的映射需要标定。标定数据存在服务器数据库，通过后端 API 设置。

**最少需要 2 个标定点**（推荐 4 个角点）：

```bash
# 标定原理：
# pixel_points = 图像中已知位置的像素坐标 [x, y]（1280×720 坐标系）
# mech_points  = 机械臂实际到达该像素对应位置时的 XY 坐标（0~150mm）

TOKEN="..."   # 服务器端的 JWT token

# 示例：4 点标定（左上、右上、左下、右下）
curl -s -X POST http://192.168.5.8:8080/api/v1/devices/1/calibrate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "pixel_points": [[64,36],[1216,36],[64,684],[1216,684]],
    "mech_points":  [[7.5,4.2],[142.5,4.2],[7.5,140.8],[142.5,140.8]]
  }'
```

---

## 11. 常见问题排查

### Klipper 无法连接 MCU

```bash
# 查看串口设备
ls /dev/serial/by-id/
ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null

# 检查 printer.cfg 中 serial: 路径是否正确
journalctl -u klipper --no-pager -n 30 | grep -i "serial\|mcu\|error"
```

### Moonraker 无法连接（后端心跳失败）

```bash
# 检查防火墙
ufw status 2>/dev/null
iptables -L INPUT | grep -E "7125|1984"

# 如有防火墙，开放端口
ufw allow 7125/tcp
ufw allow 1984/tcp   # go2rtc
ufw reload

# 检查 Moonraker 日志
tail -30 ~/printer_data/logs/moonraker.log
```

### 拍照全黑或连接超时

```bash
# 确认摄像头已被识别
v4l2-ctl --list-devices 2>/dev/null

# 测试摄像头原始输出
ffmpeg -f v4l2 -i /dev/video0 -vframes 1 /tmp/raw.jpg -y 2>/dev/null
ls -la /tmp/raw.jpg

# 查看服务日志
journalctl -u go2rtc --no-pager -n 30

# 手动测试快照（应返回 JPEG 文件）
curl -o /tmp/test2.jpg http://localhost:1984/api/streams/camera0.jpg && \
  python3 -c "from PIL import Image; img=Image.open('/tmp/test2.jpg'); print('OK:', img.size)"
```

### 分辨率不是 1280×720

```bash
# 修改 /etc/go2rtc/go2rtc.yaml，调整 width/height 参数
# streams:
#   camera0: /dev/video0#width=1280#height=720#type=v4l2

sudo systemctl restart go2rtc
curl -o /tmp/check.jpg http://localhost:1984/api/streams/camera0.jpg
python3 -c "from PIL import Image; img=Image.open('/tmp/check.jpg'); print('实际分辨率:', img.size)"
```

---

## 12. 多台 N1 批量部署

第 2~7 步在每台 N1 上重复执行，只改 IP 地址：

| N1 编号 | IP | 用途 |
|---------|----|----|
| nb-01 | 192.168.5.101 | 设备 1 |
| nb-02 | 192.168.5.102 | 设备 2 |
| … | … | … |
| nb-22 | 192.168.5.122 | 设备 22 |

后端在首次启动时自动扫描并注册 `.101~.122` 范围内的所有设备记录，无需手动添加。

---

## 13. 部署状态速查

Claude 执行完成后，运行以下命令确认整体状态：

```bash
# === 在 N1 上运行 ===
echo "--- N1 服务状态 ---"
for svc in klipper moonraker go2rtc; do
  status=$(systemctl is-active $svc 2>/dev/null)
  icon=$([ "$status" = "active" ] && echo "✅" || echo "❌")
  echo "$icon $svc: $status"
done

echo ""
echo "--- 端口监听 ---"
ss -tlnp | grep -E "7125|1984" | awk '{print "✅", $4}'

echo ""
echo "--- 本机 IP ---"
ip addr | grep "inet " | grep -v "127.0.0.1"
```

```bash
# === 在 macOS 服务器上运行 ===
N1_IP=192.168.5.101   # 改为实际 IP

echo "--- 从服务器验证 N1 ---"
curl -s --connect-timeout 3 http://$N1_IP:7125/server/info \
  && echo "✅ Moonraker ($N1_IP:7125) 可达" \
  || echo "❌ Moonraker ($N1_IP:7125) 不可达"

curl -s --connect-timeout 3 -o /dev/null -w "%{http_code}" \
  http://$N1_IP:1984/api/streams/camera0.jpg \
  | grep -q "200" \
  && echo "✅ go2rtc 拍照 ($N1_IP:1984) 可达" \
  || echo "❌ go2rtc 拍照 ($N1_IP:1984) 不可达"
```

全部 ✅ 即部署完成。
