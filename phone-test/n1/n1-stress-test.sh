#!/bin/bash
####################################################################################
# N1 稳定性验证工具 — 7×24验证 / 异常注入 / 压力测试
# 用法:
#   bash n1-stress-test.sh --mode long-run --duration 7 --ip-list ips.txt
#   bash n1-stress-test.sh --mode fault-inject --inject network-down --ip 192.168.5.112
#   bash n1-stress-test.sh --mode stress --duration 1 --ip-list ips.txt
####################################################################################

MODE="long-run"
DURATION=7
IP_LIST=""
TARGET_IP=""
INJECT_TYPE=""
INJECT_DURATION=10
PASSWORD="1234"

while [ $# -gt 0 ]; do
    case "$1" in
        --mode) MODE="$2"; shift 2 ;;
        --duration) DURATION="$2"; shift 2 ;;
        --ip-list) IP_LIST="$2"; shift 2 ;;
        --ip) TARGET_IP="$2"; shift 2 ;;
        --inject) INJECT_TYPE="$2"; shift 2 ;;
        --inject-duration) INJECT_DURATION="$2"; shift 2 ;;
        *) echo "未知参数: $1"; exit 1 ;;
    esac
done

TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
LOG_DIR="./stability_logs/${MODE}-${TIMESTAMP}"
mkdir -p "$LOG_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

get_ips() {
    if [ -n "$IP_LIST" ] && [ -f "$IP_LIST" ]; then
        grep -v '^#' "$IP_LIST" | grep -v '^$'
    elif [ -n "$TARGET_IP" ]; then
        echo "$TARGET_IP"
    else
        echo "192.168.5.101"
    fi
}

check_device_health() {
    local ip=$1
    curl -s -m 5 "http://${ip}:8090/api/health" 2>/dev/null || echo '{"status":"unreachable"}'
}

ssh_exec() {
    local ip=$1
    local cmd=$2
    ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o BatchMode=yes root@$ip "$cmd" 2>/dev/null || \
    sshpass -p $PASSWORD ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 root@$ip "$cmd" 2>/dev/null
}

inject_fault() {
    local ip=$1
    local type=$2
    local duration=$3

    echo -e "${YELLOW}[INJECT] $ip: $type for ${duration}s${NC}"

    case "$type" in
        network-down)
            ssh_exec "$ip" "ip link set eth0 down" 2>/dev/null
            sleep "$duration"
            ssh_exec "$ip" "ip link set eth0 up" 2>/dev/null
            sleep 5
            ;;
        usb-down)
            ssh_exec "$ip" "for port in /sys/bus/usb/devices/*/authorized; do devpath=\$(dirname \$port); devnum=\$(cat \$devpath/devnum 2>/dev/null || echo 0); [ \$devnum = 1 ] && continue; echo 0 > \$port 2>/dev/null; done" 2>/dev/null
            sleep "$duration"
            ssh_exec "$ip" "for port in /sys/bus/usb/devices/*/authorized; do devpath=\$(dirname \$port); devnum=\$(cat \$devpath/devnum 2>/dev/null || echo 0); [ \$devnum = 1 ] && continue; echo 1 > \$port 2>/dev/null; done" 2>/dev/null
            sleep 10
            ;;
        kill-klipper)
            ssh_exec "$ip" "kill -9 \$(pgrep -x klipper) 2>/dev/null || true" 2>/dev/null
            sleep 30
            ;;
        disk-fill)
            ssh_exec "$ip" "dd if=/dev/zero of=/tmp/stress-fill bs=1M count=500 2>/dev/null; sleep $duration; rm -f /tmp/stress-fill" 2>/dev/null
            ;;
        *)
            echo "未知注入类型: $type"
            return 1
            ;;
    esac

    local health=$(check_device_health "$ip")
    local status=$(echo "$health" | grep -oP '"status":"\K[^"]+' || echo "unknown")
    echo -e "${GREEN}[RECOVER] $ip: status=$status${NC}"
    echo "$health" >> "$LOG_DIR/inject-${type}-${ip}.json"
}

mode_long_run() {
    echo "=========================================="
    echo "  7×24小时稳定性验证"
    echo "  时长: ${DURATION}天"
    echo "  开始: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "=========================================="

    local ips=$(get_ips)
    local total_checks=$((DURATION * 24 * 12))
    local check=0
    local failures=0

    while [ "$check" -lt "$total_checks" ]; do
        check=$((check + 1))
        local now=$(date '+%Y-%m-%d %H:%M:%S')

        for ip in $ips; do
            local health=$(check_device_health "$ip")
            local status=$(echo "$health" | grep -oP '"status":"\K[^"]+' || echo "unknown")

            if [ "$status" = "healthy" ]; then
                [ $((check % 12)) -eq 0 ] && echo "[$now] $ip: $status"
            else
                failures=$((failures + 1))
                echo -e "${RED}[$now] $ip: $status (failures=$failures)${NC}"
            fi

            echo "$now|$ip|$status|$health" >> "$LOG_DIR/long-run.log"
        done

        sleep 300
    done

    echo "=========================================="
    echo "  验证完成: failures=$failures"
    echo "=========================================="
}

mode_fault_inject() {
    local ip=$(get_ips | head -1)
    echo "=========================================="
    echo "  异常注入测试"
    echo "  目标: $ip"
    echo "  注入: $INJECT_TYPE"
    echo "  持续: ${INJECT_DURATION}s"
    echo "=========================================="

    local health_before=$(check_device_health "$ip")
    echo "注入前状态: $health_before" | tee "$LOG_DIR/before.json"

    inject_fault "$ip" "$INJECT_TYPE" "$INJECT_DURATION"

    local health_after=$(check_device_health "$ip")
    echo "注入后状态: $health_after" | tee "$LOG_DIR/after.json"

    local status_after=$(echo "$health_after" | grep -oP '"status":"\K[^"]+' || echo "unknown")
    if [ "$status_after" = "healthy" ]; then
        echo -e "${GREEN}✅ 异常注入测试通过: 设备已自动恢复${NC}"
    else
        echo -e "${RED}❌ 异常注入测试失败: 设备状态=$status_after${NC}"
    fi
}

mode_stress() {
    echo "=========================================="
    echo "  压力测试"
    echo "  时长: ${DURATION}天"
    echo "=========================================="

    local ips=$(get_ips)
    local total_checks=$((DURATION * 24 * 12))
    local check=0

    while [ "$check" -lt "$total_checks" ]; do
        check=$((check + 1))
        local now=$(date '+%Y-%m-%d %H:%M:%S')

        for ip in $ips; do
            curl -s -m 5 -X POST "http://${ip}:7125/printer/gcode/help" 2>/dev/null || true
            curl -s -m 5 "http://${ip}:1984/api/frame.jpeg?src=camera0" -o /dev/null 2>/dev/null || true

            local health=$(check_device_health "$ip")
            local status=$(echo "$health" | grep -oP '"status":"\K[^"]+' || echo "unknown")
            local mem=$(echo "$health" | grep -oP '"usage_percent":\K\d+' || echo "0")
            local temp=$(echo "$health" | grep -oP '"cpu_celsius":\K\d+' || echo "0")

            [ $((check % 12)) -eq 0 ] && echo "[$now] $ip: status=$status mem=${mem}% temp=${temp}C"
            echo "$now|$ip|$status|mem=${mem}%|temp=${temp}C" >> "$LOG_DIR/stress.log"
        done

        sleep 300
    done

    echo "压力测试完成"
}

case "$MODE" in
    long-run) mode_long_run ;;
    fault-inject) mode_fault_inject ;;
    stress) mode_stress ;;
    *) echo "未知模式: $MODE (long-run|fault-inject|stress)"; exit 1 ;;
esac