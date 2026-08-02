import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.101', username='root', password='1234', timeout=10)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=10)
    return stdout.read().decode('utf-8', errors='replace')

# Step 1: 修复usb-watchdog — 增加最大恢复级别限制和冷却时间
print("=== Step 1: 修复usb-watchdog ===")
new_watchdog = r'''#!/bin/bash
MCU_ID="usb-Klipper_rp2040"
CHECK_INTERVAL=5
MAX_FAIL=2
FAIL_COUNT=0
RECOVERY_LEVEL=0
MAX_RECOVERY_LEVEL=4
COOLDOWN=300
LAST_RECOVERY=0
log() { logger -t usb-watchdog "$1"; }

while true; do
    sleep $CHECK_INTERVAL
    if ls /dev/serial/by-id/ 2>/dev/null | grep -q "$MCU_ID"; then
        if [ $FAIL_COUNT -gt 0 ]; then log "MCU recovered"; FAIL_COUNT=0; RECOVERY_LEVEL=0; fi
        continue
    fi
    FAIL_COUNT=$((FAIL_COUNT + 1))
    log "MCU not detected! fail=$FAIL_COUNT level=$RECOVERY_LEVEL"
    if [ $FAIL_COUNT -ge $MAX_FAIL ]; then
        NOW=$(date +%s)
        ELAPSED=$((NOW - LAST_RECOVERY))
        if [ $ELAPSED -lt $COOLDOWN ]; then
            log "Cooldown active (${ELAPSED}s/${COOLDOWN}s), skip recovery"
            FAIL_COUNT=0
            continue
        fi
        if [ $RECOVERY_LEVEL -ge $MAX_RECOVERY_LEVEL ]; then
            log "Max recovery level reached, stop trying until MCU reappears"
            FAIL_COUNT=0
            sleep 60
            continue
        fi
        RECOVERY_LEVEL=$((RECOVERY_LEVEL + 1))
        LAST_RECOVERY=$NOW
        if [ $RECOVERY_LEVEL -eq 1 ]; then
            log "Recovery L1: firmware_restart"
            curl -s -X POST http://127.0.0.1:7125/printer/firmware_restart 2>/dev/null
            sleep 5
        elif [ $RECOVERY_LEVEL -eq 2 ]; then
            log "Recovery L2: restart klipper"
            systemctl restart klipper 2>/dev/null
            sleep 8
        elif [ $RECOVERY_LEVEL -eq 3 ]; then
            log "Recovery L3: USB port reset (skip webcam)"
            for port in /sys/bus/usb/devices/*/authorized; do
                devpath=$(dirname "$port")
                devnum=$(cat "$devpath/devnum" 2>/dev/null || echo "0")
                if [ "$devnum" = "1" ]; then continue; fi
                echo 0 > "$port" 2>/dev/null
                sleep 1
                echo 1 > "$port" 2>/dev/null
            done
            sleep 5; systemctl restart klipper 2>/dev/null; sleep 5
        else
            log "Recovery L4: full USB reset"
            modprobe -r xhci_hcd 2>/dev/null; sleep 2; modprobe xhci_hcd 2>/dev/null
            sleep 5; systemctl restart klipper 2>/dev/null; systemctl restart moonraker 2>/dev/null; sleep 8
        fi
        FAIL_COUNT=0
    fi
done
'''

sftp = ssh.open_sftp()
with sftp.open('/usr/local/bin/usb-watchdog.sh', 'w') as f:
    f.write(new_watchdog)
sftp.close()
run("chmod +x /usr/local/bin/usb-watchdog.sh")
print("usb-watchdog.sh已修复(增加冷却+最大级别限制)")

# Step 2: 重启usb-watchdog
print("\n=== Step 2: 重启usb-watchdog ===")
run("systemctl restart usb-watchdog")
print("已重启")

# Step 3: 检查USB物理连接 — 看dmesg中RP2040的历史
print("\n=== Step 3: USB历史 ===")
out = run("dmesg | grep -i 'rp2040\\|Klipper.*rp\\|50445059' | tail -10")
print(f"RP2040历史: {out if out.strip() else '从未检测到RP2040'}")

# Step 4: 检查所有USB设备
print("\n=== Step 4: USB设备 ===")
out = run("lsusb -t 2>&1")
print(out)

# Step 5: 确认Moonraker和Fluidd当前状态
print("\n=== Step 5: 当前状态 ===")
out = run("curl -s http://localhost:7125/server/info 2>&1 | python3 -c 'import sys,json; d=json.load(sys.stdin); print(f\"klippy_state={d[\\\"result\\\"][\\\"klippy_state\\\"]}\")' 2>&1")
print(f"Klippy: {out}")

out = run("ss -tlnp | grep -E '7125|80|8080' 2>&1")
print(f"端口:\n{out}")

# Step 6: 从外部测试Fluidd页面和WebSocket
print("\n=== Step 6: 外部访问测试 ===")
out = run("curl -s -o /dev/null -w '%{http_code}' http://192.168.5.101:80/ 2>&1")
print(f"Fluidd(nginx 80): {out}")

out = run("curl -s -o /dev/null -w '%{http_code}' http://192.168.5.101:8080/ 2>&1")
print(f"Fluidd(8080): {out}")

out = run("curl -s -o /dev/null -w '%{http_code}' http://192.168.5.101:7125/server/info 2>&1")
print(f"Moonraker API: {out}")

ssh.close()