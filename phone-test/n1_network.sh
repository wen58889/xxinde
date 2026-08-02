#!/bin/bash
####################################################################################
# N1 网络配置脚本 — 纯有线架构 + WiFi彻底禁用
#
# !! 重要：此脚本只写入配置文件，不立即切换网络，避免SSH断开 !!
# !! 运行完成后需要重启N1才生效，重启后用新IP重新SSH连接 !!
#
# 核心变更：WiFi彻底禁用(三层: rfkill+nmcli+黑名单)
# 原因：brcmfmac WiFi驱动在6.18内核上固件bug导致中断风暴，
#       因S905D SoC上WiFi(SDIO)和USB(XHCI)共享中断控制器，
#       中断风暴导致USB XHCI超时→MCU断连。
#       有线网络从未出过问题，产线全部使用有线。
#
# 用法: sudo ./n1_network.sh
# 步骤: 1) 运行此脚本  2) 重启N1  3) 用新IP的SSH继续运行 n1_deploy.sh
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
log_ask()   { echo -e "${BOLD}${CYAN}$1${NC}"; }

if [ "$(id -u)" -ne 0 ]; then
    log_error "请用 root 运行: sudo ./n1_network.sh"
    exit 1
fi

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║   N1 网络配置脚本 — 纯有线 + WiFi禁用 + 固定IP + MAC      ║${NC}"
echo -e "${BOLD}║   ⚠️  配置写入后需重启才生效，不会立即断开SSH              ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

####################################################################################
# 1. 检测所有网络接口
####################################################################################
echo "=== 当前网络信息 ==="

WIRED_IFACES=()
for iface in /sys/class/net/*; do
    name=$(basename "$iface")
    [ "$name" = "lo" ] && continue
    if [ -e "$iface/device" ] && ! ethtool "$name" 2>/dev/null | grep -q "Link detected: no"; then
        if [ ! -e "$iface/wireless" ] && [ ! -d "$iface/phy80211" ]; then
            WIRED_IFACES+=("$name")
        fi
    fi
done

WIFI_IFACES=()
for iface in /sys/class/net/*; do
    name=$(basename "$iface")
    [ -e "$iface/wireless" ] || [ -d "$iface/phy80211" ] && WIFI_IFACES+=("$name")
done

CURRENT_IP=$(ip -4 addr show | grep -oP '192\.168\.5\.\d+' | head -1)
CURRENT_IFACE=$(ip -4 addr show | grep -B2 "$CURRENT_IP" | head -1 | awk '{print $2}' | tr -d ':')
if [ -z "$CURRENT_IFACE" ]; then
    CURRENT_IFACE=$(ip route | grep default | awk '{print $5}' | head -1)
fi
CURRENT_MAC=$(cat /sys/class/net/${CURRENT_IFACE}/address 2>/dev/null || echo "unknown")
CURRENT_HOSTNAME=$(hostname)

echo "  当前IP:       $CURRENT_IP"
echo "  当前接口:     $CURRENT_IFACE"
echo "  当前MAC:      $CURRENT_MAC"
echo "  有线接口:     ${WIRED_IFACES[*]:-无}"
echo "  WiFi接口:     ${WIFI_IFACES[*]:-无}"
echo "  当前hostname: $CURRENT_HOSTNAME"
echo ""

####################################################################################
# 2. 交互输入
####################################################################################

# 2.1 选择网络模式 (默认有线，WiFi仅开发调试)
log_ask "请选择网络模式:"
echo "  1) 有线网络 (产线推荐，最稳定)"
echo "  3) 有线+WiFi双网 (仅开发调试，不推荐产线使用)"
log_ask "请输入选择 [1/3, 默认1]:"
read -r NET_MODE
NET_MODE=${NET_MODE:-1}

SELECTED_IFACE=""
case $NET_MODE in
    1)
        NET_MODE_DESC="有线"
        if [ ${#WIRED_IFACES[@]} -eq 0 ]; then
            log_error "未检测到有线网卡接口"
            log_ask "是否继续使用当前接口? [y/N]:"
            read -r CONT
            [ "$CONT" = "y" ] || [ "$CONT" = "Y" ] || exit 1
            SELECTED_IFACE="$CURRENT_IFACE"
        elif [ ${#WIRED_IFACES[@]} -eq 1 ]; then
            SELECTED_IFACE="${WIRED_IFACES[0]}"
            log_info "自动选择有线接口: $SELECTED_IFACE"
        else
            log_ask "检测到多个有线接口，请选择:"
            for i in "${!WIRED_IFACES[@]}"; do
                mac=$(cat /sys/class/net/${WIRED_IFACES[$i]}/address 2>/dev/null || echo "?")
                echo "  $((i+1))) ${WIRED_IFACES[$i]} (MAC: $mac)"
            done
            read -r IFACE_CHOICE
            IFACE_CHOICE=${IFACE_CHOICE:-1}
            SELECTED_IFACE="${WIRED_IFACES[$((IFACE_CHOICE-1))]}"
        fi
        ;;
    3)
        NET_MODE_DESC="有线+WiFi双网(调试)"
        if [ ${#WIRED_IFACES[@]} -eq 0 ]; then
            log_error "双网模式需要有线网卡"
            exit 1
        fi
        SELECTED_IFACE="${WIRED_IFACES[0]}"
        log_info "主接口(有线): $SELECTED_IFACE"
        if [ ${#WIFI_IFACES[@]} -gt 0 ]; then
            log_info "备接口(WiFi): ${WIFI_IFACES[0]}"
        fi
        log_warn "WiFi模式不推荐产线使用，brcmfmac中断风暴会影响USB/MCU稳定性!"
        ;;
    *)
        log_error "无效选择"
        exit 1
        ;;
esac

log_info "网络模式: $NET_MODE_DESC, 接口: $SELECTED_IFACE"

# 2.2 新IP
DEFAULT_IP="192.168.5.101"
if [ -n "$CURRENT_IP" ]; then
    DEFAULT_IP="$CURRENT_IP"
fi
log_ask "请输入新的静态IP地址 [当前/默认: $DEFAULT_IP]:"
read -r N1_IP
N1_IP=${N1_IP:-$DEFAULT_IP}

if ! echo "$N1_IP" | grep -qP '^192\.168\.5\.\d+$'; then
    log_error "IP格式不正确，应为 192.168.5.xxx"
    exit 1
fi

# 2.3 MAC地址处理 — 永久固定(udev规则+MAC文件)
log_ask "是否需要永久固定MAC地址? (防止重启后MAC变化) [Y/n]:"
read -r FIX_MAC
FIX_MAC=${FIX_MAC:-Y}

if [ "$FIX_MAC" = "Y" ] || [ "$FIX_MAC" = "y" ]; then
    if [ -f /etc/n1-fixed-mac ]; then
        SAVED_MAC=$(cat /etc/n1-fixed-mac | tr -d '[:space:]')
        log_info "发现已保存的固定MAC: $SAVED_MAC"
        log_ask "使用已保存的MAC? [Y/n]:"
        read -r USE_SAVED
        USE_SAVED=${USE_SAVED:-Y}
        if [ "$USE_SAVED" = "Y" ] || [ "$USE_SAVED" = "y" ]; then
            DESIRED_MAC="$SAVED_MAC"
        fi
    fi

    if [ -z "$DESIRED_MAC" ]; then
        log_ask "请输入要固定的MAC地址 (直接回车=自动随机生成):"
        read -r DESIRED_MAC
    fi

    if [ -z "$DESIRED_MAC" ]; then
        DESIRED_MAC=$(printf '02:%02x:%02x:%02x:%02x:%02x' \
            $((RANDOM % 256)) $((RANDOM % 256)) $((RANDOM % 256)) $((RANDOM % 256)) $((RANDOM % 256)))
        log_info "自动生成随机MAC: $DESIRED_MAC"
    fi

    if ! echo "$DESIRED_MAC" | grep -qP '^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$'; then
        log_error "MAC格式不正确"
        exit 1
    fi

    SECOND_HEX=$(echo "$DESIRED_MAC" | cut -d: -f2)
    SECOND_DEC=$((16#$SECOND_HEX))
    if [ $((SECOND_DEC % 2)) -ne 0 ]; then
        SECOND_DEC=$((SECOND_DEC - 1))
        NEW_SECOND=$(printf "%02x" $SECOND_DEC)
        DESIRED_MAC=$(echo "$DESIRED_MAC" | sed "s/^..:/$NEW_SECOND:/")
        log_info "修正为单播MAC: $DESIRED_MAC"
    fi
    log_info "将永久固定MAC: $DESIRED_MAC"
else
    DESIRED_MAC=""
    log_info "不修改MAC地址"
fi

# 2.4 hostname
HOST_NUM=$(echo "$N1_IP" | cut -d. -f4)
DEFAULT_HOSTNAME="n${HOST_NUM}"
log_ask "请输入hostname [默认: $DEFAULT_HOSTNAME]:"
read -r N1_HOSTNAME
N1_HOSTNAME=${N1_HOSTNAME:-$DEFAULT_HOSTNAME}

# 2.5 WiFi禁用选项 (产线默认禁用WiFi)
log_ask "是否禁用WiFi? (产线推荐禁用，避免brcmfmac中断风暴影响USB/MCU) [Y/n]:"
read -r DISABLE_WIFI
DISABLE_WIFI=${DISABLE_WIFI:-Y}

if [ "$DISABLE_WIFI" = "Y" ] || [ "$DISABLE_WIFI" = "y" ]; then
    DISABLE_WIFI="Y"
    log_info "WiFi将被彻底禁用 (三层: rfkill+nmcli+黑名单)"
else
    DISABLE_WIFI="N"
    log_warn "WiFi保持启用，注意brcmfmac中断风暴风险，可能影响USB/MCU稳定性!"
fi

# 2.6 总控服务器IP
log_ask "请输入总控服务器IP [默认: 192.168.5.8]:"
read -r SERVER_IP
SERVER_IP=${SERVER_IP:-192.168.5.8}

# �认
echo ""
log_ask "============================================="
log_ask "  请确认以下配置:"
log_ask "  网络模式:     $NET_MODE_DESC"
log_ask "  网卡接口:     $SELECTED_IFACE"
log_ask "  新IP:         $N1_IP"
log_ask "  固定MAC:      ${DESIRED_MAC:-不修改}"
log_ask "  hostname:     $N1_HOSTNAME"
log_ask "  WiFi:         $([ "$DISABLE_WIFI" = "Y" ] && echo "禁用(三层: rfkill+nmcli+黑名单)" || echo "启用(开发调试)")"
log_ask "  总控服务器:   $SERVER_IP"
log_ask "============================================="
log_ask "确认写入配置? [Y/n]:"
read -r CONFIRM
CONFIRM=${CONFIRM:-Y}
if [ "$CONFIRM" != "Y" ] && [ "$CONFIRM" != "y" ]; then
    log_error "用户取消"
    exit 0
fi

####################################################################################
# 3. 写入网络配置 (不立即生效!)
####################################################################################
echo ""
log_info "写入网络配置 (不切换网络，不会断开SSH)..."

# 3.1 NetworkManager 静态IP — 主接口(有线)
CON_NAME=$(nmcli -t -f NAME,DEVICE con show --active 2>/dev/null | grep "$SELECTED_IFACE" | head -1 | cut -d: -f1)
if [ -z "$CON_NAME" ]; then
    CON_NAME=$(nmcli -t -f NAME con show --active 2>/dev/null | head -1)
fi

if [ -n "$CON_NAME" ]; then
    log_info "NetworkManager主连接: $CON_NAME (接口: $SELECTED_IFACE)"
    nmcli con mod "$CON_NAME" \
        ipv4.method manual \
        ipv4.addresses "$N1_IP/24" \
        ipv4.gateway "192.168.5.1" \
        ipv4.dns "8.8.8.8,114.114.114.114" \
        ipv4.route-metric 100 \
        connection.autoconnect-priority 100 2>/dev/null || true
    log_info "主接口静态IP已写入: $N1_IP/24 (重启后生效)"
else
    log_warn "未找到NetworkManager连接，创建新的"
    CON_NAME="${SELECTED_IFACE}-static"
    nmcli con add con-name "$CON_NAME" ifname "$SELECTED_IFACE" type ethernet \
        ipv4.method manual ipv4.addresses "$N1_IP/24" \
        ipv4.gateway "192.168.5.1" ipv4.dns "8.8.8.8" \
        connection.autoconnect-priority 100 2>/dev/null || true
fi

# 3.2 有线网络配置
log_info "配置有线网络..."

nmcli con mod "$CON_NAME" connection.autoconnect-priority 100 2>/dev/null || true
nmcli con mod "$CON_NAME" ipv6.method disabled 2>/dev/null || true
ethtool -s "$SELECTED_IFACE" wol d 2>/dev/null || true
log_info "有线优化: IPv6关闭, WoL关闭, 优先级=100, metric=100"

# 3.3 永久固定MAC地址 — 仅有线接口
if [ -n "$DESIRED_MAC" ]; then
    echo "$DESIRED_MAC" > /etc/n1-fixed-mac
    echo "$SELECTED_IFACE" > /etc/n1-fixed-iface
    log_info "MAC已保存到 /etc/n1-fixed-mac: $DESIRED_MAC"
    log_info "接口已保存到 /etc/n1-fixed-iface: $SELECTED_IFACE"

    # 方法1: udev规则 (内核级永久固定)
    ORIG_MAC=$(cat /sys/class/net/$SELECTED_IFACE/address 2>/dev/null || echo "")
    PERM_MAC=$(cat /sys/class/net/$SELECTED_IFACE/permaddr 2>/dev/null || echo "$ORIG_MAC")
    MATCH_MAC="$PERM_MAC"
    [ -z "$MATCH_MAC" ] && MATCH_MAC="$ORIG_MAC"
    if [ -n "$MATCH_MAC" ]; then
        UDEV_RULE="SUBSYSTEM==\"net\", ACTION==\"add\", KERNEL==\"$SELECTED_IFACE\", ATTR{address}==\"$MATCH_MAC\", ATTR{address}=\"$DESIRED_MAC\""
        UDEV_FILE="/etc/udev/rules.d/70-persistent-net.rules"
        sed -i "/n1-fixed-mac/d" "$UDEV_FILE" 2>/dev/null || true
        echo "# n1-fixed-mac: permanent MAC for $SELECTED_IFACE only" >> "$UDEV_FILE"
        echo "$UDEV_RULE" >> "$UDEV_FILE"
        log_info "MAC固定(udev): 内核级规则写入 $UDEV_FILE (KERNEL==$SELECTED_IFACE)"
    fi

    # 方法2: NetworkManager cloned-mac-address (仅有线)
    nmcli con mod "$CON_NAME" 802-3-ethernet.cloned-mac-address "$DESIRED_MAC" 2>/dev/null || \
    nmcli con mod "$CON_NAME" ethernet.cloned-mac-address "$DESIRED_MAC" 2>/dev/null || true
    log_info "MAC固定(NM cloned-mac): $DESIRED_MAC (仅有线连接: $CON_NAME)"

    # 方法3: systemd service — 开机后强制设置MAC
    cat > /usr/local/bin/fix-mac.sh << 'MACSCRIPT'
#!/bin/bash
MAC_FILE="/etc/n1-fixed-mac"
IFACE_FILE="/etc/n1-fixed-iface"

[ -f "$MAC_FILE" ] || exit 0
DESIRED_MAC=$(cat "$MAC_FILE" | tr -d '[:space:]')
[ -n "$DESIRED_MAC" ] || exit 0

IFACE=""
if [ -f "$IFACE_FILE" ]; then
    SAVED_IFACE=$(cat "$IFACE_FILE" | tr -d '[:space:]')
    if [ -e "/sys/class/net/$SAVED_IFACE" ]; then
        IFACE="$SAVED_IFACE"
    fi
fi

[ -n "$IFACE" ] || exit 1

for i in $(seq 1 15); do
    [ -e "/sys/class/net/$IFACE" ] && break
    sleep 0.5
done
[ -e "/sys/class/net/$IFACE" ] || exit 1

CURRENT_MAC=$(cat /sys/class/net/$IFACE/address 2>/dev/null)
[ "$CURRENT_MAC" = "$DESIRED_MAC" ] && exit 0

ip link set dev $IFACE down 2>/dev/null || true
ip link set dev $IFACE address $DESIRED_MAC 2>/dev/null || true
ip link set dev $IFACE up 2>/dev/null || true

sleep 3
CON=$(nmcli -t -f NAME,DEVICE con show --active 2>/dev/null | grep "$IFACE" | head -1 | cut -d: -f1)
[ -n "$CON" ] && nmcli con up "$CON" 2>/dev/null || true

logger -t fix-mac "MAC fixed: $IFACE $CURRENT_MAC -> $DESIRED_MAC"
MACSCRIPT
    chmod +x /usr/local/bin/fix-mac.sh

    cat > /etc/systemd/system/fix-mac.service << 'EOF'
[Unit]
Description=Force fix MAC address after NetworkManager starts
After=NetworkManager.service
Before=network-online.target
Wants=NetworkManager.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/fix-mac.sh
RemainAfterExit=yes
SuccessExitStatus=0 1

[Install]
WantedBy=multi-user.target
Also=NetworkManager.service
EOF
    systemctl daemon-reload
    systemctl enable fix-mac.service 2>/dev/null || true
    log_info "MAC固定(service): fix-mac.service (After=NM, Before=network-online)"

    # 方法4: NM dispatcher 兜底 — 仅up事件
    mkdir -p /etc/NetworkManager/dispatcher.d
    cat > /etc/NetworkManager/dispatcher.d/99-fix-mac.sh << 'DISPEOF'
#!/bin/bash
if [ "$2" = "up" ]; then
    /usr/local/bin/fix-mac.sh 2>/dev/null || true
fi
DISPEOF
    chmod +x /etc/NetworkManager/dispatcher.d/99-fix-mac.sh 2>/dev/null || true
    log_info "MAC固定(dispatcher): 仅NM up事件触发"

    log_info "MAC永久固定: 四重保险(udev + NM cloned + service + dispatcher) — 仅有线接口"
fi

# 3.4 dhcpcd 兜底
if [ -f /etc/dhcpcd.conf ]; then
    if ! grep -q "$N1_IP" /etc/dhcpcd.conf 2>/dev/null; then
        cat >> /etc/dhcpcd.conf << EOF

interface $SELECTED_IFACE
static ip_address=$N1_IP/24
static routers=192.168.5.1
static domain_name_servers=8.8.8.8
EOF
        log_info "dhcpcd兜底已写入"
    fi
fi

# 3.5 hostname
if [ "$CURRENT_HOSTNAME" != "$N1_HOSTNAME" ]; then
    hostname "$N1_HOSTNAME"
    echo "$N1_HOSTNAME" > /etc/hostname
    if ! grep -q "$N1_HOSTNAME" /etc/hosts 2>/dev/null; then
        sed -i "s/127.0.1.1.*/127.0.1.1\t$N1_HOSTNAME/" /etc/hosts 2>/dev/null || true
    fi
    log_info "Hostname: $CURRENT_HOSTNAME → $N1_HOSTNAME"
fi

# 3.6 保存配置信息
cat > /root/n1_network_info.txt << NETEOF
N1_IP=$N1_IP
OLD_IP=$CURRENT_IP
IFACE=$SELECTED_IFACE
NET_MODE=$NET_MODE_DESC
OLD_MAC=$CURRENT_MAC
FIXED_MAC=${DESIRED_MAC:-same}
HOSTNAME=$N1_HOSTNAME
SERVER_IP=$SERVER_IP
WIFI_DISABLED=$DISABLE_WIFI
WIFI_DISABLE_LAYERS=$([ "$DISABLE_WIFI" = "Y" ] && echo "rfkill+nmcli+blacklist" || echo "N/A")
CONFIG_TIME=$(date '+%Y-%m-%d %H:%M:%S')
NETEOF

####################################################################################
# 4. WiFi三层禁用 (产线默认)
####################################################################################
if [ "$DISABLE_WIFI" = "Y" ]; then
    log_info "WiFi三层彻底禁用..."

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
    log_info "  rfkill持久化service已启用 (重启后自动block wlan)"

    # WiFi服务清理
    systemctl disable wifi-watchdog 2>/dev/null || true
    systemctl stop wifi-watchdog 2>/dev/null || true
    rm -f /etc/NetworkManager/dispatcher.d/99-wifi-stability.sh 2>/dev/null || true
    rm -f /etc/NetworkManager/conf.d/no-p2p.conf 2>/dev/null || true
    rm -f /etc/NetworkManager/conf.d/wifi-no-bgscan.conf 2>/dev/null || true
    rm -f /etc/NetworkManager/conf.d/wifi-no-mac-random.conf 2>/dev/null || true
    log_info "  WiFi服务已清理: wifi-watchdog禁用, WiFi dispatcher/conf已移除"

    # 验证WiFi禁用
    RFKILL=$(rfkill list 2>/dev/null | grep -A2 "wlan" | grep "Soft blocked" | awk '{print $3}')
    NM_WIFI=$(nmcli radio wifi 2>/dev/null)
    log_info "  验证: rfkill Soft blocked=$RFKILL, nmcli radio wifi=$NM_WIFI"

    log_info "WiFi三层禁用完成 (rfkill+nmcli+黑名单+持久化)"
else
    # WiFi启用模式 — 移除黑名单，确保WiFi可用
    sed -i '/blacklist brcmfmac/d' /etc/modprobe.d/brcmfmac.conf 2>/dev/null || true
    nmcli radio wifi on 2>/dev/null || true
    rfkill unblock wlan 2>/dev/null || true
    systemctl disable n1-rfkill-persist.service 2>/dev/null || true
    log_warn "WiFi已启用，重启后生效。注意brcmfmac中断风暴可能影响USB/MCU稳定性!"
fi

####################################################################################
# 5. USB autosuspend持久化 + 网络完整性检查
####################################################################################
log_info "USB autosuspend持久化 + 网络完整性检查..."

# usb-autosuspend-fix.service: sysinit阶段强制设置autosuspend=-1
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

# modprobe.d备份
echo 'options usbcore autosuspend=-1' > /etc/modprobe.d/usb-no-autosuspend.conf 2>/dev/null || true

# udev规则备份
cat > /etc/udev/rules.d/99-usb-no-autosuspend.rules << 'UDEVEOF'
ACTION=="add", SUBSYSTEM=="usb", ATTR{power/autosuspend}="-1"
ACTION=="add", SUBSYSTEM=="usb", TEST=="power/control", ATTR{power/control}="on"
UDEVEOF

# net-check.service: 纯有线版 (NM启动后10s检查修复)
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
log_info "net-check.service 已启用 (纯有线版, NM启动后10s检查修复)"

# 运行时立即生效
echo -1 > /sys/module/usbcore/parameters/autosuspend 2>/dev/null || true
for d in /sys/bus/usb/devices/*/power/control; do echo on > "$d" 2>/dev/null; done
log_info "USB autosuspend已立即设置为-1"

####################################################################################
# 6. 有线网络稳定性加固
####################################################################################
log_info "有线网络稳定性加固..."

# L0: RTL8211F工业级有线稳定方案 — autoneg=on统一策略
ethtool --set-eee "$SELECTED_IFACE" eee off 2>/dev/null || true
EEE_STATUS=$(ethtool --show-eee "$SELECTED_IFACE" 2>/dev/null | grep -i "EEE status" || echo "N/A")
log_info "  L0-1: EEE已禁用 ($EEE_STATUS)"

CURRENT_SPEED=$(ethtool "$SELECTED_IFACE" 2>/dev/null | grep "Speed:" | awk '{print $2}')
log_info "  L0-2: 统一策略autoneg=on自由协商 (当前速度: $CURRENT_SPEED)"

nmcli con mod "$CON_NAME" 802-3-ethernet.speed 0 2>/dev/null || true
log_info "  L0-3: NM属性speed=0 (自由协商，永不强制)"

log_info "  L0: RTL8211F工业级方案完成 (autoneg=on + EEE off + CAT6网线)"

# Dispatcher: 只做EEE/WoL/PM，永不设speed/autoneg
cat > /etc/NetworkManager/dispatcher.d/99-eth0-stable.sh << ESTABEOF
#!/bin/bash
IFACE="\$1"
ACTION="\$2"
if [ "\$IFACE" = "$SELECTED_IFACE" ] && [ "\$ACTION" = "up" ]; then
    ethtool --set-eee $SELECTED_IFACE eee off 2>/dev/null || true
    ethtool -s $SELECTED_IFACE wol d 2>/dev/null || true
    echo on > /sys/class/net/$SELECTED_IFACE/power/control 2>/dev/null || true
    logger -t eth0-stable "eth0 up: EEE off + WoL off + PM on (autoneg=on, no speed force)"
fi
ESTABEOF
chmod +x /etc/NetworkManager/dispatcher.d/99-eth0-stable.sh 2>/dev/null || true
log_info "  Dispatcher: 99-eth0-stable.sh (EEE off + WoL off + PM on)"

# L2: 禁用网卡runtime PM
echo on > /sys/class/net/$SELECTED_IFACE/power/control 2>/dev/null || true
cat > /etc/udev/rules.d/99-net-no-runtime-pm.rules << 'RPMEOF'
SUBSYSTEM=="net", ACTION=="add", RUN+="/bin/sh -c 'echo on > /sys/class/net/%k/power/control 2>/dev/null'"
RPMEOF
log_info "  L2: 禁用网络设备runtime PM (power.control=on)"

# L3: 有线省电全面禁用
ethtool --set-eee "$SELECTED_IFACE" eee off 2>/dev/null || true
ethtool -s "$SELECTED_IFACE" wol d 2>/dev/null || true
log_info "  L3: 省电全面禁用 (EEE off + WoL off)"

# L3.5: eth0省电禁用systemd兜底service
cat > /usr/local/bin/eth0-power-fix.sh << 'PEOF'
#!/bin/bash
sleep 2
IFACE=$(cat /etc/n1-fixed-iface 2>/dev/null || echo "eth0")
[ -e "/sys/class/net/$IFACE" ] || IFACE="eth0"
ethtool --set-eee $IFACE eee off 2>/dev/null || true
ethtool -s $IFACE wol d 2>/dev/null || true
echo on > /sys/class/net/$IFACE/power/control 2>/dev/null || true
logger -t eth0-power-fix "$IFACE: EEE off + WoL off + PM on (autoneg=on, no speed force)"
PEOF
chmod +x /usr/local/bin/eth0-power-fix.sh 2>/dev/null || true
cat > /etc/systemd/system/eth0-power-fix.service << 'SVCEOF'
[Unit]
Description=eth0 Power Save Disable (fallback)
After=network.target NetworkManager.service

[Service]
Type=oneshot
ExecStartPre=/bin/sleep 5
ExecStart=/usr/local/bin/eth0-power-fix.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
SVCEOF
systemctl daemon-reload 2>/dev/null || true
systemctl enable eth0-power-fix.service 2>/dev/null || true
log_info "  L3.5: eth0-power-fix.service 兜底已启用"

# L4: 禁用eth0 IPv6
nmcli con mod "$CON_NAME" ipv6.method disabled 2>/dev/null || true
log_info "  L4: IPv6 on $SELECTED_IFACE 已禁用"

# L5: 路由metric (有线优先)
nmcli con mod "$CON_NAME" ipv4.route-metric 100 2>/dev/null || true
log_info "  L5: 路由metric=100 (有线优先)"

# L6: wired-watchdog默认禁用 (RTL8211F PHY卡死时重启接口无效且有害)
cat > /usr/local/bin/wired-watchdog.sh << WWDOG
#!/bin/bash
CHECK_INTERVAL=60
FAIL_COUNT=0
MAX_FAILS=3
GATEWAY="192.168.5.1"
IFACE="$SELECTED_IFACE"

while true; do
    if [ ! -e /sys/class/net/\$IFACE ]; then
        logger -t wired-watchdog "接口\$IFACE消失!"
        FAIL_COUNT=\$((FAIL_COUNT + 1))
    elif ! ethtool \$IFACE 2>/dev/null | grep -q "Link detected: yes"; then
        logger -t wired-watchdog "接口\$IFACE网线未连接"
        FAIL_COUNT=\$((FAIL_COUNT + 1))
    elif ! ping -c 1 -W 2 "\$GATEWAY" &>/dev/null; then
        FAIL_COUNT=\$((FAIL_COUNT + 1))
    else
        FAIL_COUNT=0
    fi

    if [ \$FAIL_COUNT -ge \$MAX_FAILS ]; then
        logger -t wired-watchdog "有线网络异常(\${FAIL_COUNT}次), 重启接口"
        ip link set dev \$IFACE down 2>/dev/null || true
        sleep 2
        ip link set dev \$IFACE up 2>/dev/null || true
        sleep 3
        CON=\$(nmcli -t -f NAME,DEVICE con show --active 2>/dev/null | grep "\$IFACE" | head -1 | cut -d: -f1)
        [ -n "\$CON" ] && nmcli con up "\$CON" 2>/dev/null || true
        FAIL_COUNT=0
    fi
    sleep \$CHECK_INTERVAL
done
WWDOG
chmod +x /usr/local/bin/wired-watchdog.sh 2>/dev/null || true

cat > /etc/systemd/system/wired-watchdog.service << 'EOF'
[Unit]
Description=Wired Network Watchdog
After=NetworkManager.service

[Service]
Type=simple
ExecStart=/usr/local/bin/wired-watchdog.sh
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload 2>/dev/null || true
systemctl disable wired-watchdog 2>/dev/null || true
systemctl stop wired-watchdog 2>/dev/null || true
log_info "  L6: wired-watchdog已禁用 (避免PHY卡死时循环重启)"

# L7: NM dispatcher 有线重连 (已移除: 和link-monitor.sh冲突, 会造成链路抖动循环)
# link-monitor.sh已包含断线自动重连逻辑，无需NM dispatcher重复
rm -f /etc/NetworkManager/dispatcher.d/99-wired-stability.sh 2>/dev/null || true
log_info "  L7: 有线重连由link-monitor.sh负责 (已移除NM dispatcher避免冲突)"

log_info "有线网络 7层防线已部署"

####################################################################################
# 7. 总结
####################################################################################
echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║           网络配置已写入! (未切换，SSH未断开)               ║${NC}"
echo -e "${BOLD}╠══════════════════════════════════════════════════════════════╣${NC}"
echo -e "${BOLD}║  网络模式:   $NET_MODE_DESC                                ║${NC}"
echo -e "${BOLD}║  网卡接口:   $SELECTED_IFACE                                ║${NC}"
echo -e "${BOLD}║  当前SSH仍在: $CURRENT_IP                                  ║${NC}"
echo -e "${BOLD}║  重启后新IP:  $N1_IP                                       ║${NC}"
echo -e "${BOLD}║  固定MAC:     ${DESIRED_MAC:-不修改}                              ║${NC}"
echo -e "${BOLD}║  hostname:    $N1_HOSTNAME                                  ║${NC}"
echo -e "${BOLD}║  WiFi:        $([ "$DISABLE_WIFI" = "Y" ] && echo "禁用(三层: rfkill+nmcli+黑名单)" || echo "启用(开发调试)")${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
log_warn "接下来请按以下步骤操作:"
echo ""
echo "  1. 重启N1:"
echo "       reboot"
echo ""
echo "  2. 等待N1重启完成 (约30秒)"
echo ""
echo "  3. 用新IP重新SSH连接:"
echo "       ssh root@$N1_IP"
echo ""
echo "  4. 验证WiFi禁用:"
echo "       rfkill list | grep wlan  (应显示 Soft blocked: yes)"
echo "       nmcli radio wifi         (应显示 disabled)"
echo "       lsmod | grep brcmfmac    (应无输出)"
echo ""
echo "  5. 验证MCU连接:"
echo "       ls /dev/serial/by-id/*   (应显示Klipper设备)"
echo "       curl -s http://localhost:7125/server/info | grep klippy_state"
echo ""
echo "  6. 运行软件部署脚本:"
echo "       ./n1_deploy.sh"
echo ""
echo "  7. 执行30分钟MCU稳定性验证:"
echo "       bash /root/verify_mcu_stability.sh --duration 30"
echo ""
log_info "配置信息已保存到 /root/n1_network_info.txt"
