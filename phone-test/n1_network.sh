#!/bin/bash
####################################################################################
# N1 网络配置脚本 — 固定静态IP + 固定MAC地址 + 设置hostname
#
# !! 重要：此脚本只写入配置文件，不立即切换网络，避免SSH断开 !!
# !! 运行完成后需要重启N1才生效，重启后用新IP重新SSH连接 !!
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
echo -e "${BOLD}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║   N1 网络配置脚本 — 固定IP + 固定MAC + hostname        ║${NC}"
echo -e "${BOLD}║   ⚠️  配置写入后需重启才生效，不会立即断开SSH           ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""

####################################################################################
# 1. 显示当前网络信息
####################################################################################
echo "=== 当前网络信息 ==="
CURRENT_IP=$(ip -4 addr show | grep -oP '192\.168\.5\.\d+' | head -1)
CURRENT_IFACE=$(ip -4 addr show | grep -B2 "$CURRENT_IP" | head -1 | awk '{print $2}' | tr -d ':')
if [ -z "$CURRENT_IFACE" ]; then
    CURRENT_IFACE=$(ip route | grep default | awk '{print $5}' | head -1)
fi
CURRENT_MAC=$(cat /sys/class/net/${CURRENT_IFACE}/address 2>/dev/null || echo "unknown")
CURRENT_HOSTNAME=$(hostname)

echo "  当前IP:      $CURRENT_IP"
echo "  网卡接口:    $CURRENT_IFACE"
echo "  当前MAC:     $CURRENT_MAC"
echo "  当前hostname: $CURRENT_HOSTNAME"
echo ""

####################################################################################
# 2. 交互输入
####################################################################################
# 2.1 新IP
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

# 2.2 MAC地址处理 — 自动生成随机MAC永久固定
log_ask "是否需要固定MAC地址? (防止路由器分配冲突) [Y/n]:"
read -r FIX_MAC
FIX_MAC=${FIX_MAC:-Y}

if [ "$FIX_MAC" = "Y" ] || [ "$FIX_MAC" = "y" ]; then
    # 如果已有固定MAC文件，优先使用
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

    # 自动随机生成 (确保单播: 第二位偶数)
    if [ -z "$DESIRED_MAC" ]; then
        DESIRED_MAC=$(printf '02:%02x:%02x:%02x:%02x:%02x' \
            $((RANDOM % 256)) $((RANDOM % 256)) $((RANDOM % 256)) $((RANDOM % 256)) $((RANDOM % 256)))
        log_info "自动生成随机MAC: $DESIRED_MAC"
    fi

    if ! echo "$DESIRED_MAC" | grep -qP '^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$'; then
        log_error "MAC格式不正确"
        exit 1
    fi

    # 确保单播地址(第二位偶数)
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

# 2.3 hostname
HOST_NUM=$(echo "$N1_IP" | cut -d. -f4)
DEFAULT_HOSTNAME="n${HOST_NUM}"
log_ask "请输入hostname [默认: $DEFAULT_HOSTNAME]:"
read -r N1_HOSTNAME
N1_HOSTNAME=${N1_HOSTNAME:-$DEFAULT_HOSTNAME}

# 2.4 总控服务器IP
log_ask "请输入总控服务器IP [默认: 192.168.5.8]:"
read -r SERVER_IP
SERVER_IP=${SERVER_IP:-192.168.5.8}

# 确认
echo ""
log_ask "============================================="
log_ask "  请确认以下配置:"
log_ask "  新IP:         $N1_IP"
log_ask "  网卡:         $CURRENT_IFACE"
log_ask "  固定MAC:      ${DESIRED_MAC:-不修改}"
log_ask "  hostname:     $N1_HOSTNAME"
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

# 3.1 NetworkManager 静态IP
CON_NAME=$(nmcli -t -f NAME,DEVICE con show --active 2>/dev/null | head -1 | cut -d: -f1)
if [ -z "$CON_NAME" ]; then
    CON_NAME=$(nmcli -t -f NAME con show --active 2>/dev/null | head -1)
fi

if [ -n "$CON_NAME" ]; then
    log_info "NetworkManager连接: $CON_NAME"
    nmcli con mod "$CON_NAME" \
        ipv4.method manual \
        ipv4.addresses "$N1_IP/24" \
        ipv4.gateway "192.168.5.1" \
        ipv4.dns "8.8.8.8,114.114.114.114" 2>/dev/null || true
    log_info "静态IP已写入: $N1_IP/24 (重启后生效)"
else
    log_warn "未找到NetworkManager连接，创建新的"
    CON_NAME="${CURRENT_IFACE}-static"
    nmcli con add con-name "$CON_NAME" ifname "$CURRENT_IFACE" type ethernet \
        ipv4.method manual ipv4.addresses "$N1_IP/24" \
        ipv4.gateway "192.168.5.1" ipv4.dns "8.8.8.8" 2>/dev/null || true
fi

# 3.2 固定MAC地址 — 真正可靠的方案
if [ -n "$DESIRED_MAC" ]; then
    # 持久保存MAC到文件 (供fix-mac.service读取)
    echo "$DESIRED_MAC" > /etc/n1-fixed-mac
    log_info "MAC已保存到 /etc/n1-fixed-mac: $DESIRED_MAC"

    # 方法1: NetworkManager cloned-mac-address (NM层面固定，重启后NM会使用此MAC)
    nmcli con mod "$CON_NAME" 802-3-ethernet.cloned-mac-address "$DESIRED_MAC" 2>/dev/null || \
    nmcli con mod "$CON_NAME" ethernet.cloned-mac-address "$DESIRED_MAC" 2>/dev/null || true
    log_info "MAC固定(NM cloned-mac): $DESIRED_MAC"

    # 方法2: 核心方案 — systemd service 在NM启动后立即强制设MAC再reconnect
    # 这确保即使NM忽略了cloned-mac，也会被强制覆盖
    cat > /usr/local/bin/fix-mac.sh << MACSCRIPT
#!/bin/bash
# 永久固定MAC地址 — 在NetworkManager启动后强制设置
# 读取持久保存的MAC，强制覆盖硬件MAC，然后重新连接NM确保IP正确

MAC_FILE="/etc/n1-fixed-mac"
IFACE="$CURRENT_IFACE"

if [ ! -f "\$MAC_FILE" ]; then
    exit 0
fi

DESIRED_MAC=\$(cat "\$MAC_FILE" | tr -d '[:space:]')
if [ -z "\$DESIRED_MAC" ]; then
    exit 0
fi

# 等待网卡出现
for i in \$(seq 1 10); do
    [ -e /sys/class/net/\$IFACE ] && break
    sleep 0.5
done

if [ ! -e /sys/class/net/\$IFACE ]; then
    exit 1
fi

CURRENT_MAC=\$(cat /sys/class/net/\$IFACE/address 2>/dev/null)

if [ "\$CURRENT_MAC" = "\$DESIRED_MAC" ]; then
    exit 0
fi

# 强制设置MAC: 先down → 设MAC → up
ip link set dev \$IFACE down 2>/dev/null || true
ip link set dev \$IFACE address \$DESIRED_MAC 2>/dev/null || true
ip link set dev \$IFACE up 2>/dev/null || true

# 等NM接管后，触发reconnect确保用cloned-mac+静态IP
sleep 2
nmcli con up "$CON_NAME" 2>/dev/null || true
MACSCRIPT
    chmod +x /usr/local/bin/fix-mac.sh

    # systemd service: 在NetworkManager启动之后、network-online之前执行
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

# 失败不阻塞启动
SuccessExitStatus=0 1

[Install]
WantedBy=multi-user.target
Also=NetworkManager.service
EOF
    systemctl daemon-reload
    systemctl enable fix-mac.service 2>/dev/null || true
    log_info "MAC固定(service): fix-mac.service (After=NM, Before=network-online)"

    # 方法3: rc-local 兜底 — 每次网络变化后也检查MAC
    mkdir -p /etc/NetworkManager/dispatcher.d
    cat > /etc/NetworkManager/dispatcher.d/99-fix-mac.sh << 'DISPEOF'
#!/bin/bash
# NM dispatcher: 网络事件触发后检查并修复MAC
if [ "$2" = "up" ] || [ "$2" = "connectivity-change" ]; then
    /usr/local/bin/fix-mac.sh 2>/dev/null || true
fi
DISPEOF
    chmod +x /etc/NetworkManager/dispatcher.d/99-fix-mac.sh 2>/dev/null || true
    log_info "MAC固定(dispatcher): NM事件触发兜底"

    log_info "MAC永久固定: 三重保险(NM cloned + service + dispatcher)"
fi

# 3.3 dhcpcd 兜底 (防止DHCP覆盖)
if [ -f /etc/dhcpcd.conf ]; then
    if ! grep -q "$N1_IP" /etc/dhcpcd.conf 2>/dev/null; then
        cat >> /etc/dhcpcd.conf << EOF

interface $CURRENT_IFACE
static ip_address=$N1_IP/24
static routers=192.168.5.1
static domain_name_servers=8.8.8.8
EOF
        log_info "dhcpcd兜底已写入"
    fi
fi

# 3.4 hostname
if [ "$CURRENT_HOSTNAME" != "$N1_HOSTNAME" ]; then
    hostname "$N1_HOSTNAME"
    echo "$N1_HOSTNAME" > /etc/hostname
    if ! grep -q "$N1_HOSTNAME" /etc/hosts 2>/dev/null; then
        sed -i "s/127.0.1.1.*/127.0.1.1\t$N1_HOSTNAME/" /etc/hosts 2>/dev/null || true
    fi
    log_info "Hostname: $CURRENT_HOSTNAME → $N1_HOSTNAME"
fi

# 3.5 保存配置信息
cat > /root/n1_network_info.txt << NETEOF
N1_IP=$N1_IP
OLD_IP=$CURRENT_IP
IFACE=$CURRENT_IFACE
OLD_MAC=$CURRENT_MAC
FIXED_MAC=${DESIRED_MAC:-same}
HOSTNAME=$N1_HOSTNAME
SERVER_IP=$SERVER_IP
CONFIG_TIME=$(date '+%Y-%m-%d %H:%M:%S')
NETEOF

####################################################################################
# 4. 总结
####################################################################################
echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║           网络配置已写入! (未切换，SSH未断开)           ║${NC}"
echo -e "${BOLD}╠══════════════════════════════════════════════════════════╣${NC}"
echo -e "${BOLD}║  当前SSH仍在: $CURRENT_IP                             ║${NC}"
echo -e "${BOLD}║  重启后新IP:  $N1_IP                                  ║${NC}"
echo -e "${BOLD}║  固定MAC:     ${DESIRED_MAC:-不修改}                          ║${NC}"
echo -e "${BOLD}║  hostname:    $N1_HOSTNAME                              ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════════════════╝${NC}"
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
echo "  4. 运行软件部署脚本:"
echo "       ./n1_deploy.sh"
echo ""
echo "  5. 从总控服务器端验证:"
echo "       curl -s http://$N1_IP:7125/server/info"
echo ""
log_info "配置信息已保存到 /root/n1_network_info.txt"

####################################################################################
# WiFi稳定性加固
####################################################################################
log_info "WiFi稳定性加固..."

NM_CONN=$(nmcli -t -f NAME,TYPE con show --active 2>/dev/null | grep -i wireless | head -1 | cut -d: -f1)
if [ -n "$NM_CONN" ]; then
    # L1: WiFi省电模式
    nmcli con modify "$NM_CONN" 802-11-wireless.powersave 2 2>/dev/null || true
    log_info "  L1: WiFi省电=2(适度)"

    WIFI_DEV=$(nmcli -t -f DEVICE,TYPE dev status 2>/dev/null | grep -i wifi | head -1 | cut -d: -f1)
    if [ -n "$WIFI_DEV" ]; then
        iw dev "$WIFI_DEV" set power_save off 2>/dev/null && log_info "  L1: $WIFI_DEV 省电已关闭" || true
    fi

    # L2: 自动重连加固
    nmcli con modify "$NM_CONN" connection.autoconnect-priority 10 2>/dev/null || true
    nmcli con modify "$NM_CONN" connection.autoconnect-retries 0 2>/dev/null || true
    log_info "  L2: 自动重连优先级=10, 无限重试"
else
    log_warn "  未检测到活跃WiFi连接"
fi

# L3: NM dispatcher脚本 (连接时关闭省电+确保USB活跃)
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
log_info "  L3: WiFi dispatcher已安装 (连接时关闭省电+确保USB活跃)"

# L4: wifi-watchdog服务 (每30s ping网关, 5次失败重启WiFi)
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
systemctl daemon-reload
systemctl enable wifi-watchdog 2>/dev/null || true
systemctl start wifi-watchdog 2>/dev/null || true
log_info "  L4: wifi-watchdog (每30s检测, 5次失败重启WiFi)"
log_info "WiFi 4层防线已部署"
