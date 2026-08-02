import paramiko
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=10)

def run(cmd, timeout=15):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    stdout.channel.settimeout(timeout)
    return stdout.read().decode('utf-8', errors='replace').strip()

# 1. WiFi三层禁用
print("=== WiFi三层禁用 ===")

# L1: rfkill block wlan
out = run("rfkill block wlan 2>&1 || true")
print(f"L1 rfkill block wlan: done")

# L2: nmcli radio wifi off
out = run("nmcli radio wifi off 2>&1 || true")
print(f"L2 nmcli radio wifi off: done")

# L3: brcmfmac黑名单
out = run("echo 'blacklist brcmfmac' > /etc/modprobe.d/brcmfmac.conf")
print(f"L3 brcmfmac黑名单: done")

# 2. rfkill持久化service
print("\n=== rfkill持久化service ===")
run(r"""cat > /usr/local/bin/rfkill-wifi-block.sh << 'RFEOF'
#!/bin/bash
rfkill block wlan 2>/dev/null || true
logger -t rfkill-wifi-block 'WiFi rfkill block applied'
RFEOF
chmod +x /usr/local/bin/rfkill-wifi-block.sh""")

run(r"""cat > /etc/systemd/system/n1-rfkill-persist.service << 'SVCEOF'
[Unit]
Description=Persist WiFi rfkill block state
After=NetworkManager.service
Wants=NetworkManager.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/rfkill-wifi-block.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
SVCEOF
systemctl daemon-reload
systemctl enable n1-rfkill-persist.service 2>/dev/null || true""")
print("rfkill-persist service: enabled")

# 3. WiFi服务清理
print("\n=== WiFi服务清理 ===")
run("systemctl disable wifi-watchdog 2>/dev/null || true")
run("systemctl stop wifi-watchdog 2>/dev/null || true")
run("rm -f /etc/NetworkManager/dispatcher.d/99-wifi-stability.sh 2>/dev/null || true")
run("rm -f /etc/NetworkManager/conf.d/no-p2p.conf 2>/dev/null || true")
run("rm -f /etc/NetworkManager/conf.d/wifi-no-bgscan.conf 2>/dev/null || true")
run("rm -f /etc/NetworkManager/conf.d/wifi-no-mac-random.conf 2>/dev/null || true")
print("WiFi服务已清理")

# 4. net-check.service纯有线版
print("\n=== net-check.service纯有线版 ===")
run(r"""cat > /usr/local/bin/net-check.sh << 'NETEOF'
#!/bin/bash
sleep 10
echo -1 > /sys/module/usbcore/parameters/autosuspend 2>/dev/null || true
for d in /sys/bus/usb/devices/*/power/control; do echo on > "$d" 2>/dev/null; done
for d in /sys/bus/usb/devices/*/power/autosuspend; do echo -1 > "$d" 2>/dev/null; done
IFACE=$(cat /etc/n1-fixed-iface 2>/dev/null || echo "eth0")
[ -e "/sys/class/net/$IFACE" ] || IFACE="eth0"
ethtool --set-eee $IFACE eee off 2>/dev/null || true
ethtool -s $IFACE wol d 2>/dev/null || true
echo on > /sys/class/net/$IFACE/power/control 2>/dev/null || true
logger -t net-check 'Network integrity check completed (wired-only)'
NETEOF
chmod +x /usr/local/bin/net-check.sh""")

run(r"""cat > /etc/systemd/system/net-check.service << 'SVCEOF'
[Unit]
Description=Network Integrity Check (post-boot, wired-only)
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
systemctl enable net-check.service 2>/dev/null || true""")
print("net-check.service: enabled (wired-only)")

# 5. 验证当前状态
print("\n=== 当前状态验证 ===")
out = run("rfkill list 2>/dev/null | grep -A2 wlan")
print(f"rfkill:\n{out}")

out = run("nmcli radio wifi 2>/dev/null")
print(f"nmcli radio wifi: {out}")

out = run("ls /dev/serial/by-id/ 2>/dev/null")
print(f"MCU: {out}")

out = run("curl -s http://localhost:7125/server/info 2>&1 | grep -oP '\"klippy_state\":\"\\K[^\"]+' || echo ERR")
print(f"klippy_state: {out}")

out = run("cat /sys/module/usbcore/parameters/autosuspend 2>/dev/null")
print(f"autosuspend: {out}")

out = run("ethtool eth0 2>/dev/null | grep -E 'Speed|Link detected'")
print(f"eth0: {out}")

out = run("systemctl is-enabled wifi-watchdog 2>/dev/null || echo disabled")
print(f"wifi-watchdog: {out}")

out = run("systemctl is-enabled n1-rfkill-persist 2>/dev/null || echo disabled")
print(f"rfkill-persist: {out}")

out = run("grep -c 'iw dev wlan0\\|brcmfmac\\|roamoff' /usr/local/bin/net-check.sh 2>/dev/null || echo 0")
print(f"net-check WiFi命令数: {out} (期望0)")

ssh.close()
print("\n✅ WiFi三层禁用完成! 需要重启验证持久化。")