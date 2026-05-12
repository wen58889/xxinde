#!/bin/bash
####################################################################################
# 批量部署脚本 — 从总控服务器远程部署到多台N1盒子
# 两步部署流程:
#   Phase 1: 上传并执行 n1_network.sh (配置IP+MAC+hostname，不立即生效)
#            然后远程 reboot，等待重启完成
#   Phase 2: 用新IP重新SSH，上传并执行 n1_deploy.sh (安装软件+服务)
#
# 用法: ./batch_deploy.sh
# 交互式输入每台N1的IP和蓝牙MAC，逐台远程执行
####################################################################################

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_ask()   { echo -e "${BOLD}${CYAN}$1${NC}"; }

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
NETWORK_SCRIPT="$SCRIPT_DIR/n1_network.sh"
DEPLOY_SCRIPT="$SCRIPT_DIR/n1_deploy.sh"
SSH_USER="root"
SSH_PASS="1234"
REBOOT_WAIT=45

if ! command -v sshpass &>/dev/null; then
    log_warn "sshpass 未安装，尝试安装..."
    if command -v apt &>/dev/null; then
        sudo apt install -y sshpass 2>/dev/null
    elif command -v yum &>/dev/null; then
        sudo yum install -y sshpass 2>/dev/null
    fi
    if ! command -v sshpass &>/dev/null; then
        log_error "无法安装 sshpass，请手动安装后重试"
        exit 1
    fi
fi

if [ ! -f "$NETWORK_SCRIPT" ]; then
    log_error "找不到 n1_network.sh，请确保与 batch_deploy.sh 在同一目录"
    exit 1
fi
if [ ! -f "$DEPLOY_SCRIPT" ]; then
    log_error "找不到 n1_deploy.sh，请确保与 batch_deploy.sh 在同一目录"
    exit 1
fi

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║        N1 批量部署工具 (两步流程)                        ║${NC}"
echo -e "${BOLD}║  Phase 1: n1_network.sh → 重启                           ║${NC}"
echo -e "${BOLD}║  Phase 2: n1_deploy.sh (软件部署)                        ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""

log_ask "请输入N1设备当前IP列表，空格分隔 (如 192.168.5.101 192.168.5.102 ...):"
read -r IP_LIST

if [ -z "$IP_LIST" ]; then
    log_ask "或者输入起始IP和数量 (如 192.168.5.101 22):"
    read -r START_IP COUNT
    if [ -n "$START_IP" ] && [ -n "$COUNT" ]; then
        IP_PREFIX=$(echo "$START_IP" | cut -d. -f1-3)
        START_NUM=$(echo "$START_IP" | cut -d. -f4)
        IP_LIST=""
        for i in $(seq 1 "$COUNT"); do
            NUM=$((START_NUM + i - 1))
            IP_LIST="$IP_LIST ${IP_PREFIX}.${NUM}"
        done
    else
        log_error "未输入IP，退出"
        exit 1
    fi
fi

log_ask "N1设备新IP是否与当前IP相同? (相同则直接回车; 不同则输入新IP前缀) [默认: 相同]:"
read -r NEW_IP_PREFIX
# 如果用户输入了新前缀如 192.168.5，则新IP为前缀+原IP最后一段
# 否则新IP=当前IP

log_ask "所有N1设备SSH密码是否相同? [默认: 1234]:"
read -r SSH_PASS
SSH_PASS=${SSH_PASS:-1234}

log_ask "重启等待时间(秒) [默认: $REBOOT_WAIT]:"
read -r REBOOT_INPUT
REBOOT_WAIT=${REBOOT_INPUT:-$REBOOT_WAIT}

echo ""
log_info "将部署到以下设备:"
for ip in $IP_LIST; do
    if [ -n "$NEW_IP_PREFIX" ]; then
        NUM=$(echo "$ip" | cut -d. -f4)
        NEW_IP="${NEW_IP_PREFIX}.${NUM}"
        echo "  - $ip → $NEW_IP"
    else
        echo "  - $ip"
    fi
done
echo ""

log_ask "确认开始批量部署? [Y/n]:"
read -r CONFIRM
CONFIRM=${CONFIRM:-Y}
if [ "$CONFIRM" != "Y" ] && [ "$CONFIRM" != "y" ]; then
    log_error "用户取消"
    exit 0
fi

RESULT_FILE="$SCRIPT_DIR/batch_deploy_result_$(date '+%Y%m%d_%H%M%S').txt"
echo "批量部署结果 - $(date)" > "$RESULT_FILE"

TOTAL=0
PHASE1_OK=0
PHASE2_OK=0
FAILED=0

ssh_cmd() {
    sshpass -p "$SSH_PASS" ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no "$SSH_USER@$1" "$2" 2>&1
}

scp_file() {
    sshpass -p "$SSH_PASS" scp -o StrictHostKeyChecking=no "$1" "$SSH_USER@$2:$3" 2>&1
}

wait_for_reboot() {
    local ip=$1
    local wait=$2
    log_info "等待N1重启... (最多${wait}秒)"
    sleep 10
    for i in $(seq 1 $((wait / 5))); do
        if sshpass -p "$SSH_PASS" ssh -o ConnectTimeout=3 -o StrictHostKeyChecking=no "$SSH_USER@$ip" "echo OK" >/dev/null 2>&1; then
            log_info "N1已重启完成 (第$((i * 5))秒)"
            sleep 3
            return 0
        fi
        sleep 5
    done
    log_error "等待重启超时 (${wait}秒)"
    return 1
}

for ip in $IP_LIST; do
    TOTAL=$((TOTAL+1))
    echo ""
    log_info "==================================================================="
    log_info "部署第 $TOTAL 台: $ip"
    log_info "==================================================================="

    # 计算新IP
    if [ -n "$NEW_IP_PREFIX" ]; then
        NUM=$(echo "$ip" | cut -d. -f4)
        NEW_IP="${NEW_IP_PREFIX}.${NUM}"
    else
        NEW_IP="$ip"
    fi

    ####################################################################################
    # Phase 1: 网络配置 + 重启
    ####################################################################################
    echo ""
    log_info "--- Phase 1: 网络配置 (n1_network.sh) ---"

    log_info "测试SSH连通 ($ip)..."
    if ! ssh_cmd "$ip" "echo OK" >/dev/null 2>&1; then
        log_error "SSH连接失败: $ip，跳过"
        echo "$ip: SSH_FAIL" >> "$RESULT_FILE"
        FAILED=$((FAILED+1))
        continue
    fi
    log_info "SSH连接成功"

    log_info "上传 n1_network.sh ..."
    if ! scp_file "$NETWORK_SCRIPT" "$ip" "/tmp/n1_network.sh" >/dev/null 2>&1; then
        log_error "上传失败: $ip，跳过"
        echo "$ip: SCP_FAIL" >> "$RESULT_FILE"
        FAILED=$((FAILED+1))
        continue
    fi

    log_ask "自动执行 n1_network.sh? (需要输入IP/MAC等参数) [Y/n]:"
    read -r AUTO_NETWORK
    AUTO_NETWORK=${AUTO_NETWORK:-Y}

    if [ "$AUTO_NETWORK" = "Y" ] || [ "$AUTO_NETWORK" = "y" ]; then
        log_info "远程执行 n1_network.sh (交互式)..."
        ssh_cmd "$ip" "chmod +x /tmp/n1_network.sh && bash /tmp/n1_network.sh"
        if [ $? -ne 0 ]; then
            log_error "n1_network.sh 执行失败: $ip"
            echo "$ip: NETWORK_FAIL" >> "$RESULT_FILE"
            FAILED=$((FAILED+1))
            continue
        fi
    else
        log_info "请手动登录 $ip 执行: ssh $SSH_USER@$ip"
        log_info "然后运行: bash /tmp/n1_network.sh"
        log_ask "完成后按回车继续..."
        read -r
    fi

    log_info "发送重启命令..."
    ssh_cmd "$ip" "reboot" >/dev/null 2>&1 || true

    log_info "等待 $NEW_IP 重启..."
    if ! wait_for_reboot "$NEW_IP" "$REBOOT_WAIT"; then
        log_error "重启后无法连接: $NEW_IP"
        echo "$ip: REBOOT_FAIL" >> "$RESULT_FILE"
        FAILED=$((FAILED+1))
        continue
    fi
    PHASE1_OK=$((PHASE1_OK+1))
    log_info "Phase 1 完成: 网络已配置，N1已重启"

    ####################################################################################
    # Phase 2: 软件部署
    ####################################################################################
    echo ""
    log_info "--- Phase 2: 软件部署 (n1_deploy.sh) ---"

    log_info "上传 n1_deploy.sh ..."
    if ! scp_file "$DEPLOY_SCRIPT" "$NEW_IP" "/tmp/n1_deploy.sh" >/dev/null 2>&1; then
        log_error "上传失败: $NEW_IP，跳过"
        echo "$ip: DEPLOY_SCP_FAIL" >> "$RESULT_FILE"
        FAILED=$((FAILED+1))
        continue
    fi

    log_ask "自动执行 n1_deploy.sh? (需要输入蓝牙MAC/MCU串口等) [Y/n]:"
    read -r AUTO_DEPLOY
    AUTO_DEPLOY=${AUTO_DEPLOY:-Y}

    if [ "$AUTO_DEPLOY" = "Y" ] || [ "$AUTO_DEPLOY" = "y" ]; then
        log_info "远程执行 n1_deploy.sh (交互式)..."
        ssh_cmd "$NEW_IP" "chmod +x /tmp/n1_deploy.sh && bash /tmp/n1_deploy.sh"
        DEPLOY_STATUS=$?
    else
        log_info "请手动登录 $NEW_IP 执行: ssh $SSH_USER@$NEW_IP"
        log_info "然后运行: bash /tmp/n1_deploy.sh"
        log_ask "完成后按回车继续..."
        read -r
        DEPLOY_STATUS=0
    fi

    if [ $DEPLOY_STATUS -eq 0 ]; then
        MK_HTTP=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 "http://$NEW_IP:7125/server/info" 2>/dev/null || echo "000")
        if [ "$MK_HTTP" = "200" ]; then
            log_info "$NEW_IP: ✅ 部署成功 (Moonraker可达)"
            echo "$ip→$NEW_IP: OK" >> "$RESULT_FILE"
            PHASE2_OK=$((PHASE2_OK+1))
        else
            log_warn "$NEW_IP: 部署完成但Moonraker暂不可达 (可能需要重启)"
            echo "$ip→$NEW_IP: DEPLOYED_BUT_MOONRAKER_UNREACHABLE" >> "$RESULT_FILE"
            PHASE2_OK=$((PHASE2_OK+1))
        fi
    else
        log_error "$NEW_IP: ❌ 部署失败 (exit=$DEPLOY_STATUS)"
        echo "$ip→$NEW_IP: DEPLOY_FAIL" >> "$RESULT_FILE"
        FAILED=$((FAILED+1))
    fi
done

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║              批量部署完成!                               ║${NC}"
echo -e "${BOLD}╠══════════════════════════════════════════════════════════╣${NC}"
echo -e "${BOLD}║  总计:      $TOTAL 台                                    ║${NC}"
echo -e "${BOLD}║  Phase1 OK: $PHASE1_OK 台 (网络配置+重启)               ║${NC}"
echo -e "${BOLD}║  Phase2 OK: $PHASE2_OK 台 (软件部署)                    ║${NC}"
echo -e "${BOLD}║  失败:      $FAILED 台                                  ║${NC}"
echo -e "${BOLD}║  结果文件:  $RESULT_FILE           ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════════════════╝${NC}"
