#!/bin/bash
####################################################################################
# N1 一键诊断收集工具
# 用法: bash n1-diagnose.sh [--remote IP]
####################################################################################

REMOTE_IP=""
[ "$1" = "--remote" ] && [ -n "$2" ] && REMOTE_IP="$2"

SSH_CMD=""
if [ -n "$REMOTE_IP" ]; then
    SSH_CMD="ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 root@$REMOTE_IP"
    $SSH_CMD "echo ok" &>/dev/null || { echo "SSH连接失败: $REMOTE_IP"; exit 1; }
    echo "远程诊断: $REMOTE_IP"
else
    echo "本地诊断"
fi

run() {
    if [ -n "$SSH_CMD" ]; then
        $SSH_CMD "$1" 2>&1
    else
        eval "$1" 2>&1
    fi
}

TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
DIAG_DIR="/tmp/n1-diag-${TIMESTAMP}"
mkdir -p "$DIAG_DIR"

echo "=== 1. 系统基本信息 ==="
run "hostname; uname -a; cat /etc/armbian-release 2>/dev/null || echo 'not armbian'; uptime; cat /etc/n1_network_info.txt 2>/dev/null || echo 'N/A'" > "$DIAG_DIR/system.txt"
cat "$DIAG_DIR/system.txt"

echo ""
echo "=== 2. 网络状态 ==="
run "ethtool $IFACE 2>/dev/null || ethtool eth0 2>/dev/null; echo '---'; ip addr show; echo '---'; ip route show; echo '---'; nmcli con show --active; echo '---'; arp -n; echo '---'; rfkill list; echo '---'; nmcli radio" > "$DIAG_DIR/network.txt"
cat "$DIAG_DIR/network.txt"

echo ""
echo "=== 3. MCU/USB状态 ==="
run "ls -la /dev/serial/by-id/ 2>/dev/null || echo 'no serial devices'; echo '---'; dmesg | tail -50 | grep -iE 'usb|xhci|klipper|stm32|rp2040'; echo '---'; curl -s http://localhost:7125/server/info 2>/dev/null | head -200 || echo 'Moonraker unreachable'" > "$DIAG_DIR/mcu.txt"
cat "$DIAG_DIR/mcu.txt"

echo ""
echo "=== 4. 服务状态 ==="
run "systemctl status klipper --no-pager 2>/dev/null; echo '==='; systemctl status moonraker --no-pager 2>/dev/null; echo '==='; systemctl status go2rtc --no-pager 2>/dev/null; echo '==='; systemctl status usb-watchdog --no-pager 2>/dev/null; echo '==='; systemctl status n1-health-monitor --no-pager 2>/dev/null; echo '==='; systemctl status link-monitor --no-pager 2>/dev/null; echo '==='; systemctl status n1-health-api --no-pager 2>/dev/null" > "$DIAG_DIR/services.txt"
cat "$DIAG_DIR/services.txt"

echo ""
echo "=== 5. 资源状态 ==="
run "df -h; echo '---'; free -m; echo '---'; cat /sys/class/thermal/thermal_zone*/temp 2>/dev/null || echo 'N/A'; echo '---'; cat /var/run/n1-health-status.json 2>/dev/null || echo 'N/A'" > "$DIAG_DIR/resources.txt"
cat "$DIAG_DIR/resources.txt"

echo ""
echo "=== 6. 最近日志 ==="
run "journalctl -u klipper --since '1 hour ago' --no-pager 2>/dev/null | tail -30; echo '==='; journalctl -u moonraker --since '1 hour ago' --no-pager 2>/dev/null | tail -30; echo '==='; dmesg | tail -50" > "$DIAG_DIR/logs.txt"

TAR_FILE="/tmp/n1-diag-${TIMESTAMP}.tar.gz"
tar -czf "$TAR_FILE" -C /tmp "n1-diag-${TIMESTAMP}" 2>/dev/null
rm -rf "$DIAG_DIR"

echo ""
echo "诊断信息已打包: $TAR_FILE"
echo "文件大小: $(du -h "$TAR_FILE" | cut -f1)"