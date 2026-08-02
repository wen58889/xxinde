#!/bin/bash
####################################################################################
# N1 有线链路监控服务 — 链路状态检测 + 自动重连 + 静态ARP + 抖动防抖 + 优雅降级
#
# 用法: /usr/local/bin/link-monitor.sh (由systemd service运行)
####################################################################################

source /usr/local/bin/alert-push.sh 2>/dev/null || true

LINK_CHECK_INTERVAL=5
LINK_RECONNECT_MAX_RETRIES=3
LINK_RECONNECT_INTERVAL=5
LINK_ERROR_THRESHOLD=100
LINK_FLAPPING_THRESHOLD=3
LINK_FLAPPING_WINDOW=30
NETWORK_DOWN_NOTIFY_THRESHOLD=10
STATIC_ARP_CHECK_INTERVAL=60

IFACE=$(cat /etc/n1-fixed-iface 2>/dev/null || echo "eth0")
[ -e "/sys/class/net/$IFACE" ] || IFACE="eth0"

GATEWAY_IP="192.168.5.1"
SERVER_IP=$(grep '^SERVER_IP=' /etc/n1_network_info.txt 2>/dev/null | cut -d= -f2)
SERVER_IP=${SERVER_IP:-192.168.5.8}

link_down_since=0
flap_count=0
flap_times=""
last_arp_check=0
prev_rx_errors=0
prev_tx_errors=0
prev_rx_drops=0
prev_tx_drops=0

get_link_status() {
    ethtool "$IFACE" 2>/dev/null | grep "Link detected" | awk '{print $3}'
}

get_link_speed() {
    ethtool "$IFACE" 2>/dev/null | grep "Speed:" | awk '{print $2}'
}

get_error_stats() {
    local stats=$(ip -s link show "$IFACE" 2>/dev/null)
    rx_errors=$(echo "$stats" | grep -A1 "RX:" | tail -1 | awk '{print $2}')
    tx_errors=$(echo "$stats" | grep -A1 "TX:" | tail -1 | awk '{print $2}')
    rx_drops=$(echo "$stats" | grep -A1 "RX:" | tail -1 | awk '{print $3}')
    tx_drops=$(echo "$stats" | grep -A1 "TX:" | tail -1 | awk '{print $3}')
    rx_errors=${rx_errors:-0}
    tx_errors=${tx_errors:-0}
    rx_drops=${rx_drops:-0}
    tx_drops=${tx_drops:-0}
}

setup_static_arp() {
    local gateway_mac=$(ip neigh show "$GATEWAY_IP" 2>/dev/null | grep -oP 'lladdr \K[0-9a-f:]+' | head -1)
    local server_mac=$(ip neigh show "$SERVER_IP" 2>/dev/null | grep -oP 'lladdr \K[0-9a-f:]+' | head -1)

    if [ -n "$gateway_mac" ]; then
        ip neigh del "$GATEWAY_IP" dev "$IFACE" 2>/dev/null || true
        ip neigh add "$GATEWAY_IP" lladdr "$gateway_mac" dev "$IFACE" nud perm 2>/dev/null || \
        ip neigh change "$GATEWAY_IP" lladdr "$gateway_mac" dev "$IFACE" nud perm 2>/dev/null || true
    fi

    if [ -n "$server_mac" ] && [ "$SERVER_IP" != "$GATEWAY_IP" ]; then
        ip neigh del "$SERVER_IP" dev "$IFACE" 2>/dev/null || true
        ip neigh add "$SERVER_IP" lladdr "$server_mac" dev "$IFACE" nud perm 2>/dev/null || \
        ip neigh change "$SERVER_IP" lladdr "$server_mac" dev "$IFACE" nud perm 2>/dev/null || true
    fi
}

try_reconnect() {
    local retries=0
    local con_name=$(nmcli -t -f NAME,DEVICE con show --active 2>/dev/null | grep "$IFACE" | head -1 | cut -d: -f1)

    while [ "$retries" -lt "$LINK_RECONNECT_MAX_RETRIES" ]; do
        logger -t link-monitor "Reconnect attempt $((retries+1))/$LINK_RECONNECT_MAX_RETRIES"
        if [ -n "$con_name" ]; then
            nmcli con up "$con_name" 2>/dev/null && return 0
        else
            ip link set dev "$IFACE" up 2>/dev/null || true
            sleep 3
            get_link_status | grep -q "yes" && return 0
        fi
        retries=$((retries + 1))
        sleep "$LINK_RECONNECT_INTERVAL"
    done
    return 1
}

notify_network_down() {
    type alert_push &>/dev/null && alert_push "network_down" "critical" "Network link down on $IFACE for ${1}s"
    curl -s -m 3 -X POST http://localhost:7125/server/info 2>/dev/null | grep -q "klippy_state" && \
    logger -t link-monitor "Network down: requesting test pause via Moonraker"
}

notify_network_up() {
    type alert_push &>/dev/null && alert_resolved "network_down" "$1"
    logger -t link-monitor "Network up after ${1}s downtime"
}

check_flapping() {
    local now=$(date +%s)
    flap_times="${flap_times}${now} "

    local recent=""
    for t in $flap_times; do
        local elapsed=$((now - t))
        [ "$elapsed" -le "$LINK_FLAPPING_WINDOW" ] && recent="${recent}${t} "
    done
    flap_times="$recent"

    local count=$(echo $flap_times | wc -w)
    if [ "$count" -ge "$LINK_FLAPPING_THRESHOLD" ]; then
        logger -t link-monitor "Link flapping detected ($count changes in ${LINK_FLAPPING_WINDOW}s)"
        type alert_push &>/dev/null && alert_push "link_flapping" "warning" "Link flapping on $IFACE: $count changes in ${LINK_FLAPPING_WINDOW}s"
        flap_times=""
        return 0
    fi
    return 1
}

logger -t link-monitor "Starting link monitor for $IFACE (interval=${LINK_CHECK_INTERVAL}s)"

get_error_stats
prev_rx_errors=$rx_errors
prev_tx_errors=$tx_errors
prev_rx_drops=$rx_drops
prev_tx_drops=$tx_drops

while true; do
    sleep "$LINK_CHECK_INTERVAL"

    link_status=$(get_link_status)
    now=$(date +%s)

    if [ "$link_status" = "yes" ]; then
        if [ "$link_down_since" -gt 0 ]; then
            downtime=$((now - link_down_since))
            check_flapping
            notify_network_up "$downtime"
            link_down_since=0
            logger -t link-monitor "Link recovered after ${downtime}s"
        fi

        get_error_stats
        rx_delta=$((rx_errors - prev_rx_errors))
        tx_delta=$((tx_errors - prev_tx_errors))
        rd_delta=$((rx_drops - prev_rx_drops))
        td_delta=$((tx_drops - prev_tx_drops))
        total_delta=$((rx_delta + tx_delta + rd_delta + td_delta))

        if [ "$total_delta" -gt "$LINK_ERROR_THRESHOLD" ]; then
            logger -t link-monitor "High error rate: RX_ERR=+$rx_delta TX_ERR=+$tx_delta RX_DROP=+$rd_delta TX_DROP=+$td_delta"
            type alert_push &>/dev/null && alert_push "link_errors" "warning" "High error rate on $IFACE: +$total_delta errors in ${LINK_CHECK_INTERVAL}s"
        fi
        prev_rx_errors=$rx_errors
        prev_tx_errors=$tx_errors
        prev_rx_drops=$rx_drops
        prev_tx_drops=$tx_drops

        if [ $((now - last_arp_check)) -ge "$STATIC_ARP_CHECK_INTERVAL" ]; then
            setup_static_arp
            last_arp_check=$now
        fi
    else
        if [ "$link_down_since" -eq 0 ]; then
            link_down_since=$now
            logger -t link-monitor "Link down detected on $IFACE"
            check_flapping
        fi

        downtime=$((now - link_down_since))

        if [ "$downtime" -ge "$NETWORK_DOWN_NOTIFY_THRESHOLD" ] && [ $((downtime % NETWORK_DOWN_NOTIFY_THRESHOLD)) -eq 0 ]; then
            notify_network_down "$downtime"
        fi

        if ! check_flapping; then
            try_reconnect || true
        fi
    fi
done