import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=10)

def run(cmd, timeout=15):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    stdout.channel.settimeout(timeout)
    return stdout.read().decode('utf-8', errors='replace')

# 写入net-check.sh
print("=== 写入net-check.sh ===")
run(r"""cat > /usr/local/bin/net-check.sh << 'NETEOF'
#!/bin/bash
sleep 10
echo -1 > /sys/module/usbcore/parameters/autosuspend 2>/dev/null || true
for d in /sys/bus/usb/devices/*/power/control; do echo on > "$d" 2>/dev/null; done
for d in /sys/bus/usb/devices/*/power/autosuspend; do echo -1 > "$d" 2>/dev/null; done
iw dev wlan0 set power_save off 2>/dev/null || true
for mmc in /sys/class/mmc_host/mmc*/mmc*/power/control; do
    [ -e "$mmc" ] && echo on > "$mmc" 2>/dev/null || true
done
echo 1 > /sys/module/brcmfmac/parameters/roamoff 2>/dev/null || true
if ! iw dev wlan0 link 2>/dev/null | grep -q "Connected"; then
    nmcli con up "ZTE01-24g" 2>/dev/null || nmcli con up "ZTE015G-5g" 2>/dev/null || true
fi
logger -t net-check "Network integrity check completed"
NETEOF
chmod +x /usr/local/bin/net-check.sh""")
print("net-check.sh OK")

# 写入net-check.service
print("\n=== 写入net-check.service ===")
run(r"""cat > /etc/systemd/system/net-check.service << 'SVCEOF'
[Unit]
Description=Network Integrity Check (post-boot)
After=NetworkManager.service
Wants=NetworkManager.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/net-check.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
SVCEOF
systemctl daemon-reload
systemctl enable net-check.service""")
print("net-check.service OK")

# 验证所有持久化service
print("\n=== 验证持久化service ===")
for svc in ['usb-autosuspend-fix', 'net-check', 'fix-mac', 'usb-watchdog', 'eth0-power-fix']:
    out = run(f'systemctl is-enabled {svc} 2>&1')
    print(f"  {svc}: {out.strip()}")

# 验证autosuspend
out = run('cat /sys/module/usbcore/parameters/autosuspend')
print(f"\nautosuspend: {out.strip()}")

# 验证WiFi
out = run('nmcli dev status 2>&1 | grep -E "eth0|wlan0"')
print(out.strip())

ssh.close()