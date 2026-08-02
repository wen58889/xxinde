import paramiko
import time
import json
import os

# Step 1: 从本机下载Fluidd
print("=== 从本机下载Fluidd ===")
fluidd_zip = os.path.join(os.path.dirname(__file__), 'fluidd.zip')

if not os.path.exists(fluidd_zip):
    print("本地没有fluidd.zip，尝试下载...")
    import urllib.request
    try:
        urllib.request.urlretrieve(
            'https://github.com/fluidd-core/fluidd/releases/latest/download/fluidd.zip',
            fluidd_zip
        )
        print(f"下载完成: {os.path.getsize(fluidd_zip)} bytes")
    except Exception as e:
        print(f"下载失败: {e}")
        # 尝试用API获取直接链接
        try:
            req = urllib.request.Request('https://api.github.com/repos/fluidd-core/fluidd/releases/latest')
            with urllib.request.urlopen(req, timeout=15) as resp:
                release = json.loads(resp.read())
                download_url = release['assets'][0]['browser_download_url']
                print(f"直接下载链接: {download_url}")
                urllib.request.urlretrieve(download_url, fluidd_zip)
                print(f"下载完成: {os.path.getsize(fluidd_zip)} bytes")
        except Exception as e2:
            print(f"API下载也失败: {e2}")
            exit(1)
else:
    print(f"本地已有fluidd.zip: {os.path.getsize(fluidd_zip)} bytes")

# Step 2: SCP上传到112
print("\n=== SCP上传到112 ===")
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=15)

def run(cmd, timeout=30):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    stdout.channel.settimeout(timeout)
    return stdout.read().decode('utf-8', errors='replace')

# 上传fluidd.zip
sftp = ssh.open_sftp()
remote_zip = '/tmp/fluidd.zip'
print(f"上传 {os.path.getsize(fluidd_zip)} bytes...")
sftp.put(fluidd_zip, remote_zip)
sftp.close()
print("上传完成")

# Step 3: 解压
print("\n=== 解压Fluidd ===")
out = run('rm -rf /root/printer_data/fluidd/* && unzip -o /tmp/fluidd.zip -d /root/printer_data/fluidd/ 2>&1 | tail -3')
print(f"解压: {out.strip()}")

# Step 4: 验证
out = run('ls /root/printer_data/fluidd/index.html 2>&1')
print(f"index.html: {out.strip()}")

out = run('ls /root/printer_data/fluidd/ 2>&1 | wc -l')
print(f"文件数: {out.strip()}")

# Step 5: 重启fluidd
print("\n=== 重启Fluidd ===")
run('systemctl restart fluidd')
time.sleep(3)

out = run('curl -s http://localhost:8080/ 2>&1 | head -3')
print(f"Fluidd首页: {out.strip()[:100]}")

# Step 6: 修复usb-watchdog v4 + autosuspend
print("\n=== 修复usb-watchdog + autosuspend ===")
run('echo -1 > /sys/module/usbcore/parameters/autosuspend 2>/dev/null || true')
run('for d in /sys/bus/usb/devices/*/power/control; do echo on > "$d" 2>/dev/null; done')

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

# Step 7: 最终验证
out = run("curl -s http://localhost:7125/server/info 2>&1")
if '"klippy_state"' in out:
    state = out.split('"klippy_state":"')[1].split('"')[0]
    print(f"\nklippy_state: {state}")

out = run("curl -s http://localhost:8080/ 2>&1 | head -1")
if '<!DOCTYPE' in out or '<html' in out:
    print("Fluidd Web: OK")
else:
    print(f"Fluidd Web: {out.strip()[:80]}")

ssh.close()