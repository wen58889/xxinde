import paramiko
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=15)

def run(cmd, timeout=60):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    stdout.channel.settimeout(timeout)
    return stdout.read().decode('utf-8', errors='replace')

# 1. 下载Fluidd前端 (尝试多个镜像)
print("=== 下载Fluidd前端 ===")
mirrors = [
    "https://ghfast.top/https://github.com/fluidd-core/fluidd/releases/latest/download/fluidd.zip",
    "https://gh-proxy.com/https://github.com/fluidd-core/fluidd/releases/latest/download/fluidd.zip",
    "https://github.com/fluidd-core/fluidd/releases/latest/download/fluidd.zip",
]
downloaded = False
for url in mirrors:
    print(f"  尝试: {url[:50]}...")
    out = run(f'cd /tmp && curl -sL --connect-timeout 15 --max-time 120 "{url}" -o fluidd.zip 2>&1 && ls -la /tmp/fluidd.zip && echo DOWNLOAD_OK || echo DOWNLOAD_FAIL', timeout=130)
    if 'DOWNLOAD_OK' in out:
        downloaded = True
        print(f"  下载成功!")
        break
    else:
        print(f"  下载失败，尝试下一个镜像...")
        run('rm -f /tmp/fluidd.zip')

if not downloaded:
    print("所有镜像均下载失败，退出")
    ssh.close()
    exit(1)

# 2. 解压到fluidd目录
print("\n=== 解压Fluidd ===")
out = run('rm -rf /root/printer_data/fluidd/* && unzip -o /tmp/fluidd.zip -d /root/printer_data/fluidd/ 2>&1 | tail -3')
print(f"解压: {out.strip()}")

# 3. 验证
out = run('ls /root/printer_data/fluidd/index.html 2>&1')
print(f"index.html: {out.strip()}")

out = run('ls /root/printer_data/fluidd/ 2>&1 | wc -l')
print(f"文件数: {out.strip()}")

# 4. 重启fluidd
print("\n=== 重启Fluidd ===")
run('systemctl restart fluidd')
time.sleep(3)

out = run('curl -s http://localhost:8080/ 2>&1 | head -5')
print(f"Fluidd首页: {out}")

# 5. 同时修复usb-watchdog v4 + autosuspend
print("\n=== 修复usb-watchdog + autosuspend ===")
run('echo -1 > /sys/module/usbcore/parameters/autosuspend 2>/dev/null || true')
run('for d in /sys/bus/usb/devices/*/power/control; do echo on > "$d" 2>/dev/null; done')

# 复用fix_deployed_n1.sh中的watchdog v4
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

sftp = ssh.open_sftp()
with sftp.open('/usr/local/bin/usb-watchdog.sh', 'w') as f:
    f.write(new_wd)
sftp.close()
run("chmod +x /usr/local/bin/usb-watchdog.sh")
run("systemctl restart usb-watchdog")
print("usb-watchdog v4 + autosuspend已修复")

# 6. 最终验证
out = run("curl -s http://localhost:7125/server/info 2>&1")
if '"klippy_state"' in out:
    state = out.split('"klippy_state":"')[1].split('"')[0]
    print(f"\nklippy_state: {state}")

ssh.close()