import paramiko
import time

def ssh_run(host, cmd):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username='root', password='1234', timeout=10)
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=10)
    out = stdout.read().decode('utf-8', errors='replace')
    ssh.close()
    return out

# 1. 诊断
print("=== 诊断108 ===")
out = ssh_run('192.168.5.108', 'head -3 /usr/local/bin/usb-watchdog.sh 2>&1')
print(f"usb-watchdog: {out}")
out = ssh_run('192.168.5.108', 'ls /dev/serial/by-id/ 2>&1')
print(f"MCU: {out}")
out = ssh_run('192.168.5.108', 'journalctl -u klipper --since "10 min ago" --no-pager 2>&1 | grep -c "Started klipper"')
print(f"Klipper重启(10min): {out.strip()}")
out = ssh_run('192.168.5.108', 'journalctl -u moonraker --since "10 min ago" --no-pager 2>&1 | grep -c "Started moonraker"')
print(f"Moonraker重启(10min): {out.strip()}")

# 2. 修复usb-watchdog
print("\n=== 修复usb-watchdog v4 ===")
new_watchdog = r'''#!/bin/bash
MCU_ID="usb-Klipper"
CHECK_INTERVAL=5
MAX_FAIL=3
FAIL_COUNT=0
RECOVERY_LEVEL=0
MAX_RECOVERY_LEVEL=5
COOLDOWN=300
LAST_RECOVERY=0
XHCI_FAIL_COUNT=0
XHCI_REBOOT_THRESHOLD=6
log() { logger -t usb-watchdog "$1"; }
check_xhci_error() { dmesg | tail -30 | grep -qiE 'HC died|xHCI host controller not responding'; }
check_xhci_timeout() { dmesg | tail -30 | grep -qiE 'Timeout while waiting for setup device|unable to enumerate USB device|device descriptor read.*error -1[12]0|device not accepting address.*error -62'; }
while true; do
    sleep $CHECK_INTERVAL
    if check_xhci_error; then log "CRITICAL: XHCI HC died!"; sleep 1; reboot; fi
    if check_xhci_timeout; then
        XHCI_FAIL_COUNT=$((XHCI_FAIL_COUNT + 1))
        [ $XHCI_FAIL_COUNT -ge $XHCI_REBOOT_THRESHOLD ] && { log "XHCI timeout threshold"; sleep 1; reboot; }
    else
        [ $XHCI_FAIL_COUNT -gt 0 ] && XHCI_FAIL_COUNT=$((XHCI_FAIL_COUNT - 1))
    fi
    if ls /dev/serial/by-id/ 2>/dev/null | grep -q "$MCU_ID"; then
        [ $FAIL_COUNT -gt 0 ] && { log "MCU recovered"; FAIL_COUNT=0; RECOVERY_LEVEL=0; }
        continue
    fi
    FAIL_COUNT=$((FAIL_COUNT + 1))
    log "MCU not detected! fail=$FAIL_COUNT level=$RECOVERY_LEVEL"
    if [ $FAIL_COUNT -ge $MAX_FAIL ]; then
        NOW=$(date +%s); ELAPSED=$((NOW - LAST_RECOVERY))
        if [ $ELAPSED -lt $COOLDOWN ]; then log "Cooldown (${ELAPSED}s/${COOLDOWN}s)"; FAIL_COUNT=0; continue; fi
        if [ $RECOVERY_LEVEL -ge $MAX_RECOVERY_LEVEL ]; then log "Max level"; FAIL_COUNT=0; sleep 60; continue; fi
        RECOVERY_LEVEL=$((RECOVERY_LEVEL + 1)); LAST_RECOVERY=$NOW
        if [ $RECOVERY_LEVEL -eq 1 ]; then log "L1: firmware_restart"; curl -s -X POST http://127.0.0.1:7125/printer/firmware_restart 2>/dev/null; sleep 5
        elif [ $RECOVERY_LEVEL -eq 2 ]; then log "L2: restart klipper"; systemctl restart klipper 2>/dev/null; sleep 8
        elif [ $RECOVERY_LEVEL -eq 3 ]; then log "L3: USB reset"
            for port in /sys/bus/usb/devices/*/authorized; do devpath=$(dirname "$port"); devnum=$(cat "$devpath/devnum" 2>/dev/null || echo "0"); [ "$devnum" = "1" ] && continue; echo 0 > "$port" 2>/dev/null; sleep 1; echo 1 > "$port" 2>/dev/null; done
            sleep 5; systemctl restart klipper 2>/dev/null; sleep 5
        elif [ $RECOVERY_LEVEL -eq 4 ]; then log "L4: xhci reset"
            for dev in /sys/bus/pci/drivers/xhci_hcd/*/; do dn=$(basename "$dev"); echo "$dn" > /sys/bus/pci/drivers/xhci_hcd/unbind 2>/dev/null; sleep 2; echo "$dn" > /sys/bus/pci/drivers/xhci_hcd/bind 2>/dev/null; sleep 3; done
            systemctl restart klipper moonraker 2>/dev/null; sleep 8
        else log "L5: reboot"; sleep 2; reboot
        fi
        FAIL_COUNT=0
    fi
done
'''

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.108', username='root', password='1234', timeout=10)
sftp = ssh.open_sftp()
with sftp.open('/usr/local/bin/usb-watchdog.sh', 'w') as f:
    f.write(new_watchdog)
sftp.close()
stdin, stdout, stderr = ssh.exec_command("chmod +x /usr/local/bin/usb-watchdog.sh", timeout=10)
stdout.read()
stdin, stdout, stderr = ssh.exec_command("systemctl restart usb-watchdog; systemctl restart moonraker", timeout=10)
stdout.read()
ssh.close()
print("已修复并重启")
time.sleep(12)

# 3. 验证
out = ssh_run('192.168.5.108', 'curl -s http://localhost:7125/server/info 2>&1')
if '"klippy_state"' in out:
    state = out.split('"klippy_state":"')[1].split('"')[0]
    print(f"klippy_state: {state}")

# 4. 5分钟稳定性测试
print("\n=== 5分钟稳定性测试 ===")
print("时间     | 7125 | klippy  | Fluidd")
print("-" * 45)

errors = 0
for i in range(60):
    try:
        out = ssh_run('192.168.5.108', 'ss -tlnp | grep 7125 2>&1')
        port_ok = "OK" if out.strip() else "NO"
        
        out = ssh_run('192.168.5.108', 'curl -s http://localhost:7125/server/info 2>&1')
        if '"klippy_state"' in out:
            klippy = out.split('"klippy_state":"')[1].split('"')[0]
        else:
            klippy = "ERR"; errors += 1
        
        out = ssh_run('192.168.5.108', 'curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/ 2>&1')
        fluidd = out.strip()
        
        if i % 6 == 0:
            t = time.strftime("%H:%M:%S")
            print(f"{t} | {port_ok}  | {klippy:7s} | {fluidd}")
    except Exception as e:
        errors += 1
        if i % 6 == 0:
            print(f"{time.strftime('%H:%M:%S')} | ERROR: {e}")
    
    time.sleep(5)

# 最终统计
print(f"\n结果: {errors}次错误 / 60次测试")
klip_r = ssh_run('192.168.5.108', 'journalctl -u klipper --since "5 min ago" --no-pager 2>&1 | grep -c "Started klipper"')
mr_r = ssh_run('192.168.5.108', 'journalctl -u moonraker --since "5 min ago" --no-pager 2>&1 | grep -c "Started moonraker"')
print(f"Klipper重启(5min): {klip_r.strip()}")
print(f"Moonraker重启(5min): {mr_r.strip()}")
