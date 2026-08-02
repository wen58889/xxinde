#!/bin/bash
####################################################################################
# N1 系统资源监控服务 — 磁盘/内存/温度/服务健康 + 状态缓存 + 告警推送
#
# 用法: /usr/local/bin/n1-health-monitor.sh (由systemd service运行)
####################################################################################

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
last_retry_time=0

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
    if [ ! -f "$temp_file" ]; then
        echo "0"
        return
    fi
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
        if [ "$klippy_fail" -ge "$SERVICE_HTTP_FAILURE_THRESHOLD" ]; then
            if [ "$klippy_fail" -lt "$SERVICE_CRASH_LOOP_THRESHOLD" ]; then
                systemctl restart klipper 2>/dev/null || true
                type alert_push &>/dev/null && alert_push "klipper_unhealthy" "warning" "Klipper state=$klippy_state, restarted"
            else
                type alert_push &>/dev/null && alert_push "klipper_crash_loop" "critical" "Klipper crash loop detected, stopping auto-restart"
            fi
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
    else
        logger -t health-monitor "Hardware watchdog not available (/dev/watchdog not found)"
    fi
}

setup_ntp() {
    if command -v timedatectl &>/dev/null; then
        cat > /etc/systemd/timesyncd.conf << 'EOF'
[Time]
NTP=ntp.aliyun.com ntp.tencent.com
FallbackNTP=pool.ntp.org
EOF
        systemctl enable systemd-timesyncd 2>/dev/null || true
        systemctl start systemd-timesyncd 2>/dev/null || true
        logger -t health-monitor "NTP configured: aliyun + tencent"
    fi
}

setup_logrotate() {
    cat > /etc/logrotate.d/n1-stability << 'EOF'
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
EOF
    logger -t health-monitor "Logrotate configured"
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