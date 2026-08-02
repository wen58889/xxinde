#!/bin/bash
####################################################################################
# N1 黄金镜像部署脚本 v3
# 保证新N1设备一次性稳定部署，正确对接总控服务器
#
# 改进(v3):
#   - 完整系统依赖安装 (libsodium, ffmpeg, gcc-arm, pkg-config, libusb等)
#   - go2rtc服务添加PATH环境变量(修复ffmpeg找不到的502问题)
#   - USB 8层稳定性加固
#   - WiFi 4层防线稳定性加固
#   - 固件编译+刷写 (flash_usb.py + BOOTSEL uf2双方法)
#   - MCU serial自动更新printer.cfg
#   - 全服务验证 (Moonraker/MCU/G28/摄像头/go2rtc)
#   - 可选注册到总控服务器
#
# 前置: n1_golden_image.tar.gz 在 /root/
# 用法: chmod +x n1_golden_deploy.sh && sudo ./n1_golden_deploy.sh
####################################################################################

set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step()  { echo -e "\n${CYAN}${BOLD}======== $1 ========${NC}"; }
log_ask()   { echo -e "${BOLD}${CYAN}$1${NC}"; }

ROOT_DIR=/root
PRINTER_DATA=$ROOT_DIR/printer_data
KLIPPER_DIR=$ROOT_DIR/klipper
KLIPPY_ENV=$ROOT_DIR/klippy-env
IMAGE_FILE=$ROOT_DIR/n1_golden_image.tar.gz

####################################################################################
# 0. 前置检查
####################################################################################
log_step "Step 0/9: 前置检查"

[ "$(id -u)" -ne 0 ] && log_error "请用 root 运行" && exit 1
[ ! -f "$IMAGE_FILE" ] && log_error "黄金镜像不存在: $IMAGE_FILE" && exit 1

ARCH=$(uname -m)
log_info "系统: $(cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d'"' -f2)"
log_info "内核: $(uname -r)  架构: $ARCH"
log_info "镜像: $(du -h $IMAGE_FILE | awk '{print $1}')"

####################################################################################
# 1. 安装系统依赖 (完整列表，确保一次性装好)
####################################################################################
log_step "Step 1/9: 安装系统依赖"

apt-get update -qq 2>/dev/null || true

DEPS="python3 python3-venv python3-dev python3-numpy python3-pip \
      git wget curl jq dbus avahi-daemon \
      gcc-arm-none-eabi libnewlib-arm-none-eabi \
      libsodium23 pkg-config libusb-1.0-0 libusb-1.0-dev \
      libffi-dev libssl-dev \
      ffmpeg v4l-utils \
      network-manager iw wireless-tools rfkill"

for pkg in $DEPS; do
    if ! dpkg -l "$pkg" &>/dev/null 2>&1; then
        log_info "安装 $pkg..."
        apt-get install -y -qq "$pkg" 2>/dev/null || true
    fi
done

log_info "关键依赖验证:"
CRITICAL_DEPS="libsodium23 libnewlib-arm-none-eabi gcc-arm-none-eabi pkg-config ffmpeg"
for pkg in $CRITICAL_DEPS; do
    if dpkg -l "$pkg" &>/dev/null 2>&1; then
        log_info "  $pkg: OK"
    else
        log_error "  $pkg: MISSING (可能影响功能)"
    fi
done

command -v ffmpeg &>/dev/null && log_info "  ffmpeg路径: $(which ffmpeg)" || log_error "  ffmpeg: 未找到!"

####################################################################################
# 2. 停止现有服务
####################################################################################
log_step "Step 2/9: 停止现有服务"

for svc in klipper moonraker go2rtc fluidd usb-watchdog; do
    systemctl stop "$svc" 2>/dev/null || true
done

####################################################################################
# 3. 解压黄金镜像
####################################################################################
log_step "Step 3/9: 解压黄金镜像"

cd /
tar xzf "$IMAGE_FILE"
log_info "解压完成"

if [ -f /tmp/n1_golden_meta.txt ]; then
    log_info "镜像信息:"
    cat /tmp/n1_golden_meta.txt | while IFS= read -r line; do
        log_info "  $line"
    done
fi

# Fluidd前端：如果目录不存在或为空，自动下载
FLUIDD_RETRY=0
FLUIDD_MAX_RETRY=3
FLUIDD_MIRRORS=(
    "https://ghfast.top/https://github.com/fluidd-core/fluidd/releases/latest/download/fluidd.zip"
    "https://gh-proxy.com/https://github.com/fluidd-core/fluidd/releases/latest/download/fluidd.zip"
    "https://github.com/fluidd-core/fluidd/releases/latest/download/fluidd.zip"
)
while [ ! -f "$PRINTER_DATA/fluidd/index.html" ] && [ "$FLUIDD_RETRY" -lt "$FLUIDD_MAX_RETRY" ]; do
    FLUIDD_RETRY=$((FLUIDD_RETRY + 1))
    if [ "$FLUIDD_RETRY" -gt 1 ]; then
        log_warn "Fluidd前端下载重试 $FLUIDD_RETRY/$FLUIDD_MAX_RETRY..."
        sleep 5
    fi
    log_info "Fluidd前端不存在，自动下载..."
    mkdir -p "$PRINTER_DATA/fluidd"
    DOWNLOADED=0
    for mirror in "${FLUIDD_MIRRORS[@]}"; do
        log_info "  尝试: ${mirror:0:50}..."
        if curl -sfL --connect-timeout 15 --max-time 60 "$mirror" -o /tmp/fluidd.zip 2>/dev/null && [ -s /tmp/fluidd.zip ]; then
            DOWNLOADED=1
            break
        fi
        rm -f /tmp/fluidd.zip
    done
    if [ "$DOWNLOADED" -eq 1 ]; then
        cd "$PRINTER_DATA/fluidd"
        if command -v unzip &>/dev/null; then
            unzip -o /tmp/fluidd.zip 2>/dev/null | tail -3
        else
            apt-get install -y -qq unzip 2>/dev/null || true
            unzip -o /tmp/fluidd.zip 2>/dev/null | tail -3
        fi
        rm -f /tmp/fluidd.zip
    else
        log_warn "Fluidd前端下载失败(第${FLUIDD_RETRY}次，所有镜像不可达)"
    fi
    cd /
done
if [ -f "$PRINTER_DATA/fluidd/index.html" ]; then
    log_info "Fluidd前端下载完成 (index.html 验证通过)"
else
    log_warn "Fluidd前端下载失败(重试${FLUIDD_MAX_RETRY}次)，可手动下载后放到 $PRINTER_DATA/fluidd/"
fi

# 修正fluidd-serve.sh路径（黄金镜像可能包含旧路径）
if [ -f /usr/local/bin/fluidd-serve.sh ]; then
    if ! grep -q "/root/printer_data/fluidd" /usr/local/bin/fluidd-serve.sh 2>/dev/null; then
        log_info "修正fluidd-serve.sh路径..."
        printf '#!/bin/bash\ncd /root/printer_data/fluidd\nexec python3 -m http.server 8080 --bind 0.0.0.0\n' > /usr/local/bin/fluidd-serve.sh
        chmod +x /usr/local/bin/fluidd-serve.sh
    fi
fi

####################################################################################
# 4. 修复go2rtc服务 — 添加PATH环境变量
#    根因: systemd默认PATH不含/usr/bin，go2rtc找不到ffmpeg导致502
####################################################################################
log_step "Step 4/9: 修复go2rtc服务PATH"

if [ -f /etc/systemd/system/go2rtc.service ]; then
    if ! grep -q "Environment=PATH" /etc/systemd/system/go2rtc.service 2>/dev/null; then
        sed -i '/^\[Service\]/a Environment=PATH=/usr/local/bin:/usr/bin:/bin' /etc/systemd/system/go2rtc.service
        log_info "go2rtc.service: 添加 Environment=PATH=/usr/local/bin:/usr/bin:/bin"
    else
        log_info "go2rtc.service: PATH已配置"
    fi
else
    log_warn "go2rtc.service不存在，创建新的..."
    cat > /etc/systemd/system/go2rtc.service << 'EOF'
[Unit]
Description=go2rtc camera service
After=network.target
Wants=network-online.target

[Service]
Type=simple
Environment=PATH=/usr/local/bin:/usr/bin:/bin
ExecStartPre=/bin/sleep 3
ExecStart=/usr/local/bin/go2rtc -config /etc/go2rtc/go2rtc.yaml
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
fi

####################################################################################
# 5. USB稳定性加固
####################################################################################
log_step "Step 5/9: USB稳定性加固"

cat > /etc/modprobe.d/usb-no-autosuspend.conf << 'EOF'
options usbcore autosuspend=-1
EOF
echo -1 > /sys/module/usbcore/parameters/autosuspend 2>/dev/null || true
AUTOSUSPEND_VAL=$(cat /sys/module/usbcore/parameters/autosuspend 2>/dev/null || echo "unknown")
if [ "$AUTOSUSPEND_VAL" != "-1" ]; then
    log_warn "autosuspend写入失败(当前=$AUTOSUSPEND_VAL), 尝试modprobe重载"
    modprobe -r usbcore 2>/dev/null || true
    modprobe usbcore autosuspend=-1 2>/dev/null || true
    AUTOSUSPEND_VAL=$(cat /sys/module/usbcore/parameters/autosuspend 2>/dev/null || echo "unknown")
fi
log_info "USB autosuspend=$AUTOSUSPEND_VAL (期望-1, 永久+运行时)"

cat > /etc/udev/rules.d/99-usb-no-autosuspend.rules << 'EOF'
ACTION=="add", SUBSYSTEM=="usb", ATTR{power/autosuspend}="-1"
ACTION=="add", SUBSYSTEM=="usb", TEST=="power/control", ATTR{power/control}="on"
ACTION=="add", SUBSYSTEM=="tty", ATTRS{idVendor}=="1d50", ATTRS{idProduct}=="614e", SYMLINK+="klipper-mcu", GROUP="root", MODE="0666"
ACTION=="add", SUBSYSTEM=="tty", ATTRS{idVendor}=="0483", ATTRS{idProduct}=="5740", SYMLINK+="klipper-mcu", GROUP="root", MODE="0666"
EOF
udevadm control --reload-rules 2>/dev/null || true
log_info "udev: USB永不挂起 + Klipper串口固定"

for d in /sys/bus/usb/devices/*/power/control; do
    echo on > "$d" 2>/dev/null || true
done
log_info "所有USB设备 power=on"

if ! grep -q "autosuspend" /boot/armbianEnv.txt 2>/dev/null; then
    echo "extraargs=usbcore.autosuspend=-1" >> /boot/armbianEnv.txt 2>/dev/null || true
fi
log_info "Armbian启动参数: autosuspend=-1"

cat > /etc/sysctl.d/99-n1-stability.conf << 'EOF'
vm.swappiness=1
vm.dirty_ratio=10
vm.dirty_background_ratio=5
EOF
sysctl -p /etc/sysctl.d/99-n1-stability.conf 2>/dev/null || true
log_info "sysctl: swappiness=1, dirty_ratio=10"

cat > /etc/apt/apt.conf.d/99force-ipv4 << 'EOF'
Acquire::ForceIPv4 "true";
EOF
log_info "apt强制IPv4"

####################################################################################
# 6. WiFi彻底禁用 (三层: rfkill+nmcli+黑名单) + USB watchdog
# 原因: brcmfmac WiFi驱动在6.18内核上固件bug导致中断风暴，
#       S905D SoC上WiFi(SDIO)和USB(XHCI)共享中断控制器，
#       中断风暴导致USB XHCI超时→MCU断连。产线全部使用有线。
####################################################################################
log_step "Step 6/9: WiFi彻底禁用 (三层: rfkill+nmcli+黑名单)"

# L1: rfkill block wlan (硬件级禁用)
rfkill block wlan 2>/dev/null || true
log_info "  L1: rfkill block wlan (硬件级禁用)"

# L2: nmcli radio wifi off (NetworkManager级禁用)
nmcli radio wifi off 2>/dev/null || true
log_info "  L2: nmcli radio wifi off (NM级禁用)"

# L3: brcmfmac黑名单 (驱动级禁用，阻止模块加载)
echo "blacklist brcmfmac" > /etc/modprobe.d/brcmfmac.conf
log_info "  L3: brcmfmac黑名单 (驱动级禁用，重启后不加载)"

# rfkill持久化service
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
log_info "  WiFi服务已清理"

# net-check.service (纯有线版)
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
log_info "  net-check.service 已启用 (纯有线版)"

# USB watchdog (v5工业级: 通用MCU匹配 + 冷却防抖 + 告警通知 + XHCI预防 + Klipper双重验证)
if [ ! -f /usr/local/bin/usb-watchdog.sh ]; then
    cat > /usr/local/bin/usb-watchdog.sh << 'USBW'
#!/bin/bash
source /usr/local/bin/alert-push.sh 2>/dev/null || true

MCU_ID="usb-Klipper"
CHECK_INTERVAL=5
MAX_FAIL=3
FAIL_COUNT=0
RECOVERY_LEVEL=0
MAX_RECOVERY_LEVEL=5
COOLDOWN=300
LAST_RECOVERY=0
XHCI_FAIL_COUNT=0
XHCI_REBOOT_THRESHOLD=6
MCU_DOWN_SINCE=0
log() { logger -t usb-watchdog "$1"; }
check_xhci_error() { dmesg | tail -30 | grep -qiE 'HC died|xHCI host controller not responding'; }
check_xhci_timeout() { dmesg | tail -30 | grep -qiE 'Timeout while waiting for setup device|unable to enumerate USB device|device descriptor read.*error -1[12]0|device not accepting address.*error -62'; }

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
        [ "$state" = "ready" ] && return 0
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
        sleep 1; reboot
    fi
    if check_xhci_timeout; then
        XHCI_FAIL_COUNT=$((XHCI_FAIL_COUNT + 1))
        log "XHCI timeout detected (count=$XHCI_FAIL_COUNT/$XHCI_REBOOT_THRESHOLD)"
        if [ $XHCI_FAIL_COUNT -ge $XHCI_REBOOT_THRESHOLD ]; then
            log "XHCI timeout threshold reached, rebooting"
            type alert_push &>/dev/null && alert_push "xhci_timeout" "critical" "XHCI timeout threshold reached, rebooting"
            sleep 1; reboot
        fi
    else
        [ $XHCI_FAIL_COUNT -gt 0 ] && XHCI_FAIL_COUNT=$((XHCI_FAIL_COUNT - 1))
    fi
    if ls /dev/serial/by-id/ 2>/dev/null | grep -q "$MCU_ID"; then
        if [ $FAIL_COUNT -gt 0 ]; then
            local down_duration=0
            [ $MCU_DOWN_SINCE -gt 0 ] && down_duration=$(( $(date +%s) - MCU_DOWN_SINCE ))
            log "MCU recovered (was down ${down_duration}s)"
            type alert_resolved &>/dev/null && alert_resolved "mcu_disconnected" "$down_duration"
            FAIL_COUNT=0; RECOVERY_LEVEL=0; MCU_DOWN_SINCE=0
        fi
        continue
    fi
    FAIL_COUNT=$((FAIL_COUNT + 1))
    if [ $MCU_DOWN_SINCE -eq 0 ]; then
        MCU_DOWN_SINCE=$(date +%s)
        type alert_push &>/dev/null && alert_push "mcu_disconnected" "critical" "MCU not detected, starting recovery"
    fi
    log "MCU not detected! fail=$FAIL_COUNT level=$RECOVERY_LEVEL"
    if [ $FAIL_COUNT -ge $MAX_FAIL ]; then
        NOW=$(date +%s); ELAPSED=$((NOW - LAST_RECOVERY))
        if [ $ELAPSED -lt $COOLDOWN ]; then
            log "Cooldown active (${ELAPSED}s/${COOLDOWN}s), skip recovery"
            FAIL_COUNT=0; continue
        fi
        if [ $RECOVERY_LEVEL -ge $MAX_RECOVERY_LEVEL ]; then
            log "Max recovery level reached, stop trying until MCU reappears"
            type alert_push &>/dev/null && alert_push "mcu_recovery_exhausted" "critical" "All recovery levels exhausted, MCU still disconnected"
            FAIL_COUNT=0; sleep 60; continue
        fi
        RECOVERY_LEVEL=$((RECOVERY_LEVEL + 1)); LAST_RECOVERY=$NOW
        if [ $RECOVERY_LEVEL -eq 1 ]; then
            log "Recovery L1: firmware_restart"
            curl -s -X POST http://127.0.0.1:7125/printer/firmware_restart 2>/dev/null; sleep 5
        elif [ $RECOVERY_LEVEL -eq 2 ]; then
            log "Recovery L2: restart klipper"
            systemctl restart klipper 2>/dev/null; sleep 8
        elif [ $RECOVERY_LEVEL -eq 3 ]; then
            log "Recovery L3: USB port authorized reset (skip hub)"
            for port in /sys/bus/usb/devices/*/authorized; do
                devpath=$(dirname "$port"); devnum=$(cat "$devpath/devnum" 2>/dev/null || echo "0")
                [ "$devnum" = "1" ] && continue
                echo 0 > "$port" 2>/dev/null; sleep 1; echo 1 > "$port" 2>/dev/null
            done
            sleep 5; systemctl restart klipper 2>/dev/null; sleep 5
        elif [ $RECOVERY_LEVEL -eq 4 ]; then
            log "Recovery L4: xhci_hcd preventive unbind/rebind + service restart"
            xhci_preventive_reset
            systemctl restart klipper moonraker 2>/dev/null; sleep 8
        else
            log "Recovery L5: full reboot"
            type alert_push &>/dev/null && alert_push "mcu_reboot" "critical" "MCU recovery L5: full reboot"
            sleep 2; reboot
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
USBW
    chmod +x /usr/local/bin/usb-watchdog.sh 2>/dev/null || true
fi

if [ ! -f /etc/systemd/system/usb-watchdog.service ]; then
    cat > /etc/systemd/system/usb-watchdog.service << 'EOF'
[Unit]
Description=USB Serial Watchdog
After=systemd-udev-settle.service

[Service]
Type=simple
ExecStart=/usr/local/bin/usb-watchdog.sh
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
EOF
fi

log_info "WiFi三层禁用 + USB watchdog 已部署"

####################################################################################
# 7. 固件编译 + 刷写
####################################################################################
log_step "Step 7/9: 固件编译 & 刷写"

FIRMWARE_UF2=""
for fw in "$KLIPPER_DIR/out/klipper.uf2" "$KLIPPER_DIR/out/klipper.elf.uf2"; do
    if [ -f "$fw" ]; then
        FIRMWARE_UF2="$fw"
        log_info "预编译固件: $FIRMWARE_UF2 ($(wc -c < "$FIRMWARE_UF2") bytes)"
        break
    fi
done

if [ -z "$FIRMWARE_UF2" ]; then
    log_info "无预编译固件，开始编译..."
    cd "$KLIPPER_DIR"

    if [ ! -f .config ]; then
        log_error "Klipper .config 不存在! 无法编译固件"
        log_error "黄金镜像打包时需包含 .config 文件"
    else
        log_info "编译Klipper固件 (可能需要1-3分钟)..."
        make clean 2>/dev/null || true
        make olddefconfig 2>&1 | tail -3 || true
        make -j4 2>&1 | tail -10

        for fw in out/klipper.uf2 out/klipper.elf.uf2; do
            if [ -f "$fw" ]; then
                FIRMWARE_UF2="$KLIPPER_DIR/$fw"
                log_info "固件编译成功: $FIRMWARE_UF2"
                break
            fi
        done

        if [ -z "$FIRMWARE_UF2" ]; then
            log_error "固件编译失败! 检查: gcc-arm-none-eabi, libnewlib-arm-none-eabi"
        fi
    fi
    cd /
fi

# 检测MCU
MCU_SERIAL=""
log_info "等待RP2040设备..."
for i in $(seq 1 10); do
    DETECTED=$(ls /dev/serial/by-id/ 2>/dev/null | grep -i klipper | head -1)
    if [ -n "$DETECTED" ]; then
        MCU_SERIAL="/dev/serial/by-id/$DETECTED"
        log_info "检测到MCU: $MCU_SERIAL"
        break
    fi
    sleep 2
done

# 固件刷写
FLASH_DONE="no"
if [ -n "$FIRMWARE_UF2" ] && [ -n "$MCU_SERIAL" ]; then
    log_ask "是否刷写固件到RP2040? [Y/n]:"
    read -r FLASH_YN
    FLASH_YN=${FLASH_YN:-Y}
    if [ "$FLASH_YN" = "Y" ] || [ "$FLASH_YN" = "y" ]; then
        log_info "方法1: flash_usb.py (通过serial进入bootloader)..."
        systemctl stop klipper 2>/dev/null || true
        systemctl stop moonraker 2>/dev/null || true
        sleep 2

        cd "$KLIPPER_DIR"
        if [ -f out/klipper.elf ] && python3 scripts/flash_usb.py -t rp2 -d "$MCU_SERIAL" out/klipper.elf 2>&1; then
            log_info "flash_usb.py 刷写成功!"
            FLASH_DONE="yes"
        else
            log_warn "flash_usb.py失败，尝试方法2: BOOTSEL + uf2复制..."

            # flash_usb.py发送1200baud会进入bootloader, RP2040作为USB存储设备出现
            for part in /dev/sda1 /dev/sdb1 /dev/sdc1; do
                if [ -b "$part" ]; then
                    FS_TYPE=$(blkid -o value -s TYPE "$part" 2>/dev/null)
                    if [ "$FS_TYPE" = "vfat" ] || [ "$FS_TYPE" = "FAT16" ]; then
                        SIZE=$(blockdev --getsize64 "$part" 2>/dev/null || echo 0)
                        if [ "$SIZE" -lt 200000000 ] 2>/dev/null; then
                            mkdir -p /mnt/rp2040
                            if mount "$part" /mnt/rp2040 2>/dev/null; then
                                if ls /mnt/rp2040/INFO_UF2.TXT &>/dev/null; then
                                    log_info "检测到RP2040 BOOT设备: $part"
                                    cp "$FIRMWARE_UF2" /mnt/rp2040/
                                    sync
                                    sleep 2
                                    umount /mnt/rp2040 2>/dev/null || true
                                    log_info "uf2已复制! RP2040将自动重启"
                                    FLASH_DONE="yes"
                                    break
                                fi
                                umount /mnt/rp2040 2>/dev/null || true
                            fi
                        fi
                    fi
                fi
            done

            if [ "$FLASH_DONE" = "no" ]; then
                log_warn "未自动检测到RP2040 BOOT设备"
                log_warn "请按住RP2040 BOOTSEL按钮, 然后插USB线"
                log_ask "准备好后按回车继续..."
                read -r

                for part in /dev/sda1 /dev/sdb1 /dev/sdc1; do
                    if [ -b "$part" ]; then
                        mkdir -p /mnt/rp2040
                        if mount "$part" /mnt/rp2040 2>/dev/null; then
                            if ls /mnt/rp2040/INFO_UF2.TXT &>/dev/null; then
                                cp "$FIRMWARE_UF2" /mnt/rp2040/
                                sync; sleep 2
                                umount /mnt/rp2040 2>/dev/null || true
                                log_info "固件已刷写!"
                                FLASH_DONE="yes"
                                break
                            fi
                            umount /mnt/rp2040 2>/dev/null || true
                        fi
                    fi
                done
            fi
        fi
        cd /
    fi
fi

if [ "$FLASH_DONE" = "yes" ]; then
    log_info "等待RP2040重启(15秒)..."
    sleep 15
fi

# 再次检测MCU并更新printer.cfg
log_info "检测MCU串口..."
MCU_SERIAL=""
for i in $(seq 1 10); do
    DETECTED=$(ls /dev/serial/by-id/ 2>/dev/null | grep -i klipper | head -1)
    if [ -n "$DETECTED" ]; then
        MCU_SERIAL="/dev/serial/by-id/$DETECTED"
        log_info "MCU串口: $MCU_SERIAL"
        break
    fi
    if [ "$i" = "10" ]; then
        log_warn "未检测到MCU，请确认固件已刷写"
    fi
    sleep 2
done

if [ -n "$MCU_SERIAL" ] && [ -f "$PRINTER_DATA/config/printer.cfg" ]; then
    CURRENT_SERIAL=$(grep '^serial:' "$PRINTER_DATA/config/printer.cfg" 2>/dev/null | awk '{print $2}')
    if [ "$CURRENT_SERIAL" != "$MCU_SERIAL" ]; then
        log_info "更新 printer.cfg serial: $CURRENT_SERIAL → $MCU_SERIAL"
        sed -i "s|^serial: .*|serial: $MCU_SERIAL|" "$PRINTER_DATA/config/printer.cfg"
    fi
fi

####################################################################################
# 8. 启动所有服务
####################################################################################
log_step "Step 8/9: 启动服务"

mkdir -p "$PRINTER_DATA/config" "$PRINTER_DATA/logs" "$PRINTER_DATA/gcodes"

systemctl daemon-reload

# go2rtc需要先启动(摄像头)
for svc in go2rtc klipper moonraker; do
    if [ -f "/etc/systemd/system/$svc.service" ]; then
        systemctl enable "$svc" 2>/dev/null || true
        systemctl restart "$svc" 2>/dev/null || true
        sleep 3
        STATUS=$(systemctl is-active "$svc" 2>/dev/null || echo "unknown")
        log_info "  $svc: $STATUS"
    else
        log_warn "  $svc: 服务文件不存在"
    fi
done

# 可选服务
for svc in fluidd usb-watchdog; do
    if [ -f "/etc/systemd/system/$svc.service" ]; then
        systemctl enable "$svc" 2>/dev/null || true
        systemctl restart "$svc" 2>/dev/null || true
        STATUS=$(systemctl is-active "$svc" 2>/dev/null || echo "unknown")
        log_info "  $svc: $STATUS"
    fi
done

# fix-mac服务(如果存在)
if [ -f /etc/systemd/system/fix-mac.service ]; then
    systemctl enable fix-mac 2>/dev/null || true
    systemctl start fix-mac 2>/dev/null || true
    log_info "  fix-mac: $(systemctl is-active fix-mac 2>/dev/null || echo unknown)"
fi

# 修复Fluidd WebSocket周期性断连: 增大ping_interval (10s→30s)
if [ -f /root/moonraker/moonraker/components/application.py ]; then
    if grep -q "websocket_ping_interval.*else 10\." /root/moonraker/moonraker/components/application.py 2>/dev/null; then
        sed -i "s/'websocket_ping_interval': None if tornado_ver < (6, 5) else 10\./'websocket_ping_interval': None if tornado_ver < (6, 5) else 30./" /root/moonraker/moonraker/components/application.py
        log_info "  Fluidd WebSocket ping_interval已修复 (10s→30s)"
    fi
fi

####################################################################################
# 8.5 工业级监控组件部署
####################################################################################
log_step "Step 8.5/9: 工业级监控组件部署"

# alert-push.sh 告警推送函数库
log_info "部署 alert-push.sh..."
cat > /usr/local/bin/alert-push.sh << 'ALERTEOF'
#!/bin/bash
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
    local alert_type="$1"; local alert_level="${2:-info}"; local message="$3"
    [ -z "$alert_type" ] && return 1
    _alert_get_config; mkdir -p "$ALERT_DEDUP_DIR" 2>/dev/null || true
    local dedup_file="${ALERT_DEDUP_DIR}/${alert_type}.ts"; local now=$(date +%s)
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
    local json=$(printf '{"device_id":"%s","alert_type":"%s","alert_level":"%s","timestamp":"%s","details":"%s"}' "$N1_IP" "$alert_type" "$alert_level" "$timestamp" "$message")
    local http_code=$(curl -s -m 5 --connect-timeout 3 -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: application/json" -d "$json" "$ALERT_PUSH_URL" 2>/dev/null || echo "000")
    if [ "$http_code" = "200" ] || [ "$http_code" = "201" ] || [ "$http_code" = "204" ]; then
        echo "{\"count\":1,\"last_pushed\":$now,\"first_timestamp\":$now}" > "$dedup_file"
        logger -t alert-push "Pushed: $alert_type level=$alert_level"; return 0
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
    local alert_type="$1"; local duration="${2:-0}"
    [ -z "$alert_type" ] && return 1; _alert_get_config
    rm -f "${ALERT_DEDUP_DIR}/${alert_type}.ts" 2>/dev/null || true
    local timestamp=$(date -Iseconds 2>/dev/null || date '+%Y-%m-%dT%H:%M:%S%z')
    local json=$(printf '{"device_id":"%s","alert_type":"%s_resolved","alert_level":"info","timestamp":"%s","duration_seconds":%s}' "$N1_IP" "$alert_type" "$timestamp" "$duration")
    local http_code=$(curl -s -m 5 --connect-timeout 3 -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: application/json" -d "$json" "$ALERT_PUSH_URL" 2>/dev/null || echo "000")
    if [ "$http_code" = "200" ] || [ "$http_code" = "201" ] || [ "$http_code" = "204" ]; then
        logger -t alert-push "Resolved: $alert_type duration=${duration}s"; return 0
    else
        echo "$json" >> "$ALERT_QUEUE_FILE" 2>/dev/null || true; return 1
    fi
}
alert_retry_cached() {
    [ -f "$ALERT_QUEUE_FILE" ] || return 0; _alert_get_config
    local remaining="" retried=0 succeeded=0
    while IFS= read -r line; do
        [ -z "$line" ] && continue
        local http_code=$(curl -s -m 5 --connect-timeout 3 -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: application/json" -d "$line" "$ALERT_PUSH_URL" 2>/dev/null || echo "000")
        if [ "$http_code" = "200" ] || [ "$http_code" = "201" ] || [ "$http_code" = "204" ]; then succeeded=$((succeeded + 1))
        else remaining="${remaining}${line}"$'\n'; retried=$((retried + 1)); fi
    done < "$ALERT_QUEUE_FILE"
    [ -n "$remaining" ] && printf '%s' "$remaining" > "$ALERT_QUEUE_FILE" || rm -f "$ALERT_QUEUE_FILE"
    [ "$succeeded" -gt 0 ] || [ "$retried" -gt 0 ] && logger -t alert-push "Retry cached: succeeded=$succeeded remaining=$retried"
    return 0
}
ALERTEOF
chmod +x /usr/local/bin/alert-push.sh
log_info "  alert-push.sh 已部署"

# link-monitor.sh
log_info "部署 link-monitor.service..."
cat > /usr/local/bin/link-monitor.sh << 'LINKEOF'
#!/bin/bash
source /usr/local/bin/alert-push.sh 2>/dev/null || true
LINK_CHECK_INTERVAL=5; LINK_RECONNECT_MAX_RETRIES=3; LINK_RECONNECT_INTERVAL=5
LINK_ERROR_THRESHOLD=100; LINK_FLAPPING_THRESHOLD=3; LINK_FLAPPING_WINDOW=30
NETWORK_DOWN_NOTIFY_THRESHOLD=10; STATIC_ARP_CHECK_INTERVAL=60
IFACE=$(cat /etc/n1-fixed-iface 2>/dev/null || echo "eth0")
[ -e "/sys/class/net/$IFACE" ] || IFACE="eth0"
GATEWAY_IP="192.168.5.1"
SERVER_IP=$(grep '^SERVER_IP=' /etc/n1_network_info.txt 2>/dev/null | cut -d= -f2)
SERVER_IP=${SERVER_IP:-192.168.5.8}
link_down_since=0; flap_times=""; last_arp_check=0
prev_rx_errors=0; prev_tx_errors=0; prev_rx_drops=0; prev_tx_drops=0
get_link_status() { ethtool "$IFACE" 2>/dev/null | grep "Link detected" | awk '{print $3}'; }
get_error_stats() {
    local stats=$(ip -s link show "$IFACE" 2>/dev/null)
    rx_errors=$(echo "$stats" | grep -A1 "RX:" | tail -1 | awk '{print $2}')
    tx_errors=$(echo "$stats" | grep -A1 "TX:" | tail -1 | awk '{print $2}')
    rx_drops=$(echo "$stats" | grep -A1 "RX:" | tail -1 | awk '{print $3}')
    tx_drops=$(echo "$stats" | grep -A1 "TX:" | tail -1 | awk '{print $3}')
    rx_errors=${rx_errors:-0}; tx_errors=${tx_errors:-0}; rx_drops=${rx_drops:-0}; tx_drops=${tx_drops:-0}
}
setup_static_arp() {
    local gmac=$(ip neigh show "$GATEWAY_IP" 2>/dev/null | grep -oP 'lladdr \K[0-9a-f:]+' | head -1)
    local smac=$(ip neigh show "$SERVER_IP" 2>/dev/null | grep -oP 'lladdr \K[0-9a-f:]+' | head -1)
    [ -n "$gmac" ] && { ip neigh del "$GATEWAY_IP" dev "$IFACE" 2>/dev/null || true
        ip neigh add "$GATEWAY_IP" lladdr "$gmac" dev "$IFACE" nud perm 2>/dev/null || ip neigh change "$GATEWAY_IP" lladdr "$gmac" dev "$IFACE" nud perm 2>/dev/null || true; }
    [ -n "$smac" ] && [ "$SERVER_IP" != "$GATEWAY_IP" ] && { ip neigh del "$SERVER_IP" dev "$IFACE" 2>/dev/null || true
        ip neigh add "$SERVER_IP" lladdr "$smac" dev "$IFACE" nud perm 2>/dev/null || ip neigh change "$SERVER_IP" lladdr "$smac" dev "$IFACE" nud perm 2>/dev/null || true; }
}
try_reconnect() {
    local retries=0; local con_name=$(nmcli -t -f NAME,DEVICE con show --active 2>/dev/null | grep "$IFACE" | head -1 | cut -d: -f1)
    while [ "$retries" -lt "$LINK_RECONNECT_MAX_RETRIES" ]; do
        logger -t link-monitor "Reconnect attempt $((retries+1))/$LINK_RECONNECT_MAX_RETRIES"
        if [ -n "$con_name" ]; then nmcli con up "$con_name" 2>/dev/null && return 0
        else ip link set dev "$IFACE" up 2>/dev/null || true; sleep 3; get_link_status | grep -q "yes" && return 0; fi
        retries=$((retries + 1)); sleep "$LINK_RECONNECT_INTERVAL"
    done; return 1
}
notify_network_down() { type alert_push &>/dev/null && alert_push "network_down" "critical" "Network link down on $IFACE for ${1}s"; }
notify_network_up() { type alert_push &>/dev/null && alert_resolved "network_down" "$1"; logger -t link-monitor "Network up after ${1}s downtime"; }
check_flapping() {
    local now=$(date +%s); flap_times="${flap_times}${now} "; local recent=""
    for t in $flap_times; do local elapsed=$((now - t)); [ "$elapsed" -le "$LINK_FLAPPING_WINDOW" ] && recent="${recent}${t} "; done
    flap_times="$recent"; local count=$(echo $flap_times | wc -w)
    if [ "$count" -ge "$LINK_FLAPPING_THRESHOLD" ]; then
        logger -t link-monitor "Link flapping detected ($count changes in ${LINK_FLAPPING_WINDOW}s)"
        type alert_push &>/dev/null && alert_push "link_flapping" "warning" "Link flapping on $IFACE: $count changes in ${LINK_FLAPPING_WINDOW}s"
        flap_times=""; return 0
    fi; return 1
}
logger -t link-monitor "Starting link monitor for $IFACE (interval=${LINK_CHECK_INTERVAL}s)"
get_error_stats; prev_rx_errors=$rx_errors; prev_tx_errors=$tx_errors; prev_rx_drops=$rx_drops; prev_tx_drops=$tx_drops
while true; do
    sleep "$LINK_CHECK_INTERVAL"; local link_status=$(get_link_status); local now=$(date +%s)
    if [ "$link_status" = "yes" ]; then
        if [ "$link_down_since" -gt 0 ]; then
            local downtime=$((now - link_down_since)); check_flapping; notify_network_up "$downtime"; link_down_since=0
            logger -t link-monitor "Link recovered after ${downtime}s"
        fi
        get_error_stats; local rx_delta=$((rx_errors - prev_rx_errors)); local tx_delta=$((tx_errors - prev_tx_errors))
        local rd_delta=$((rx_drops - prev_rx_drops)); local td_delta=$((tx_drops - prev_tx_drops)); local total_delta=$((rx_delta + tx_delta + rd_delta + td_delta))
        if [ "$total_delta" -gt "$LINK_ERROR_THRESHOLD" ]; then
            logger -t link-monitor "High error rate: +$total_delta errors in ${LINK_CHECK_INTERVAL}s"
            type alert_push &>/dev/null && alert_push "link_errors" "warning" "High error rate on $IFACE: +$total_delta errors"
        fi
        prev_rx_errors=$rx_errors; prev_tx_errors=$tx_errors; prev_rx_drops=$rx_drops; prev_tx_drops=$tx_drops
        if [ $((now - last_arp_check)) -ge "$STATIC_ARP_CHECK_INTERVAL" ]; then setup_static_arp; last_arp_check=$now; fi
    else
        if [ "$link_down_since" -eq 0 ]; then link_down_since=$now; logger -t link-monitor "Link down detected on $IFACE"; check_flapping; fi
        local downtime=$((now - link_down_since))
        if [ "$downtime" -ge "$NETWORK_DOWN_NOTIFY_THRESHOLD" ] && [ $((downtime % NETWORK_DOWN_NOTIFY_THRESHOLD)) -eq 0 ]; then notify_network_down "$downtime"; fi
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
systemctl daemon-reload; systemctl enable link-monitor 2>/dev/null || true; systemctl start link-monitor 2>/dev/null || true
log_info "  link-monitor.service 已启动"

# n1-health-monitor.sh + n1-health-api.py
log_info "部署 n1-health-monitor + n1-health-api..."
cat > /usr/local/bin/n1-health-monitor.sh << 'HEOF'
#!/bin/bash
source /usr/local/bin/alert-push.sh 2>/dev/null || true
RESOURCE_CHECK_INTERVAL=30; DISK_USAGE_WARN_THRESHOLD=90; DISK_USAGE_CRITICAL_THRESHOLD=95
DISK_CLEANUP_TARGET=85; MEM_USAGE_WARN_THRESHOLD=80; MEM_RECOVERY_TARGET=70
CPU_TEMP_WARN_THRESHOLD=80; CPU_TEMP_CRITICAL_THRESHOLD=90
SERVICE_HTTP_FAILURE_THRESHOLD=3; SERVICE_CRASH_LOOP_THRESHOLD=3
HEALTH_STATUS_FILE="/var/run/n1-health-status.json"
IFACE=$(cat /etc/n1-fixed-iface 2>/dev/null || echo "eth0")
[ -e "/sys/class/net/$IFACE" ] || IFACE="eth0"
N1_IP=$(grep '^N1_IP=' /etc/n1_network_info.txt 2>/dev/null | cut -d= -f2)
N1_IP=${N1_IP:-$(hostname -I 2>/dev/null | awk '{print $1}')}
crash_counts=""
check_disk() {
    local usage=$(df / 2>/dev/null | tail -1 | awk '{print $5}' | tr -d '%'); usage=${usage:-0}
    if [ "$usage" -ge "$DISK_USAGE_CRITICAL_THRESHOLD" ]; then
        find /var/log/ -name "*.log" -mtime +1 -delete 2>/dev/null || true; find /var/log/ -name "*.gz" -delete 2>/dev/null || true
        find ~/printer_data/logs/ -name "*.log" -mtime +1 -delete 2>/dev/null || true; journalctl --vacuum-time=1d 2>/dev/null || true
        type alert_push &>/dev/null && alert_push "disk_critical" "critical" "Disk usage ${usage}%"
    elif [ "$usage" -ge "$DISK_USAGE_WARN_THRESHOLD" ]; then
        find /var/log/ -name "*.log" -mtime +3 -delete 2>/dev/null || true; journalctl --vacuum-time=3d 2>/dev/null || true
        type alert_push &>/dev/null && alert_push "disk_warning" "warning" "Disk usage ${usage}%"
    fi
    local after=$(df / 2>/dev/null | tail -1 | awk '{print $5}' | tr -d '%'); after=${after:-0}
    if [ "$after" -ge "$DISK_USAGE_WARN_THRESHOLD" ] && [ "$usage" -ge "$DISK_USAGE_WARN_THRESHOLD" ]; then
        type alert_push &>/dev/null && alert_push "disk_cleanup_insufficient" "critical" "Disk cleanup insufficient: ${after}%"
    fi; echo "$after"
}
check_memory() {
    local mem_info=$(free -m 2>/dev/null | grep "Mem:"); local total=$(echo "$mem_info" | awk '{print $2}'); local used=$(echo "$mem_info" | awk '{print $3}')
    [ -z "$total" ] || [ "$total" -eq 0 ] && echo "0" && return; local pct=$((used * 100 / total))
    if [ "$pct" -ge "$MEM_USAGE_WARN_THRESHOLD" ]; then
        systemctl restart go2rtc 2>/dev/null || true; sleep 10
        local after=$(free -m 2>/dev/null | grep "Mem:" | awk '{print $3}'); local ap=$((after * 100 / total))
        [ "$ap" -le "$MEM_RECOVERY_TARGET" ] && echo "$ap" && return
        systemctl restart moonraker 2>/dev/null || true; sleep 10
        after=$(free -m 2>/dev/null | grep "Mem:" | awk '{print $3}'); ap=$((after * 100 / total))
        [ "$ap" -le "$MEM_RECOVERY_TARGET" ] && echo "$ap" && return
        systemctl restart klipper 2>/dev/null || true; sleep 10
        after=$(free -m 2>/dev/null | grep "Mem:" | awk '{print $3}'); ap=$((after * 100 / total))
        [ "$ap" -ge "$MEM_USAGE_WARN_THRESHOLD" ] && type alert_push &>/dev/null && alert_push "memory_critical" "critical" "Memory ${ap}%"
        echo "$ap"
    else echo "$pct"; fi
}
check_temperature() {
    local tf="/sys/class/thermal/thermal_zone0/temp"
    [ ! -f "$tf" ] && echo "0" && return; local raw=$(cat "$tf" 2>/dev/null || echo "0"); [ -z "$raw" ] && raw=0
    local temp=$((raw / 1000))
    if [ "$temp" -gt 0 ] && [ "$temp" -ge "$CPU_TEMP_CRITICAL_THRESHOLD" ]; then
        type alert_push &>/dev/null && alert_push "cpu_critical" "critical" "CPU ${temp}C"
    elif [ "$temp" -gt 0 ] && [ "$temp" -ge "$CPU_TEMP_WARN_THRESHOLD" ]; then
        for gov in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do [ -e "$gov" ] && echo powersave > "$gov" 2>/dev/null || true; done
        type alert_push &>/dev/null && alert_push "cpu_overheat" "warning" "CPU ${temp}C"
    fi; echo "$temp"
}
check_services() {
    local result=""
    local ks=$(curl -s -m 3 http://localhost:7125/server/info 2>/dev/null | grep -oP '"klippy_state":"\K[^"]+' || echo "unknown")
    if [ "$ks" != "ready" ]; then
        local kf=$(echo "$crash_counts" | grep -c "klipper" || echo 0); kf=$((kf + 1))
        if [ "$kf" -ge "$SERVICE_HTTP_FAILURE_THRESHOLD" ] && [ "$kf" -lt "$SERVICE_CRASH_LOOP_THRESHOLD" ]; then
            systemctl restart klipper 2>/dev/null || true; type alert_push &>/dev/null && alert_push "klipper_unhealthy" "warning" "Klipper state=$ks"
        fi; crash_counts="${crash_counts}klipper "
    else result="\"klipper\":\"ready\","; fi
    local mh=$(curl -s -o /dev/null -w "%{http_code}" -m 3 http://localhost:7125/server/info 2>/dev/null || echo "000")
    if [ "$mh" != "200" ]; then
        local mf=$(echo "$crash_counts" | grep -c "moonraker" || echo 0); mf=$((mf + 1))
        if [ "$mf" -ge "$SERVICE_HTTP_FAILURE_THRESHOLD" ] && [ "$mf" -lt "$SERVICE_CRASH_LOOP_THRESHOLD" ]; then
            systemctl restart moonraker 2>/dev/null || true; type alert_push &>/dev/null && alert_push "moonraker_unhealthy" "warning" "Moonraker HTTP=$mh"
        fi; crash_counts="${crash_counts}moonraker "
    else result="${result}\"moonraker\":\"ok\","; fi
    local gh=$(curl -s -o /dev/null -w "%{http_code}" -m 3 http://localhost:1984/api/streams 2>/dev/null || echo "000")
    if [ "$gh" != "200" ]; then
        local gf=$(echo "$crash_counts" | grep -c "go2rtc" || echo 0); gf=$((gf + 1))
        if [ "$gf" -ge "$SERVICE_HTTP_FAILURE_THRESHOLD" ] && [ "$gf" -lt "$SERVICE_CRASH_LOOP_THRESHOLD" ]; then
            systemctl restart go2rtc 2>/dev/null || true; type alert_push &>/dev/null && alert_push "go2rtc_unhealthy" "warning" "go2rtc HTTP=$gh"
        fi; crash_counts="${crash_counts}go2rtc "
    else result="${result}\"go2rtc\":\"ok\","; fi
    echo "$result"
}
setup_watchdog() {
    [ -e /dev/watchdog ] || return
    if grep -q "^WatchdogSec=" /etc/systemd/system.conf 2>/dev/null; then sed -i 's/^WatchdogSec=.*/WatchdogSec=60/' /etc/systemd/system.conf 2>/dev/null || true
    elif grep -q "^#WatchdogSec=" /etc/systemd/system.conf 2>/dev/null; then sed -i 's/^#WatchdogSec=.*/WatchdogSec=60/' /etc/systemd/system.conf 2>/dev/null || true
    else echo "WatchdogSec=60" >> /etc/systemd/system.conf 2>/dev/null || true; fi
}
setup_ntp() {
    command -v timedatectl &>/dev/null || return
    cat > /etc/systemd/timesyncd.conf << 'NTEOF'
[Time]
NTP=ntp.aliyun.com ntp.tencent.com
FallbackNTP=pool.ntp.org
NTEOF
    systemctl enable systemd-timesyncd 2>/dev/null || true; systemctl start systemd-timesyncd 2>/dev/null || true
}
setup_logrotate() {
    cat > /etc/logrotate.d/n1-stability << 'LREOF'
/var/log/syslog /var/log/kern.log { daily; rotate 7; compress; missingok; notifempty; create 0640 root adm; }
/root/printer_data/logs/*.log { daily; rotate 7; compress; missingok; notifempty; copytruncate; }
/var/log/n1-health-monitor.log /var/log/n1-alert-queue.log { daily; rotate 7; missingok; notifempty; copytruncate; }
LREOF
}
write_health_status() {
    local du=$1 mu=$2 ct=$3 sv=$4; local st="healthy"
    [ "$du" -ge "$DISK_USAGE_WARN_THRESHOLD" ] && st="degraded"; [ "$mu" -ge "$MEM_USAGE_WARN_THRESHOLD" ] && st="degraded"
    [ "$ct" -ge "$CPU_TEMP_WARN_THRESHOLD" ] && st="degraded"; [ "$du" -ge "$DISK_USAGE_CRITICAL_THRESHOLD" ] && st="critical"
    [ "$ct" -ge "$CPU_TEMP_CRITICAL_THRESHOLD" ] && st="critical"
    local up=$(cat /proc/uptime 2>/dev/null | awk '{print int($1)}'); local mc=$(ls /dev/serial/by-id/ 2>/dev/null | grep -c Klipper || echo 0)
    local ls=$(ethtool "$IFACE" 2>/dev/null | grep "Link detected" | awk '{print $3}')
    local lsp=$(ethtool "$IFACE" 2>/dev/null | grep "Speed:" | awk '{print $2}')
    local as=$(cat /sys/module/usbcore/parameters/autosuspend 2>/dev/null || echo "?")
    sv=$(echo "$sv" | sed 's/,$//'); local ts=$(date -Iseconds 2>/dev/null || date '+%Y-%m-%dT%H:%M:%S%z')
    cat > "$HEALTH_STATUS_FILE" << EOFJ
{"status":"$st","timestamp":"$ts","device_id":"$N1_IP","uptime_seconds":$up,"network":{"interface":"$IFACE","link":"$ls","speed":"$lsp"},"mcu":{"detected":$mc,"autosuspend":"$as"},"disk":{"usage_percent":$du},"memory":{"usage_percent":$mu},"temperature":{"cpu_celsius":$ct},"services":{$sv},"alerts":[]}
EOFJ
}
logger -t health-monitor "Starting N1 health monitor (interval=${RESOURCE_CHECK_INTERVAL}s)"
setup_watchdog; setup_ntp; setup_logrotate
loop_count=0
while true; do
    sleep "$RESOURCE_CHECK_INTERVAL"; loop_count=$((loop_count + 1))
    disk_usage=$(check_disk); mem_usage=$(check_memory); cpu_temp=$(check_temperature); services=$(check_services)
    write_health_status "$disk_usage" "$mem_usage" "$cpu_temp" "$services"
    [ $((loop_count % 10)) -eq 0 ] && { type alert_retry_cached &>/dev/null && alert_retry_cached; }
    [ $((loop_count % 20)) -eq 0 ] && { ! timedatectl status 2>/dev/null | grep -q "NTP synchronized: yes" && type alert_push &>/dev/null && alert_push "ntp_sync_failed" "warning" "NTP not synchronized"; }
    crash_counts=""
done
HEOF
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
systemctl daemon-reload; systemctl enable n1-health-monitor 2>/dev/null || true; systemctl start n1-health-monitor 2>/dev/null || true
log_info "  n1-health-monitor.service 已启动"

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
            self.send_response(404); self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(json.dumps({"error": "not found"}).encode()); return
        client_ip = self.client_address[0]
        if not client_ip.startswith(ALLOWED_PREFIX) and client_ip != "127.0.0.1":
            self.send_response(403); self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(json.dumps({"error": "access denied"}).encode()); return
        if not os.path.exists(HEALTH_STATUS_FILE):
            self.send_response(503); self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(json.dumps({"status": "unknown", "error": "health data not available"}).encode()); return
        try:
            with open(HEALTH_STATUS_FILE, "r") as f: data = f.read().strip()
            json.loads(data); self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-cache"); self.end_headers(); self.wfile.write(data.encode())
        except (json.JSONDecodeError, IOError):
            self.send_response(503); self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(json.dumps({"status": "unknown", "error": "health data corrupt"}).encode())
    def log_message(self, format, *args): pass
if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", HEALTH_API_PORT), HealthHandler); server.serve_forever()
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
systemctl daemon-reload; systemctl enable n1-health-api 2>/dev/null || true; systemctl start n1-health-api 2>/dev/null || true
log_info "  n1-health-api.service 已启动 (端口8090)"

# n1-diagnose.sh
cat > /usr/local/bin/n1-diagnose.sh << 'DEOF'
#!/bin/bash
DIAG_DIR="/tmp/n1-diag-$(date +%Y%m%d_%H%M%S)"; mkdir -p "$DIAG_DIR"
run() { echo "=== $1 ===" >> "$DIAG_DIR/diag.log"; eval "$1" >> "$DIAG_DIR/diag.log" 2>&1; }
run "uname -a"; run "uptime"; run "free -h"; run "df -h"
run "cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null"
run "ip addr show"; run "ip route show"; run "ethtool eth0 2>/dev/null"
run "ls /dev/serial/by-id/ 2>/dev/null"; run "cat /sys/module/usbcore/parameters/autosuspend"
run "systemctl status klipper moonraker go2rtc usb-watchdog n1-health-monitor link-monitor n1-health-api --no-pager 2>/dev/null" > "$DIAG_DIR/services.txt"
run "curl -s http://localhost:7125/server/info 2>/dev/null"
run "dmesg | tail -50"; run "rfkill list 2>/dev/null"; run "lsmod | grep brcmfmac"
tar czf "/tmp/n1-diag-$(date +%Y%m%d_%H%M%S).tar.gz" -C /tmp "$(basename "$DIAG_DIR")" 2>/dev/null
echo "诊断完成: $DIAG_DIR"
DEOF
chmod +x /usr/local/bin/n1-diagnose.sh

log_info "工业级监控组件部署完成"

####################################################################################
# 9. 验证 + 可选注册总控
####################################################################################
log_step "Step 9/9: 验证部署"

PASS=0
FAIL=0
STATE=""

# Moonraker + MCU
log_info "等待Moonraker/Klipper就绪..."
for i in $(seq 1 20); do
    STATE=$(curl -sf --connect-timeout 2 --max-time 3 "http://localhost:7125/server/info" 2>/dev/null | jq -r '.result.klippy_state' 2>/dev/null || echo "")
    if [ "$STATE" = "ready" ]; then
        log_info "MCU: ready ✓"
        PASS=$((PASS + 1))
        break
    elif [ -n "$STATE" ]; then
        log_info "MCU: $STATE (等待 $i/20)"
    else
        log_info "Moonraker未响应 ($i/20)"
    fi
    sleep 3
done

[ "$STATE" != "ready" ] && log_warn "MCU未就绪" && FAIL=$((FAIL + 1))

# go2rtc + 摄像头
CAM_STREAMS=$(curl -sf --connect-timeout 2 --max-time 3 "http://localhost:1984/api/streams" 2>/dev/null | jq -r 'keys[]' 2>/dev/null | head -1)
if [ -n "$CAM_STREAMS" ]; then
    log_info "摄像头流: $CAM_STREAMS ✓"
    PASS=$((PASS + 1))

    # 抓图测试
    SNAP_HTTP=$(curl -sf --max-time 10 "http://localhost:1984/api/frame.jpeg?src=$CAM_STREAMS" -o /dev/null -w '%{http_code}' 2>/dev/null || echo "000")
    if [ "$SNAP_HTTP" = "200" ]; then
        log_info "抓图测试: OK ✓"
        PASS=$((PASS + 1))
    else
        log_warn "抓图测试: FAIL (HTTP=$SNAP_HTTP)"
        FAIL=$((FAIL + 1))
    fi
else
    log_warn "摄像头: 未检测到流"
    FAIL=$((FAIL + 1))
fi

# G28测试
if [ "$STATE" = "ready" ]; then
    log_info "G28测试..."
    G28_HTTP=$(curl -sf --connect-timeout 5 --max-time 30 \
        -H "Content-Type: application/json" -d '{"script":"G28"}' \
        http://localhost:7125/printer/gcode/script \
        -o /dev/null -w '%{http_code}' 2>/dev/null || echo "000")
    sleep 5
    G28_STATE=$(curl -sf --connect-timeout 2 --max-time 3 "http://localhost:7125/server/info" 2>/dev/null | jq -r '.result.klippy_state' 2>/dev/null || echo "unknown")
    if [ "$G28_HTTP" = "200" ] && [ "$G28_STATE" = "ready" ]; then
        log_info "G28: OK ✓"
        PASS=$((PASS + 1))
    else
        log_warn "G28: FAIL (HTTP=$G28_HTTP, MCU=$G28_STATE)"
        FAIL=$((FAIL + 1))
    fi
fi

# WiFi禁用验证
RFKILL=$(rfkill list 2>/dev/null | grep -A2 "wlan" | grep "Soft blocked" | awk '{print $3}')
NM_WIFI=$(nmcli radio wifi 2>/dev/null || echo "unknown")
if [ "$RFKILL" = "yes" ] && [ "$NM_WIFI" = "disabled" ]; then
    log_info "WiFi禁用: rfkill=blocked, nmcli=disabled ✓"
    PASS=$((PASS + 1))
else
    log_warn "WiFi禁用: rfkill=$RFKILL, nmcli=$NM_WIFI"
    FAIL=$((FAIL + 1))
fi

# 部署总结
MY_IP=$(hostname -I | awk '{print $1}')

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║              N1 部署完成!                                ║${NC}"
echo -e "${BOLD}╠══════════════════════════════════════════════════════════╣${NC}"
echo -e "${BOLD}║  本机IP:       $MY_IP                                  ║${NC}"
echo -e "${BOLD}║  MCU串口:      ${MCU_SERIAL:-未检测}           ║${NC}"
echo -e "${BOLD}║  验证通过:     $PASS 项                                ║${NC}"
echo -e "${BOLD}║  需要处理:     $FAIL 项                                ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""

log_info "访问地址:"
echo "  Moonraker: http://$MY_IP:7125"
echo "  Fluidd:    http://$MY_IP:8080"
echo "  摄像头:    http://$MY_IP:1984"
echo ""

# 可选: 注册到总控服务器
log_ask "是否注册到总控服务器? [y/N]:"
read -r REG_YN
if [ "$REG_YN" = "y" ] || [ "$REG_YN" = "Y" ]; then
    log_ask "总控服务器IP [默认: 192.168.5.8]:"
    read -r SERVER_IP
    SERVER_IP=${SERVER_IP:-192.168.5.8}

    log_info "尝试注册到 $SERVER_IP:8080..."
    REGISTER_HTTP=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 \
        "http://$SERVER_IP:8080/api/v1/token" 2>/dev/null || echo "000")
    if [ "$REGISTER_HTTP" != "200" ]; then
        log_warn "总控服务器不可达 (HTTP $REGISTER_HTTP)"
        log_warn "请在总控前端手动添加设备: IP=$MY_IP"
    else
        TOKEN=$(curl -s --connect-timeout 5 "http://$SERVER_IP:8080/api/v1/token" 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || echo "")
        if [ -n "$TOKEN" ]; then
            REG_RESULT=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 \
                -X POST -H "Authorization: Bearer $TOKEN" \
                -H "Content-Type: application/json" \
                -d "{\"ip\":\"$MY_IP\",\"hostname\":\"$(hostname)\"}" \
                "http://$SERVER_IP:8080/api/v1/devices" 2>/dev/null || echo "000")
            if [ "$REG_RESULT" = "201" ]; then
                log_info "注册成功! (HTTP 201)"
            elif [ "$REG_RESULT" = "409" ]; then
                log_info "设备已注册 (HTTP 409)"
            else
                log_warn "注册失败 (HTTP $REG_RESULT)，请手动添加"
            fi
        else
            log_warn "获取token失败，请手动添加"
        fi
    fi
fi

echo ""
log_info "配置文件:"
echo "  printer.cfg:   $PRINTER_DATA/config/printer.cfg"
echo "  moonraker.conf: $PRINTER_DATA/config/moonraker.conf"
echo "  go2rtc.yaml:    /etc/go2rtc/go2rtc.yaml"

# 保存部署信息
cat > /root/n1_deploy_info.txt << DEPLOYEOF
deploy_version=3
deploy_time=$(date '+%Y-%m-%d %H:%M:%S')
hostname=$(hostname)
ip=$MY_IP
mcu_serial=$MCU_SERIAL
pass=$PASS
fail=$FAIL
DEPLOYEOF
log_info "部署信息: /root/n1_deploy_info.txt"

if [ $FAIL -gt 0 ]; then
    echo ""
    log_warn "有 $FAIL 项未通过，排查方法:"
    echo "  1. MCU串口: ls /dev/serial/by-id/"
    echo "  2. 固件刷写: cd ~/klipper && make flash"
    echo "  3. 服务日志: journalctl -u klipper -n 30; journalctl -u go2rtc -n 30"
    echo "  4. 摄像头:   ls /dev/video*; ffmpeg -f v4l2 -i /dev/video1 -frames:v 1 -f image2 -"
fi
