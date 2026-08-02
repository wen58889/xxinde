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

# 强制apt使用IPv4 (部分N1网络IPv6不通)
mkdir -p /etc/apt/apt.conf.d
echo 'Acquire::ForceIPv4 "true";' > /etc/apt/apt.conf.d/99force-ipv4 2>/dev/null || true

apt update -qq 2>&1 | tail -3 || log_warn "apt update失败(可能无外网，部分依赖可能缺失)"
apt install -y \
    git python3 python3-pip python3-venv python3-dev wget curl v4l-utils \
    avahi-daemon \
    bluez bluez-tools \
    pulseaudio pulseaudio-module-bluetooth pulseaudio-utils \
    mpg123 ffmpeg \
    gcc-arm-none-eabi libnewlib-arm-none-eabi \
    libsodium23 pkg-config libusb-1.0-0 libusb-1.0-dev \
    network-manager iw wireless-tools rfkill \
    jq \
    2>&1 | tail -5 || log_warn "部分依赖安装失败(无外网)，继续部署"

# 验证关键依赖
for cmd in python3 git ffmpeg; do
    if ! command -v $cmd &>/dev/null; then
        log_error "关键依赖 $cmd 未安装! 请确保有外网访问后重新运行"
        exit 1
    fi
done
if command -v arm-none-eabi-gcc &>/dev/null; then
    log_info "ARM gcc已安装: $(arm-none-eabi-gcc --version 2>&1 | head -1)"
else
    log_warn "gcc-arm-none-eabi未安装，将跳过MCU固件编译(需要外网)"
fi

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
# 立即生效 (强制写入, 忽略错误)
echo -1 > /sys/module/usbcore/parameters/autosuspend 2>/dev/null || true
# 验证: 如果运行时仍是默认值2, 说明写入失败, 需要modprobe重载
AUTOSUSPEND_VAL=$(cat /sys/module/usbcore/parameters/autosuspend 2>/dev/null || echo "unknown")
if [ "$AUTOSUSPEND_VAL" != "-1" ]; then
    log_warn "autosuspend写入失败(当前=$AUTOSUSPEND_VAL), 尝试modprobe重载"
    modprobe -r usbcore 2>/dev/null || true
    modprobe usbcore autosuspend=-1 2>/dev/null || true
    AUTOSUSPEND_VAL=$(cat /sys/module/usbcore/parameters/autosuspend 2>/dev/null || echo "unknown")
fi
log_info "USB autosuspend=$AUTOSUSPEND_VAL (期望-1, 永久+运行时)"

# 2. udev规则: USB设备永不挂起 + Klipper串口固定(RP2040+STM32)
cat > /etc/udev/rules.d/99-usb-no-autosuspend.rules << 'EOF'
# 禁用所有USB设备自动挂起
ACTION=="add", SUBSYSTEM=="usb", ATTR{power/autosuspend}="-1"
ACTION=="add", SUBSYSTEM=="usb", TEST=="power/control", ATTR{power/control}="on"
# Klipper RP2040 CDC ACM: 固定符号链接+权限
ACTION=="add", SUBSYSTEM=="tty", ATTRS{idVendor}=="1d50", ATTRS{idProduct}=="614e", SYMLINK+="klipper-mcu", GROUP="root", MODE="0666"
# Klipper STM32 CDC ACM: 固定符号链接+权限
ACTION=="add", SUBSYSTEM=="tty", ATTRS{idVendor}=="0483", ATTRS{idProduct}=="5740", SYMLINK+="klipper-mcu", GROUP="root", MODE="0666"
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

# 5. usb-autosuspend-fix.service (sysinit阶段, 最可靠的持久化方式)
cat > /usr/local/bin/usb-autosuspend-fix.sh << 'ASEOF'
#!/bin/bash
echo -1 > /sys/module/usbcore/parameters/autosuspend 2>/dev/null || true
for d in /sys/bus/usb/devices/*/power/control; do echo on > "$d" 2>/dev/null; done
for d in /sys/bus/usb/devices/*/power/autosuspend; do echo -1 > "$d" 2>/dev/null; done
logger -t usb-autosuspend-fix "autosuspend=-1 + USB PM=on"
ASEOF
chmod +x /usr/local/bin/usb-autosuspend-fix.sh

cat > /etc/systemd/system/usb-autosuspend-fix.service << 'SVCEOF'
[Unit]
Description=Force USB autosuspend=-1 (sysinit stage)
DefaultDependencies=no
After=sysinit.target
Before=basic.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/usb-autosuspend-fix.sh
RemainAfterExit=yes

[Install]
WantedBy=sysinit.target
SVCEOF
systemctl daemon-reload
systemctl enable usb-autosuspend-fix.service 2>/dev/null || true
log_info "usb-autosuspend-fix.service 已启用 (sysinit阶段, 最可靠)"

# 6. net-check.service (纯有线版, NM启动后10s检查修复)
cat > /usr/local/bin/net-check.sh << 'NETEOF'
#!/bin/bash
sleep 10
echo -1 > /sys/module/usbcore/parameters/autosuspend 2>/dev/null || true
for d in /sys/bus/usb/devices/*/power/control; do echo on > "$d" 2>/dev/null; done
for d in /sys/bus/usb/devices/*/power/autosuspend; do echo -1 > "$d" 2>/dev/null; done
IFACE=$(cat /etc/n1-fixed-iface 2>/dev/null || echo "eth0")
[ -e "/sys/class/net/$IFACE" ] || IFACE="eth0"
ethtool --set-eee $IFACE eee off 2>/dev/null || true
ethtool -s $IFACE wol d 2>/dev/null || true
echo on > /sys/class/net/$IFACE/power/control 2>/dev/null || true
logger -t net-check "Network integrity check completed (wired-only)"
NETEOF
chmod +x /usr/local/bin/net-check.sh

cat > /etc/systemd/system/net-check.service << 'SVCEOF'
[Unit]
Description=Network Integrity Check (post-boot, wired-only)
After=NetworkManager.service
Wants=NetworkManager.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/net-check.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
SVCEOF
systemctl daemon-reload
systemctl enable net-check.service 2>/dev/null || true
log_info "net-check.service 已启用 (纯有线版)"

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
# WiFi彻底禁用 (三层: rfkill+nmcli+黑名单)
# 原因: brcmfmac WiFi驱动在6.18内核上固件bug导致中断风暴，
#       S905D SoC上WiFi(SDIO)和USB(XHCI)共享中断控制器，
#       中断风暴导致USB XHCI超时→MCU断连。产线全部使用有线。
####################################################################################
log_info "WiFi彻底禁用 (三层: rfkill+nmcli+黑名单)..."

# L1: rfkill block wlan (硬件级禁用)
rfkill block wlan 2>/dev/null || true
log_info "  L1: rfkill block wlan (硬件级禁用)"

# L2: nmcli radio wifi off (NetworkManager级禁用)
nmcli radio wifi off 2>/dev/null || true
log_info "  L2: nmcli radio wifi off (NM级禁用)"

# L3: brcmfmac黑名单 (驱动级禁用，阻止模块加载)
echo "blacklist brcmfmac" > /etc/modprobe.d/brcmfmac.conf
log_info "  L3: brcmfmac黑名单 (驱动级禁用，重启后不加载)"

# rfkill持久化service — 开机后自动block wlan
cat > /usr/local/bin/rfkill-wifi-block.sh << 'RFEOF'
#!/bin/bash
rfkill block wlan 2>/dev/null || true
logger -t rfkill-wifi-block "WiFi rfkill block applied"
RFEOF
chmod +x /usr/local/bin/rfkill-wifi-block.sh

cat > /etc/systemd/system/n1-rfkill-persist.service << 'SVCEOF'
[Unit]
Description=Persist WiFi rfkill block state
After=NetworkManager.service
Wants=NetworkManager.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/rfkill-wifi-block.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
SVCEOF
systemctl daemon-reload
systemctl enable n1-rfkill-persist.service 2>/dev/null || true
log_info "  rfkill持久化service已启用"

# WiFi服务清理
systemctl disable wifi-watchdog 2>/dev/null || true
systemctl stop wifi-watchdog 2>/dev/null || true
rm -f /etc/NetworkManager/dispatcher.d/99-wifi-stability.sh 2>/dev/null || true
rm -f /etc/NetworkManager/conf.d/no-p2p.conf 2>/dev/null || true
rm -f /etc/NetworkManager/conf.d/wifi-no-bgscan.conf 2>/dev/null || true
rm -f /etc/NetworkManager/conf.d/wifi-no-mac-random.conf 2>/dev/null || true
log_info "  WiFi服务已清理: wifi-watchdog禁用, WiFi dispatcher/conf已移除"

log_info "WiFi三层禁用完成 (rfkill+nmcli+黑名单+持久化)"

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
    log_info "克隆 Klipper (最新版本)..."
    git clone https://github.com/Klipper3d/klipper.git "$KLIPPER_DIR" 2>&1 | tail -3
    cd "$KLIPPER_DIR"
    log_info "Klipper 版本: $(git log --oneline -1)"
    cd /
else
    log_info "Klipper 目录已存在，更新到最新版本..."
    cd "$KLIPPER_DIR"
    git pull --ff-only 2>/dev/null || log_warn "Klipper 更新失败(可能本地有修改)，使用当前版本"
    log_info "Klipper 版本: $(git log --oneline -1)"
    cd /
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

# 写入 printer.cfg (与101/102实际验证通过的配置完全一致)
log_info "写入 printer.cfg ..."
cat > "$PRINTER_DATA/config/printer.cfg" << PRINTERCFG
####################################################################################
# CoreXY机械臂控制系统 - 手机屏幕点击/滑动自动化
# 硬件: SKR Pico V1.0 + TMC2209 + CoreXY
# 行程: X=150mm, Y=150mm, Z=10mm (无限位, 纯自由移动)
# 注意: 此配置已在101/102上验证通过，请勿随意修改
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
square_corner_velocity: 5.0

# ==================== X轴 ====================
[stepper_x]
step_pin: gpio11
dir_pin: !gpio10
enable_pin: !gpio12
rotation_distance: 20
microsteps: 16
endstop_pin: ^gpio4
position_endstop: 0
position_max: 150
homing_speed: 50
homing_retract_dist: 3

[tmc2209 stepper_x]
uart_pin: gpio9
tx_pin: gpio8
uart_address: 0
run_current: 0.8
hold_current: 0.5
sense_resistor: 0.110
stealthchop_threshold: 999999

# ==================== Y轴 ====================
[stepper_y]
step_pin: gpio6
dir_pin: !gpio5
enable_pin: !gpio7
rotation_distance: 20
microsteps: 16
endstop_pin: ^gpio3
position_endstop: 0
position_max: 150
homing_speed: 50
homing_retract_dist: 3

[tmc2209 stepper_y]
uart_pin: gpio9
tx_pin: gpio8
uart_address: 2
run_current: 0.8
hold_current: 0.5
sense_resistor: 0.110
stealthchop_threshold: 999999

# ==================== Z轴（无限位, 纯自由移动） ====================
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

# ==================== 基础功能 ====================
[fan]
pin: gpio17

[idle_timeout]
timeout: 28800

[virtual_sdcard]
path: $PRINTER_DATA/gcodes

[respond]
[display_status]
[pause_resume]

[force_move]
enable_force_move: True

[gcode_macro G28]
description: 覆盖标准G28 (Z轴无限位, 仅归X/Y后设Z=0)
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

# 编译Klipper MCU固件 (RP2040)
if command -v arm-none-eabi-gcc &>/dev/null; then
    log_info "编译Klipper RP2040固件..."
    cd "$KLIPPER_DIR"
    # 配置RP2040
    make menuconfig KCONFIG_CONFIG=.config.rp2040 << 'MENUEOF' 2>/dev/null || true
MENUEOF
    # 使用scripts/config设置RP2040
    scripts/config --set-str CONFIG_MCU rp2040 2>/dev/null || true
    scripts/config --enable CONFIG_USB 2>/dev/null || true
    scripts/config --disable CONFIG_SERIAL 2>/dev/null || true
    # 编译
    if make -j4 2>&1 | tail -5; then
        if [ -f out/klipper.elf.uf2 ]; then
            log_info "Klipper固件编译成功: out/klipper.elf.uf2"
            # 自动刷写 (如果MCU已连接)
            if [ "$MCU_SERIAL" != "/dev/serial/by-id/REPLACE_ME" ] && [ -e "$MCU_SERIAL" ]; then
                log_ask "是否立即刷写固件到RP2040? [Y/n]:"
                read -r FLASH_YN
                FLASH_YN=${FLASH_YN:-Y}
                if [ "$FLASH_YN" = "Y" ] || [ "$FLASH_YN" = "y" ]; then
                    log_info "刷写固件 (请等待RP2040重启)..."
                    make flash FLASH_DEVICE="$MCU_SERIAL" 2>&1 | tail -5 || \
                        log_warn "刷写失败，可手动执行: cd /root/klipper && make flash FLASH_DEVICE=$MCU_SERIAL"
                    sleep 5
                fi
            else
                log_warn "MCU未连接，跳过自动刷写。连接MCU后手动执行:"
                log_warn "  cd /root/klipper && make flash FLASH_DEVICE=/dev/serial/by-id/xxx"
            fi
        else
            log_warn "固件编译未生成uf2文件"
        fi
    else
        log_warn "固件编译失败，可稍后手动编译: cd /root/klipper && make menuconfig && make -j4"
    fi
    cd /
else
    log_warn "跳过MCU固件编译(无ARM gcc)。部署后手动编译:"
    log_warn "  apt install -y gcc-arm-none-eabi"
    log_warn "  cd /root/klipper && make menuconfig  # 选RP2040"
    log_warn "  make -j4 && make flash FLASH_DEVICE=$MCU_SERIAL"
fi

# Klipper systemd 服务 (依赖MCU串口设备)
cat > /etc/systemd/system/klipper.service << 'EOF'
[Unit]
Description=Klipper 3D Printer Firmware
After=network.target
Wants=dev-ttyACM0.device

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
    log_info "克隆 Moonraker (最新版本)..."
    git clone https://github.com/Arksine/moonraker.git "$MOONRAKER_DIR" 2>&1 | tail -3
    cd "$MOONRAKER_DIR"
    log_info "Moonraker 版本: $(git log --oneline -1)"
    cd /
else
    log_info "Moonraker 目录已存在，更新到最新版本..."
    cd "$MOONRAKER_DIR"
    git pull --ff-only 2>/dev/null || log_warn "Moonraker 更新失败(可能本地有修改)，使用当前版本"
    log_info "Moonraker 版本: $(git log --oneline -1)"
    cd /
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
FLUIDD_DIR=$ROOT_DIR/printer_data/fluidd
FLUIDD_RETRY=0
FLUIDD_MAX_RETRY=3
FLUIDD_MIRRORS=(
    "https://ghfast.top/https://github.com/fluidd-core/fluidd/releases/latest/download/fluidd.zip"
    "https://gh-proxy.com/https://github.com/fluidd-core/fluidd/releases/latest/download/fluidd.zip"
    "https://github.com/fluidd-core/fluidd/releases/latest/download/fluidd.zip"
)
while [ ! -f "$FLUIDD_DIR/index.html" ] && [ "$FLUIDD_RETRY" -lt "$FLUIDD_MAX_RETRY" ]; do
    FLUIDD_RETRY=$((FLUIDD_RETRY + 1))
    if [ "$FLUIDD_RETRY" -gt 1 ]; then
        log_warn "Fluidd 下载重试 $FLUIDD_RETRY/$FLUIDD_MAX_RETRY..."
        sleep 5
    fi
    log_info "下载 Fluidd 前端 (预编译release)..."
    mkdir -p "$FLUIDD_DIR"
    rm -f /tmp/fluidd.zip
    DOWNLOADED=0
    for mirror in "${FLUIDD_MIRRORS[@]}"; do
        log_info "  尝试: ${mirror:0:50}..."
        if wget -q --timeout=30 "$mirror" -O /tmp/fluidd.zip 2>/dev/null && [ -s /tmp/fluidd.zip ]; then
            DOWNLOADED=1
            break
        fi
        rm -f /tmp/fluidd.zip
    done
    if [ "$DOWNLOADED" -eq 1 ]; then
        (cd "$FLUIDD_DIR" && unzip -qo /tmp/fluidd.zip) && \
        rm -f /tmp/fluidd.zip || \
        log_warn "Fluidd 解压失败"
    else
        log_warn "Fluidd 下载失败 (第${FLUIDD_RETRY}次，所有镜像不可达)"
    fi
done
if [ -f "$FLUIDD_DIR/index.html" ]; then
    log_info "Fluidd 安装成功 (index.html 验证通过)"
else
    log_warn "Fluidd 下载失败 (重试${FLUIDD_MAX_RETRY}次)，可稍后手动安装: 下载 fluidd.zip 解压到 $FLUIDD_DIR"
fi
cat >> "$PRINTER_DATA/config/moonraker.conf" << EOF

[update_manager]
refresh_interval: 168

[update_manager client fluidd]
type: web
repo: fluidd-core/fluidd
path: ~/printer_data/fluidd

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

# 修复Fluidd WebSocket周期性断连: 增大ping_interval (10s→30s)
# 根因: Tornado默认ping_interval=10s, N1 CPU负载或网络延迟导致pong超时→Fluidd断连
# 症状: Moonraker日志 "Pong Time Elapsed: 3.33" → Websocket Closed
if [ -f /root/moonraker/moonraker/components/application.py ]; then
    if grep -q "websocket_ping_interval.*else 10\." /root/moonraker/moonraker/components/application.py 2>/dev/null; then
        sed -i "s/'websocket_ping_interval': None if tornado_ver < (6, 5) else 10\./'websocket_ping_interval': None if tornado_ver < (6, 5) else 30./" /root/moonraker/moonraker/components/application.py
        log_info "Fluidd WebSocket ping_interval已修复 (10s→30s, 防止周期性断连)"
    fi
fi

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
Environment=PATH=/usr/local/bin:/usr/bin:/bin
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
cd /root/printer_data/fluidd
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

# USB看门狗 v5 (工业级: 通用MCU匹配 + 冷却防抖 + 告警通知 + XHCI预防 + Klipper双重验证)
# v4→v5: +source alert-push +MCU断连/恢复通知 +XHCI预防unbind/bind +恢复后Klipper验证
cat > /usr/local/bin/usb-watchdog.sh << 'WDEOF'
#!/bin/bash
source /usr/local/bin/alert-push.sh 2>/dev/null || true

MCU_ID="usb-Klipper"
CHECK_INTERVAL=5
MAX_FAIL=3
FAIL_COUNT=0
XHCI_FAIL_COUNT=0
XHCI_REBOOT_THRESHOLD=6
RECOVERY_LEVEL=0
MAX_RECOVERY_LEVEL=5
COOLDOWN=300
LAST_RECOVERY=0
MCU_DOWN_SINCE=0
log() { logger -t usb-watchdog "$1"; }

check_xhci_error() {
    dmesg | tail -30 | grep -qiE 'HC died|xHCI host controller not responding'
}

check_xhci_timeout() {
    dmesg | tail -30 | grep -qiE 'Timeout while waiting for setup device|unable to enumerate USB device|device descriptor read.*error -1[12]0|device not accepting address.*error -62'
}

xhci_preventive_reset() {
    for dev in /sys/bus/pci/drivers/xhci_hcd/*/; do
        [ -d "$dev" ] || continue
        dn=$(basename "$dev")
        echo "$dn" > /sys/bus/pci/drivers/xhci_hcd/unbind 2>/dev/null || true
        sleep 2
        echo "$dn" > /sys/bus/pci/drivers/xhci_hcd/bind 2>/dev/null || true
        sleep 3
    done
}

verify_klippy_ready() {
    local retries=0
    while [ $retries -lt 6 ]; do
        local state=$(curl -s -m 3 http://127.0.0.1:7125/server/info 2>/dev/null | grep -oP '"klippy_state":"\K[^"]+' || echo "")
        if [ "$state" = "ready" ]; then
            return 0
        fi
        retries=$((retries + 1))
        sleep 5
    done
    return 1
}

while true; do
    sleep $CHECK_INTERVAL

    if check_xhci_error; then
        log "CRITICAL: XHCI HC died! Rebooting"
        type alert_push &>/dev/null && alert_push "xhci_died" "critical" "XHCI host controller died, rebooting"
        sleep 1
        reboot
    fi

    if check_xhci_timeout; then
        XHCI_FAIL_COUNT=$((XHCI_FAIL_COUNT + 1))
        log "XHCI timeout detected (count=$XHCI_FAIL_COUNT/$XHCI_REBOOT_THRESHOLD)"
        if [ $XHCI_FAIL_COUNT -ge $XHCI_REBOOT_THRESHOLD ]; then
            log "XHCI timeout threshold reached, rebooting"
            type alert_push &>/dev/null && alert_push "xhci_timeout" "critical" "XHCI timeout threshold reached, rebooting"
            sleep 1
            reboot
        fi
    else
        if [ $XHCI_FAIL_COUNT -gt 0 ]; then
            XHCI_FAIL_COUNT=$((XHCI_FAIL_COUNT - 1))
        fi
    fi

    if ls /dev/serial/by-id/ 2>/dev/null | grep -q "$MCU_ID"; then
        if [ $FAIL_COUNT -gt 0 ]; then
            local down_duration=0
            if [ $MCU_DOWN_SINCE -gt 0 ]; then
                down_duration=$(( $(date +%s) - MCU_DOWN_SINCE ))
            fi
            log "MCU recovered (was down ${down_duration}s)"
            type alert_resolved &>/dev/null && alert_resolved "mcu_disconnected" "$down_duration"
            FAIL_COUNT=0
            RECOVERY_LEVEL=0
            MCU_DOWN_SINCE=0
        fi
        continue
    fi
    FAIL_COUNT=$((FAIL_COUNT + 1))
    if [ $MCU_DOWN_SINCE -eq 0 ]; then
        MCU_DOWN_SINCE=$(date +%s)
        type alert_push &>/dev/null && alert_push "mcu_disconnected" "critical" "MCU not detected at /dev/serial/by-id/, starting recovery"
    fi
    log "MCU not detected! fail=$FAIL_COUNT level=$RECOVERY_LEVEL"
    if [ $FAIL_COUNT -ge $MAX_FAIL ]; then
        NOW=$(date +%s)
        ELAPSED=$((NOW - LAST_RECOVERY))
        if [ $ELAPSED -lt $COOLDOWN ]; then
            log "Cooldown active (${ELAPSED}s/${COOLDOWN}s), skip recovery"
            FAIL_COUNT=0
            continue
        fi
        if [ $RECOVERY_LEVEL -ge $MAX_RECOVERY_LEVEL ]; then
            log "Max recovery level reached, stop trying until MCU reappears"
            type alert_push &>/dev/null && alert_push "mcu_recovery_exhausted" "critical" "All recovery levels exhausted, MCU still disconnected"
            FAIL_COUNT=0
            sleep 60
            continue
        fi
        RECOVERY_LEVEL=$((RECOVERY_LEVEL + 1))
        LAST_RECOVERY=$NOW
        if [ $RECOVERY_LEVEL -eq 1 ]; then
            log "Recovery L1: firmware_restart"
            curl -s -X POST http://127.0.0.1:7125/printer/firmware_restart 2>/dev/null
            sleep 5
        elif [ $RECOVERY_LEVEL -eq 2 ]; then
            log "Recovery L2: restart klipper"
            systemctl restart klipper 2>/dev/null
            sleep 8
        elif [ $RECOVERY_LEVEL -eq 3 ]; then
            log "Recovery L3: USB port authorized reset (skip hub)"
            for port in /sys/bus/usb/devices/*/authorized; do
                devpath=$(dirname "$port")
                devnum=$(cat "$devpath/devnum" 2>/dev/null || echo "0")
                if [ "$devnum" = "1" ]; then continue; fi
                echo 0 > "$port" 2>/dev/null
                sleep 1
                echo 1 > "$port" 2>/dev/null
            done
            sleep 5
            systemctl restart klipper 2>/dev/null
            sleep 5
        elif [ $RECOVERY_LEVEL -eq 4 ]; then
            log "Recovery L4: xhci_hcd preventive unbind/rebind + service restart"
            xhci_preventive_reset
            systemctl restart klipper moonraker 2>/dev/null
            sleep 8
        else
            log "Recovery L5: full reboot"
            type alert_push &>/dev/null && alert_push "mcu_reboot" "critical" "MCU recovery L5: full reboot"
            sleep 2
            reboot
        fi
        if [ $RECOVERY_LEVEL -lt $MAX_RECOVERY_LEVEL ]; then
            if verify_klippy_ready; then
                log "Klipper verified ready after L$RECOVERY_LEVEL"
            else
                log "Klipper NOT ready after L$RECOVERY_LEVEL"
                type alert_push &>/dev/null && alert_push "klipper_not_ready" "warning" "Klipper not ready after recovery L$RECOVERY_LEVEL"
            fi
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
log_info "USB看门狗已启动 (v5: 告警通知+XHCI预防+Klipper验证)"

####################################################################################
# 10.5 工业级监控组件部署
####################################################################################
log_step "Step 10.5/12: 工业级监控组件部署"

# 10.5a: alert-push.sh 告警推送函数库
log_info "部署 alert-push.sh 告警推送函数库..."
cat > /usr/local/bin/alert-push.sh << 'ALERTEOF'
#!/bin/bash
source /usr/local/bin/alert-push.sh 2>/dev/null || true

ALERT_DEDUP_DIR="/var/run/n1-alert-dedup"
ALERT_QUEUE_FILE="/var/log/n1-alert-queue.log"
ALERT_QUEUE_MAX=100
ALERT_DEDUP_WINDOW=300

_alert_get_config() {
    if [ -f /etc/n1_network_info.txt ]; then
        SERVER_IP=$(grep '^SERVER_IP=' /etc/n1_network_info.txt 2>/dev/null | cut -d= -f2)
        N1_IP=$(grep '^N1_IP=' /etc/n1_network_info.txt 2>/dev/null | cut -d= -f2)
    fi
    SERVER_IP=${SERVER_IP:-192.168.5.8}
    N1_IP=${N1_IP:-$(hostname -I 2>/dev/null | awk '{print $1}')}
    ALERT_PUSH_URL="http://${SERVER_IP}:8080/api/v1/alerts"
}

alert_push() {
    local alert_type="$1"
    local alert_level="${2:-info}"
    local message="$3"
    [ -z "$alert_type" ] && return 1
    _alert_get_config
    mkdir -p "$ALERT_DEDUP_DIR" 2>/dev/null || true
    local dedup_file="${ALERT_DEDUP_DIR}/${alert_type}.ts"
    local now=$(date +%s)
    if [ -f "$dedup_file" ]; then
        local last_push=$(cat "$dedup_file" 2>/dev/null | grep -oP '"last_pushed":\K\d+' || echo 0)
        local count=$(cat "$dedup_file" 2>/dev/null | grep -oP '"count":\K\d+' || echo 0)
        local elapsed=$((now - last_push))
        if [ "$elapsed" -lt "$ALERT_DEDUP_WINDOW" ]; then
            count=$((count + 1))
            echo "{\"count\":$count,\"last_pushed\":$last_push,\"first_timestamp\":$(cat "$dedup_file" 2>/dev/null | grep -oP '"first_timestamp":\K\d+' || echo $now)}" > "$dedup_file"
            logger -t alert-push "Dedup: $alert_type (count=$count, ${elapsed}s/${ALERT_DEDUP_WINDOW}s)"
            return 0
        fi
    fi
    local timestamp=$(date -Iseconds 2>/dev/null || date '+%Y-%m-%dT%H:%M:%S%z')
    local json=$(printf '{"device_id":"%s","alert_type":"%s","alert_level":"%s","timestamp":"%s","details":"%s"}' \
        "$N1_IP" "$alert_type" "$alert_level" "$timestamp" "$message")
    local http_code=$(curl -s -m 5 --connect-timeout 3 -o /dev/null -w "%{http_code}" \
        -X POST -H "Content-Type: application/json" -d "$json" "$ALERT_PUSH_URL" 2>/dev/null || echo "000")
    if [ "$http_code" = "200" ] || [ "$http_code" = "201" ] || [ "$http_code" = "204" ]; then
        echo "{\"count\":1,\"last_pushed\":$now,\"first_timestamp\":$now}" > "$dedup_file"
        logger -t alert-push "Pushed: $alert_type level=$alert_level"
        return 0
    else
        logger -t alert-push "Push failed: $alert_type http=$http_code, caching locally"
        echo "$json" >> "$ALERT_QUEUE_FILE" 2>/dev/null || true
        local queue_len=$(wc -l < "$ALERT_QUEUE_FILE" 2>/dev/null || echo 0)
        if [ "$queue_len" -gt "$ALERT_QUEUE_MAX" ]; then
            tail -n "$ALERT_QUEUE_MAX" "$ALERT_QUEUE_FILE" > "${ALERT_QUEUE_FILE}.tmp" 2>/dev/null
            mv "${ALERT_QUEUE_FILE}.tmp" "$ALERT_QUEUE_FILE" 2>/dev/null || true
        fi
        return 1
    fi
}

alert_resolved() {
    local alert_type="$1"
    local duration="${2:-0}"
    [ -z "$alert_type" ] && return 1
    _alert_get_config
    local dedup_file="${ALERT_DEDUP_DIR}/${alert_type}.ts"
    rm -f "$dedup_file" 2>/dev/null || true
    local timestamp=$(date -Iseconds 2>/dev/null || date '+%Y-%m-%dT%H:%M:%S%z')
    local json=$(printf '{"device_id":"%s","alert_type":"%s_resolved","alert_level":"info","timestamp":"%s","duration_seconds":%s}' \
        "$N1_IP" "$alert_type" "$timestamp" "$duration")
    local http_code=$(curl -s -m 5 --connect-timeout 3 -o /dev/null -w "%{http_code}" \
        -X POST -H "Content-Type: application/json" -d "$json" "$ALERT_PUSH_URL" 2>/dev/null || echo "000")
    if [ "$http_code" = "200" ] || [ "$http_code" = "201" ] || [ "$http_code" = "204" ]; then
        logger -t alert-push "Resolved: $alert_type duration=${duration}s"
        return 0
    else
        echo "$json" >> "$ALERT_QUEUE_FILE" 2>/dev/null || true
        return 1
    fi
}

alert_retry_cached() {
    [ -f "$ALERT_QUEUE_FILE" ] || return 0
    _alert_get_config
    local remaining=""
    local retried=0
    local succeeded=0
    while IFS= read -r line; do
        [ -z "$line" ] && continue
        local http_code=$(curl -s -m 5 --connect-timeout 3 -o /dev/null -w "%{http_code}" \
            -X POST -H "Content-Type: application/json" -d "$line" "$ALERT_PUSH_URL" 2>/dev/null || echo "000")
        if [ "$http_code" = "200" ] || [ "$http_code" = "201" ] || [ "$http_code" = "204" ]; then
            succeeded=$((succeeded + 1))
        else
            remaining="${remaining}${line}"$'\n'
            retried=$((retried + 1))
        fi
    done < "$ALERT_QUEUE_FILE"
    if [ -n "$remaining" ]; then
        printf '%s' "$remaining" > "$ALERT_QUEUE_FILE"
    else
        rm -f "$ALERT_QUEUE_FILE"
    fi
    [ "$succeeded" -gt 0 ] || [ "$retried" -gt 0 ] && \
        logger -t alert-push "Retry cached: succeeded=$succeeded remaining=$retried"
    return 0
}
ALERTEOF
chmod +x /usr/local/bin/alert-push.sh
log_info "  alert-push.sh 已部署"

# 10.5b: link-monitor.sh 有线链路监控服务
log_info "部署 link-monitor.sh 有线链路监控服务..."
IFACE_FOR_MONITOR=$(cat /etc/n1-fixed-iface 2>/dev/null || echo "eth0")
[ -e "/sys/class/net/$IFACE_FOR_MONITOR" ] || IFACE_FOR_MONITOR="eth0"
cat > /usr/local/bin/link-monitor.sh << LINKEOF
#!/bin/bash
source /usr/local/bin/alert-push.sh 2>/dev/null || true

LINK_CHECK_INTERVAL=5
LINK_RECONNECT_MAX_RETRIES=3
LINK_RECONNECT_INTERVAL=5
LINK_ERROR_THRESHOLD=100
LINK_FLAPPING_THRESHOLD=3
LINK_FLAPPING_WINDOW=30
NETWORK_DOWN_NOTIFY_THRESHOLD=10
STATIC_ARP_CHECK_INTERVAL=60

IFACE=\$(cat /etc/n1-fixed-iface 2>/dev/null || echo "eth0")
[ -e "/sys/class/net/\$IFACE" ] || IFACE="eth0"
GATEWAY_IP="192.168.5.1"
SERVER_IP=\$(grep '^SERVER_IP=' /etc/n1_network_info.txt 2>/dev/null | cut -d= -f2)
SERVER_IP=\${SERVER_IP:-192.168.5.8}

link_down_since=0
flap_count=0
flap_times=""
last_arp_check=0
prev_rx_errors=0
prev_tx_errors=0
prev_rx_drops=0
prev_tx_drops=0

get_link_status() { ethtool "\$IFACE" 2>/dev/null | grep "Link detected" | awk '{print \$3}'; }
get_link_speed() { ethtool "\$IFACE" 2>/dev/null | grep "Speed:" | awk '{print \$2}'; }
get_error_stats() {
    local stats=\$(ip -s link show "\$IFACE" 2>/dev/null)
    rx_errors=\$(echo "\$stats" | grep -A1 "RX:" | tail -1 | awk '{print \$2}')
    tx_errors=\$(echo "\$stats" | grep -A1 "TX:" | tail -1 | awk '{print \$2}')
    rx_drops=\$(echo "\$stats" | grep -A1 "RX:" | tail -1 | awk '{print \$3}')
    tx_drops=\$(echo "\$stats" | grep -A1 "TX:" | tail -1 | awk '{print \$3}')
    rx_errors=\${rx_errors:-0}; tx_errors=\${tx_errors:-0}; rx_drops=\${rx_drops:-0}; tx_drops=\${tx_drops:-0}
}

setup_static_arp() {
    local gateway_mac=\$(ip neigh show "\$GATEWAY_IP" 2>/dev/null | grep -oP 'lladdr \K[0-9a-f:]+' | head -1)
    local server_mac=\$(ip neigh show "\$SERVER_IP" 2>/dev/null | grep -oP 'lladdr \K[0-9a-f:]+' | head -1)
    if [ -n "\$gateway_mac" ]; then
        ip neigh del "\$GATEWAY_IP" dev "\$IFACE" 2>/dev/null || true
        ip neigh add "\$GATEWAY_IP" lladdr "\$gateway_mac" dev "\$IFACE" nud perm 2>/dev/null || \
        ip neigh change "\$GATEWAY_IP" lladdr "\$gateway_mac" dev "\$IFACE" nud perm 2>/dev/null || true
    fi
    if [ -n "\$server_mac" ] && [ "\$SERVER_IP" != "\$GATEWAY_IP" ]; then
        ip neigh del "\$SERVER_IP" dev "\$IFACE" 2>/dev/null || true
        ip neigh add "\$SERVER_IP" lladdr "\$server_mac" dev "\$IFACE" nud perm 2>/dev/null || \
        ip neigh change "\$SERVER_IP" lladdr "\$server_mac" dev "\$IFACE" nud perm 2>/dev/null || true
    fi
}

try_reconnect() {
    local retries=0
    local con_name=\$(nmcli -t -f NAME,DEVICE con show --active 2>/dev/null | grep "\$IFACE" | head -1 | cut -d: -f1)
    while [ "\$retries" -lt "\$LINK_RECONNECT_MAX_RETRIES" ]; do
        logger -t link-monitor "Reconnect attempt \$((retries+1))/\$LINK_RECONNECT_MAX_RETRIES"
        if [ -n "\$con_name" ]; then
            nmcli con up "\$con_name" 2>/dev/null && return 0
        else
            ip link set dev "\$IFACE" up 2>/dev/null || true
            sleep 3
            get_link_status | grep -q "yes" && return 0
        fi
        retries=\$((retries + 1)); sleep "\$LINK_RECONNECT_INTERVAL"
    done
    return 1
}

notify_network_down() {
    type alert_push &>/dev/null && alert_push "network_down" "critical" "Network link down on \$IFACE for \${1}s"
}
notify_network_up() {
    type alert_push &>/dev/null && alert_resolved "network_down" "\$1"
    logger -t link-monitor "Network up after \${1}s downtime"
}

check_flapping() {
    local now=\$(date +%s)
    flap_times="\${flap_times}\${now} "
    local recent=""
    for t in \$flap_times; do
        local elapsed=\$((now - t))
        [ "\$elapsed" -le "\$LINK_FLAPPING_WINDOW" ] && recent="\${recent}\${t} "
    done
    flap_times="\$recent"
    local count=\$(echo \$flap_times | wc -w)
    if [ "\$count" -ge "\$LINK_FLAPPING_THRESHOLD" ]; then
        logger -t link-monitor "Link flapping detected (\$count changes in \${LINK_FLAPPING_WINDOW}s)"
        type alert_push &>/dev/null && alert_push "link_flapping" "warning" "Link flapping on \$IFACE: \$count changes in \${LINK_FLAPPING_WINDOW}s"
        flap_times=""
        return 0
    fi
    return 1
}

logger -t link-monitor "Starting link monitor for \$IFACE (interval=\${LINK_CHECK_INTERVAL}s)"
get_error_stats
prev_rx_errors=\$rx_errors; prev_tx_errors=\$tx_errors; prev_rx_drops=\$rx_drops; prev_tx_drops=\$tx_drops

while true; do
    sleep "\$LINK_CHECK_INTERVAL"
    local link_status=\$(get_link_status)
    local now=\$(date +%s)
    if [ "\$link_status" = "yes" ]; then
        if [ "\$link_down_since" -gt 0 ]; then
            local downtime=\$((now - link_down_since))
            check_flapping; notify_network_up "\$downtime"; link_down_since=0
            logger -t link-monitor "Link recovered after \${downtime}s"
        fi
        get_error_stats
        local rx_delta=\$((rx_errors - prev_rx_errors))
        local tx_delta=\$((tx_errors - prev_tx_errors))
        local rd_delta=\$((rx_drops - prev_rx_drops))
        local td_delta=\$((tx_drops - prev_tx_drops))
        local total_delta=\$((rx_delta + tx_delta + rd_delta + td_delta))
        if [ "\$total_delta" -gt "\$LINK_ERROR_THRESHOLD" ]; then
            logger -t link-monitor "High error rate: RX_ERR=+\$rx_delta TX_ERR=+\$tx_delta RX_DROP=+\$rd_delta TX_DROP=+\$td_delta"
            type alert_push &>/dev/null && alert_push "link_errors" "warning" "High error rate on \$IFACE: +\$total_delta errors in \${LINK_CHECK_INTERVAL}s"
        fi
        prev_rx_errors=\$rx_errors; prev_tx_errors=\$tx_errors; prev_rx_drops=\$rx_drops; prev_tx_drops=\$tx_drops
        if [ \$((now - last_arp_check)) -ge "\$STATIC_ARP_CHECK_INTERVAL" ]; then
            setup_static_arp; last_arp_check=\$now
        fi
    else
        if [ "\$link_down_since" -eq 0 ]; then
            link_down_since=\$now
            logger -t link-monitor "Link down detected on \$IFACE"
            check_flapping
        fi
        local downtime=\$((now - link_down_since))
        if [ "\$downtime" -ge "\$NETWORK_DOWN_NOTIFY_THRESHOLD" ] && [ \$((downtime % NETWORK_DOWN_NOTIFY_THRESHOLD)) -eq 0 ]; then
            notify_network_down "\$downtime"
        fi
        if ! check_flapping; then try_reconnect || true; fi
    fi
done
LINKEOF
chmod +x /usr/local/bin/link-monitor.sh

cat > /etc/systemd/system/link-monitor.service << 'EOF'
[Unit]
Description=N1 Wired Link Monitor
After=network.target NetworkManager.service

[Service]
Type=simple
ExecStart=/usr/local/bin/link-monitor.sh
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable link-monitor
systemctl start link-monitor
log_info "  link-monitor.service 已启动"

# 10.5c: n1-health-monitor.sh 系统资源监控
log_info "部署 n1-health-monitor.sh 系统资源监控..."
cat > /usr/local/bin/n1-health-monitor.sh << 'HEALTHEOF'
#!/bin/bash
source /usr/local/bin/alert-push.sh 2>/dev/null || true

RESOURCE_CHECK_INTERVAL=30
DISK_USAGE_WARN_THRESHOLD=90
DISK_USAGE_CRITICAL_THRESHOLD=95
DISK_CLEANUP_TARGET=85
MEM_USAGE_WARN_THRESHOLD=80
MEM_RECOVERY_TARGET=70
CPU_TEMP_WARN_THRESHOLD=80
CPU_TEMP_CRITICAL_THRESHOLD=90
SERVICE_HTTP_FAILURE_THRESHOLD=3
SERVICE_CRASH_LOOP_THRESHOLD=3
SERVICE_CRASH_LOOP_WINDOW=300
HEALTH_STATUS_FILE="/var/run/n1-health-status.json"

IFACE=$(cat /etc/n1-fixed-iface 2>/dev/null || echo "eth0")
[ -e "/sys/class/net/$IFACE" ] || IFACE="eth0"
N1_IP=$(grep '^N1_IP=' /etc/n1_network_info.txt 2>/dev/null | cut -d= -f2)
N1_IP=${N1_IP:-$(hostname -I 2>/dev/null | awk '{print $1}')}

crash_counts=""

check_disk() {
    local usage=$(df / 2>/dev/null | tail -1 | awk '{print $5}' | tr -d '%')
    usage=${usage:-0}
    if [ "$usage" -ge "$DISK_USAGE_CRITICAL_THRESHOLD" ]; then
        logger -t health-monitor "Disk critical: ${usage}% used, cleaning all logs"
        find /var/log/ -name "*.log" -mtime +1 -delete 2>/dev/null || true
        find /var/log/ -name "*.gz" -delete 2>/dev/null || true
        find ~/printer_data/logs/ -name "*.log" -mtime +1 -delete 2>/dev/null || true
        find ~/printer_data/logs/ -name "*.gz" -delete 2>/dev/null || true
        journalctl --vacuum-time=1d 2>/dev/null || true
        type alert_push &>/dev/null && alert_push "disk_critical" "critical" "Disk usage ${usage}% on /"
    elif [ "$usage" -ge "$DISK_USAGE_WARN_THRESHOLD" ]; then
        logger -t health-monitor "Disk warning: ${usage}% used, cleaning old logs"
        find /var/log/ -name "*.log" -mtime +3 -delete 2>/dev/null || true
        find /var/log/ -name "*.gz" -mtime +7 -delete 2>/dev/null || true
        find ~/printer_data/logs/ -name "*.log" -mtime +3 -delete 2>/dev/null || true
        find ~/printer_data/logs/ -name "*.gz" -mtime +7 -delete 2>/dev/null || true
        journalctl --vacuum-time=3d 2>/dev/null || true
        type alert_push &>/dev/null && alert_push "disk_warning" "warning" "Disk usage ${usage}% on /"
    fi
    local after_usage=$(df / 2>/dev/null | tail -1 | awk '{print $5}' | tr -d '%')
    after_usage=${after_usage:-0}
    if [ "$after_usage" -ge "$DISK_USAGE_WARN_THRESHOLD" ] && [ "$usage" -ge "$DISK_USAGE_WARN_THRESHOLD" ]; then
        type alert_push &>/dev/null && alert_push "disk_cleanup_insufficient" "critical" "Disk cleanup insufficient: ${after_usage}% still above ${DISK_CLEANUP_TARGET}%"
    fi
    echo "$after_usage"
}

check_memory() {
    local mem_info=$(free -m 2>/dev/null | grep "Mem:")
    local total=$(echo "$mem_info" | awk '{print $2}')
    local used=$(echo "$mem_info" | awk '{print $3}')
    [ -z "$total" ] || [ "$total" -eq 0 ] && echo "0" && return
    local pct=$((used * 100 / total))
    if [ "$pct" -ge "$MEM_USAGE_WARN_THRESHOLD" ]; then
        logger -t health-monitor "Memory warning: ${pct}% used, restarting services"
        systemctl restart go2rtc 2>/dev/null || true
        sleep 10
        local after_info=$(free -m 2>/dev/null | grep "Mem:")
        local after_used=$(echo "$after_info" | awk '{print $3}')
        local after_pct=$((after_used * 100 / total))
        [ "$after_pct" -le "$MEM_RECOVERY_TARGET" ] && echo "$after_pct" && return
        systemctl restart moonraker 2>/dev/null || true
        sleep 10
        after_info=$(free -m 2>/dev/null | grep "Mem:")
        after_used=$(echo "$after_info" | awk '{print $3}')
        after_pct=$((after_used * 100 / total))
        [ "$after_pct" -le "$MEM_RECOVERY_TARGET" ] && echo "$after_pct" && return
        systemctl restart klipper 2>/dev/null || true
        sleep 10
        after_info=$(free -m 2>/dev/null | grep "Mem:")
        after_used=$(echo "$after_info" | awk '{print $3}')
        after_pct=$((after_used * 100 / total))
        if [ "$after_pct" -ge "$MEM_USAGE_WARN_THRESHOLD" ]; then
            type alert_push &>/dev/null && alert_push "memory_critical" "critical" "Memory ${after_pct}% after service restarts"
        fi
        echo "$after_pct"
    else
        echo "$pct"
    fi
}

check_temperature() {
    local temp_file="/sys/class/thermal/thermal_zone0/temp"
    if [ ! -f "$temp_file" ]; then echo "0"; return; fi
    local raw=$(cat "$temp_file" 2>/dev/null || echo "0")
    [ -z "$raw" ] && raw=0
    local temp=$((raw / 1000))
    if [ "$temp" -gt 0 ] && [ "$temp" -ge "$CPU_TEMP_CRITICAL_THRESHOLD" ]; then
        type alert_push &>/dev/null && alert_push "cpu_critical" "critical" "CPU temperature ${temp}C"
    elif [ "$temp" -gt 0 ] && [ "$temp" -ge "$CPU_TEMP_WARN_THRESHOLD" ]; then
        for gov in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
            [ -e "$gov" ] && echo powersave > "$gov" 2>/dev/null || true
        done
        type alert_push &>/dev/null && alert_push "cpu_overheat" "warning" "CPU temperature ${temp}C, set powersave"
    fi
    echo "$temp"
}

check_services() {
    local result=""
    local klippy_state=$(curl -s -m 3 http://localhost:7125/server/info 2>/dev/null | grep -oP '"klippy_state":"\K[^"]+' || echo "unknown")
    if [ "$klippy_state" != "ready" ]; then
        local klippy_fail=$(echo "$crash_counts" | grep -c "klipper" || echo 0)
        klippy_fail=$((klippy_fail + 1))
        if [ "$klippy_fail" -ge "$SERVICE_HTTP_FAILURE_THRESHOLD" ] && [ "$klippy_fail" -lt "$SERVICE_CRASH_LOOP_THRESHOLD" ]; then
            systemctl restart klipper 2>/dev/null || true
            type alert_push &>/dev/null && alert_push "klipper_unhealthy" "warning" "Klipper state=$klippy_state, restarted"
        fi
        crash_counts="${crash_counts}klipper "
    else
        result="\"klipper\":\"ready\","
    fi
    local moonraker_http=$(curl -s -o /dev/null -w "%{http_code}" -m 3 http://localhost:7125/server/info 2>/dev/null || echo "000")
    if [ "$moonraker_http" != "200" ]; then
        local moonraker_fail=$(echo "$crash_counts" | grep -c "moonraker" || echo 0)
        moonraker_fail=$((moonraker_fail + 1))
        if [ "$moonraker_fail" -ge "$SERVICE_HTTP_FAILURE_THRESHOLD" ] && [ "$moonraker_fail" -lt "$SERVICE_CRASH_LOOP_THRESHOLD" ]; then
            systemctl restart moonraker 2>/dev/null || true
            type alert_push &>/dev/null && alert_push "moonraker_unhealthy" "warning" "Moonraker HTTP=$moonraker_http, restarted"
        fi
        crash_counts="${crash_counts}moonraker "
    else
        result="${result}\"moonraker\":\"ok\","
    fi
    local go2rtc_http=$(curl -s -o /dev/null -w "%{http_code}" -m 3 http://localhost:1984/api/streams 2>/dev/null || echo "000")
    if [ "$go2rtc_http" != "200" ]; then
        local go2rtc_fail=$(echo "$crash_counts" | grep -c "go2rtc" || echo 0)
        go2rtc_fail=$((go2rtc_fail + 1))
        if [ "$go2rtc_fail" -ge "$SERVICE_HTTP_FAILURE_THRESHOLD" ] && [ "$go2rtc_fail" -lt "$SERVICE_CRASH_LOOP_THRESHOLD" ]; then
            systemctl restart go2rtc 2>/dev/null || true
            type alert_push &>/dev/null && alert_push "go2rtc_unhealthy" "warning" "go2rtc HTTP=$go2rtc_http, restarted"
        fi
        crash_counts="${crash_counts}go2rtc "
    else
        result="${result}\"go2rtc\":\"ok\","
    fi
    echo "$result"
}

setup_watchdog() {
    if [ -e /dev/watchdog ]; then
        if grep -q "^WatchdogSec=" /etc/systemd/system.conf 2>/dev/null; then
            sed -i 's/^WatchdogSec=.*/WatchdogSec=60/' /etc/systemd/system.conf 2>/dev/null || true
        elif grep -q "^#WatchdogSec=" /etc/systemd/system.conf 2>/dev/null; then
            sed -i 's/^#WatchdogSec=.*/WatchdogSec=60/' /etc/systemd/system.conf 2>/dev/null || true
        else
            echo "WatchdogSec=60" >> /etc/systemd/system.conf 2>/dev/null || true
        fi
        logger -t health-monitor "Hardware watchdog configured: WatchdogSec=60"
    fi
}

setup_ntp() {
    if command -v timedatectl &>/dev/null; then
        cat > /etc/systemd/timesyncd.conf << 'NTEOF'
[Time]
NTP=ntp.aliyun.com ntp.tencent.com
FallbackNTP=pool.ntp.org
NTEOF
        systemctl enable systemd-timesyncd 2>/dev/null || true
        systemctl start systemd-timesyncd 2>/dev/null || true
    fi
}

setup_logrotate() {
    cat > /etc/logrotate.d/n1-stability << 'LREOF'
/var/log/syslog
/var/log/kern.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
    create 0640 root adm
}

/root/printer_data/logs/*.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
    copytruncate
}

/var/log/n1-health-monitor.log
/var/log/n1-alert-queue.log {
    daily
    rotate 7
    missingok
    notifempty
    copytruncate
}
LREOF
}

write_health_status() {
    local disk_usage=$1
    local mem_usage=$2
    local cpu_temp=$3
    local services=$4
    local status="healthy"
    [ "$disk_usage" -ge "$DISK_USAGE_WARN_THRESHOLD" ] && status="degraded"
    [ "$mem_usage" -ge "$MEM_USAGE_WARN_THRESHOLD" ] && status="degraded"
    [ "$cpu_temp" -ge "$CPU_TEMP_WARN_THRESHOLD" ] && status="degraded"
    [ "$disk_usage" -ge "$DISK_USAGE_CRITICAL_THRESHOLD" ] && status="critical"
    [ "$cpu_temp" -ge "$CPU_TEMP_CRITICAL_THRESHOLD" ] && status="critical"
    local uptime_sec=$(cat /proc/uptime 2>/dev/null | awk '{print int($1)}')
    local mcu_count=$(ls /dev/serial/by-id/ 2>/dev/null | grep -c Klipper || echo 0)
    local link_status=$(ethtool "$IFACE" 2>/dev/null | grep "Link detected" | awk '{print $3}')
    local link_speed=$(ethtool "$IFACE" 2>/dev/null | grep "Speed:" | awk '{print $2}')
    local autosuspend=$(cat /sys/module/usbcore/parameters/autosuspend 2>/dev/null || echo "?")
    services=$(echo "$services" | sed 's/,$//')
    local timestamp=$(date -Iseconds 2>/dev/null || date '+%Y-%m-%dT%H:%M:%S%z')
    cat > "$HEALTH_STATUS_FILE" << EOFJSON
{"status":"$status","timestamp":"$timestamp","device_id":"$N1_IP","uptime_seconds":$uptime_sec,"network":{"interface":"$IFACE","link":"$link_status","speed":"$link_speed"},"mcu":{"detected":$mcu_count,"autosuspend":"$autosuspend"},"disk":{"usage_percent":$disk_usage},"memory":{"usage_percent":$mem_usage},"temperature":{"cpu_celsius":$cpu_temp},"services":{$services},"alerts":[]}
EOFJSON
}

logger -t health-monitor "Starting N1 health monitor (interval=${RESOURCE_CHECK_INTERVAL}s)"
setup_watchdog
setup_ntp
setup_logrotate

loop_count=0
while true; do
    sleep "$RESOURCE_CHECK_INTERVAL"
    loop_count=$((loop_count + 1))
    disk_usage=$(check_disk)
    mem_usage=$(check_memory)
    cpu_temp=$(check_temperature)
    services=$(check_services)
    write_health_status "$disk_usage" "$mem_usage" "$cpu_temp" "$services"
    if [ $((loop_count % 10)) -eq 0 ]; then
        type alert_retry_cached &>/dev/null && alert_retry_cached
    fi
    if [ $((loop_count % 20)) -eq 0 ]; then
        if ! timedatectl status 2>/dev/null | grep -q "NTP synchronized: yes"; then
            type alert_push &>/dev/null && alert_push "ntp_sync_failed" "warning" "NTP not synchronized"
        fi
    fi
    crash_counts=""
done
HEALTHEOF
chmod +x /usr/local/bin/n1-health-monitor.sh

cat > /etc/systemd/system/n1-health-monitor.service << 'EOF'
[Unit]
Description=N1 Health Monitor
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/n1-health-monitor.sh
Restart=always
RestartSec=15

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable n1-health-monitor
systemctl start n1-health-monitor
log_info "  n1-health-monitor.service 已启动"

# 10.5d: n1-health-api.py 健康状态HTTP API
log_info "部署 n1-health-api.py 健康状态HTTP API (端口8090)..."
cat > /usr/local/bin/n1-health-api.py << 'PYEOF'
#!/usr/bin/env python3
import json, os
from http.server import HTTPServer, BaseHTTPRequestHandler

HEALTH_STATUS_FILE = "/var/run/n1-health-status.json"
HEALTH_API_PORT = 8090
ALLOWED_PREFIX = "192.168.5."

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/api/health":
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "not found"}).encode())
            return
        client_ip = self.client_address[0]
        if not client_ip.startswith(ALLOWED_PREFIX) and client_ip != "127.0.0.1":
            self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "access denied"}).encode())
            return
        if not os.path.exists(HEALTH_STATUS_FILE):
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "unknown", "error": "health data not available"}).encode())
            return
        try:
            with open(HEALTH_STATUS_FILE, "r") as f:
                data = f.read().strip()
            json.loads(data)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data.encode())
        except (json.JSONDecodeError, IOError):
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "unknown", "error": "health data corrupt"}).encode())
    def log_message(self, format, *args):
        pass

if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", HEALTH_API_PORT), HealthHandler)
    server.serve_forever()
PYEOF
chmod +x /usr/local/bin/n1-health-api.py

cat > /etc/systemd/system/n1-health-api.service << 'EOF'
[Unit]
Description=N1 Health Status API (port 8090)
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/n1-health-api.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable n1-health-api
systemctl start n1-health-api
log_info "  n1-health-api.service 已启动 (端口8090)"

# 10.5e: n1-diagnose.sh 一键诊断
log_info "部署 n1-diagnose.sh 一键诊断..."
cat > /usr/local/bin/n1-diagnose.sh << 'DIAGEOF'
#!/bin/bash
DIAG_DIR="/tmp/n1-diag-$(date +%Y%m%d_%H%M%S)"
mkdir -p "$DIAG_DIR"

run() { echo "=== $1 ===" >> "$DIAG_DIR/diag.log"; eval "$1" >> "$DIAG_DIR/diag.log" 2>&1; }

run "uname -a"
run "uptime"
run "free -h"
run "df -h"
run "cat /proc/cpuinfo | head -5"
run "cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null"
run "ip addr show"
run "ip route show"
run "cat /etc/resolv.conf"
run "ping -c 3 192.168.5.1 2>&1"
run "ethtool eth0 2>/dev/null"
run "ls /dev/serial/by-id/ 2>/dev/null"
run "cat /sys/module/usbcore/parameters/autosuspend"
run "systemctl status klipper --no-pager 2>/dev/null; echo '==='; systemctl status moonraker --no-pager 2>/dev/null; echo '==='; systemctl status go2rtc --no-pager 2>/dev/null; echo '==='; systemctl status usb-watchdog --no-pager 2>/dev/null; echo '==='; systemctl status n1-health-monitor --no-pager 2>/dev/null; echo '==='; systemctl status link-monitor --no-pager 2>/dev/null; echo '==='; systemctl status n1-health-api --no-pager 2>/dev/null" > "$DIAG_DIR/services.txt"
run "curl -s http://localhost:7125/server/info 2>/dev/null"
run "dmesg | tail -50"
run "journalctl -u klipper --since '10 min ago' --no-pager 2>&1 | tail -20"
run "journalctl -u usb-watchdog --since '10 min ago' --no-pager 2>&1 | tail -20"
run "rfkill list 2>/dev/null"
run "lsmod | grep brcmfmac"

tar czf "/tmp/n1-diag-$(date +%Y%m%d_%H%M%S).tar.gz" -C /tmp "$(basename "$DIAG_DIR")" 2>/dev/null
echo "诊断完成: $DIAG_DIR"
echo "打包: /tmp/n1-diag-*.tar.gz"
DIAGEOF
chmod +x /usr/local/bin/n1-diagnose.sh
log_info "  n1-diagnose.sh 已部署"

log_info "工业级监控组件部署完成 (alert-push + link-monitor + health-monitor + health-api + diagnose)"

####################################################################################
# 11. 全服务验证
####################################################################################
log_step "Step 11/12: 全服务验证"

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
log_step "Step 12/12: 部署总结"

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
echo "  curl -s -o /dev/null http://$N1_IP:1984/api/frame.jpeg?src=${CAM_STREAM}   # 截图"
echo "  ssh root@$N1_IP   # SSH连通 (密码: 1234)"
echo ""
log_info "后端会自动发现此设备 (DEVICE_IP范围需包含 $N1_IP)"
echo ""
log_info "配置文件路径:"
echo "  printer.cfg:   $PRINTER_DATA/config/printer.cfg"
echo "  moonraker.conf: $PRINTER_DATA/config/moonraker.conf"
echo "  go2rtc.yaml:    /etc/go2rtc/go2rtc.yaml"
echo "  watchdog:       /usr/local/bin/usb-watchdog.sh (v5)"
echo "  bt脚本:         /usr/local/bin/bt-speaker-connect.sh"

# 自动注册到总控服务器
echo ""
log_info "尝试自动注册到总控服务器 ($SERVER_IP:8080)..."
REGISTER_HTTP=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 \
    "http://$SERVER_IP:8080/api/v1/token" 2>/dev/null || echo "000")
if [ "$REGISTER_HTTP" != "200" ]; then
    log_warn "总控服务器不可达 (HTTP $REGISTER_HTTP)，跳过自动注册"
    log_warn "请在总控前端手动添加设备: IP=$N1_IP"
else
    # 获取token
    TOKEN=$(curl -s --connect-timeout 5 "http://$SERVER_IP:8080/api/v1/token" 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || echo "")
    if [ -n "$TOKEN" ]; then
        # 注册设备
        REG_RESULT=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 \
            -X POST -H "Authorization: Bearer $TOKEN" \
            -H "Content-Type: application/json" \
            -d "{\"ip\":\"$N1_IP\",\"hostname\":\"$(hostname)\"}" \
            "http://$SERVER_IP:8080/api/v1/devices" 2>/dev/null || echo "000")
        if [ "$REG_RESULT" = "201" ]; then
            log_info "自动注册成功! (HTTP 201)"
        elif [ "$REG_RESULT" = "409" ]; then
            log_info "设备已注册 (HTTP 409，已存在)"
        else
            log_warn "自动注册失败 (HTTP $REG_RESULT)，请手动添加"
        fi
    else
        log_warn "获取token失败，请手动添加设备"
    fi
fi

# 保存部署信息
cat > /root/n1_deploy_info.txt << DEPLOYEOF
N1_IP=$N1_IP
SERVER_IP=$SERVER_IP
BT_MAC=${BT_MAC:-none}
MCU_SERIAL=$MCU_SERIAL
CAMERA=$CAM_DEV
CAM_STREAM=$CAM_STREAM
HOSTNAME=$(hostname)
DEPLOY_TIME=$(date '+%Y-%m-%d %H:%M:%S')
PASS=$PASS
FAIL=$FAIL
DEPLOYEOF
log_info "部署信息已保存到 /root/n1_deploy_info.txt"
