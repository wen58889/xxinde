import paramiko
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

connected_ip = None
for ip in ['192.168.5.112', '192.168.5.106', '192.168.5.107', '192.168.5.108']:
    try:
        ssh.connect(ip, username='root', password='1234', timeout=5)
        connected_ip = ip
        break
    except:
        continue

if not connected_ip:
    print("无法连接!")
    exit(1)

print(f"连接: {connected_ip}")

def run(cmd, timeout=15):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    stdout.channel.settimeout(timeout)
    return stdout.read().decode('utf-8', errors='replace')

# ============================================================
# 终极修复: WiFi断连 + IP变化
# ============================================================

# Step 1: 查看当前WiFi MAC
print("\n=== Step 1: 当前MAC ===")
out = run('cat /sys/class/net/wlan0/address 2>&1')
current_mac = out.strip()
print(f"wlan0 MAC: {current_mac}")

# Step 2: 修复ZTE015G连接 — 强制静态IP + 高优先级 + MAC
print("\n=== Step 2: 修复ZTE015G连接 ===")
# 先删除旧连接，重建
out = run('nmcli con delete "ZTE015G" 2>&1 || true')
print(f"删除旧连接: {out.strip()}")

# 获取WiFi密码
out = run('nmcli -s -t -f 802-11-wireless-security.psk con show "ZTE015G" 2>/dev/null || echo ""')
wifi_psk = out.strip().split(':')[-1] if ':' in out.strip() else ''
print(f"WiFi密码: {'***' if wifi_psk else '未获取到'}")

# 如果没获取到密码，从其他地方获取
if not wifi_psk:
    out = run('cat /etc/NetworkManager/system-connections/ZTE015G.nmconnection 2>/dev/null | grep psk=')
    if 'psk=' in out:
        wifi_psk = out.strip().split('=')[-1]
        print(f"从文件获取密码: {'***' if wifi_psk else '失败'}")

# 重建连接
if wifi_psk:
    out = run(f'nmcli con add con-name "ZTE015G" ifname wlan0 type wifi ssid "ZTE015G" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "{wifi_psk}" ipv4.method manual ipv4.addresses "192.168.5.112/24" ipv4.gateway "192.168.5.1" ipv4.dns "8.8.8.8,114.114.114.114" connection.autoconnect yes connection.autoconnect-priority 100 connection.autoconnect-retries 0 2>&1')
    print(f"创建连接: {out.strip()}")
else:
    print("无法获取WiFi密码，尝试直接修改现有连接...")
    # 如果删除后无法重建，尝试用UUID查找
    out = run('nmcli con show 2>&1 | grep -i wifi')
    print(f"现有WiFi连接: {out.strip()}")

# Step 3: 设置WiFi省电=2(禁用) + MAC固定
print("\n=== Step 3: WiFi省电+MAC ===")
out = run('nmcli con mod "ZTE015G" 802-11-wireless.powersave 2 2>&1')
print(f"省电: {out.strip()}")
out = run('nmcli con mod "ZTE015G" 802-11-wireless.cloned-mac-address "02:28:6a:10:5b:61" 2>&1 || nmcli con mod "ZTE015G" wifi.cloned-mac-address "02:28:6a:10:5b:61" 2>&1 || echo "cloned-mac failed"')
print(f"cloned-mac: {out.strip()}")

# Step 4: 立即禁用WiFi省电
print("\n=== Step 4: 立即禁用WiFi省电 ===")
out = run('iw dev wlan0 set power_save off 2>&1')
print(f"power_save off: {out.strip()}")

# Step 5: 禁用SDIO/MMC省电
print("\n=== Step 5: 禁用SDIO/MMC省电 ===")
out = run('for mmc in /sys/class/mmc_host/mmc*/mmc*/power/control; do [ -e "$mmc" ] && echo on > "$mmc" 2>/dev/null && echo "  $mmc = on"; done')
print(out.strip())

# Step 6: 修复fix-mac.sh — 从/etc/n1-fixed-iface读取接口
print("\n=== Step 6: 修复fix-mac.sh ===")
new_fix_mac = r'''#!/bin/bash
MAC_FILE="/etc/n1-fixed-mac"
IFACE_FILE="/etc/n1-fixed-iface"

[ -f "$MAC_FILE" ] || exit 0
DESIRED_MAC=$(cat "$MAC_FILE" | tr -d '[:space:]')
[ -n "$DESIRED_MAC" ] || exit 0

IFACE=""
if [ -f "$IFACE_FILE" ]; then
    SAVED_IFACE=$(cat "$IFACE_FILE" | tr -d '[:space:]')
    if [ -e "/sys/class/net/$SAVED_IFACE" ]; then
        IFACE="$SAVED_IFACE"
    fi
fi
[ -n "$IFACE" ] || exit 1

for i in $(seq 1 15); do
    [ -e "/sys/class/net/$IFACE" ] && break
    sleep 0.5
done
[ -e "/sys/class/net/$IFACE" ] || exit 1

CURRENT_MAC=$(cat /sys/class/net/$IFACE/address 2>/dev/null)
[ "$CURRENT_MAC" = "$DESIRED_MAC" ] && exit 0

ip link set dev $IFACE down 2>/dev/null || true
ip link set dev $IFACE address $DESIRED_MAC 2>/dev/null || true
ip link set dev $IFACE up 2>/dev/null || true

sleep 3
CON=$(nmcli -t -f NAME,DEVICE con show --active 2>/dev/null | grep "$IFACE" | head -1 | cut -d: -f1)
[ -n "$CON" ] && nmcli con up "$CON" 2>/dev/null || true

logger -t fix-mac "MAC fixed: $IFACE $CURRENT_MAC -> $DESIRED_MAC"
'''

sftp = ssh.open_sftp()
with sftp.open('/usr/local/bin/fix-mac.sh', 'w') as f:
    f.write(new_fix_mac)
sftp.close()
run('chmod +x /usr/local/bin/fix-mac.sh')
print("fix-mac.sh已修复(从/etc/n1-fixed-iface读取)")

# 保存接口信息
run('echo "wlan0" > /etc/n1-fixed-iface')
print("/etc/n1-fixed-iface = wlan0")

# Step 7: 修复dispatcher — 只在up事件触发，不触发connectivity-change
print("\n=== Step 7: 修复dispatcher ===")
new_dispatcher = '''#!/bin/bash
if [ "$2" = "up" ]; then
    /usr/local/bin/fix-mac.sh 2>/dev/null || true
    iw dev "$1" set power_save off 2>/dev/null || true
    for mmc in /sys/class/mmc_host/mmc*/mmc*/power/control; do
        [ -e "$mmc" ] && echo on > "$mmc" 2>/dev/null || true
    done
fi
'''
sftp = ssh.open_sftp()
with sftp.open('/etc/NetworkManager/dispatcher.d/99-fix-mac.sh', 'w') as f:
    f.write(new_dispatcher)
sftp.close()
run('chmod +x /etc/NetworkManager/dispatcher.d/99-fix-mac.sh')
print("dispatcher已修复(只up事件)")

# Step 8: 增加brcmfmac稳定性 — 禁用SDIO时钟门控
print("\n=== Step 8: brcmfmac稳定性 ===")
# 禁用MMC runtime PM
out = run('echo on > /sys/class/mmc_host/mmc0/device/power/control 2>/dev/null && echo "MMC0 PM=on" || echo "MMC0 PM skip"')
print(out.strip())

# Step 9: 验证配置
print("\n=== Step 9: 验证 ===")
out = run('nmcli con show "ZTE015G" 2>&1 | grep -iE "ipv4.method|ipv4.address|autoconnect-priority|cloned-mac|powersave"')
print(out.strip())

# Step 10: 启用WiFi连接
print("\n=== Step 10: 启用连接 ===")
out = run('nmcli con up "ZTE015G" 2>&1')
print(f"连接: {out.strip()[:100]}")

time.sleep(5)

# 验证
out = run('ip addr show wlan0 2>&1 | grep "inet "')
print(f"\n当前IP: {out.strip()}")

out = run('iw dev wlan0 link 2>&1 | head -3')
print(f"WiFi: {out.strip()}")

ssh.close()