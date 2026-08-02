#!/bin/bash
####################################################################################
# N1 批量运维工具
# 用法: bash n1-batch-ops.sh --ip-list <file> --command <command>
# 命令: restart_services|restart_klipper|check_health|deploy_fix
####################################################################################

IP_LIST=""
COMMAND=""
PASSWORD="1234"

while [ $# -gt 0 ]; do
    case "$1" in
        --ip-list) IP_LIST="$2"; shift 2 ;;
        --command) COMMAND="$2"; shift 2 ;;
        *) echo "未知参数: $1"; exit 1 ;;
    esac
done

if [ -z "$IP_LIST" ] || [ -z "$COMMAND" ]; then
    echo "用法: bash n1-batch-ops.sh --ip-list <file> --command <command>"
    echo "命令: restart_services|restart_klipper|check_health|deploy_fix"
    exit 1
fi

[ -f "$IP_LIST" ] || { echo "IP列表文件不存在: $IP_LIST"; exit 1; }

IPS=$(grep -v '^#' "$IP_LIST" | grep -v '^$')

execute_on_device() {
    local IP=$1
    local CMD=$2

    ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o BatchMode=yes root@$IP "echo ok" &>/dev/null
    if [ $? -ne 0 ]; then
        if ! command -v sshpass &>/dev/null; then
            echo "[FAIL] $IP: SSH失败且sshpass未安装"
            return 1
        fi
        SSH_CMD="sshpass -p $PASSWORD ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 root@$IP"
    else
        SSH_CMD="ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 root@$IP"
    fi

    case "$CMD" in
        restart_services)
            $SSH_CMD "systemctl restart klipper moonraker go2rtc 2>/dev/null; echo 'services restarted'" 2>/dev/null
            ;;
        restart_klipper)
            $SSH_CMD "systemctl restart klipper 2>/dev/null; echo 'klipper restarted'" 2>/dev/null
            ;;
        check_health)
            local health=$(curl -s -m 5 "http://${IP}:8090/api/health" 2>/dev/null || echo '{"status":"unreachable"}')
            echo "$IP: $health"
            ;;
        deploy_fix)
            SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
            bash "$SCRIPT_DIR/fix_deployed_n1.sh" "$IP" 2>/dev/null
            ;;
        *)
            $SSH_CMD "$CMD" 2>/dev/null
            ;;
    esac
}

echo "=========================================="
echo "批量运维: $COMMAND"
echo "目标设备: $(echo "$IPS" | wc -l)台"
echo "=========================================="

SUCCESS=0
FAIL=0
RESULTS=""

for IP in $IPS; do
    RESULT=$(execute_on_device "$IP" "$COMMAND" 2>&1)
    if [ $? -eq 0 ]; then
        SUCCESS=$((SUCCESS + 1))
        echo "[OK] $IP: $RESULT"
    else
        FAIL=$((FAIL + 1))
        echo "[FAIL] $IP: $RESULT"
    fi
done

echo ""
echo "=========================================="
echo "完成: 成功=$SUCCESS 失败=$FAIL"
echo "=========================================="