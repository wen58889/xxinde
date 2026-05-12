#!/bin/bash
####################################################################################
# N1 盒子一键交互式部署脚本 (纯软件部署)
# 适用：全新 Armbian Debian 13 (aarch64) 系统
# 前置：先运行 n1_network.sh 配置网络并重启，再运行本脚本
# 功能：自动安装 Klipper + Moonraker + go2rtc + 蓝牙音箱 + 音频
#       交互式配置 蓝牙MAC / MCU串口，永久固化
# 用法：chmod +x n1_deploy.sh && sudo ./n1_deploy.sh
####################################################################################
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step()  { echo -e "\n${CYAN}${BOLD}======== $1 ========${NC}"; }
log_ask()   { echo -e "${BOLD}${CYAN}$1${NC}"; }

ROOT_DIR=/root
PRINTER_DATA=$ROOT_DIR/printer_data
KLIPPER_DIR=$ROOT_DIR/klipper
KLIPPY_ENV=$ROOT_DIR/klippy-env
MOONRAKER_DIR=$ROOT_DIR/moonraker
MOONRAKER_ENV=$ROOT_DIR/moonraker-env

####################################################################################
# 0. 前置检查
####################################################################################
log_step "Step 0/11: 前置检查"

if [ "$(id -u)" -ne 0 ]; then
    log_error "请用 root 运行: sudo ./n1_deploy.sh"
    exit 1
fi

ARCH=$(uname -m)
if [ "$ARCH" != "aarch64" ]; then
    log_warn "当前架构: $ARCH (期望 aarch64)，继续但可能不兼容"
fi

log_info "系统: $(cat /etc/os-release | grep PRETTY_NAME | cut -d'"' -f2)"
log_info "内核: $(uname -r)"
log_info "架构: $ARCH"
log_info "内存: $(free -m | grep Mem | awk '{print $2}')MB"

####################################################################################
# 1. 交互式输入
####################################################################################
log_step "Step 1/11: 交互式配置"

# 1.1 N1 静态IP
DEFAULT_IP=$(ip -4 addr show | grep -oP '192\.168\.5\.\d+' | head -1)
if [ -z "$DEFAULT_IP" ]; then
    DEFAULT_IP="192.168.5.101"
fi
log_ask "请输入本机静态IP地址 [当前/默认: $DEFAULT_IP]:"
read -r N1_IP
N1_IP=${N1_IP:-$DEFAULT_IP}

# 验证IP格式
if ! echo "$N1_IP" | grep -qP '^192\.168\.5\.\d+$'; then
    log_error "IP格式不正确，应为 192.168.5.xxx，退出"
    exit 1
fi
log_info "本机IP: $N1_IP"

# 1.2 总控服务器IP
log_ask "请输入总控服务器IP [默认: 192.168.5.8]:"
read -r SERVER_IP
SERVER_IP=${SERVER_IP:-192.168.5.8}
log_info "总控服务器: $SERVER_IP"

# 1.3 蓝牙音箱MAC
log_ask "请输入蓝牙音箱MAC地址 (如 00:12:6F:B3:3B:2A，没有蓝牙音箱直接回车跳过):"
read -r BT_MAC
if [ -n "$BT_MAC" ]; then
    if ! echo "$BT_MAC" | grep -qP '^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$'; then
        log_error "MAC格式不正确，退出"
        exit 1
    fi
    log_info "蓝牙音箱MAC: $BT_MAC"
else
    log_warn "未设置蓝牙音箱，跳过蓝牙配置"
fi

# 1.4 MCU串口
log_ask "请输入MCU串口路径 (如 /dev/serial/by-id/usb-Klipper_xxx-if00)，稍后可自动检测:"
read -r MCU_SERIAL
if [ -z "$MCU_SERIAL" ]; then
    MCU_SERIAL="AUTO_DETECT"
    log_info "MCU串口将自动检测"
else
    log_info "MCU串口: $MCU_SERIAL"
fi

# 1.5 摄像头设备 — 智能检测USB摄像头
# 策略: 优先用video1+(video0通常是硬件解码器)，回退video0
# 如果只有video0，用v4l2-ctl检查是否是真实摄像头
CAM_DEVS=$(ls /dev/video* 2>/dev/null | sort -V || true)
if [ -n "$CAM_DEVS" ]; then
    # 排除video0(通常是csi/isp解码器)，优先用video1+
    NON_VIDEO0=$(echo "$CAM_DEVS" | grep -v '/dev/video0$' | head -1 || true)
    if [ -n "$NON_VIDEO0" ]; then
        CAM_DEV="$NON_VIDEO0"
        log_info "检测到USB摄像头: $CAM_DEV"
    elif [ -e /dev/video0 ]; then
        # 检查video0是否是真实USB摄像头
        V4L2_CARD=$(v4l2-ctl -d /dev/video0 --info 2>/dev/null | grep "Card type" | cut -d: -f2- | xargs || echo "")
        if echo "$V4L2_CARD" | grep -qiE "UVC|USB|webcam"; then
            CAM_DEV=/dev/video0
            log_info "video0是USB摄像头: $V4L2_CARD"
        else
            CAM_DEV=/dev/video0
            log_warn "video0可能是硬件解码器($V4L2_CARD)，但作为回退使用"
        fi
    fi
else
    log_warn "未检测到任何摄像头设备，使用默认 /dev/video1"
    CAM_DEV=/dev/video1
fi
CAM_NUM=$(basename "$CAM_DEV" | grep -oP '\d+')
CAM_STREAM="camera${CAM_NUM}"
log_info "摄像头: $CAM_DEV (流名: $CAM_STREAM)"

# 确认
echo ""
log_ask "============================================="
log_ask "  请确认以下配置:"
log_ask "  本机IP:       $N1_IP"
log_ask "  总控服务器:   $SERVER_IP"
log_ask "  蓝牙MAC:      ${BT_MAC:-无(跳过)}"
log_ask "  MCU串口:      ${MCU_SERIAL:-自动检测}"
log_ask "  摄像头:       $CAM_DEV"
log_ask "============================================="
log_ask "确认开始部署? [Y/n]:"
read -r CONFIRM
CONFIRM=${CONFIRM:-Y}
if [ "$CONFIRM" != "Y" ] && [ "$CONFIRM" != "y" ]; then
    log_error "用户取消，退出"
    exit 0
fi

####################################################################################
# 2. 网络配置 — 已拆分到 n1_network.sh
####################################################################################
log_step "Step 2/11: 网络配置 (已由 n1_network.sh 完成)"
log_info "网络配置(IP+MAC固定+hostname)已由 n1_network.sh 处理"
log_info "当前IP: $N1_IP"
CURRENT_IP=$(ip -4 addr show | grep -oP '192\.168\.5\.\d+' | head -1)
if [ "$CURRENT_IP" != "$N1_IP" ]; then
    log_warn "当前IP($CURRENT_IP)与配置IP($N1_IP)不一致!"
    log_warn "请先运行 n1_network.sh 并重启，再运行本脚本"
fi

####################################################################################
# 3. 安装基础依赖
####################################################################################
log_step "Step 2/11: 安装基础依赖"

apt update -qq
apt install -y \
    git python3 python3-pip python3-venv python3-dev wget curl v4l-utils \
    avahi-daemon \
    bluez bluez-tools \
    pulseaudio pulseaudio-module-bluetooth pulseaudio-utils \
    mpg123 ffmpeg \
    2>&1 | tail -5

log_info "基础依赖安装完成"

# 确保SSH服务运行且开机自启
systemctl enable ssh 2>/dev/null || systemctl enable sshd 2>/dev/null || true
systemctl start ssh 2>/dev/null || systemctl start sshd 2>/dev/null || true
log_info "SSH服务已确认"

# USB稳定性优化 (交付级: 防止MCU串口断连)
log_info "配置USB稳定性优化..."

# 1. 永久禁用Linux USB自动挂起 (断连头号元凶)
cat > /etc/modprobe.d/usb-no-autosuspend.conf << 'EOF'
options usbcore autosuspend=-1
EOF
# 立即生效
echo -1 > /sys/module/usbcore/parameters/autosuspend 2>/dev/null || true
log_info "USB autosuspend=disabled (永久+运行时)"

# 2. udev规则: USB设备永不挂起 + Klipper RP2040串口固定
cat > /etc/udev/rules.d/99-usb-no-autosuspend.rules << 'EOF'
# 禁用所有USB设备自动挂起
ACTION=="add", SUBSYSTEM=="usb", ATTR{power/control}="on"
# Klipper RP2040 CDC ACM: 固定符号链接+权限
ACTION=="add", SUBSYSTEM=="tty", ATTRS{idVendor}=="1d50", ATTRS{idProduct}=="614e", SYMLINK+="klipper-mcu", GROUP="root", MODE="0666"
EOF
udevadm control --reload-rules 2>/dev/null || true
log_info "udev: USB永不挂起 + Klipper串口固定"

# 3. 当前所有USB设备立即设为power=on
for d in /sys/bus/usb/devices/*/power/control; do
    echo on > "$d" 2>/dev/null || true
done
log_info "所有USB设备 power=on"

# 4. Armbian启动参数: 永久禁用autosuspend
if ! grep -q "autosuspend" /boot/armbianEnv.txt 2>/dev/null; then
    echo "extraargs=usbcore.autosuspend=-1" >> /boot/armbianEnv.txt 2>/dev/null || true
fi
log_info "Armbian启动参数: autosuspend=-1"

# 创建TTS音频临时目录
mkdir -p /tmp/phone_tts
log_info "TTS临时目录: /tmp/phone_tts"

# 防火墙放行 (如有ufw)
if command -v ufw &>/dev/null; then
    ufw allow 7125/tcp 2>/dev/null || true
    ufw allow 1984/tcp 2>/dev/null || true
    ufw allow 22/tcp 2>/dev/null || true
    log_info "防火墙规则已添加 (7125/1984/22)"
fi

# 启动avahi-daemon (mDNS设备发现)
systemctl enable avahi-daemon 2>/dev/null || true
systemctl start avahi-daemon 2>/dev/null || true

####################################################################################
# 4. 蓝牙音箱配置
####################################################################################
log_step "Step 3/11: 蓝牙音箱配置"

if [ -n "$BT_MAC" ]; then
    systemctl enable bluetooth
    systemctl start bluetooth
    sleep 1
    bluetoothctl power on 2>/dev/null || true

    log_info "扫描蓝牙设备 (10秒)..."
    bluetoothctl --timeout 10 scan on 2>/dev/null || true

    log_info "配对蓝牙音箱 $BT_MAC ..."
    bluetoothctl trust "$BT_MAC" 2>/dev/null || true
    bluetoothctl pair "$BT_MAC" 2>/dev/null || true
    bluetoothctl connect "$BT_MAC" 2>/dev/null || true
    sleep 2

    # 验证
    BT_CONNECTED=$(bluetoothctl info "$BT_MAC" 2>/dev/null | grep "Connected: yes" || true)
    if [ -n "$BT_CONNECTED" ]; then
        log_info "蓝牙音箱已连接!"
    else
        log_warn "蓝牙音箱未连接，请确认音箱已开机。部署完成后可手动连接。"
    fi
else
    log_info "跳过蓝牙配置 (未设置MAC)"
fi

####################################################################################
# 5. PulseAudio 配置
####################################################################################
log_step "Step 4/11: PulseAudio 配置"

mkdir -p /etc/pulse
cat > /etc/pulse/daemon.conf << 'EOF'
resample-method = trivial
default-sample-rate = 48000
EOF

# 允许root运行PulseAudio
mkdir -p /etc/pulse
if [ ! -f /etc/pulse/client.conf ]; then
    cat > /etc/pulse/client.conf << 'EOF'
autospawn = yes
EOF
fi
# PulseAudio默认不允许root运行，需要设置环境变量
export PULSE_RUNTIME_PATH=/run/pulse
mkdir -p /run/pulse
chown root:root /run/pulse 2>/dev/null || true

# 启动PulseAudio (root用户需要特殊处理)
if ! pgrep -x pulseaudio >/dev/null; then
    pulseaudio --start 2>/dev/null || pulseaudio -D --fail=quiet 2>/dev/null || \
        PULSE_RUNTIME_PATH=/run/pulse pulseaudio --system -D 2>/dev/null || true
fi
sleep 2

if [ -n "$BT_MAC" ]; then
    # 等待蓝牙sink出现
    for i in $(seq 1 10); do
        BT_SINK=$(pactl list sinks short 2>/dev/null | grep bluez | head -1 | awk '{print $2}')
        if [ -n "$BT_SINK" ]; then
            break
        fi
        sleep 1
    done

    if [ -n "$BT_SINK" ]; then
        pactl set-default-sink "$BT_SINK" 2>/dev/null || true
        pactl set-sink-volume @DEFAULT_SINK@ 75% 2>/dev/null || true
        log_info "蓝牙音频输出: $BT_SINK (75%音量)"
    else
        log_warn "未检测到蓝牙sink，音频将走板载声卡"
    fi
fi

# PulseAudio 用户级 systemd 自启
mkdir -p /etc/systemd/user
cat > /etc/systemd/user/pulseaudio.service << 'EOF'
[Unit]
Description=PulseAudio Sound Server

[Service]
Type=simple
ExecStart=/usr/bin/pulseaudio --daemonize=no
Restart=always

[Install]
WantedBy=default.target
EOF
systemctl --global enable pulseaudio.service 2>/dev/null || true

log_info "PulseAudio 配置完成"

####################################################################################
# 6. 蓝牙开机自启脚本
####################################################################################
log_step "Step 5/11: 蓝牙开机自启"

if [ -n "$BT_MAC" ]; then
    cat > /usr/local/bin/bt-speaker-connect.sh << BTEOF
#!/bin/bash
# Auto-connect Bluetooth speaker and set as default audio output
# MAC: $BT_MAC
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
    log_info "蓝牙开机自启已配置 (bt-speaker.service)"
else
    log_info "跳过蓝牙自启 (未设置MAC)"
fi

####################################################################################
# 7. 安装 Klipper
####################################################################################
log_step "Step 6/11: 安装 Klipper"

if [ ! -d "$KLIPPER_DIR" ]; then
    log_info "克隆 Klipper..."
    git clone --depth 1 https://github.com/Klipper3d/klipper.git "$KLIPPER_DIR" 2>&1 | tail -3
else
    log_info "Klipper 目录已存在，跳过克隆"
fi

if [ ! -d "$KLIPPY_ENV" ]; then
    log_info "创建 Klipper venv..."
    python3 -m venv "$KLIPPY_ENV"
    "$KLIPPY_ENV/bin/pip" install -r "$KLIPPER_DIR/scripts/klippy-requirements.txt" -q 2>&1 | tail -3
else
    log_info "Klipper venv 已存在"
fi

# 创建目录
mkdir -p "$PRINTER_DATA/config" "$PRINTER_DATA/logs" "$PRINTER_DATA/gcodes"

# MCU串口自动检测
if [ "$MCU_SERIAL" = "AUTO_DETECT" ]; then
    DETECTED_SERIAL=$(ls /dev/serial/by-id/ 2>/dev/null | grep -i klipper | head -1)
    if [ -n "$DETECTED_SERIAL" ]; then
        MCU_SERIAL="/dev/serial/by-id/$DETECTED_SERIAL"
        log_info "自动检测到MCU: $MCU_SERIAL"
    else
        log_warn "未自动检测到MCU串口，将在printer.cfg中留占位符"
        MCU_SERIAL="/dev/serial/by-id/REPLACE_ME"
    fi
fi

# 写入 printer.cfg (与N1实际配置完全一致)
log_info "写入 printer.cfg ..."
cat > "$PRINTER_DATA/config/printer.cfg" << PRINTERCFG
####################################################################################
# CoreXY机械臂控制系统 - 手机屏幕点击/滑动自动化
# 硬件: SKR Pico V1.0 + TMC2209 + CoreXY
# 行程: X=150mm, Y=150mm, Z=10mm
####################################################################################

[mcu]
serial: $MCU_SERIAL
restart_method: command

[temperature_sensor SKR_Pico]
sensor_type: temperature_mcu
min_temp: 0
max_temp: 100

[printer]
kinematics: corexy
max_velocity: 300
max_accel: 3000
max_z_velocity: 5
max_z_accel: 100

[stepper_x]
step_pin: gpio11
dir_pin: !gpio10
enable_pin: !gpio12
microsteps: 16
rotation_distance: 40
endstop_pin: gpio4
position_endstop: 150
position_min: 0
position_max: 150
homing_speed: 50
homing_retract_dist: 5

[tmc2209 stepper_x]
uart_pin: gpio9
tx_pin: gpio8
uart_address: 0
run_current: 0.8
hold_current: 0.5
sense_resistor: 0.110
stealthchop_threshold: 999999
driver_TBL: 2
driver_TOFF: 3
driver_HSTRT: 0
driver_HEND: 3
interpolate: True

[stepper_y]
step_pin: gpio6
dir_pin: gpio5
enable_pin: !gpio12
microsteps: 16
rotation_distance: 40
endstop_pin: gpio3
position_endstop: 150
position_min: 0
position_max: 150
homing_speed: 50
homing_retract_dist: 5

[tmc2209 stepper_y]
uart_pin: gpio9
tx_pin: gpio8
uart_address: 2
run_current: 0.8
hold_current: 0.5
sense_resistor: 0.110
stealthchop_threshold: 999999
driver_TBL: 2
driver_TOFF: 3
driver_HSTRT: 0
driver_HEND: 3
interpolate: True

[stepper_z]
step_pin: gpio19
dir_pin: !gpio28
enable_pin: !gpio2
rotation_distance: 32
microsteps: 16
endstop_pin: gpio26
position_endstop: 0
position_min: -1
position_max: 10
homing_speed: 1
second_homing_speed: 0.5
homing_retract_dist: 0

[tmc2209 stepper_z]
uart_pin: gpio9
tx_pin: gpio8
uart_address: 1
run_current: 0.9
hold_current: 0.6
sense_resistor: 0.110
stealthchop_threshold: 999999
driver_TBL: 2
driver_TOFF: 3
driver_HSTRT: 0
driver_HEND: 3
interpolate: True

[virtual_sdcard]
path: $PRINTER_DATA/gcodes

[display_status]
[pause_resume]

[force_move]
enable_force_move: True

[gcode_macro G28]
description: 覆盖标准G28
rename_existing: G28.0
gcode:
    {% if 'X' in params or 'Y' in params or 'Z' in params %}
        G28.0 {rawparams}
    {% else %}
        G28.0 X
        G28.0 Y
        G92 Z0
    {% endif %}

[gcode_macro SAFE_HOME]
gcode:
    G28
    G1 Z1 F3000
PRINTERCFG

log_info "printer.cfg 已写入 (MCU serial: $MCU_SERIAL)"

# Klipper systemd 服务
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
RestartSec=2
KillSignal=SIGINT
TimeoutStopSec=10

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable klipper
log_info "Klipper 服务已注册"

####################################################################################
# 8. 安装 Moonraker
####################################################################################
log_step "Step 7/11: 安装 Moonraker"

if [ ! -d "$MOONRAKER_DIR" ]; then
    log_info "克隆 Moonraker..."
    git clone --depth 1 https://github.com/Arksine/moonraker.git "$MOONRAKER_DIR" 2>&1 | tail -3
else
    log_info "Moonraker 目录已存在"
fi

if [ ! -d "$MOONRAKER_ENV" ]; then
    log_info "创建 Moonraker venv..."
    python3 -m venv "$MOONRAKER_ENV"
fi
log_info "安装 Moonraker 依赖 (可能需要编译，请耐心等待)..."
"$MOONRAKER_ENV/bin/pip" install -r "$MOONRAKER_DIR/scripts/moonraker-requirements.txt" 2>&1 | tail -10
if [ $? -ne 0 ]; then
    log_warn "部分依赖安装失败，尝试逐个安装关键包..."
    for pkg in importlib_metadata tornado zeroconf apprise; do
        "$MOONRAKER_ENV/bin/pip" install "$pkg" 2>&1 | tail -1 || true
    done
fi

# moonraker.conf
cat > "$PRINTER_DATA/config/moonraker.conf" << 'EOF'
[server]
host: 0.0.0.0
port: 7125
klippy_uds_address: /tmp/klippy_uds
max_upload_size: 1024

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

[machine]
EOF

# 安装 Fluidd 前端 (预编译release)
FLUIDD_DIR=$ROOT_DIR/printer_data/companion/fluidd
if [ ! -f "$FLUIDD_DIR/index.html" ]; then
    log_info "下载 Fluidd 前端 (预编译release)..."
    mkdir -p "$FLUIDD_DIR"
    wget -q https://github.com/fluidd-core/fluidd/releases/latest/download/fluidd.zip \
        -O /tmp/fluidd.zip 2>/dev/null && \
    (cd "$FLUIDD_DIR" && unzip -qo /tmp/fluidd.zip && rm -f /tmp/fluidd.zip) && \
    log_info "Fluidd 安装成功" || \
    log_warn "Fluidd 下载失败 (网络问题)，可稍后手动安装: 下载 fluidd.zip 解压到 $FLUIDD_DIR"
else
    log_info "Fluidd 已存在"
fi
cat >> "$PRINTER_DATA/config/moonraker.conf" << EOF

[update_manager]
refresh_interval: 168

[update_manager client fluidd]
type: web
repo: fluidd-core/fluidd
path: ~/printer_data/companion/fluidd

[webcam ${CAM_STREAM}]
name: N1 Camera
stream_url: http://$N1_IP:1984/api/stream.mjpeg?src=${CAM_STREAM}
snapshot_url: http://$N1_IP:1984/api/frame.jpeg?src=${CAM_STREAM}
flip_horizontal: False
flip_vertical: False
rotation: 0
EOF

# Moonraker systemd 服务
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
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable moonraker
log_info "Moonraker 服务已注册"

####################################################################################
# 9. 安装 go2rtc (摄像头截图)
####################################################################################
log_step "Step 8/11: 安装 go2rtc"

if ! command -v go2rtc &>/dev/null; then
    log_info "下载 go2rtc (arm64)..."
    GO2RTC_URL="https://github.com/AlexxIT/go2rtc/releases/latest/download/go2rtc_linux_arm64"
    wget -q -O /usr/local/bin/go2rtc "$GO2RTC_URL" 2>/dev/null || \
        curl -sL -o /usr/local/bin/go2rtc "$GO2RTC_URL" 2>/dev/null || {
            log_warn "GitHub下载失败，尝试镜像..."
            wget -q -O /usr/local/bin/go2rtc \
                "https://ghproxy.com/${GO2RTC_URL}" 2>/dev/null || true
        }
    if [ -s /usr/local/bin/go2rtc ]; then
        chmod +x /usr/local/bin/go2rtc
        log_info "go2rtc 下载成功"
    else
        log_error "go2rtc 下载失败，请手动下载: $GO2RTC_URL"
        rm -f /usr/local/bin/go2rtc
    fi
else
    log_info "go2rtc 已存在"
fi

# go2rtc 配置 (使用ffmpeg exec模式，比直接v4l2更稳定)
# 支持两种模式: 按需截图(frame.jpeg) + MJPEG视频流(stream.mjpeg)
mkdir -p /etc/go2rtc
cat > /etc/go2rtc/go2rtc.yaml << EOF
api:
  listen: "0.0.0.0:1984"

streams:
  ${CAM_STREAM}:
    - exec:ffmpeg -f v4l2 -input_format mjpeg -video_size 1280x720 -i ${CAM_DEV} -frames:v 1 -f image2pipe -vcodec mjpeg -
EOF

# go2rtc systemd 服务 (依赖网络+ffmpeg就绪)
cat > /etc/systemd/system/go2rtc.service << 'EOF'
[Unit]
Description=go2rtc camera snapshot service
After=network.target
Wants=network-online.target

[Service]
Type=simple
ExecStartPre=/bin/sleep 3
ExecStart=/usr/local/bin/go2rtc -config /etc/go2rtc/go2rtc.yaml
Restart=always
RestartSec=5
StartLimitBurst=5
StartLimitIntervalSec=60
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable go2rtc
log_info "go2rtc 服务已注册 (摄像头: $CAM_DEV)"

# Fluidd Web前端服务 (独立serve静态文件)
cat > /usr/local/bin/fluidd-serve.sh << 'EOF'
#!/bin/bash
cd /root/printer_data/companion/fluidd
exec python3 -m http.server 8080 --bind 0.0.0.0
EOF
chmod +x /usr/local/bin/fluidd-serve.sh
cat > /etc/systemd/system/fluidd.service << 'EOF'
[Unit]
Description=Fluidd Web Frontend
After=network.target moonraker.service

[Service]
Type=simple
ExecStart=/usr/local/bin/fluidd-serve.sh
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable fluidd
log_info "Fluidd 服务已注册 (端口: 8080)"

####################################################################################
# 10. 启动所有服务
####################################################################################
log_step "Step 9/11: 启动所有服务"

log_info "启动 Klipper..."
systemctl start klipper || true
sleep 5

log_info "启动 Moonraker..."
systemctl start moonraker || true
sleep 3

log_info "启动 go2rtc..."
systemctl start go2rtc || true
sleep 2

log_info "启动 Fluidd..."
systemctl start fluidd || true
sleep 1

log_info "所有服务已启动"

# USB看门狗 v3 (交付级: XHCI死亡检测 + MCU断连5级递进恢复)
cat > /usr/local/bin/usb-watchdog.sh << 'WDEOF'
#!/bin/bash
MCU_ID="usb-Klipper_rp2040"
CHECK_INTERVAL=5
MAX_FAIL=2
FAIL_COUNT=0
RECOVERY_LEVEL=0
log() { logger -t usb-watchdog "$1"; }

check_xhci_dead() {
    dmesg | tail -20 | grep -qiE 'xHCI host controller not responding|HC died|xhci_hcd.*error'
}

while true; do
    sleep $CHECK_INTERVAL

    # L0: XHCI死亡检测 → 直接reboot（最严重，不可恢复）
    if check_xhci_dead; then
        log "CRITICAL: XHCI host controller died! Rebooting immediately"
        sleep 1
        reboot
    fi

    if ls /dev/serial/by-id/ 2>/dev/null | grep -q "$MCU_ID"; then
        if [ $FAIL_COUNT -gt 0 ]; then
            log "MCU recovered"
            FAIL_COUNT=0
            RECOVERY_LEVEL=0
        fi
        continue
    fi
    FAIL_COUNT=$((FAIL_COUNT + 1))
    log "MCU not detected! fail=$FAIL_COUNT level=$RECOVERY_LEVEL"
    if [ $FAIL_COUNT -ge $MAX_FAIL ]; then
        RECOVERY_LEVEL=$((RECOVERY_LEVEL + 1))
        if [ $RECOVERY_LEVEL -eq 1 ]; then
            log "Recovery L1: firmware_restart"
            curl -s -X POST http://127.0.0.1:7125/printer/firmware_restart 2>/dev/null
            sleep 5
        elif [ $RECOVERY_LEVEL -eq 2 ]; then
            log "Recovery L2: restart klipper"
            systemctl restart klipper 2>/dev/null
            sleep 8
        elif [ $RECOVERY_LEVEL -eq 3 ]; then
            log "Recovery L3: USB port authorized reset"
            for port in /sys/bus/usb/devices/*/authorized; do
                echo 0 > "$port" 2>/dev/null
                sleep 1
                echo 1 > "$port" 2>/dev/null
            done
            sleep 5
            systemctl restart klipper 2>/dev/null
            sleep 5
        elif [ $RECOVERY_LEVEL -eq 4 ]; then
            log "Recovery L4: xhci_hcd unbind/rebind"
            for dev in /sys/bus/pci/drivers/xhci_hcd/*/; do
                dn=$(basename "$dev")
                echo "$dn" > /sys/bus/pci/drivers/xhci_hcd/unbind 2>/dev/null
                sleep 2
                echo "$dn" > /sys/bus/pci/drivers/xhci_hcd/bind 2>/dev/null
                sleep 3
            done
            systemctl restart klipper 2>/dev/null
            systemctl restart moonraker 2>/dev/null
            sleep 8
        else
            log "Recovery L5: full reboot (XHCI unrecoverable)"
            sleep 2
            reboot
        fi
        FAIL_COUNT=0
    fi
done
WDEOF
chmod +x /usr/local/bin/usb-watchdog.sh
cat > /etc/systemd/system/usb-watchdog.service << 'EOF'
[Unit]
Description=USB Watchdog for Klipper MCU
After=network.target klipper.service

[Service]
Type=simple
ExecStart=/usr/local/bin/usb-watchdog.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable usb-watchdog
systemctl start usb-watchdog
log_info "USB看门狗已启动 (10s检查/3次断连自动恢复)"

####################################################################################
# 11. 全服务验证
####################################################################################
log_step "Step 10/11: 全服务验证"

PASS=0
FAIL=0

check_service() {
    local name=$1
    local status=$(systemctl is-active "$name" 2>/dev/null)
    if [ "$status" = "active" ]; then
        log_info "  $name: ✅ active"
        PASS=$((PASS+1))
    else
        log_error "  $name: ❌ $status"
        FAIL=$((FAIL+1))
    fi
}

echo "服务状态:"
check_service klipper
check_service moonraker
check_service go2rtc
check_service bluetooth

echo ""
echo "PulseAudio:"
if pgrep -x pulseaudio >/dev/null; then
    log_info "  PulseAudio: ✅ 运行中"
    PASS=$((PASS+1))
else
    log_error "  PulseAudio: ❌ 未运行"
    FAIL=$((FAIL+1))
fi

echo ""
echo "Moonraker 连通:"
MK_INFO=$(curl -s --connect-timeout 3 http://localhost:7125/server/info 2>/dev/null || echo "")
if echo "$MK_INFO" | grep -q "klippy_connected"; then
    KLIPPY_CONN=$(echo "$MK_INFO" | python3 -c "import sys,json; print(json.load(sys.stdin).get('result',{}).get('klippy_connected','?'))" 2>/dev/null || echo "?")
    log_info "  klippy_connected: ✅ $KLIPPY_CONN"
    PASS=$((PASS+1))
else
    log_error "  Moonraker: ❌ 无法连接"
    FAIL=$((FAIL+1))
fi

echo ""
echo "截图服务:"
# 先检查go2rtc API可达性
G2RTC_HTTP=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 http://localhost:1984/api/streams 2>/dev/null || echo "000")
if [ "$G2RTC_HTTP" != "200" ]; then
    log_error "  go2rtc API: ❌ HTTP $G2RTC_HTTP (go2rtc服务未响应)"
    FAIL=$((FAIL+1))
else
    log_info "  go2rtc API: ✅ 可连接"
    PASS=$((PASS+1))
fi
# 用实际流名截图
SNAP_HTTP=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 http://localhost:1984/api/frame.jpeg?src=${CAM_STREAM} 2>/dev/null || echo "000")
if [ "$SNAP_HTTP" = "200" ]; then
    log_info "  go2rtc截图 (${CAM_STREAM}): ✅ HTTP $SNAP_HTTP"
    PASS=$((PASS+1))
elif [ "$SNAP_HTTP" = "502" ]; then
    log_warn "  go2rtc截图: ⚠ HTTP 502 (流未就绪，摄像头可能需要预热)"
    # 502不算失败，等1秒重试
    sleep 2
    SNAP_HTTP2=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 http://localhost:1984/api/frame.jpeg?src=${CAM_STREAM} 2>/dev/null || echo "000")
    if [ "$SNAP_HTTP2" = "200" ]; then
        log_info "  go2rtc截图 (重试): ✅ HTTP $SNAP_HTTP2"
        PASS=$((PASS+1))
    else
        log_error "  go2rtc截图 (重试): ❌ HTTP $SNAP_HTTP2"
        FAIL=$((FAIL+1))
    fi
else
    log_error "  go2rtc截图: ❌ HTTP $SNAP_HTTP"
    FAIL=$((FAIL+1))
fi

echo ""
echo "蓝牙音箱:"
if [ -n "$BT_MAC" ]; then
    BT_SINK=$(pactl list sinks short 2>/dev/null | grep bluez | head -1 | awk '{print $2}')
    if [ -n "$BT_SINK" ]; then
        log_info "  蓝牙sink: ✅ $BT_SINK"
        PASS=$((PASS+1))
    else
        log_warn "  蓝牙sink: ❌ 未连接 (音箱未开机？)"
        FAIL=$((FAIL+1))
    fi
else
    log_info "  蓝牙: 跳过 (未配置)"
fi

echo ""
echo "MCU串口:"
if [ -e "$MCU_SERIAL" ]; then
    log_info "  MCU: ✅ $MCU_SERIAL 存在"
    PASS=$((PASS+1))
else
    log_warn "  MCU: ❌ $MCU_SERIAL 不存在 (请确认已刷Klipper固件)"
    FAIL=$((FAIL+1))
fi

echo ""
echo "总控服务器连通:"
SERVER_REACH=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 "http://$SERVER_IP:8080/api/v1/health" 2>/dev/null || echo "000")
if [ "$SERVER_REACH" != "000" ]; then
    log_info "  总控服务器: ✅ HTTP $SERVER_REACH"
    PASS=$((PASS+1))
else
    PING_OK=$(ping -c 1 -W 2 "$SERVER_IP" 2>/dev/null | grep "1 received" || true)
    if [ -n "$PING_OK" ]; then
        log_info "  总控服务器: ✅ ping可达 (HTTP未响应，可能后端未启动)"
        PASS=$((PASS+1))
    else
        log_warn "  总控服务器: ❌ 不可达 (检查网络/总控IP)"
        FAIL=$((FAIL+1))
    fi
fi

echo ""
echo "SSH服务:"
SSH_OK=$(ss -tlnp | grep ":22 " | head -1 || true)
if [ -n "$SSH_OK" ]; then
    log_info "  SSH: ✅ 端口22监听中"
    PASS=$((PASS+1))
else
    log_error "  SSH: ❌ 端口22未监听"
    FAIL=$((FAIL+1))
fi

####################################################################################
# 12. 总结
####################################################################################
log_step "Step 11/11: 部署总结"

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║              N1 部署完成!                                ║${NC}"
echo -e "${BOLD}╠══════════════════════════════════════════════════════════╣${NC}"
echo -e "${BOLD}║  本机IP:       $N1_IP                                  ║${NC}"
echo -e "${BOLD}║  总控服务器:   $SERVER_IP                              ║${NC}"
echo -e "${BOLD}║  蓝牙MAC:      ${BT_MAC:-未配置}                              ║${NC}"
echo -e "${BOLD}║  MCU串口:      $MCU_SERIAL             ║${NC}"
echo -e "${BOLD}║  验证通过:     $PASS 项                                ║${NC}"
echo -e "${BOLD}║  需要处理:     $FAIL 项                                ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""

if [ $FAIL -gt 0 ]; then
    log_warn "有 $FAIL 项未通过，常见原因:"
    echo "  1. MCU串口不存在 → 需要先刷Klipper固件到主控板"
    echo "     刷固件方法: cd ~/klipper && make flash"
    echo "  2. 蓝牙音箱未连接 → 确认音箱已开机，然后运行:"
    echo "     bluetoothctl connect $BT_MAC"
    echo "  3. Moonraker未连接Klipper → 重启服务:"
    echo "     systemctl restart klipper moonraker"
fi

echo ""
log_info "总控服务器端验证命令:"
echo "  curl -s http://$N1_IP:7125/server/info   # Moonraker心跳"
echo "  curl -s -o /dev/null http://$N1_IP:1984/api/frame.jpeg?src=camera0   # 截图"
echo "  ssh root@$N1_IP   # SSH连通 (密码: 1234)"
echo ""
log_info "后端会自动发现此设备 (DEVICE_IP范围需包含 $N1_IP)"
echo ""
log_info "配置文件路径:"
echo "  printer.cfg:   $PRINTER_DATA/config/printer.cfg"
echo "  moonraker.conf: $PRINTER_DATA/config/moonraker.conf"
echo "  go2rtc.yaml:    /etc/go2rtc/go2rtc.yaml"
echo "  bt脚本:         /usr/local/bin/bt-speaker-connect.sh"

# 保存部署信息
cat > /root/n1_deploy_info.txt << DEPLOYEOF
N1_IP=$N1_IP
SERVER_IP=$SERVER_IP
BT_MAC=${BT_MAC:-none}
MCU_SERIAL=$MCU_SERIAL
CAMERA=$CAM_DEV
DEPLOY_TIME=$(date '+%Y-%m-%d %H:%M:%S')
PASS=$PASS
FAIL=$FAIL
DEPLOYEOF
log_info "部署信息已保存到 /root/n1_deploy_info.txt"
