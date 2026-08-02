#!/bin/bash
################################################################################
# 已部署N1设备批量修复脚本 v3.0
# 修复内容:
#   1. USB watchdog v4 (MCU_ID通用匹配 + 冷却防抖 + 最大级别限制)
#   2. USB autosuspend=-1 (运行时+systemd持久化, sysinit阶段最可靠)
#   3. eth0省电修复 (移除speed硬编码, 只做EEE/WoL/PM)
#   4. NM连接属性 (speed=0自由协商)
#   5. wired-watchdog默认禁用
#   6. net-check.service (纯有线版, NM启动后10s检查修复)
#   7. WiFi三层禁用 (rfkill+nmcli+黑名单, 消除brcmfmac中断风暴)
#   8. WiFi服务清理 (禁用wifi-watchdog, 移除WiFi dispatcher/conf)
#   9. rfkill持久化service (重启后自动block wlan)
################################################################################
# 用法: bash fix_deployed_n1.sh [IP1] [IP2] ...
# 示例: bash fix_deployed_n1.sh 192.168.5.101 192.168.5.105 192.168.5.106
# 默认密码: root/1234
################################################################################

PASSWORD="1234"
USER="root"
LOG_PREFIX="[N1-FIX]"

log() { echo "$         LOG_PREFIX $(date +%H:%M:%S) $1"; }
warn() { echo "$LOG_PREFIX $(date +%H:%M:%S) [WARN] $1"; }

fix_device() {
    local IP=$1
    log "========== 修复 $IP =========="

    ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o BatchMode=yes $USER@$IP "echo ok" &>/dev/null
    if [ $? -ne 0 ]; then
        warn "$IP: SSH连接失败, 使用sshpass..."
        if ! command -v sshpass &>/dev/null; then
            warn "$IP: sshpass未安装, 跳过. 安装: apt install sshpass"
            return 1
        fi
        SSH_CMD="sshpass -p $PASSWORD ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 $USER@$IP"
    else
        SSH_CMD="ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 $USER@$IP"
    fi

    $SSH_CMD "echo connected" &>/dev/null || { warn "$IP: SSH连接失败"; return 1; }
    log "$IP: SSH连接成功"

    # ==================== 1. USB watchdog v5 ====================
    log "$IP: [1/9] 修复USB watchdog v5 (告警通知+XHCI预防+Klipper验证)..."
    $SSH_CMD "cat > /usr/local/bin/usb-watchdog.sh << 'WDEOF'
#!/bin/bash
source /usr/local/bin/alert-push.sh 2>/dev/null || true
MCU_ID=\"usb-Klipper\"
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
log() { logger -t usb-watchdog \"\$1\"; }
check_xhci_error() { dmesg | tail -30 | grep -qiE 'HC died|xHCI host controller not responding'; }
check_xhci_timeout() { dmesg | tail -30 | grep -qiE 'Timeout while waiting for setup device|unable to enumerate USB device|device descriptor read.*error -1[12]0|device not accepting address.*error -62'; }
xhci_preventive_reset() {
    for dev in /sys/bus/pci/drivers/xhci_hcd/*/; do
        [ -d \"\$dev\" ] || continue
        dn=\$(basename \"\$dev\")
        echo \"\$dn\" > /sys/bus/pci/drivers/xhci_hcd/unbind 2>/dev/null || true
        sleep 2
        echo \"\$dn\" > /sys/bus/pci/drivers/xhci_hcd/bind 2>/dev/null || true
        sleep 3
    done
}
verify_klippy_ready() {
    local retries=0
    while [ \$retries -lt 6 ]; do
        local state=\$(curl -s -m 3 http://127.0.0.1:7125/server/info 2>/dev/null | grep -oP '\"klippy_state\":\\K[^\"]+' || echo \"\")
        [ \"\$state\" = \"ready\" ] && return 0
        retries=\$((retries + 1))
        sleep 5
    done
    return 1
}
while true; do
    sleep \$CHECK_INTERVAL
    if check_xhci_error; then
        log \"CRITICAL: XHCI HC died! Rebooting\"
        type alert_push &>/dev/null && alert_push \"xhci_died\" \"critical\" \"XHCI host controller died, rebooting\"
        sleep 1; reboot
    fi
    if check_xhci_timeout; then
        XHCI_FAIL_COUNT=\$((XHCI_FAIL_COUNT + 1))
        log \"XHCI timeout (count=\$XHCI_FAIL_COUNT/\$XHCI_REBOOT_THRESHOLD)\"
        if [ \$XHCI_FAIL_COUNT -ge \$XHCI_REBOOT_THRESHOLD ]; then
            type alert_push &>/dev/null && alert_push \"xhci_timeout\" \"critical\" \"XHCI timeout threshold, rebooting\"
            sleep 1; reboot
        fi
    else
        [ \$XHCI_FAIL_COUNT -gt 0 ] && XHCI_FAIL_COUNT=\$((XHCI_FAIL_COUNT - 1))
    fi
    if ls /dev/serial/by-id/ 2>/dev/null | grep -q \"\$MCU_ID\"; then
        if [ \$FAIL_COUNT -gt 0 ]; then
            local dd=0; [ \$MCU_DOWN_SINCE -gt 0 ] && dd=\$(( \$(date +%s) - MCU_DOWN_SINCE ))
            log \"MCU recovered (was down \${dd}s)\"
            type alert_resolved &>/dev/null && alert_resolved \"mcu_disconnected\" \"\$dd\"
            FAIL_COUNT=0; RECOVERY_LEVEL=0; MCU_DOWN_SINCE=0
        fi
        continue
    fi
    FAIL_COUNT=\$((FAIL_COUNT + 1))
    if [ \$MCU_DOWN_SINCE -eq 0 ]; then
        MCU_DOWN_SINCE=\$(date +%s)
        type alert_push &>/dev/null && alert_push \"mcu_disconnected\" \"critical\" \"MCU not detected, starting recovery\"
    fi
    log \"MCU not detected! fail=\$FAIL_COUNT level=\$RECOVERY_LEVEL\"
    if [ \$FAIL_COUNT -ge \$MAX_FAIL ]; then
        NOW=\$(date +%s); ELAPSED=\$((NOW - LAST_RECOVERY))
        if [ \$ELAPSED -lt \$COOLDOWN ]; then log \"Cooldown (\${ELAPSED}s/\${COOLDOWN}s)\"; FAIL_COUNT=0; continue; fi
        if [ \$RECOVERY_LEVEL -ge \$MAX_RECOVERY_LEVEL ]; then
            type alert_push &>/dev/null && alert_push \"mcu_recovery_exhausted\" \"critical\" \"All recovery levels exhausted\"
            log \"Max level\"; FAIL_COUNT=0; sleep 60; continue
        fi
        RECOVERY_LEVEL=\$((RECOVERY_LEVEL + 1)); LAST_RECOVERY=\$NOW
        if [ \$RECOVERY_LEVEL -eq 1 ]; then log \"L1: firmware_restart\"; curl -s -X POST http://127.0.0.1:7125/printer/firmware_restart 2>/dev/null; sleep 5
        elif [ \$RECOVERY_LEVEL -eq 2 ]; then log \"L2: restart klipper\"; systemctl restart klipper 2>/dev/null; sleep 8
        elif [ \$RECOVERY_LEVEL -eq 3 ]; then log \"L3: USB reset\"
            for port in /sys/bus/usb/devices/*/authorized; do devpath=\$(dirname \"\$port\"); devnum=\$(cat \"\$devpath/devnum\" 2>/dev/null || echo \"0\"); [ \"\$devnum\" = \"1\" ] && continue; echo 0 > \"\$port\" 2>/dev/null; sleep 1; echo 1 > \"\$port\" 2>/dev/null; done
            sleep 5; systemctl restart klipper 2>/dev/null; sleep 5
        elif [ \$RECOVERY_LEVEL -eq 4 ]; then log \"L4: xhci preventive reset\"
            xhci_preventive_reset
            systemctl restart klipper moonraker 2>/dev/null; sleep 8
        else log \"L5: reboot\"; type alert_push &>/dev/null && alert_push \"mcu_reboot\" \"critical\" \"MCU recovery L5: full reboot\"; sleep 2; reboot
        fi
        if [ \$RECOVERY_LEVEL -lt \$MAX_RECOVERY_LEVEL ]; then
            if verify_klippy_ready; then log \"Klipper ready after L\$RECOVERY_LEVEL\"
            else log \"Klipper NOT ready after L\$RECOVERY_LEVEL\"; type alert_push &>/dev/null && alert_push \"klipper_not_ready\" \"warning\" \"Klipper not ready after L\$RECOVERY_LEVEL\"; fi
        fi
        FAIL_COUNT=0
    fi
done
WDEOF
chmod +x /usr/local/bin/usb-watchdog.sh
systemctl restart usb-watchdog 2>/dev/null || true" &>/dev/null

    [ $? -eq 0 ] &&     log "$IP: USB watchdog v5 已更新 (告警通知+XHCI预防+Klipper验证)" || warn "$IP: USB watchdog 更新失败"

    # ==================== 2. USB autosuspend (systemd持久化) ====================
    log "$IP: [2/9] 修复USB autosuspend=-1 (systemd持久化)..."

    $SSH_CMD "echo -1 > /sys/module/usbcore/parameters/autosuspend 2>/dev/null || true
for d in /sys/bus/usb/devices/*/power/control; do echo on > \"\$d\" 2>/dev/null; done" &>/dev/null

    $SSH_CMD "cat > /usr/local/bin/usb-autosuspend-fix.sh << 'ASEOF'
#!/bin/bash
echo -1 > /sys/module/usbcore/parameters/autosuspend 2>/dev/null || true
for d in /sys/bus/usb/devices/*/power/control; do echo on > \"\$d\" 2>/dev/null; done
for d in /sys/bus/usb/devices/*/power/autosuspend; do echo -1 > \"\$d\" 2>/dev/null; done
logger -t usb-autosuspend-fix 'autosuspend=-1 + USB PM=on'
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

echo 'options usbcore autosuspend=-1' > /etc/modprobe.d/usb-no-autosuspend.conf 2>/dev/null || true

cat > /etc/udev/rules.d/99-usb-no-autosuspend.rules << 'EOF'
ACTION==\"add\", SUBSYSTEM==\"usb\", ATTR{power/autosuspend}=\"-1\"
ACTION==\"add\", SUBSYSTEM==\"usb\", TEST==\"power/control\", ATTR{power/control}=\"on\"
EOF" &>/dev/null

    AS=$($SSH_CMD "cat /sys/module/usbcore/parameters/autosuspend 2>/dev/null" 2>/dev/null)
    log "$IP: autosuspend=$AS (期望-1)"

    # ==================== 3. eth0省电修复 ====================
    log "$IP: [3/9] 修复eth0省电(移除speed硬编码)..."

    $SSH_CMD "cat > /usr/local/bin/eth0-power-fix.sh << 'PEOF'
#!/bin/bash
sleep 2
IFACE=\$(cat /etc/n1-fixed-iface 2>/dev/null || echo \"eth0\")
[ -e \"/sys/class/net/\$IFACE\" ] || IFACE=\"eth0\"
ethtool --set-eee \$IFACE eee off 2>/dev/null || true
ethtool -s \$IFACE wol d 2>/dev/null || true
echo on > /sys/class/net/\$IFACE/power/control 2>/dev/null || true
logger -t eth0-power-fix \"\$IFACE: EEE off + WoL off + PM on (no speed force)\"
PEOF
chmod +x /usr/local/bin/eth0-power-fix.sh 2>/dev/null || true

cat > /etc/NetworkManager/dispatcher.d/99-eth0-stable.sh << 'DEOF'
#!/bin/bash
IFACE=\"\$1\"
ACTION=\"\$2\"
if [ \"\$IFACE\" = \"eth0\" ] && [ \"\$ACTION\" = \"up\" ]; then
    ethtool --set-eee eth0 eee off 2>/dev/null || true
    ethtool -s eth0 wol d 2>/dev/null || true
    echo on > /sys/class/net/eth0/power/control 2>/dev/null || true
    logger -t eth0-stable \"eth0 up: EEE off + WoL off + PM on (no speed force)\"
fi
DEOF
chmod +x /etc/NetworkManager/dispatcher.d/99-eth0-stable.sh 2>/dev/null || true

LINK=\$(ethtool eth0 2>/dev/null | grep 'Link detected' | awk '{print \$3}')
if [ \"\$LINK\" = \"no\" ]; then
    ethtool -s eth0 autoneg on 2>/dev/null || true
    logger -t n1-fix 'eth0 PHY卡死已恢复(autoneg=on)'
fi" &>/dev/null

    log "$IP: eth0省电已修复"

    # ==================== 4. NM连接属性 ====================
    log "$IP: [4/9] 修复NM speed=0..."
    $SSH_CMD "CON=\$(nmcli -t -f NAME,DEVICE con show --active 2>/dev/null | grep eth0 | head -1 | cut -d: -f1)
if [ -n \"\$CON\" ]; then
    nmcli con mod \"\$CON\" 802-3-ethernet.speed 0 2>/dev/null || true
fi" &>/dev/null
    log "$IP: NM speed=0 已设置"

    # ==================== 5. wired-watchdog禁用 ====================
    log "$IP: [5/9] 禁用wired-watchdog..."
    $SSH_CMD "systemctl disable wired-watchdog 2>/dev/null || true; systemctl stop wired-watchdog 2>/dev/null || true" &>/dev/null
    log "$IP: wired-watchdog已禁用"

    # ==================== 6. net-check.service (纯有线版) ====================
    log "$IP: [6/9] 部署net-check.service (纯有线版)..."

    $SSH_CMD "cat > /usr/local/bin/net-check.sh << 'NETEOF'
#!/bin/bash
sleep 10
echo -1 > /sys/module/usbcore/parameters/autosuspend 2>/dev/null || true
for d in /sys/bus/usb/devices/*/power/control; do echo on > \"\$d\" 2>/dev/null; done
for d in /sys/bus/usb/devices/*/power/autosuspend; do echo -1 > \"\$d\" 2>/dev/null; done
IFACE=\$(cat /etc/n1-fixed-iface 2>/dev/null || echo \"eth0\")
[ -e \"/sys/class/net/\$IFACE\" ] || IFACE=\"eth0\"
ethtool --set-eee \$IFACE eee off 2>/dev/null || true
ethtool -s \$IFACE wol d 2>/dev/null || true
echo on > /sys/class/net/\$IFACE/power/control 2>/dev/null || true
logger -t net-check 'Network integrity check completed (wired-only)'
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
systemctl enable net-check.service 2>/dev/null || true" &>/dev/null

    log "$IP: net-check.service 已部署 (纯有线版)"

    # ==================== 7. WiFi三层禁用 ====================
    log "$IP: [7/9] WiFi三层禁用 (rfkill+nmcli+黑名单)..."

    $SSH_CMD "rfkill block wlan 2>/dev/null || true
nmcli radio wifi off 2>/dev/null || true
echo 'blacklist brcmfmac' > /etc/modprobe.d/brcmfmac.conf" &>/dev/null

    log "$IP: WiFi三层禁用已执行"

    # ==================== 8. WiFi服务清理 ====================
    log "$IP: [8/9] WiFi服务清理..."

    $SSH_CMD "systemctl disable wifi-watchdog 2>/dev/null || true
systemctl stop wifi-watchdog 2>/dev/null || true
rm -f /etc/NetworkManager/dispatcher.d/99-wifi-stability.sh 2>/dev/null || true
rm -f /etc/NetworkManager/conf.d/no-p2p.conf 2>/dev/null || true
rm -f /etc/NetworkManager/conf.d/wifi-no-bgscan.conf 2>/dev/null || true
rm -f /etc/NetworkManager/conf.d/wifi-no-mac-random.conf 2>/dev/null || true" &>/dev/null

    log "$IP: WiFi服务已清理"

    # ==================== 9. rfkill持久化service ====================
    log "$IP: [9/9] 部署rfkill持久化service..."

    $SSH_CMD "cat > /usr/local/bin/rfkill-wifi-block.sh << 'RFEOF'
#!/bin/bash
rfkill block wlan 2>/dev/null || true
logger -t rfkill-wifi-block 'WiFi rfkill block applied'
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
systemctl enable n1-rfkill-persist.service 2>/dev/null || true" &>/dev/null

    log "$IP: rfkill持久化service已部署"

    # ==================== 10. alert-push.sh 告警推送函数库 ====================
    log "$IP: [10/17] 部署alert-push.sh告警推送函数库..."
    $SSH_CMD "cat > /usr/local/bin/alert-push.sh << 'ALERTEOF'
#!/bin/bash
ALERT_DEDUP_DIR=\"/var/run/n1-alert-dedup\"
ALERT_QUEUE_FILE=\"/var/log/n1-alert-queue.log\"
ALERT_QUEUE_MAX=100
ALERT_DEDUP_WINDOW=300
_alert_get_config() {
    [ -f /etc/n1_network_info.txt ] && { SERVER_IP=\$(grep '^SERVER_IP=' /etc/n1_network_info.txt 2>/dev/null | cut -d= -f2); N1_IP=\$(grep '^N1_IP=' /etc/n1_network_info.txt 2>/dev/null | cut -d= -f2); }
    SERVER_IP=\${SERVER_IP:-192.168.5.8}; N1_IP=\${N1_IP:-\$(hostname -I 2>/dev/null | awk '{print \$1}')}; ALERT_PUSH_URL=\"http://\${SERVER_IP}:8080/api/v1/alerts\"
}
alert_push() {
    local at=\"\$1\" al=\"\${2:-info}\" msg=\"\$3\"; [ -z \"\$at\" ] && return 1; _alert_get_config; mkdir -p \"\$ALERT_DEDUP_DIR\" 2>/dev/null || true
    local df=\"\${ALERT_DEDUP_DIR}/\${at}.ts\" now=\$(date +%s)
    if [ -f \"\$df\" ]; then
        local lp=\$(cat \"\$df\" 2>/dev/null | grep -oP '\"last_pushed\":\\K\\d+' || echo 0) cnt=\$(cat \"\$df\" 2>/dev/null | grep -oP '\"count\":\\K\\d+' || echo 0) el=\$((now - lp))
        if [ \"\$el\" -lt \"\$ALERT_DEDUP_WINDOW\" ]; then
            cnt=\$((cnt + 1)); echo \"{\\\"count\\\":\$cnt,\\\"last_pushed\\\":\$lp,\\\"first_timestamp\\\":\$(cat \"\$df\" 2>/dev/null | grep -oP '\"first_timestamp\":\\K\\d+' || echo \$now)}\" > \"\$df\"
            logger -t alert-push \"Dedup: \$at (count=\$cnt)\"; return 0
        fi
    fi
    local ts=\$(date -Iseconds 2>/dev/null || date '+%Y-%m-%dT%H:%M:%S%z')
    local json=\$(printf '{\"device_id\":\"%s\",\"alert_type\":\"%s\",\"alert_level\":\"%s\",\"timestamp\":\"%s\",\"details\":\"%s\"}' \"\$N1_IP\" \"\$at\" \"\$al\" \"\$ts\" \"\$msg\")
    local hc=\$(curl -s -m 5 --connect-timeout 3 -o /dev/null -w \"%{http_code}\" -X POST -H \"Content-Type: application/json\" -d \"\$json\" \"\$ALERT_PUSH_URL\" 2>/dev/null || echo \"000\")
    if [ \"\$hc\" = \"200\" ] || [ \"\$hc\" = \"201\" ] || [ \"\$hc\" = \"204\" ]; then
        echo \"{\\\"count\\\":1,\\\"last_pushed\\\":\$now,\\\"first_timestamp\\\":\$now}\" > \"\$df\"; logger -t alert-push \"Pushed: \$at level=\$al\"; return 0
    else
        logger -t alert-push \"Push failed: \$at http=\$hc\"; echo \"\$json\" >> \"\$ALERT_QUEUE_FILE\" 2>/dev/null || true
        local ql=\$(wc -l < \"\$ALERT_QUEUE_FILE\" 2>/dev/null || echo 0)
        [ \"\$ql\" -gt \"\$ALERT_QUEUE_MAX\" ] && { tail -n \"\$ALERT_QUEUE_MAX\" \"\$ALERT_QUEUE_FILE\" > \"\${ALERT_QUEUE_FILE}.tmp\" 2>/dev/null; mv \"\${ALERT_QUEUE_FILE}.tmp\" \"\$ALERT_QUEUE_FILE\" 2>/dev/null || true; }
        return 1
    fi
}
alert_resolved() {
    local at=\"\$1\" dur=\"\${2:-0}\"; [ -z \"\$at\" ] && return 1; _alert_get_config
    rm -f \"\${ALERT_DEDUP_DIR}/\${at}.ts\" 2>/dev/null || true
    local ts=\$(date -Iseconds 2>/dev/null || date '+%Y-%m-%dT%H:%M:%S%z')
    local json=\$(printf '{\"device_id\":\"%s\",\"alert_type\":\"%s_resolved\",\"alert_level\":\"info\",\"timestamp\":\"%s\",\"duration_seconds\":%s}' \"\$N1_IP\" \"\$at\" \"\$ts\" \"\$dur\")
    local hc=\$(curl -s -m 5 --connect-timeout 3 -o /dev/null -w \"%{http_code}\" -X POST -H \"Content-Type: application/json\" -d \"\$json\" \"\$ALERT_PUSH_URL\" 2>/dev/null || echo \"000\")
    [ \"\$hc\" = \"200\" ] || [ \"\$hc\" = \"201\" ] || [ \"\$hc\" = \"204\" ] && { logger -t alert-push \"Resolved: \$at dur=\${dur}s\"; return 0; } || { echo \"\$json\" >> \"\$ALERT_QUEUE_FILE\" 2>/dev/null || true; return 1; }
}
alert_retry_cached() {
    [ -f \"\$ALERT_QUEUE_FILE\" ] || return 0; _alert_get_config
    local rem=\"\" ret=0 suc=0
    while IFS= read -r line; do
        [ -z \"\$line\" ] && continue
        local hc=\$(curl -s -m 5 --connect-timeout 3 -o /dev/null -w \"%{http_code}\" -X POST -H \"Content-Type: application/json\" -d \"\$line\" \"\$ALERT_PUSH_URL\" 2>/dev/null || echo \"000\")
        [ \"\$hc\" = \"200\" ] || [ \"\$hc\" = \"201\" ] || [ \"\$hc\" = \"204\" ] && suc=\$((suc + 1)) || { rem=\"\${rem}\${line}\"$'\\n'; ret=\$((ret + 1)); }
    done < \"\$ALERT_QUEUE_FILE\"
    [ -n \"\$rem\" ] && printf '%s' \"\$rem\" > \"\$ALERT_QUEUE_FILE\" || rm -f \"\$ALERT_QUEUE_FILE\"
    [ \"\$suc\" -gt 0 ] || [ \"\$ret\" -gt 0 ] && logger -t alert-push \"Retry: suc=\$suc rem=\$ret\"
    return 0
}
ALERTEOF
chmod +x /usr/local/bin/alert-push.sh" &>/dev/null
    log "$IP: alert-push.sh已部署"

    # ==================== 11. link-monitor.service ====================
    log "$IP: [11/17] 部署link-monitor.service..."
    $SSH_CMD "cat > /etc/systemd/system/link-monitor.service << 'EOF'
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
systemctl enable link-monitor 2>/dev/null || true
systemctl start link-monitor 2>/dev/null || true" &>/dev/null
    log "$IP: link-monitor.service已部署"

    # ==================== 12. n1-health-monitor.service ====================
    log "$IP: [12/17] 部署n1-health-monitor.service..."
    $SSH_CMD "cat > /etc/systemd/system/n1-health-monitor.service << 'EOF'
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
systemctl enable n1-health-monitor 2>/dev/null || true
systemctl start n1-health-monitor 2>/dev/null || true" &>/dev/null
    log "$IP: n1-health-monitor.service已部署"

    # ==================== 13. n1-health-api.service ====================
    log "$IP: [13/17] 部署n1-health-api.service (端口8090)..."
    $SSH_CMD "cat > /etc/systemd/system/n1-health-api.service << 'EOF'
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
systemctl enable n1-health-api 2>/dev/null || true
systemctl start n1-health-api 2>/dev/null || true" &>/dev/null
    log "$IP: n1-health-api.service已部署"

    # ==================== 14. n1-diagnose.sh ====================
    log "$IP: [14/17] 部署n1-diagnose.sh..."
    $SSH_CMD "cat > /usr/local/bin/n1-diagnose.sh << 'DEOF'
#!/bin/bash
DIAG_DIR=\"/tmp/n1-diag-\$(date +%Y%m%d_%H%M%S)\"; mkdir -p \"\$DIAG_DIR\"
run() { echo \"=== \$1 ===\" >> \"\$DIAG_DIR/diag.log\"; eval \"\$1\" >> \"\$DIAG_DIR/diag.log\" 2>&1; }
run \"uname -a\"; run \"uptime\"; run \"free -h\"; run \"df -h\"
run \"cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null\"
run \"ip addr show\"; run \"ethtool eth0 2>/dev/null\"
run \"ls /dev/serial/by-id/ 2>/dev/null\"; run \"cat /sys/module/usbcore/parameters/autosuspend\"
run \"systemctl status klipper moonraker go2rtc usb-watchdog n1-health-monitor link-monitor n1-health-api --no-pager 2>/dev/null\" > \"\$DIAG_DIR/services.txt\"
run \"curl -s http://localhost:7125/server/info 2>/dev/null\"
run \"dmesg | tail -50\"; run \"rfkill list 2>/dev/null\"; run \"lsmod | grep brcmfmac\"
tar czf \"/tmp/n1-diag-\$(date +%Y%m%d_%H%M%S).tar.gz\" -C /tmp \"\$(basename \"\$DIAG_DIR\")\" 2>/dev/null
echo \"诊断完成: \$DIAG_DIR\"
DEOF
chmod +x /usr/local/bin/n1-diagnose.sh" &>/dev/null
    log "$IP: n1-diagnose.sh已部署"

    # ==================== 15. 硬件看门狗 ====================
    log "$IP: [15/17] 配置硬件看门狗..."
    $SSH_CMD "if [ -e /dev/watchdog ]; then
    if grep -q '^WatchdogSec=' /etc/systemd/system.conf 2>/dev/null; then
        sed -i 's/^WatchdogSec=.*/WatchdogSec=60/' /etc/systemd/system.conf 2>/dev/null || true
    elif grep -q '^#WatchdogSec=' /etc/systemd/system.conf 2>/dev/null; then
        sed -i 's/^#WatchdogSec=.*/WatchdogSec=60/' /etc/systemd/system.conf 2>/dev/null || true
    else
        echo 'WatchdogSec=60' >> /etc/systemd/system.conf 2>/dev/null || true
    fi
fi" &>/dev/null
    log "$IP: 硬件看门狗已配置"

    # ==================== 16. NTP + logrotate ====================
    log "$IP: [16/17] 配置NTP + logrotate..."
    $SSH_CMD "if command -v timedatectl &>/dev/null; then
    cat > /etc/systemd/timesyncd.conf << 'NTEOF'
[Time]
NTP=ntp.aliyun.com ntp.tencent.com
FallbackNTP=pool.ntp.org
NTEOF
    systemctl enable systemd-timesyncd 2>/dev/null || true
    systemctl start systemd-timesyncd 2>/dev/null || true
fi

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
LREOF" &>/dev/null
    log "$IP: NTP + logrotate已配置"

    # ==================== 17. 重启usb-watchdog (加载alert-push) ====================
    log "$IP: [17/18] 重启usb-watchdog (加载alert-push)..."
    $SSH_CMD "systemctl restart usb-watchdog 2>/dev/null || true" &>/dev/null
    log "$IP: usb-watchdog已重启"

    # ==================== 18. 修复Fluidd WebSocket周期性断连 ====================
    log "$IP: [18/18] 修复Fluidd WebSocket周期性断连 (ping_interval 10s→30s)..."
    $SSH_CMD "if [ -f /root/moonraker/moonraker/components/application.py ]; then
    if grep -q 'websocket_ping_interval.*else 10\.' /root/moonraker/moonraker/components/application.py 2>/dev/null; then
        sed -i \"s/'websocket_ping_interval': None if tornado_ver < (6, 5) else 10\./'websocket_ping_interval': None if tornado_ver < (6, 5) else 30./\" /root/moonraker/moonraker/components/application.py
        systemctl restart moonraker 2>/dev/null || true
        echo FIXED
    else
        echo ALREADY_OK
    fi
else
    echo NO_FILE
fi" &>/dev/null
    log "$IP: Fluidd WebSocket ping_interval已检查/修复"

    # ==================== 验证 ====================
    log "$IP: 验证修复结果..."

    STATE=$($SSH_CMD "curl -s http://localhost:7125/server/info 2>&1 | grep -oP '\"klippy_state\":\"\\K[^\"]+' || echo ERR" 2>/dev/null)
    MCU=$($SSH_CMD "ls /dev/serial/by-id/ 2>/dev/null | grep -c Klipper || echo 0" 2>/dev/null)
    AS=$($SSH_CMD "cat /sys/module/usbcore/parameters/autosuspend 2>/dev/null || echo ?" 2>/dev/null)
    WD=$($SSH_CMD "head -2 /usr/local/bin/usb-watchdog.sh 2>/dev/null | grep -c 'usb-Klipper' || echo 0" 2>/dev/null)
    SVC=$($SSH_CMD "systemctl is-enabled usb-autosuspend-fix 2>/dev/null || echo disabled" 2>/dev/null)
    NC=$($SSH_CMD "systemctl is-enabled net-check 2>/dev/null || echo disabled" 2>/dev/null)
    RFKILL=$($SSH_CMD "rfkill list 2>/dev/null | grep -A2 wlan | grep 'Soft blocked' | awk '{print \$3}' || echo unknown" 2>/dev/null)
    NM_WIFI=$($SSH_CMD "nmcli radio wifi 2>/dev/null || echo unknown" 2>/dev/null)
    WDOG=$($SSH_CMD "systemctl is-enabled wifi-watchdog 2>/dev/null || echo disabled" 2>/dev/null)

    log "$IP: klippy=$STATE | mcu=$MCU | autosuspend=$AS | watchdog_v5=$WD"
    log "$IP: usb-autosuspend-fix=$SVC | net-check=$NC"
    log "$IP: WiFi: rfkill=$RFKILL | nmcli=$NM_WIFI | wifi-watchdog=$WDOG"

    LM=$($SSH_CMD "systemctl is-active link-monitor 2>/dev/null || echo inactive" 2>/dev/null)
    HM=$($SSH_CMD "systemctl is-active n1-health-monitor 2>/dev/null || echo inactive" 2>/dev/null)
    HA=$($SSH_CMD "systemctl is-active n1-health-api 2>/dev/null || echo inactive" 2>/dev/null)
    log "$IP: 工业级: link-monitor=$LM | health-monitor=$HM | health-api=$HA"

    if [ "$STATE" = "ready" ] && [ "$AS" = "-1" ] && [ "$SVC" = "enabled" ] && [ "$RFKILL" = "yes" ]; then
        log "$IP: ✅ 修复成功!"
    else
        warn "$IP: ⚠️ 需要关注 (klippy=$STATE autosuspend=$AS rfkill=$RFKILL)"
    fi

    log "$IP: ========== 完成 =========="
    echo ""
}

# ==================== 主流程 ====================
if [ $# -eq 0 ]; then
    echo "用法: bash fix_deployed_n1.sh <IP1> [IP2] [IP3] ..."
    echo "示例: bash fix_deployed_n1.sh 192.168.5.101 192.168.5.105 192.168.5.106"
    echo ""
    echo "修复内容 (v4.1):"
    echo "  1.  USB watchdog v5 (告警通知+XHCI预防+Klipper双重验证+冷却防抖)"
    echo "  2.  USB autosuspend=-1 (运行时+systemd持久化)"
    echo "  3.  eth0省电修复 (EEE/WoL/PM, 不设speed)"
    echo "  4.  NM连接属性 speed=0 (自由协商)"
    echo "  5.  wired-watchdog默认禁用"
    echo "  6.  net-check.service (纯有线版)"
    echo "  7.  WiFi三层禁用 (rfkill+nmcli+黑名单)"
    echo "  8.  WiFi服务清理"
    echo "  9.  rfkill持久化service"
    echo "  10. alert-push.sh 告警推送函数库"
    echo "  11. link-monitor.service 有线链路监控"
    echo "  12. n1-health-monitor.service 系统资源监控"
    echo "  13. n1-health-api.service 健康状态HTTP API (端口8090)"
    echo "  14. n1-diagnose.sh 一键诊断收集"
    echo "  15. 硬件看门狗配置 (WatchdogSec=60)"
    echo "  16. NTP + logrotate配置"
    echo "  17. 重启usb-watchdog (加载alert-push)"
    echo "  18. 修复Fluidd WebSocket周期性断连 (ping_interval 10s→30s)"
    echo ""
    echo "前提: SSH root免密登录或sshpass已安装"
    exit 1
fi

SUCCESS=0
FAIL=0

for IP in "$@"; do
    fix_device "$IP"
    if [ $? -eq 0 ]; then
        SUCCESS=$((SUCCESS + 1))
    else
        FAIL=$((FAIL + 1))
    fi
done

echo ""
echo "=========================================="
echo "修复完成: 成功=$SUCCESS 失败=$FAIL"
echo "=========================================="
