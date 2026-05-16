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

for svc in klipper moonraker go2rtc fluidd usb-watchdog wifi-watchdog; do
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
if [ ! -f "$PRINTER_DATA/fluidd/index.html" ]; then
    log_info "Fluidd前端不存在，自动下载..."
    mkdir -p "$PRINTER_DATA/fluidd"
    cd "$PRINTER_DATA/fluidd"
    if curl -sfL https://github.com/fluidd-core/fluidd/releases/latest/download/fluidd.zip -o fluidd.zip 2>/dev/null; then
        if command -v unzip &>/dev/null; then
            unzip -o fluidd.zip 2>/dev/null | tail -3
        else
            apt-get install -y -qq unzip 2>/dev/null || true
            unzip -o fluidd.zip 2>/dev/null | tail -3
        fi
        rm -f fluidd.zip
        log_info "Fluidd前端下载完成"
    else
        log_warn "Fluidd前端下载失败(无外网)，可手动下载后放到 $PRINTER_DATA/fluidd/"
    fi
    cd /
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
log_info "USB autosuspend=-1 (永久+运行时)"

cat > /etc/udev/rules.d/99-usb-no-autosuspend.rules << 'EOF'
ACTION=="add", SUBSYSTEM=="usb", ATTR{power/control}="on"
ACTION=="add", SUBSYSTEM=="tty", ATTRS{idVendor}=="1d50", ATTRS{idProduct}=="614e", SYMLINK+="klipper-mcu", GROUP="root", MODE="0666"
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
# 6. WiFi稳定性加固 (4层防线)
####################################################################################
log_step "Step 6/9: WiFi稳定性加固 (4层防线)"

# L1: WiFi省电模式关闭
NM_CONN=$(nmcli -t -f NAME,TYPE con show --active 2>/dev/null | grep -i wireless | head -1 | cut -d: -f1)
if [ -n "$NM_CONN" ]; then
    log_info "检测到WiFi连接: $NM_CONN"
    nmcli con modify "$NM_CONN" 802-11-wireless.powersave 2 2>/dev/null || true
    log_info "  L1: WiFi省电=2(适度)"

    WIFI_DEV=$(nmcli -t -f DEVICE,TYPE dev status 2>/dev/null | grep -i wifi | head -1 | cut -d: -f1)
    if [ -n "$WIFI_DEV" ]; then
        iw dev "$WIFI_DEV" set power_save off 2>/dev/null && log_info "  L1: $WIFI_DEV power_save=off" || true
    fi

    # L2: 自动重连加固
    nmcli con modify "$NM_CONN" connection.autoconnect-priority 10 2>/dev/null || true
    nmcli con modify "$NM_CONN" connection.autoconnect-retries 0 2>/dev/null || true
    log_info "  L2: 自动重连优先级=10, 无限重试"
else
    log_warn "未检测到WiFi连接(以太网设备?)"
fi

# L3: NM dispatcher脚本
mkdir -p /etc/NetworkManager/dispatcher.d
cat > /etc/NetworkManager/dispatcher.d/99-wifi-stability.sh << 'DISP'
#!/bin/bash
IFACE="$1"
ACTION="$2"
if [ "$ACTION" = "up" ]; then
    iw dev "$IFACE" set power_save off 2>/dev/null || true
    for usbdev in /sys/bus/usb/devices/*/power/control; do
        echo "on" > "$usbdev" 2>/dev/null || true
    done
fi
DISP
chmod +x /etc/NetworkManager/dispatcher.d/99-wifi-stability.sh 2>/dev/null || true
log_info "  L3: NM dispatcher (连接时关闭省电+确保USB活跃)"

# L4: wifi-watchdog服务
cat > /usr/local/bin/wifi-watchdog.sh << 'WDOG'
#!/bin/bash
CHECK_INTERVAL=30
FAIL_COUNT=0
MAX_FAILS=5
GATEWAY=$(ip route | grep default | awk '{print $3}' | head -1)

while true; do
    if ping -c 1 -W 2 "$GATEWAY" &>/dev/null; then
        FAIL_COUNT=0
    else
        FAIL_COUNT=$((FAIL_COUNT + 1))
        if [ $FAIL_COUNT -ge $MAX_FAILS ]; then
            logger -t wifi-watchdog "网关$GATEWAY不可达(${FAIL_COUNT}次), 重启WiFi"
            nmcli radio wifi off 2>/dev/null
            sleep 3
            nmcli radio wifi on 2>/dev/null
            FAIL_COUNT=0
        fi
    fi
    sleep $CHECK_INTERVAL
done
WDOG
chmod +x /usr/local/bin/wifi-watchdog.sh 2>/dev/null || true

cat > /etc/systemd/system/wifi-watchdog.service << 'EOF'
[Unit]
Description=WiFi Connectivity Watchdog
After=NetworkManager.service

[Service]
Type=simple
ExecStart=/usr/local/bin/wifi-watchdog.sh
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
EOF
log_info "  L4: wifi-watchdog (每30s检测, 5次失败重启WiFi)"

# USB watchdog
if [ ! -f /usr/local/bin/usb-watchdog.sh ]; then
    cat > /usr/local/bin/usb-watchdog.sh << 'USBW'
#!/bin/bash
EXPECTED_SERIAL=$(ls /dev/serial/by-id/ 2>/dev/null | grep -i klipper | head -1)
while true; do
    CURRENT=$(ls /dev/serial/by-id/ 2>/dev/null | grep -i klipper | head -1)
    if [ -z "$CURRENT" ] && [ -n "$EXPECTED_SERIAL" ]; then
        logger -t usb-watchdog "MCU串口丢失, 触发USB重扫描"
        for h in /sys/bus/usb/devices/*/authorized; do echo 0 > "$h" 2>/dev/null; sleep 1; echo 1 > "$h" 2>/dev/null; done
        sleep 5
    fi
    sleep 15
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

log_info "WiFi 4层防线 + USB watchdog 已部署"

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
for svc in fluidd usb-watchdog wifi-watchdog; do
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

# WiFi watchdog
WDOG=$(systemctl is-active wifi-watchdog 2>/dev/null || echo inactive)
if [ "$WDOG" = "active" ]; then
    log_info "wifi-watchdog: active ✓"
    PASS=$((PASS + 1))
else
    log_warn "wifi-watchdog: $WDOG"
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
