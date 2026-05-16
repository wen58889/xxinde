#!/bin/bash
# ============================================================
# N1 设备稳定性长期监控脚本
# 用途: 从总控端通过 HTTP API 持续监控 N1 设备
# 使用: ./n1_stability_monitor.sh [设备IP列表]
# 示例: ./n1_stability_monitor.sh 192.168.5.101 192.168.5.102
# ============================================================

DEVICES=("${@:-192.168.5.101 192.168.5.102}")
MOONRAKER_PORT=7125
GO2RTC_PORT=1984
FLUIDD_PORT=8080
INTERVAL=30
G28_EVERY=10
LOG_DIR="./stability_logs"
TMP="/tmp/n1_monitor"

mkdir -p "$LOG_DIR" "$TMP"

TS=$(date +%Y%m%d_%H%M%S)
MAIN_LOG="$LOG_DIR/monitor_${TS}.log"
CSV="$LOG_DIR/summary_${TS}.csv"

echo "timestamp,ip,status,mcu,latency_ms,camera,fluidd,g28,errors" > "$CSV"

for ip in "${DEVICES[@]}"; do
    eval "ERR_$ip=0; SHUT_$ip=0; G28F_$ip=0"
done

CYCLE=0
TOTAL_ERR=0

echo ""
echo "=========================================="
echo "  N1 稳定性监控"
echo "  设备: ${DEVICES[*]}"
echo "  间隔: ${INTERVAL}s | G28每${G28_EVERY}轮"
echo "  日志: ${MAIN_LOG}"
echo "  CSV:  ${CSV}"
echo "=========================================="
echo ""

while true; do
    CYCLE=$((CYCLE + 1))
    DO_G28=0
    [ $((CYCLE % G28_EVERY)) -eq 0 ] && DO_G28=1

    for ip in "${DEVICES[@]}"; do
        NOW=$(date '+%Y-%m-%d %H:%M:%S')
        ST="HEALTHY"
        MCU="UNKNOWN"
        LAT=0
        CAM="NO"
        FLU="NO"
        G28="N/A"
        ERR=""

        T1=$(date +%s%N | sed 's/......$//')

        MF="$TMP/m_${ip}.json"
        curl -sf --connect-timeout 3 --max-time 5 "http://${ip}:${MOONRAKER_PORT}/server/info" -o "$MF" 2>/dev/null
        MRC=$?

        T2=$(date +%s%N | sed 's/......$//')
        LAT=$((T2 - T1))

        if [ $MRC -eq 0 ] && [ -s "$MF" ]; then
            MCU=$(jq -r '.result.klippy_state // "unknown"' "$MF" 2>/dev/null) || MCU="err"
            if [ "$MCU" != "ready" ]; then
                ST="UNHEALTHY"; ERR="${ERR}MCU:${MCU};"
            fi
        else
            MCU="OFFLINE"; ST="OFFLINE"; ERR="${ERR}Moonraker:OFF;"
        fi

        CF="$TMP/c_${ip}.json"
        curl -sf --connect-timeout 3 --max-time 5 "http://${ip}:${GO2RTC_PORT}/api/streams" -o "$CF" 2>/dev/null
        CRC=$?
        if [ $CRC -eq 0 ] && [ -s "$CF" ]; then
            CK=$(jq -r 'if has("camera0") then "Y" elif (.|length)>0 then "A" else "E" end' "$CF" 2>/dev/null) || CK="E"
            if [ "$CK" = "Y" ] || [ "$CK" = "A" ]; then
                CAM="YES"
            else
                ERR="${ERR}CAM:${CK};"; [ "$ST" = "HEALTHY" ] && ST="DEGRADED"
            fi
        else
            ERR="${ERR}CAM:OFF;"; [ "$ST" = "HEALTHY" ] && ST="DEGRADED"
        fi

        FC=$(curl -sf -o /dev/null -w "%{http_code}" --connect-timeout 3 --max-time 5 "http://${ip}:${FLUIDD_PORT}/" 2>/dev/null) || FC="000"
        if [ "$FC" = "200" ]; then
            FLU="YES"
        else
            ERR="${ERR}FLU:${FC};"; [ "$ST" = "HEALTHY" ] && ST="DEGRADED"
        fi

        if [ "$MCU" = "ready" ] && [ "$DO_G28" = "1" ]; then
            GF="$TMP/g28_${ip}.json"
            curl -sf --connect-timeout 5 --max-time 15 -H "Content-Type: application/json" -d '{"script":"G28"}' "http://${ip}:${MOONRAKER_PORT}/printer/gcode/script" -o "$GF" 2>/dev/null
            GRC=$?
            if [ $GRC -eq 0 ]; then
                G28="YES"
            else
                G28="FAIL"; ERR="${ERR}G28:FAIL;"; [ "$ST" = "HEALTHY" ] && ST="DEGRADED"
            fi
        fi

        if [ "$ST" = "HEALTHY" ]; then
            COL="\033[0;32m"
        elif [ "$ST" = "DEGRADED" ]; then
            COL="\033[1;33m"
        else
            COL="\033[0;31m"
        fi

        LINE=$(printf "\033[0;36m[%s]\033[0m %s %s%s\033[0m MCU=%s(%dms) CAM=%s Flu=%s G28=%s" "$NOW" "$ip" "$COL" "$ST" "$MCU" "$LAT" "$CAM" "$FLU" "$G28")
        [ -n "$ERR" ] && LINE="$LINE err=$ERR"
        echo "$LINE" | tee -a "$MAIN_LOG"

        echo "${NOW},${ip},${ST},${MCU},${LAT},${CAM},${FLU},${G28},${ERR}" >> "$CSV"

        if [ "$ST" != "HEALTHY" ]; then
            eval "ERR_$ip=\$((ERR_$ip + 1))"; TOTAL_ERR=$((TOTAL_ERR + 1))
        fi
        if [ "$MCU" = "shutdown" ]; then
            eval "SHUT_$ip=\$((SHUT_$ip + 1))"
        fi
        if [ "$G28" = "FAIL" ]; then
            eval "G28F_$ip=\$((G28F_$ip + 1))"
        fi
    done

    if [ $((CYCLE % 20)) -eq 0 ] && [ $CYCLE -gt 0 ]; then
        E=$((CYCLE * INTERVAL)); H=$((E / 3600)); M=$(((E % 3600) / 60))
        echo "" | tee -a "$MAIN_LOG"
        echo "--- 第${CYCLE}轮报告 (运行${H}h${M}m) ---" | tee -a "$MAIN_LOG"
        for ip in "${DEVICES[@]}"; do
            eval "e=\$ERR_$ip; s=\$SHUT_$ip; g=\$G28F_$ip"
            a=$(awk "BEGIN{printf \"%.1f\",(1-$e/$CYCLE)*100}")
            echo "  $ip: 错误${e}次 Shutdown${s}次 G28失败${g}次 可用率${a}%" | tee -a "$MAIN_LOG"
        done
        echo "  总错误: ${TOTAL_ERR} / 总检查: $((CYCLE * ${#DEVICES[@]}))" | tee -a "$MAIN_LOG"
        echo "" | tee -a "$MAIN_LOG"
    fi

    sleep "$INTERVAL"
done
