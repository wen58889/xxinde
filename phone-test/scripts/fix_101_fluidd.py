import paramiko
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.101', username='root', password='1234', timeout=10)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=15)
    return stdout.read().decode('utf-8', errors='replace'), stderr.read().decode('utf-8', errors='replace')

# Step 1: 修复eth0 — 恢复autoneg=on
print("=== Step 1: 修复eth0 PHY卡死 ===")
out, _ = run("ethtool -s eth0 autoneg on 2>&1")
print(f"恢复autoneg=on: {out}")
time.sleep(3)
out, _ = run("ethtool eth0 2>&1 | grep -E 'Link|Speed|Auto-neg'")
print(f"eth0状态: {out}")

# Step 2: 修复eth0-power-fix.sh — 移除speed硬编码
print("\n=== Step 2: 修复eth0-power-fix.sh ===")
new_script = """#!/bin/bash
# eth0省电禁用兜底脚本 (开机后延迟执行)
# 只做EEE/WoL/PM，永不设speed/autoneg (让PHY自由协商)
sleep 2
IFACE=$(cat /etc/n1-fixed-iface 2>/dev/null || echo "eth0")
[ -e "/sys/class/net/$IFACE" ] || IFACE="eth0"
ethtool --set-eee $IFACE eee off 2>/dev/null || true
ethtool -s $IFACE wol d 2>/dev/null || true
echo on > /sys/class/net/$IFACE/power/control 2>/dev/null || true
logger -t eth0-power-fix "$IFACE: EEE off + WoL off + PM on (autoneg=on, no speed force)"
"""
sftp = ssh.open_sftp()
with sftp.open('/usr/local/bin/eth0-power-fix.sh', 'w') as f:
    f.write(new_script)
sftp.close()
run("chmod +x /usr/local/bin/eth0-power-fix.sh")
print("eth0-power-fix.sh已修复(移除speed硬编码)")

# Step 3: 修复dispatcher 99-eth0-stable.sh
print("\n=== Step 3: 修复dispatcher ===")
new_dispatcher = """#!/bin/bash
IFACE="$1"
ACTION="$2"
if [ "$IFACE" = "eth0" ] && [ "$ACTION" = "up" ]; then
    ethtool --set-eee eth0 eee off 2>/dev/null || true
    ethtool -s eth0 wol d 2>/dev/null || true
    echo on > /sys/class/net/eth0/power/control 2>/dev/null || true
    logger -t eth0-stable "eth0 up: EEE off + WoL off + PM on (autoneg=on, no speed force)"
fi
"""
with sftp.open('/etc/NetworkManager/dispatcher.d/99-eth0-stable.sh', 'w') as f:
    f.write(new_dispatcher)
sftp.close()
run("chmod +x /etc/NetworkManager/dispatcher.d/99-eth0-stable.sh")
print("99-eth0-stable.sh已修复(移除speed硬编码)")

# Step 4: 修复NM连接属性 — speed=0让NM自由协商
print("\n=== Step 4: 修复NM连接属性 ===")
out, _ = run("nmcli -t -f NAME,DEVICE con show --active 2>&1 | grep eth0")
con_name = out.strip().split(':')[0] if out.strip() else ""
print(f"有线连接名: {con_name}")
if con_name:
    run(f"nmcli con mod '{con_name}' 802-3-ethernet.speed 0 2>/dev/null || true")
    print("NM speed=0已设置")

# Step 5: 检查eth0是否恢复
print("\n=== Step 5: 检查eth0恢复 ===")
time.sleep(5)
out, _ = run("ethtool eth0 2>&1 | grep -E 'Link|Speed|Auto-neg'")
print(f"eth0状态: {out}")
out, _ = run("ip addr show eth0 2>&1 | grep inet")
print(f"eth0 IP: {out}")

# Step 6: 重启moonraker
print("\n=== Step 6: 重启moonraker ===")
run("systemctl restart moonraker")
time.sleep(10)

out, _ = run("systemctl status moonraker --no-pager -l 2>&1 | head -15")
print(out)

# Step 7: 测试Moonraker API
print("\n=== Step 7: 测试Moonraker API ===")
out, _ = run("ss -tlnp | grep 7125 2>&1")
print(f"7125端口: {out}")

out, _ = run("curl -s http://localhost:7125/server/info 2>&1")
print(f"server/info: {out[:200]}")

# Step 8: 测试Fluidd
print("\n=== Step 8: 测试Fluidd ===")
out, _ = run("curl -s -o /dev/null -w '%{http_code}' http://localhost:80/ 2>&1")
print(f"nginx 80端口: {out}")

out, _ = run("curl -s -o /dev/null -w '%{http_code}' http://localhost:8080/ 2>&1")
print(f"fluidd 8080端口: {out}")

# Step 9: 测试WebSocket
print("\n=== Step 9: 测试WebSocket ===")
out, _ = run("curl -s -o /dev/null -w '%{http_code}' -H 'Connection: Upgrade' -H 'Upgrade: websocket' -H 'Sec-WebSocket-Version: 13' -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' http://localhost:7125/websocket 2>&1")
print(f"WebSocket 7125: {out}")

out, _ = run("curl -s -o /dev/null -w '%{http_code}' -H 'Connection: Upgrade' -H 'Upgrade: websocket' -H 'Sec-WebSocket-Version: 13' -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' http://localhost:80/websocket 2>&1")
print(f"WebSocket nginx 80: {out}")

ssh.close()