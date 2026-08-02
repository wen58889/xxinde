import paramiko
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=10)

def run(cmd, timeout=15):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    stdout.channel.settimeout(timeout)
    return stdout.read().decode('utf-8', errors='replace')

# 1. 修复USB autosuspend=-1 (持久化)
print("=== 1. 修复USB autosuspend ===")
out = run('echo -1 > /sys/module/usbcore/parameters/autosuspend 2>&1 && echo "runtime OK" || echo "runtime FAIL"')
print(out.strip())

# 持久化: modprobe.d
out = run('cat /etc/modprobe.d/usb-no-autosuspend.conf 2>&1')
if 'autosuspend=-1' not in out:
    run('echo "options usbcore autosuspend=-1" > /etc/modprobe.d/usb-no-autosuspend.conf')
    print("modprobe.d 已写入")
else:
    print("modprobe.d 已存在")

# 持久化: armbianEnv.txt
out = run('grep autosuspend /boot/armbianEnv.txt 2>&1')
if 'autosuspend' not in out:
    run('echo "usbcore.autosuspend=-1" >> /boot/armbianEnv.txt')
    print("armbianEnv.txt 已写入")
else:
    print("armbianEnv.txt 已存在")

# udev规则
out = run('cat /etc/udev/rules.d/99-usb-no-autosuspend.rules 2>&1')
if 'autosuspend' not in out:
    run('echo \'ACTION=="add", SUBSYSTEM=="usb", ATTR{power/autosuspend}="-1"\' > /etc/udev/rules.d/99-usb-no-autosuspend.rules')
    run('echo \'ACTION=="add", SUBSYSTEM=="usb", ATTR{idVendor}=="1d50", ATTR{power/control}="on"\' >> /etc/udev/rules.d/99-usb-no-autosuspend.rules')
    print("udev规则已写入")
else:
    print("udev规则已存在")

# 立即对所有USB设备生效
run('for d in /sys/bus/usb/devices/*/power/control; do echo on > "$d" 2>/dev/null; done')
run('for d in /sys/bus/usb/devices/*/power/autosuspend; do echo -1 > "$d" 2>/dev/null; done')
print("USB PM已禁用")

# 2. 修复WiFi — 创建2.4G连接(ZTE01) + 5G连接(ZTE015G)，2.4G优先
print("\n=== 2. 修复WiFi连接 ===")

# 获取WiFi密码
out = run('grep -r "psk=" /etc/NetworkManager/system-connections/ 2>/dev/null | head -1')
psk = ''
if 'psk=' in out:
    psk = out.strip().split('psk=')[-1].strip()
print(f"WiFi密码: {'***' if psk else 'NOT_FOUND'}")

if psk:
    # 创建2.4G连接
    out = run(f'nmcli con add con-name "ZTE01" ifname wlan0 type wifi ssid "ZTE01" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "{psk}" ipv4.method manual ipv4.addresses "192.168.5.112/24" ipv4.gateway "192.168.5.1" ipv4.dns "8.8.8.8,114.114.114.114" connection.autoconnect yes connection.autoconnect-priority 50 connection.autoconnect-retries 0 802-11-wireless.powersave 2 802-11-wireless.mac-address "02:28:6a:10:5b:61" 802-11-wireless.band bg 2>&1')
    print(f"2.4G ZTE01: {out.strip()}")
    
    # 创建5G连接
    out = run(f'nmcli con add con-name "ZTE015G" ifname wlan0 type wifi ssid "ZTE015G" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "{psk}" ipv4.method manual ipv4.addresses "192.168.5.112/24" ipv4.gateway "192.168.5.1" ipv4.dns "8.8.8.8,114.114.114.114" connection.autoconnect yes connection.autoconnect-priority 10 connection.autoconnect-retries 0 802-11-wireless.powersave 2 802-11-wireless.mac-address "02:28:6a:10:5b:61" 802-11-wireless.band a 2>&1')
    print(f"5G ZTE015G: {out.strip()}")
    
    # 设置WiFi route-metric=200(低于有线的100)
    run('nmcli con mod "ZTE01" ipv4.route-metric 200 2>/dev/null || true')
    run('nmcli con mod "ZTE015G" ipv4.route-metric 200 2>/dev/null || true')
    
    # 启用2.4G
    print("\n连接2.4G WiFi...")
    out = run('nmcli con up "ZTE01" 2>&1', timeout=30)
    print(f"2.4G: {out.strip()[:100]}")
else:
    print("无法获取WiFi密码!")

# 3. 修复usb-watchdog v4 (MCU_ID通用匹配)
print("\n=== 3. 修复usb-watchdog v4 ===")
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
run('chmod +x /usr/local/bin/usb-watchdog.sh')
run('systemctl restart usb-watchdog')
print("usb-watchdog v4已修复 (MCU_ID=usb-Klipper通用匹配)")

# 4. 修复有线连接静态IP
print("\n=== 4. 修复有线连接 ===")
out = run('nmcli con mod "Wired connection 1" ipv4.method manual ipv4.addresses "192.168.5.112/24" ipv4.gateway "192.168.5.1" ipv4.dns "8.8.8.8,114.114.114.114" connection.autoconnect-priority 100 ipv4.route-metric 100 2>&1')
print(f"有线: {out.strip()}")
run('nmcli con mod "Wired connection 1" ipv6.method disabled 2>/dev/null || true')

# 5. 验证
print("\n=== 5. 验证 ===")
out = run('cat /sys/module/usbcore/parameters/autosuspend')
print(f"autosuspend: {out.strip()}")

out = run('nmcli -t -f NAME,TYPE,AUTOCONNECT-PRIORITY con show 2>&1')
print(out.strip())

out = run('nmcli dev status 2>&1')
print(out.strip())

out = run('ls /dev/serial/by-id/ 2>&1')
print(f"MCU: {out.strip()}")

ssh.close()