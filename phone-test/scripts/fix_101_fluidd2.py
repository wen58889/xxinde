import paramiko
import time

def ssh_exec(host, cmds, timeout=15):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username='root', password='1234', timeout=10)
    results = {}
    for cmd in cmds:
        stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode('utf-8', errors='replace')
        err = stderr.read().decode('utf-8', errors='replace')
        results[cmd] = (out, err)
    ssh.close()
    return results

# Step 1: 先恢复eth0 PHY
print("=== Step 1: 恢复eth0 PHY ===")
r = ssh_exec('192.168.5.101', [
    'ethtool -s eth0 autoneg on 2>&1',
])
print(r)

time.sleep(5)

# Step 2: 检查eth0状态
print("\n=== Step 2: 检查eth0 ===")
r = ssh_exec('192.168.5.101', [
    'ethtool eth0 2>&1 | grep -E "Link|Speed|Auto-neg"',
    'ip addr show eth0 2>&1 | grep inet',
])
for k, v in r.items():
    print(f"{k}: {v[0]}")

# Step 3: 修复eth0-power-fix.sh
print("\n=== Step 3: 修复eth0-power-fix.sh ===")
r = ssh_exec('192.168.5.101', [
    """cat > /usr/local/bin/eth0-power-fix.sh << 'PEOF'
#!/bin/bash
sleep 2
IFACE=$(cat /etc/n1-fixed-iface 2>/dev/null || echo "eth0")
[ -e "/sys/class/net/$IFACE" ] || IFACE="eth0"
ethtool --set-eee $IFACE eee off 2>/dev/null || true
ethtool -s $IFACE wol d 2>/dev/null || true
echo on > /sys/class/net/$IFACE/power/control 2>/dev/null || true
logger -t eth0-power-fix "$IFACE: EEE off + WoL off + PM on (no speed force)"
PEOF
chmod +x /usr/local/bin/eth0-power-fix.sh
echo DONE""",
])
print(r)

# Step 4: 修复dispatcher
print("\n=== Step 4: 修复dispatcher ===")
r = ssh_exec('192.168.5.101', [
    """cat > /etc/NetworkManager/dispatcher.d/99-eth0-stable.sh << 'DEOF'
#!/bin/bash
IFACE="$1"
ACTION="$2"
if [ "$IFACE" = "eth0" ] && [ "$ACTION" = "up" ]; then
    ethtool --set-eee eth0 eee off 2>/dev/null || true
    ethtool -s eth0 wol d 2>/dev/null || true
    echo on > /sys/class/net/eth0/power/control 2>/dev/null || true
    logger -t eth0-stable "eth0 up: EEE off + WoL off + PM on (no speed force)"
fi
DEOF
chmod +x /etc/NetworkManager/dispatcher.d/99-eth0-stable.sh
echo DONE""",
])
print(r)

# Step 5: 修复NM连接属性
print("\n=== Step 5: 修复NM属性 ===")
r = ssh_exec('192.168.5.101', [
    'nmcli -t -f NAME,DEVICE con show --active 2>&1 | grep eth0',
])
con_line = r[list(r.keys())[0]][0].strip()
print(f"连接: {con_line}")
if con_line:
    con_name = con_line.split(':')[0]
    r2 = ssh_exec('192.168.5.101', [
        f"nmcli con mod '{con_name}' 802-3-ethernet.speed 0 2>/dev/null || true; echo DONE",
    ])
    print(r2)

# Step 6: 重启moonraker
print("\n=== Step 6: 重启moonraker ===")
r = ssh_exec('192.168.5.101', [
    'systemctl restart moonraker 2>&1; echo RESTARTED',
])
print(r)
time.sleep(12)

# Step 7: 验证
print("\n=== Step 7: 验证 ===")
r = ssh_exec('192.168.5.101', [
    'systemctl status moonraker --no-pager -l 2>&1 | head -12',
    'ss -tlnp | grep 7125 2>&1',
    'curl -s http://localhost:7125/server/info 2>&1',
    'curl -s -o /dev/null -w "%{http_code}" http://localhost:80/ 2>&1',
    'curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/ 2>&1',
    'ethtool eth0 2>&1 | grep -E "Link|Speed"',
    'ip addr show eth0 2>&1 | grep inet',
    'ip route show 2>&1 | head -5',
])
for k, v in r.items():
    print(f"\n--- {k} ---")
    print(v[0][:300])