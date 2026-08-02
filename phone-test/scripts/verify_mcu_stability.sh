#!/bin/bash
####################################################################################
# N1 MCU稳定性验证脚本 — 30分钟零断连测试
# 验证WiFi禁用后USB/MCU是否稳定（无brcmfmac中断风暴干扰）
#
# 用法: bash verify_mcu_stability.sh [--duration MINUTES] [--interval SECONDS]
# 示例: bash verify_mcu_stability.sh --duration 30 --interval 5
# 快速验证: bash verify_mcu_stability.sh --duration 1
####################################################################################

DURATION_MIN=30
INTERVAL_SEC=5

while [ $# -gt 0 ]; do
    case "$1" in
        --duration) DURATION_MIN="$2"; shift 2 ;;
        --interval) INTERVAL_SEC="$2"; shift 2 ;;
        *) echo "未知参数: $1"; exit 1 ;;
    esac
done

TOTAL_CHECKS=$((DURATION_MIN * 60 / INTERVAL_SEC))
FAIL_COUNT=0
PASS_COUNT=0
XHCI_ERROR_COUNT=0
MCU_LOST_COUNT=0
KLIPPY_FAIL_COUNT=0
START_TIME=$(date +%s)

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "================================================"
echo "  MCU稳定性验证"
echo "  时长: ${DURATION_MIN}分钟"
echo "  间隔: ${INTERVAL_SEC}秒"
echo "  总检查次数: ${TOTAL_CHECKS}"
echo "  开始时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "================================================"
echo ""

# 预检查
MCU_DEVICE=$(ls /dev/serial/by-id/ 2>/dev/null | grep Klipper | head -1)
if [ -z "$MCU_DEVICE" ]; then
    echo -e "${RED}[ERROR] MCU未检测到! 请检查USB连接${NC}"
    exit 1
fi
echo -e "${GREEN}[OK]${NC} MCU: $MCU_DEVICE"

KLIPPY_STATE=$(curl -s http://localhost:7125/server/info 2>&1 | grep -oP '"klippy_state":"\K[^"]+' || echo "unknown")
if [ "$KLIPPY_STATE" != "ready" ]; then
    echo -e "${RED}[ERROR] Klipper状态: $KLIPPY_STATE (期望: ready)${NC}"
    exit 1
fi
echo -e "${GREEN}[OK]${NC} Klipper: $KLIPPY_STATE"

AUTOSUSPEND=$(cat /sys/module/usbcore/parameters/autosuspend 2>/dev/null || echo "?")
echo -e "${GREEN}[OK]${NC} autosuspend: $AUTOSUSPEND"

RFKILL=$(rfkill list 2>/dev/null | grep -A2 wlan | grep "Soft blocked" | awk '{print $3}')
NM_WIFI=$(nmcli radio wifi 2>/dev/null)
echo -e "${GREEN}[OK]${NC} WiFi: rfkill=$RFKILL nmcli=$NM_WIFI"

echo ""
echo "开始验证..."

for i in $(seq 1 $TOTAL_CHECKS); do
    NOW=$(date +%s)
    ELAPSED=$((NOW - START_TIME))
    ELAPSED_MIN=$((ELAPSED / 60))
    ELAPSED_SEC=$((ELAPSED % 60))
    PROGRESS=$(printf "%3d/%d" "$i" "$TOTAL_CHECKS")

    # 检查1: MCU串口可达性
    MCU_CHECK=$(ls /dev/serial/by-id/ 2>/dev/null | grep -c Klipper)
    if [ "$MCU_CHECK" -eq 0 ]; then
        MCU_LOST_COUNT=$((MCU_LOST_COUNT + 1))
        FAIL_COUNT=$((FAIL_COUNT + 1))
        echo -e "${RED}[$PROGRESS] ${ELAPSED_MIN}m${ELAPSED_SEC}s MCU丢失! (累计${MCU_LOST_COUNT}次)${NC}"
        dmesg | tail -20 | grep -iE "usb|xhci|mcu" >> /root/verify_mcu_diag.log 2>/dev/null || true
    fi

    # 检查2: dmesg XHCI错误
    XHCI_ERR=$(dmesg | tail -30 | grep -ciE 'xHCI.*not responding|HC died|Timeout.*setup|device not accepting address.*error -62' 2>/dev/null || echo "0")
    if [ "$XHCI_ERR" -gt 0 ]; then
        XHCI_ERROR_COUNT=$((XHCI_ERROR_COUNT + 1))
        echo -e "${YELLOW}[$PROGRESS] ${ELAPSED_MIN}m${ELAPSED_SEC}s XHCI错误检测 (累计${XHCI_ERROR_COUNT}次)${NC}"
    fi

    # 检查3: Klipper连接状态
    KLIPPY=$(curl -s http://localhost:7125/server/info 2>&1 | grep -oP '"klippy_state":"\K[^"]+' || echo "error")
    if [ "$KLIPPY" != "ready" ]; then
        KLIPPY_FAIL_COUNT=$((KLIPPY_FAIL_COUNT + 1))
        FAIL_COUNT=$((FAIL_COUNT + 1))
        echo -e "${RED}[$PROGRESS] ${ELAPSED_MIN}m${ELAPSED_SEC}s Klipper=$KLIPPY (累计${KLIPPY_FAIL_COUNT}次)${NC}"
    fi

    # 正常状态 — 每60次(5分钟)输出一次
    if [ "$MCU_CHECK" -gt 0 ] && [ "$KLIPPY" = "ready" ]; then
        PASS_COUNT=$((PASS_COUNT + 1))
        if [ $((i % 60)) -eq 0 ] || [ "$i" -eq "$TOTAL_CHECKS" ]; then
            echo -e "${GREEN}[$PROGRESS] ${ELAPSED_MIN}m${ELAPSED_SEC}s OK (MCU✓ Klippy✓)${NC}"
        fi
    fi

    # 非最后一次则等待
    [ "$i" -lt "$TOTAL_CHECKS" ] && sleep $INTERVAL_SEC
done

# 结果汇总
END_TIME=$(date +%s)
TOTAL_ELAPSED=$((END_TIME - START_TIME))
TOTAL_MIN=$((TOTAL_ELAPSED / 60))
TOTAL_SEC=$((TOTAL_ELAPSED % 60))

echo ""
echo "================================================"
echo "  验证结果"
echo "  时长: ${TOTAL_MIN}m${TOTAL_SEC}s"
echo "  通过: ${PASS_COUNT}/${TOTAL_CHECKS}"
echo "  MCU丢失: ${MCU_LOST_COUNT}次"
echo "  XHCI错误: ${XHCI_ERROR_COUNT}次"
echo "  Klipper异常: ${KLIPPY_FAIL_COUNT}次"
echo "  总失败: ${FAIL_COUNT}次"
echo "================================================"

RESULT_FILE="/root/verify_result.txt"
cat > "$RESULT_FILE" << EOF
VERIFY_TIME=$(date '+%Y-%m-%d %H:%M:%S')
VERIFY_DURATION_MIN=$DURATION_MIN
VERIFY_TOTAL_CHECKS=$TOTAL_CHECKS
VERIFY_PASSED=$PASS_COUNT
VERIFY_FAILED=$FAIL_COUNT
VERIFY_MCU_LOST=$MCU_LOST_COUNT
VERIFY_XHCI_ERRORS=$XHCI_ERROR_COUNT
VERIFY_KLIPPY_FAIL=$KLIPPY_FAIL_COUNT
VERIFY_RESULT=$([ "$FAIL_COUNT" -eq 0 ] && echo "PASS" || echo "FAIL")
EOF

if [ "$FAIL_COUNT" -eq 0 ]; then
    echo -e "${GREEN}✅ 验证通过! ${DURATION_MIN}分钟零断连${NC}"
    exit 0
else
    echo -e "${RED}❌ 验证失败! 共${FAIL_COUNT}次异常${NC}"
    echo "诊断日志: /root/verify_mcu_diag.log"
    exit 1
fi