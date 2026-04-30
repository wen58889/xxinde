# N1 盒子部署手册

> 本文档指导在新 N1 设备上完成全部部署，接入总控服务器。
> 包含：Klipper + Moonraker + go2rtc + 蓝牙音箱 + TTS 语音播放。
> 适用于批量出厂场景。

---

## 0. 系统架构

```
总控服务器 (192.168.5.8:8080)
    │
    ├── 心跳检测 ────────── N1:7125  Moonraker（G-code 控制机械臂）
    ├── G-code 指令 ─────── N1:7125  /printer/gcode/script
    ├── 按需拍照 ────────── N1:1984  go2rtc /api/streams/camera0.jpg
    ├── TTS 语音 ────────── N1:SSH   scp + mpg123 -o pulse → PulseAudio → 蓝牙音箱
    └── 紧急停止 ────────── N1:7125  /printer/emergency_stop → firmware_restart 恢复
```

**N1 硬件规格**

| 项目 | 规格 |
|------|------|
| 操作系统 | Armbian 26.2.1 trixie (Debian 13) |
| 架构 | aarch64 (64-bit ARMv8) |
| 内存 | 2 GB |
| 存储 | 8 GB eMMC |
| SSH | root / 1234 |

**机械参数（来自 printer.cfg，切勿随意修改）**

| 参数 | 值 | 说明 |
|------|-----|------|
| X 轴行程 | 0 ~ 150 mm | 水平移动 |
| Y 轴行程 | 0 ~ 150 mm | 前后移动 |
| Z 轴行程 | -1 ~ 6 mm | 拉线触控笔，sensorless homing |
| TAP_Z | -1.0 mm | 下压点击深度 |
| Z_SAFE | 3.0 mm | 安全抬起高度 |
| TAP_Z_FEED | 6000 mm/min | 下压进给速度 |
| 截图分辨率 | 1280 × 720 px | |

---

## 1. 前置条件检查

SSH 登录 N1 后运行：

```bash
uname -m                              # 期望: aarch64
cat /etc/os-release | grep VERSION_ID # 期望: 13
ip addr show | grep "inet " | grep -v "127.0.0.1"  # 期望: 有IP
ls /dev/video* 2>/dev/null            # 期望: 摄像头设备存在
ss -tlnp | grep -E "7125|1984"        # 期望: 端口未占用
```

---

## 2. 网络配置（静态 IP）

N1 的 IP 必须在 192.168.5.101 ~ 192.168.5.200 范围内。

```bash
# NetworkManager 方式（推荐）
CON=$(nmcli -t -f NAME con show --active | head -1)
nmcli con mod "$CON" \
  ipv4.method manual \
  ipv4.addresses "192.168.5.10X/24" \
  ipv4.gateway "192.168.5.1" \
  ipv4.dns "8.8.8.8,114.114.114.114"
nmcli con up "$CON"
```

> 多台 N1 分别用 .101、.102、.103 … 依次递增，不要重复。

---

## 3. 安装基础依赖 + 蓝牙 + 音频

```bash
apt update && apt install -y \
  git python3 python3-pip wget curl v4l-utils \
  bluez bluez-tools \
  pulseaudio pulseaudio-module-bluetooth pulseaudio-utils \
  mpg123 ffmpeg
```

---

## 4. 配置 PulseAudio

```bash
mkdir -p /etc/pulse
cat > /etc/pulse/daemon.conf << 'EOF'
resample-method = trivial
default-sample-rate = 48000
EOF
```

---

## 5. 蓝牙音箱配对

### 5.1 启动蓝牙服务

```bash
systemctl enable bluetooth
systemctl start bluetooth
bluetoothctl power on
```

### 5.2 扫描并配对

```bash
# 扫描 10 秒
bluetoothctl --timeout 10 scan on

# 查看发现的设备，记下音箱 MAC 地址
bluetoothctl devices
# 例如: Device 00:12:6F:B3:3B:2A Beoplay A1

# 配对（替换为你的音箱 MAC）
BT_MAC=00:12:6F:B3:3B:2A
bluetoothctl trust $BT_MAC
bluetoothctl pair $BT_MAC
bluetoothctl connect $BT_MAC
```

### 5.3 验证

```bash
bluetoothctl info $BT_MAC | grep -E "Paired|Trusted|Connected"
# 期望: 全部 yes
```

---

## 6. 设置蓝牙音箱为默认音频输出

```bash
# 启动 PulseAudio
pulseaudio --start 2>/dev/null || pulseaudio -D --fail=quiet 2>/dev/null
sleep 2

# 查看所有输出设备
pactl list sinks short
# 0  alsa_output...           module-alsa-card.c       ...  (板载声卡)
# 1  bluez_sink.XX_XX_...     module-bluez5-device.c  ...  (蓝牙音箱)

# 设置蓝牙为默认输出
pactl set-default-sink 1

# 设置音量 75%
pactl set-sink-volume @DEFAULT_SINK@ 75%
```

### 6.1 测试播放

```bash
# 通过 PulseAudio → 蓝牙播放
mpg123 -o pulse /usr/share/sounds/alsa/Front_Left.wav
# 蓝牙音箱应发出声音

# 或用 paplay
paplay /usr/share/sounds/alsa/Front_Left.wav
```

---

## 7. 配置开机自启（自动连接蓝牙音箱）

### 7.1 创建连接脚本

> **重要**：将 `BT_MAC` 替换为该台 N1 对应的蓝牙音箱 MAC 地址

```bash
BT_MAC=00:12:6F:B3:3B:2A  # 替换为实际 MAC

cat > /usr/local/bin/bt-speaker-connect.sh << EOF
#!/bin/bash
# Auto-connect Bluetooth speaker and set as default audio output
pulseaudio --start 2>/dev/null || pulseaudio -D --fail=quiet 2>/dev/null
sleep 2
echo -e "power on\nconnect $BT_MAC" | bluetoothctl
sleep 5
SINK=\$(pactl list sinks short 2>/dev/null | grep bluez | head -1 | awk '{print \$2}')
if [ -n "\$SINK" ]; then
  pactl set-default-sink "\$SINK" 2>/dev/null
  pactl set-sink-volume @DEFAULT_SINK@ 75% 2>/dev/null
fi
EOF

chmod +x /usr/local/bin/bt-speaker-connect.sh
```

### 7.2 创建 systemd 服务

```bash
cat > /etc/systemd/system/bt-speaker.service << 'EOF'
[Unit]
Description=Auto-connect Bluetooth speaker
After=bluetooth.service
Wants=bluetooth.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/bin/bt-speaker-connect.sh

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable bt-speaker.service
```

---

## 8. 安装 Klipper 固件

### 8.1 克隆并安装

```bash
cd ~
git clone https://github.com/Klipper3d/klipper.git
cd ~/klipper
python3 -m venv ~/klippy-env
~/klippy-env/bin/pip install -r scripts/klippy-requirements.txt
```

### 8.2 创建 printer.cfg

```bash
mkdir -p ~/printer_data/config ~/printer_data/logs

cat > ~/printer_data/config/printer.cfg << 'EOF'
# ============================================================
# N1 手机测试机械臂 - Klipper 配置
# Z轴: sensorless homing (拉线触控笔，无物理限位开关)
# ============================================================

[printer]
kinematics: cartesian
max_velocity: 150
max_accel: 1000
max_z_velocity: 80
max_z_accel: 200
square_corner_velocity: 5.0

[stepper_x]
step_pin: PB13
dir_pin: PB12
enable_pin: !PB14
microsteps: 16
rotation_distance: 40
endstop_pin: ^PC0
position_min: 0
position_max: 150
position_endstop: 0
homing_speed: 30

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

[stepper_z]
step_pin: PB0
dir_pin: PC5
enable_pin: !PB1
microsteps: 16
rotation_distance: 8
endstop_pin: tmc2209_stepper_z:virtual_endstop
position_min: -1
position_max: 6
position_endstop: 0
homing_speed: 5
homing_retract_dist: 1

[tmc2209 stepper_z]
uart_pin: PD3
run_current: 0.4
hold_current: 0.2
stealthchop_threshold: 0
diag_pin: ^PD4
driver_SGTHRS: 80

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

[mcu]
serial: /dev/serial/by-id/usb-Klipper_stm32f103xe_XXXXXXXXX-if00
# 运行 ls /dev/serial/by-id/ 获取实际路径后替换

[gcode_macro SAFE_HOME]
gcode:
    G28
    G1 Z3 F3000

[virtual_sdcard]
path: ~/printer_data/gcodes

[display_status]
[pause_resume]
EOF
```

> **关键**：运行 `ls /dev/serial/by-id/` 找到 MCU 实际串口路径，替换 `serial:` 行。

### 8.3 创建 systemd 服务

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
```

---

## 9. 安装 Moonraker

### 9.1 克隆并安装

```bash
cd ~
git clone https://github.com/Arksine/moonraker.git
cd moonraker
python3 -m venv ~/moonraker-env
~/moonraker-env/bin/pip install -r scripts/moonraker-requirements.txt
```

### 9.2 配置

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

### 9.3 创建 systemd 服务

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
```

### 9.4 验证

```bash
curl -s http://localhost:7125/server/info | python3 -c "
import sys,json
d=json.load(sys.stdin).get('result',{})
print('Klipper connected:', d.get('klippy_connected'))
"
# 期望: Klipper connected: True
```

---

## 10. 安装 go2rtc（摄像头快照）

### 10.1 下载

```bash
wget -O /usr/local/bin/go2rtc \
  https://github.com/AlexxIT/go2rtc/releases/latest/download/go2rtc_linux_arm64
chmod +x /usr/local/bin/go2rtc
```

### 10.2 配置

```bash
mkdir -p /etc/go2rtc
cat > /etc/go2rtc/go2rtc.yaml << 'EOF'
api:
  listen: ":1984"

streams:
  camera0:
    - /dev/video0#width=1280#height=720#input-format=mjpeg
EOF
```

### 10.3 创建 systemd 服务

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
```

### 10.4 验证

```bash
curl -s -o /tmp/shot.jpg http://localhost:1984/api/streams/camera0.jpg
file /tmp/shot.jpg  # 期望: JPEG image data
```

---

## 11. 全服务验证

```bash
echo "=== 服务状态 ==="
for svc in klipper moonraker go2rtc bluetooth; do
  s=$(systemctl is-active $svc 2>/dev/null)
  echo "$svc: $s"
done

echo ""
echo "=== PulseAudio ==="
pgrep pulseaudio > /dev/null && echo "PulseAudio: OK" || echo "PulseAudio: 未运行"

echo ""
echo "=== 蓝牙音箱 ==="
pactl list sinks short 2>/dev/null | grep bluez && echo "蓝牙sink: OK" || echo "蓝牙sink: 未连接"

echo ""
echo "=== Moonraker ==="
curl -s http://localhost:7125/server/info | grep -o '"klippy_connected": true' && echo "Klipper: 已连接" || echo "Klipper: 未连接"

echo ""
echo "=== 拍照 ==="
curl -s -o /tmp/verify.jpg http://localhost:1984/api/streams/camera0.jpg && echo "拍照: OK" || echo "拍照: 失败"
```

---

## 12. 从总控服务器端验证

```bash
N1_IP=192.168.5.10X  # 替换为实际 IP

# Moonraker 心跳
curl -s --connect-timeout 3 http://$N1_IP:7125/server/info \
  && echo "Moonraker OK" || echo "Moonraker FAIL"

# 截图
curl -s --connect-timeout 3 -o /dev/null http://$N1_IP:1984/api/streams/camera0.jpg \
  && echo "go2rtc OK" || echo "go2rtc FAIL"

# SSH（TTS 播放通道）
ssh -o ConnectTimeout=3 root@$N1_IP "echo SSH_OK" 2>/dev/null

# 等待后端自动发现设备（约10秒后变为 ONLINE）
```

---

## 13. 首次运动测试

```bash
N1_IP=192.168.5.10X

# 归零
curl -X POST http://$N1_IP:7125/printer/gcode/script \
  -H "Content-Type: application/json" -d '{"script":"G28"}'

# 抬起 Z
curl -X POST http://$N1_IP:7125/printer/gcode/script \
  -H "Content-Type: application/json" -d '{"script":"G1 Z3 F3000"}'

# 移动到中心
curl -X POST http://$N1_IP:7125/printer/gcode/script \
  -H "Content-Type: application/json" -d '{"script":"G1 X75 Y75 F6000"}'

# 测试 Z 下压
curl -X POST http://$N1_IP:7125/printer/gcode/script \
  -H "Content-Type: application/json" -d '{"script":"G1 Z-0.5 F3000"}'
```

---

## 14. 批量部署一键脚本

将以下脚本保存为 `n1_setup.sh`，在每台 N1 上执行：

```bash
#!/bin/bash
# N1 设备批量部署脚本
# 用法: ./n1_setup.sh <蓝牙音箱MAC> [N1静态IP]
# 示例: ./n1_setup.sh 00:12:6F:B3:3B:2A 192.168.5.102

BT_MAC=${1:?用法: $0 <蓝牙音箱MAC> [N1_IP]}
N1_IP=${2:-}

set -e

echo "[1/9] 更新系统..."
apt update && apt upgrade -y

echo "[2/9] 安装软件包..."
apt install -y git python3 python3-pip wget curl v4l-utils \
  bluez bluez-tools \
  pulseaudio pulseaudio-module-bluetooth pulseaudio-utils \
  mpg123 ffmpeg

echo "[3/9] 配置 PulseAudio..."
mkdir -p /etc/pulse
cat > /etc/pulse/daemon.conf << 'PAEOF'
resample-method = trivial
default-sample-rate = 48000
PAEOF

echo "[4/9] 启动蓝牙服务并配对 $BT_MAC ..."
systemctl enable bluetooth
systemctl start bluetooth
sleep 1
bluetoothctl power on
bluetoothctl trust "$BT_MAC"
bluetoothctl pair "$BT_MAC"
bluetoothctl connect "$BT_MAC"

echo "[5/9] 启动 PulseAudio 并设置蓝牙为默认输出..."
pulseaudio --start 2>/dev/null || pulseaudio -D --fail=quiet 2>/dev/null
sleep 2
SINK=$(pactl list sinks short 2>/dev/null | grep bluez | head -1 | awk '{print $2}')
if [ -n "$SINK" ]; then
  pactl set-default-sink "$SINK" 2>/dev/null
  pactl set-sink-volume @DEFAULT_SINK@ 75% 2>/dev/null
  echo "蓝牙默认输出: $SINK"
else
  echo "警告: 未检测到蓝牙sink，请确认音箱已连接"
fi

echo "[6/9] 配置开机自启..."
cat > /usr/local/bin/bt-speaker-connect.sh << BTEOF
#!/bin/bash
pulseaudio --start 2>/dev/null || pulseaudio -D --fail=quiet 2>/dev/null
sleep 2
echo -e "power on\nconnect $BT_MAC" | bluetoothctl
sleep 5
SINK=\$(pactl list sinks short 2>/dev/null | grep bluez | head -1 | awk '{print \$2}')
if [ -n "\$SINK" ]; then
  pactl set-default-sink "\$SINK" 2>/dev/null
  pactl set-sink-volume @DEFAULT_SINK@ 75% 2>/dev/null
fi
BTEOF
chmod +x /usr/local/bin/bt-speaker-connect.sh

cat > /etc/systemd/system/bt-speaker.service << 'SVCEOF'
[Unit]
Description=Auto-connect Bluetooth speaker
After=bluetooth.service
Wants=bluetooth.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/bin/bt-speaker-connect.sh

[Install]
WantedBy=multi-user.target
SVCEOF
systemctl daemon-reload
systemctl enable bt-speaker.service

echo "[7/9] 配置静态IP ($N1_IP)..."
if [ -n "$N1_IP" ]; then
  CON=$(nmcli -t -f NAME con show --active | head -1)
  nmcli con mod "$CON" ipv4.method manual \
    ipv4.addresses "$N1_IP/24" \
    ipv4.gateway "192.168.5.1" \
    ipv4.dns "8.8.8.8,114.114.114.114" 2>/dev/null || true
fi

echo "[8/9] 安装 Klipper + Moonraker + go2rtc..."
# (此处需根据实际情况补充 Klipper/Moonraker/go2rtc 的安装步骤)
# 参见第 8~10 步的详细说明

echo "[9/9] 验证..."
echo "--- 服务状态 ---"
for svc in bluetooth; do
  s=$(systemctl is-active $svc 2>/dev/null)
  echo "  $svc: $s"
done
echo "--- PulseAudio ---"
pgrep pulseaudio > /dev/null && echo "  PulseAudio: OK" || echo "  PulseAudio: 未运行"
echo "--- 蓝牙sink ---"
pactl list sinks short 2>/dev/null | grep bluez | head -1 || echo "  未检测到"

echo ""
echo "========================================"
echo "  N1 部署完成！"
echo "  蓝牙音箱: $BT_MAC"
echo "  IP: $N1_IP"
echo "========================================"
echo ""
echo "后续步骤:"
echo "  1. 部署 Klipper + Moonraker + go2rtc (第8~10步)"
echo "  2. 运行 ls /dev/serial/by-id/ 获取 MCU 串口路径"
echo "  3. 修改 printer.cfg 中的 serial: 行"
echo "  4. 从总控服务器端验证连接"
```

### 从总控服务器远程部署

```bash
# 发送脚本到 N1
scp n1_setup.sh root@192.168.5.102:/tmp/

# 远程执行（替换为实际蓝牙音箱 MAC）
ssh root@192.168.5.102 "bash /tmp/n1_setup.sh 00:12:6F:B3:3B:2A 192.168.5.102"
```

---

## 15. 故障排查

| 问题 | 检查 | 解决 |
|------|------|------|
| 蓝牙服务未运行 | `systemctl status bluetooth` | `systemctl start bluetooth` |
| 找不到蓝牙适配器 | `hciconfig` | 检查硬件/`lsmod \| grep bluetooth` |
| 音箱未连接 | `bluetoothctl info MAC` | `bluetoothctl connect MAC` |
| PulseAudio 未运行 | `pgrep pulseaudio` | `pulseaudio --start` |
| 无蓝牙 sink | `pactl list sinks short` | 安装 `pulseaudio-module-bluetooth` 并重启 PA |
| mpg123 无声 | `mpg123 -o pulse test.mp3` | 确认默认 sink 是蓝牙 |
| SSH 连接失败 | `ssh root@N1_IP` | 检查网络/密码/SSH 服务 |
| Moonraker 不可达 | `curl N1_IP:7125/server/info` | 检查防火墙/服务状态 |
| 拍照全黑 | `curl -o test.jpg N1_IP:1984/...` | 检查摄像头设备/ffmpeg/go2rtc |
| Z轴 Move out of range | 看后端日志 | 系统自动 fallback 到 Z=0.05，无需处理 |
| 紧急停止后设备无响应 | 前端点"复位"按钮 | 后端自动 `firmware_restart` 恢复 |
