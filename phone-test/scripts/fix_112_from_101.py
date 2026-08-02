import paramiko
import time

def run_on(ssh, cmd, timeout=30):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    stdout.channel.settimeout(timeout)
    return stdout.read().decode('utf-8', errors='replace')

# Step 1: 检查101和105的Fluidd
print("=== 检查各设备Fluidd ===")
for ip in ['192.168.5.101', '192.168.5.105']:
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(ip, username='root', password='1234', timeout=5)
        out = run_on(ssh, 'ls /root/printer_data/fluidd/index.html 2>&1')
        count = run_on(ssh, 'ls /root/printer_data/fluidd/ 2>&1 | wc -l')
        print(f"  {ip}: {out.strip()} ({count.strip()} files)")
        ssh.close()
    except Exception as e:
        print(f"  {ip}: OFFLINE ({e})")

# Step 2: 从101复制Fluidd到112（通过101的scp）
print("\n=== 从101复制Fluidd到112 ===")
ssh101 = paramiko.SSHClient()
ssh101.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh101.connect('192.168.5.101', username='root', password='1234', timeout=10)

# 先打包101的fluidd
out = run_on(ssh101, 'cd /root/printer_data && tar czf /tmp/fluidd.tar.gz fluidd/ 2>&1 && echo PACK_OK || echo PACK_FAIL')
print(f"打包: {out.strip()[-20:]}")

# 通过SFTP下载到本机，再上传到112
print("下载fluidd.tar.gz到本机...")
sftp101 = ssh101.open_sftp()
sftp101.get('/tmp/fluidd.tar.gz', r'D:\Users\59520\IDEProjects\xxinde\phone-test\scripts\fluidd.tar.gz')
sftp101.close()
ssh101.close()

import os
local_size = os.path.getsize(r'D:\Users\59520\IDEProjects\xxinde\phone-test\scripts\fluidd.tar.gz')
print(f"本机文件: {local_size} bytes")

# 上传到112
print("上传fluidd.tar.gz到112...")
ssh112 = paramiko.SSHClient()
ssh112.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh112.connect('192.168.5.112', username='root', password='1234', timeout=10)

sftp112 = ssh112.open_sftp()
sftp112.put(r'D:\Users\59520\IDEProjects\xxinde\phone-test\scripts\fluidd.tar.gz', '/tmp/fluidd.tar.gz')
sftp112.close()

# 解压
print("解压Fluidd到112...")
out = run_on(ssh112, 'rm -rf /root/printer_data/fluidd/* && cd /root/printer_data && tar xzf /tmp/fluidd.tar.gz 2>&1 && echo EXTRACT_OK || echo EXTRACT_FAIL')
print(f"解压: {out.strip()}")

# 验证
out = run_on(ssh112, 'ls /root/printer_data/fluidd/index.html 2>&1')
print(f"index.html: {out.strip()}")

out = run_on(ssh112, 'ls /root/printer_data/fluidd/ 2>&1 | wc -l')
print(f"文件数: {out.strip()}")

# 重启fluidd
print("\n=== 重启Fluidd ===")
run_on(ssh112, 'systemctl restart fluidd')
time.sleep(3)

out = run_on(ssh112, 'curl -s http://localhost:8080/ 2>&1 | head -1')
if '<!DOCTYPE' in out or '<html' in out:
    print("Fluidd Web: OK")
else:
    print(f"Fluidd Web: {out.strip()[:80]}")

# 修复usb-watchdog v4 + autosuspend
print("\n=== 修复usb-watchdog + autosuspend ===")
run_on(ssh112, 'echo -1 > /sys/module/usbcore/parameters/autosuspend 2>/dev/null || true')
run_on(ssh112, 'for d in /sys/bus/usb/devices/*/power/control; do echo on > "$d" 2>/dev/null; done')

new_wd = r'''#!/bin/bash
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
        if [ $ELAPSED -lt $COOLDOWN ]; then log "Cooldown"; FAIL_COUNT=0; continue; fi
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

sftp112 = ssh112.open_sftp()
with sftp112.open('/usr/local/bin/usb-watchdog.sh', 'w') as f:
    f.write(new_wd)
sftp112.close()
run_on(ssh112, "chmod +x /usr/local/bin/usb-watchdog.sh")
run_on(ssh112, "systemctl restart usb-watchdog")
print("usb-watchdog v4 + autosuspend已修复")

# 最终验证
out = run_on(ssh112, "curl -s http://localhost:7125/server/info 2>&1")
if '"klippy_state"' in out:
    state = out.split('"klippy_state":"')[1].split('"')[0]
    print(f"\nklippy_state: {state}")

ssh112.close()

# 清理本机临时文件
os.remove(r'D:\Users\59520\IDEProjects\xxinde\phone-test\scripts\fluidd.tar.gz')
print("完成!")