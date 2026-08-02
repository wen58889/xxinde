import paramiko
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=10)

def run(cmd, timeout=15):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    stdout.channel.settimeout(timeout)
    return stdout.read().decode('utf-8', errors='replace')

# ============================================================
# 终极持久化修复
# ============================================================

# 1. USB autosuspend=-1 持久化 — Armbian不走armbianEnv.txt的extraargs
#    用systemd service在开机时强制设置
print("=== 1. USB autosuspend持久化 ===")

# 立即设置
run('echo -1 > /sys/module/usbcore/parameters/autosuspend')
run('for d in /sys/bus/usb/devices/*/power/control; do echo on > "$d" 2>/dev/null; done')
run('for d in /sys/bus/usb/devices/*/power/autosuspend; do echo -1 > "$d" 2>/dev/null; done')

# 创建systemd service (最可靠的持久化方式)
new_service = '''[Unit]
Description=Force USB autosuspend=-1 and power control=on
After=sysinit.target
Before=basic.target

[Service]
Type=oneshot
ExecStart=/bin/bash -c 'echo -1 > /sys/module/usbcore/parameters/autosuspend; for d in /sys/bus/usb/devices/*/power/control; do echo on > "$d" 2>/dev/null; done; for d in /sys/bus/usb/devices/*/power/autosuspend; do echo -1 > "$d" 2>/dev/null; done'
RemainAfterExit=yes

[Install]
WantedBy=sysinit.target
'''
sftp = ssh.open_sftp()
with sftp.open('/etc/systemd/system/usb-autosuspend-fix.service', 'w') as f:
    f.write(new_service)
sftp.close()
run('systemctl daemon-reload')
run('systemctl enable usb-autosuspend-fix.service')
out = run('cat /sys/module/usbcore/parameters/autosuspend')
print(f"autosuspend: {out.strip()} (service已启用)")

# 2. WiFi连接修复 — 重新连接2.4G
print("\n=== 2. WiFi连接修复 ===")
out = run('nmcli dev status 2>&1 | grep wlan0')
print(f"当前: {out.strip()}")

if 'disconnected' in out or 'unavailable' in out:
    out = run('nmcli con up "ZTE01-24g" 2>&1', timeout=30)
    print(f"2.4G: {out.strip()[:80]}")
    if 'Error' in out:
        out = run('nmcli con up "ZTE015G-5g" 2>&1', timeout=30)
        print(f"5G: {out.strip()[:80]}")

time.sleep(3)
out = run('nmcli dev status 2>&1 | grep wlan0')
print(f"WiFi: {out.strip()}")

# 3. 有线连接修复 — 确保静态IP
print("\n=== 3. 有线连接修复 ===")
out = run('nmcli con show "Wired connection 1" 2>&1 | grep ipv4.addresses')
print(f"有线IP: {out.strip()}")
if not '192.168.5.112' in out:
    run('nmcli con mod "Wired connection 1" ipv4.method manual ipv4.addresses "192.168.5.112/24" ipv4.gateway "192.168.5.1" ipv4.dns "8.8.8.8,114.114.114.114" connection.autoconnect-priority 100 ipv4.route-metric 100 ipv6.method disabled')
    print("有线静态IP已修复")

# 4. WiFi省电持久化 — 确保dispatcher在up时禁用省电
print("\n=== 4. WiFi省电持久化 ===")
new_wifi_disp = '''#!/bin/bash
if [ "$2" = "up" ]; then
    iw dev "$1" set power_save off 2>/dev/null || true
    for mmc in /sys/class/mmc_host/mmc*/mmc*/power/control; do
        [ -e "$mmc" ] && echo on > "$mmc" 2>/dev/null || true
    done
    /usr/local/bin/fix-mac.sh 2>/dev/null || true
    logger -t wifi-stability "$1 up: power_save off + SDIO PM on + fix-mac"
fi
'''
sftp = ssh.open_sftp()
with sftp.open('/etc/NetworkManager/dispatcher.d/99-wifi-stability.sh', 'w') as f:
    f.write(new_wifi_disp)
sftp.close()
run('chmod +x /etc/NetworkManager/dispatcher.d/99-wifi-stability.sh')
print("WiFi dispatcher已更新")

# 5. 创建开机后网络完整性检查service
print("\n=== 5. 网络完整性检查service ===")
new_net_check = '''#!/bin/bash
# 开机后网络完整性检查 — 确保所有配置生效
sleep 10

# USB autosuspend
echo -1 > /sys/module/usbcore/parameters/autosuspend 2>/dev/null || true
for d in /sys/bus/usb/devices/*/power/control; do echo on > "$d" 2>/dev/null; done
for d in /sys/bus/usb/devices/*/power/autosuspend; do echo -1 > "$d" 2>/dev/null; done

# WiFi省电
iw dev wlan0 set power_save off 2>/dev/null || true

# SDIO/MMC省电
for mmc in /sys/class/mmc_host/mmc*/mmc*/power/control; do
    [ -e "$mmc" ] && echo on > "$mmc" 2>/dev/null || true
done

# brcmfmac漫游禁用
echo 1 > /sys/module/brcmfmac/parameters/roamoff 2>/dev/null || true

# 确保WiFi连接(如果断开)
if ! iw dev wlan0 link 2>/dev/null | grep -q "Connected"; then
    nmcli con up "ZTE01-24g" 2>/dev/null || nmcli con up "ZTE015G-5g" 2>/dev/null || true
fi

logger -t net-check "Network integrity check completed"
'''
sftp = ssh.open_sftp()
with sftp.open('/usr/local/bin/net-check.sh', 'w') as f:
    f.write(new_net_check)
sftp.close()
run('chmod +x /usr/local/bin/net-check.sh')

new_net_svc = '''[Unit]
Description=Network Integrity Check (post-boot)
After=NetworkManager.service
Wants=NetworkManager.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/net-check.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
'''
with sftp.open('/etc/systemd/system/net-check.service', 'w') as f:
    f.write(new_net_svc)
sftp.close()
run('systemctl daemon-reload')
run('systemctl enable net-check.service')
print("net-check.service已启用 (开机10s后自动检查修复)")

# 6. 最终验证
print("\n=== 6. 验证 ===")
out = run('cat /sys/module/usbcore/parameters/autosuspend')
print(f"autosuspend: {out.strip()}")
out = run('systemctl is-enabled usb-autosuspend-fix.service')
print(f"usb-autosuspend-fix: {out.strip()}")
out = run('systemctl is-enabled net-check.service')
print(f"net-check: {out.strip()}")
out = run('nmcli dev status 2>&1 | grep -E "eth0|wlan0"')
print(out.strip())
out = run('hostname -I')
print(f"IP: {out.strip()}")

ssh.close()