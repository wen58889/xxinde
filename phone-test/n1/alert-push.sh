#!/bin/bash
####################################################################################
# N1 告警推送函数库 — 统一告警推送 + 去重 + 本地缓存 + 重试
#
# 用法: source /usr/local/bin/alert-push.sh
#       alert_push "alert_type" "level" "message"
#       alert_resolved "alert_type" duration_seconds
#       alert_retry_cached
####################################################################################

ALERT_DEDUP_DIR="/var/run/n1-alert-dedup"
ALERT_QUEUE_FILE="/var/log/n1-alert-queue.log"
ALERT_QUEUE_MAX=100
ALERT_DEDUP_WINDOW=300

_alert_get_config() {
    if [ -f /etc/n1_network_info.txt ]; then
        SERVER_IP=$(grep '^SERVER_IP=' /etc/n1_network_info.txt 2>/dev/null | cut -d= -f2)
        N1_IP=$(grep '^N1_IP=' /etc/n1_network_info.txt 2>/dev/null | cut -d= -f2)
    fi
    SERVER_IP=${SERVER_IP:-192.168.5.8}
    N1_IP=${N1_IP:-$(hostname -I 2>/dev/null | awk '{print $1}')}
    ALERT_PUSH_URL="http://${SERVER_IP}:8080/api/v1/alerts"
}

alert_push() {
    local alert_type="$1"
    local alert_level="${2:-info}"
    local message="$3"

    [ -z "$alert_type" ] && return 1

    _alert_get_config

    mkdir -p "$ALERT_DEDUP_DIR" 2>/dev/null || true

    local dedup_file="${ALERT_DEDUP_DIR}/${alert_type}.ts"
    local now=$(date +%s)

    if [ -f "$dedup_file" ]; then
        local last_push=$(cat "$dedup_file" 2>/dev/null | grep -oP '"last_pushed":\K\d+' || echo 0)
        local count=$(cat "$dedup_file" 2>/dev/null | grep -oP '"count":\K\d+' || echo 0)
        local elapsed=$((now - last_push))

        if [ "$elapsed" -lt "$ALERT_DEDUP_WINDOW" ]; then
            count=$((count + 1))
            echo "{\"count\":$count,\"last_pushed\":$last_push,\"first_timestamp\":$(cat "$dedup_file" 2>/dev/null | grep -oP '"first_timestamp":\K\d+' || echo $now)}" > "$dedup_file"
            logger -t alert-push "Dedup: $alert_type (count=$count, ${elapsed}s/${ALERT_DEDUP_WINDOW}s)"
            return 0
        fi
    fi

    local timestamp=$(date -Iseconds 2>/dev/null || date '+%Y-%m-%dT%H:%M:%S%z')
    local json=$(printf '{"device_id":"%s","alert_type":"%s","alert_level":"%s","timestamp":"%s","details":"%s"}' \
        "$N1_IP" "$alert_type" "$alert_level" "$timestamp" "$message")

    local http_code=$(curl -s -m 5 --connect-timeout 3 -o /dev/null -w "%{http_code}" \
        -X POST -H "Content-Type: application/json" -d "$json" "$ALERT_PUSH_URL" 2>/dev/null || echo "000")

    if [ "$http_code" = "200" ] || [ "$http_code" = "201" ] || [ "$http_code" = "204" ]; then
        echo "{\"count\":1,\"last_pushed\":$now,\"first_timestamp\":$now}" > "$dedup_file"
        logger -t alert-push "Pushed: $alert_type level=$alert_level"
        return 0
    else
        logger -t alert-push "Push failed: $alert_type http=$http_code, caching locally"
        echo "$json" >> "$ALERT_QUEUE_FILE" 2>/dev/null || true
        local queue_len=$(wc -l < "$ALERT_QUEUE_FILE" 2>/dev/null || echo 0)
        if [ "$queue_len" -gt "$ALERT_QUEUE_MAX" ]; then
            tail -n "$ALERT_QUEUE_MAX" "$ALERT_QUEUE_FILE" > "${ALERT_QUEUE_FILE}.tmp" 2>/dev/null
            mv "${ALERT_QUEUE_FILE}.tmp" "$ALERT_QUEUE_FILE" 2>/dev/null || true
        fi
        return 1
    fi
}

alert_resolved() {
    local alert_type="$1"
    local duration="${2:-0}"

    [ -z "$alert_type" ] && return 1

    _alert_get_config

    local dedup_file="${ALERT_DEDUP_DIR}/${alert_type}.ts"
    rm -f "$dedup_file" 2>/dev/null || true

    local timestamp=$(date -Iseconds 2>/dev/null || date '+%Y-%m-%dT%H:%M:%S%z')
    local json=$(printf '{"device_id":"%s","alert_type":"%s_resolved","alert_level":"info","timestamp":"%s","duration_seconds":%s}' \
        "$N1_IP" "$alert_type" "$timestamp" "$duration")

    local http_code=$(curl -s -m 5 --connect-timeout 3 -o /dev/null -w "%{http_code}" \
        -X POST -H "Content-Type: application/json" -d "$json" "$ALERT_PUSH_URL" 2>/dev/null || echo "000")

    if [ "$http_code" = "200" ] || [ "$http_code" = "201" ] || [ "$http_code" = "204" ]; then
        logger -t alert-push "Resolved: $alert_type duration=${duration}s"
        return 0
    else
        echo "$json" >> "$ALERT_QUEUE_FILE" 2>/dev/null || true
        return 1
    fi
}

alert_retry_cached() {
    [ -f "$ALERT_QUEUE_FILE" ] || return 0

    _alert_get_config

    local remaining=""
    local retried=0
    local succeeded=0

    while IFS= read -r line; do
        [ -z "$line" ] && continue

        local http_code=$(curl -s -m 5 --connect-timeout 3 -o /dev/null -w "%{http_code}" \
            -X POST -H "Content-Type: application/json" -d "$line" "$ALERT_PUSH_URL" 2>/dev/null || echo "000")

        if [ "$http_code" = "200" ] || [ "$http_code" = "201" ] || [ "$http_code" = "204" ]; then
            succeeded=$((succeeded + 1))
        else
            remaining="${remaining}${line}"$'\n'
            retried=$((retried + 1))
        fi
    done < "$ALERT_QUEUE_FILE"

    if [ -n "$remaining" ]; then
        printf '%s' "$remaining" > "$ALERT_QUEUE_FILE"
    else
        rm -f "$ALERT_QUEUE_FILE"
    fi

    [ "$succeeded" -gt 0 ] || [ "$retried" -gt 0 ] && \
        logger -t alert-push "Retry cached: succeeded=$succeeded remaining=$retried"

    return 0
}