#!/bin/bash
####################################################################################
# N1 黄金镜像打包脚本 v3
# 保证新N1设备一次性稳定部署，正确对接总控服务器
# 
# 改进(v3):
#   - 包含预编译固件 + .config + go2rtc二进制 + ffmpeg
#   - 包含Fluidd前端 + 所有systemd服务 + WiFi/USB稳定性配置
#   - 记录完整系统依赖列表 + 版本信息
#   - 保留Klipper/Moonraker源码+python venv
#
# 用法: 在正常运行设备(101)上执行: bash n1_golden_pack.sh
# 输出: /root/n1_golden_image.tar.gz
####################################################################################

set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step()  { echo -e "\n${CYAN}${BOLD}======== $1 ========${NC}"; }

ROOT_DIR=/root
PRINTER_DATA=$ROOT_DIR/printer_data
KLIPPER_DIR=$ROOT_DIR/klipper
KLIPPY_ENV=$ROOT_DIR/klippy-env
MOONRAKER_DIR=$ROOT_DIR/moonraker
MOONRAKER_ENV=$ROOT_DIR/moonraker-env
OUTPUT_FILE=$ROOT_DIR/n1_golden_image.tar.gz

log_step "N1 黄金镜像打包 v3"

####################################################################################
# 1. 检测版本信息
####################################################################################
log_info "检测版本信息..."
KLIPPER_VER=$(cd "$KLIPPER_DIR" && git log --oneline -1 2>/dev/null | awk '{print $1}' || echo "unknown")
MOONRAKER_VER=$(cd "$MOONRAKER_DIR" && git log --oneline -1 2>/dev/null | awk '{print $1}' || echo "unknown")
log_info "Klipper commit: $KLIPPER_VER"
log_info "Moonraker commit: $MOONRAKER_VER"

####################################################################################
# 2. 固件检查/编译
####################################################################################
FIRMWARE_FILE=""
HAS_FIRMWARE="no"

for fw in "$KLIPPER_DIR/out/klipper.uf2" "$KLIPPER_DIR/out/klipper.elf.uf2"; do
    if [ -f "$fw" ]; then
        FIRMWARE_FILE="$fw"
        HAS_FIRMWARE="yes"
        log_info "预编译固件: $FIRMWARE_FILE ($(wc -c < "$FIRMWARE_FILE") bytes)"
        break
    fi
done

if [ -z "$FIRMWARE_FILE" ]; then
    log_warn "预编译固件不存在，尝试编译..."
    if command -v arm-none-eabi-gcc &>/dev/null; then
        log_info "编译Klipper固件 (RP2040)..."
        cd "$KLIPPER_DIR"
        if [ ! -f .config ]; then
            log_error "无.config! 无法编译，需先在Klipper上执行 make menuconfig"
        else
            make olddefconfig 2>&1 | tail -3 || true
            make -j4 2>&1 | tail -5 || log_warn "编译失败"
            for fw in out/klipper.uf2 out/klipper.elf.uf2; do
                if [ -f "$fw" ]; then
                    FIRMWARE_FILE="$KLIPPER_DIR/$fw"
                    HAS_FIRMWARE="yes"
                    log_info "固件编译成功: $fw"
                    break
                fi
            done
        fi
        cd /
    else
        log_warn "缺少arm-none-eabi-gcc，无法编译固件"
    fi
fi

if [ -f "$KLIPPER_DIR/.config" ]; then
    log_info "Klipper .config: OK ($(wc -c < "$KLIPPER_DIR/.config") bytes)"
else
    log_error "Klipper .config 不存在! 新设备将无法编译固件"
fi

####################################################################################
# 3. 关键文件完整性检查
####################################################################################
log_step "关键文件检查"

CRITICAL_FILES=(
    "$PRINTER_DATA/config/printer.cfg"
    "$PRINTER_DATA/config/moonraker.conf"
    /etc/go2rtc/go2rtc.yaml
    /usr/local/bin/go2rtc
)
MISSING_COUNT=0
for f in "${CRITICAL_FILES[@]}"; do
    if [ -f "$f" ]; then
        log_info "  OK: $f"
    else
        log_error "  MISSING: $f"
        MISSING_COUNT=$((MISSING_COUNT + 1))
    fi
done

if [ $MISSING_COUNT -gt 0 ]; then
    log_error "有 $MISSING_COUNT 个关键文件缺失! 打包可能不完整"
    log_ask "是否继续? [y/N]:"
    read -r CONTINUE
    [ "$CONTINUE" != "y" ] && [ "$CONTINUE" != "Y" ] && exit 1
fi

####################################################################################
# 4. 记录元数据
####################################################################################
SYSTEM_DEPS="libsodium23 libnewlib-arm-none-eabi gcc-arm-none-eabi pkg-config libusb-1.0-0 ffmpeg jq network-manager iw wireless-tools rfkill curl v4l-utils"

cat > /tmp/n1_golden_meta.txt << META
N1 Golden Image Metadata
=======================
pack_version: 3
pack_time: $(date '+%Y-%m-%d %H:%M:%S')
pack_host: $(hostname)
klipper_commit: $KLIPPER_VER
moonraker_commit: $MOONRAKER_VER
has_firmware: $HAS_FIRMWARE
firmware_file: $FIRMWARE_FILE
kernel: $(uname -r)
arch: $(uname -m)
required_system_deps: $SYSTEM_DEPS
go2rtc_binary: /usr/local/bin/go2rtc
ffmpeg_required: yes
go2rtc_needs_path: yes
META

log_info "元数据已生成"

####################################################################################
# 5. 打包
####################################################################################
log_step "打包文件"

PACK_LIST=""

# 核心目录
for item in \
    "$KLIPPER_DIR" \
    "$KLIPPY_ENV" \
    "$MOONRAKER_DIR" \
    "$MOONRAKER_ENV" \
    "$PRINTER_DATA/config" \
    "$PRINTER_DATA/fluidd" \
; do
    if [ -d "$item" ]; then
        log_info "  + $item"
        PACK_LIST="$PACK_LIST $item"
    else
        log_warn "  - $item (不存在，跳过)"
    fi
done

# 配置文件 + 二进制 + 服务 + 稳定性配置
for item in \
    /etc/go2rtc/go2rtc.yaml \
    /usr/local/bin/go2rtc \
    /usr/local/bin/fluidd-serve.sh \
    /usr/local/bin/usb-watchdog.sh \
    /usr/local/bin/wifi-watchdog.sh \
    /usr/local/bin/fix-mac.sh \
    /etc/systemd/system/klipper.service \
    /etc/systemd/system/moonraker.service \
    /etc/systemd/system/go2rtc.service \
    /etc/systemd/system/fluidd.service \
    /etc/systemd/system/usb-watchdog.service \
    /etc/systemd/system/wifi-watchdog.service \
    /etc/systemd/system/fix-mac.service \
    /etc/modprobe.d/usb-no-autosuspend.conf \
    /etc/udev/rules.d/99-usb-no-autosuspend.rules \
    /etc/sysctl.d/99-n1-stability.conf \
    /etc/apt/apt.conf.d/99force-ipv4 \
    /etc/NetworkManager/dispatcher.d/99-wifi-stability.sh \
    /etc/n1-fixed-mac \
; do
    if [ -f "$item" ]; then
        log_info "  + $item"
        PACK_LIST="$PACK_LIST $item"
    fi
done

PACK_LIST="$PACK_LIST /tmp/n1_golden_meta.txt"

####################################################################################
# 6. 创建压缩包
####################################################################################
log_step "创建压缩包"

tar czf "$OUTPUT_FILE" \
    --exclude='*.pyc' \
    --exclude='__pycache__' \
    --exclude='*.log' \
    --exclude='.git/objects/pack' \
    --exclude='klipper/out/*.elf' \
    --exclude='klipper/out/*.bin' \
    --exclude='klipper/out/*.map' \
    --exclude='klipper/out/*.o' \
    --exclude='klipper/out/src/' \
    --exclude='klipper/out/lib/' \
    --exclude='klipper/out/board-generic/' \
    --exclude='gcodes/*' \
    --exclude='printer_data/logs/*' \
    $PACK_LIST 2>/dev/null

FILESIZE=$(du -h "$OUTPUT_FILE" | awk '{print $1}')
log_info "打包完成: $OUTPUT_FILE ($FILESIZE)"

####################################################################################
# 7. 使用说明
####################################################################################
echo ""
log_step "部署新N1设备步骤"
echo ""
log_info "1. 传文件到新设备:"
echo "     scp $OUTPUT_FILE root@新IP:/root/"
echo "     scp n1_golden_deploy.sh root@新IP:/root/"
echo ""
log_info "2. SSH到新设备执行部署:"
echo "     ssh root@新IP"
echo "     chmod +x /root/n1_golden_deploy.sh"
echo "     sudo /root/n1_golden_deploy.sh"
echo ""
log_info "3. 部署脚本将自动完成:"
echo "     - 安装所有系统依赖 (libsodium, ffmpeg, gcc-arm等)"
echo "     - 解压黄金镜像"
echo "     - USB + WiFi 4层防线稳定性加固"
echo "     - 编译/刷写RP2040固件"
echo "     - 启动所有服务 (go2rtc/klipper/moonraker/fluidd/watchdog)"
echo "     - 验证 Moonraker/MCU/G28/摄像头"
echo "     - 可选: 注册到总控服务器"
