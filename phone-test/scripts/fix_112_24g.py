import paramiko
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

for ip in ['192.168.5.112', '192.168.5.106', '192.168.5.107']:
    try:
        ssh.connect(ip, username='root', password='1234', timeout=5)
        print(f"连接: {ip}")
        break
    except:
        continue
else:
    print("无法连接!")
    exit(1)

def run(cmd, timeout=15):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    stdout.channel.settimeout(timeout)
    return stdout.read().decode('utf-8', errors='replace')

# 查看当前WiFi
print("=== 当前WiFi ===")
out = run('iw dev wlan0 link 2>&1 | head -5')
print(out.strip())

out = run('nmcli -t -f NAME,TYPE con show --active 2>&1')
print(out.strip())

# 获取WiFi密码
print("\n=== 获取WiFi密码 ===")
out = run('grep -r "psk=" /etc/NetworkManager/system-connections/ 2>/dev/null | head -1')
print(f"密码文件: {out.strip()[:60]}...")

# 查看可用的2.4G SSID
print("\n=== 扫描WiFi ===")
out = run('nmcli -t -f SSID,SIGNAL,BAND dev wifi list 2>&1 | grep -i ZTE | head -5')
print(out.strip())

# 获取当前连接的密码
out = run('cat /etc/NetworkManager/system-connections/ZTE015G.nmconnection 2>/dev/null | grep psk=')
psk = out.strip().replace('psk=', '') if 'psk=' in out else ''
print(f"PSK: {'***' if psk else 'NOT_FOUND'}")

# 创建2.4G WiFi连接(ZTE01)
if psk:
    print("\n=== 创建2.4G WiFi连接 ZTE01 ===")
    out = run(f'nmcli con add con-name "ZTE01" ifname wlan0 type wifi ssid "ZTE01" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "{psk}" 802-11-wireless.band bg ipv4.method manual ipv4.addresses "192.168.5.112/24" ipv4.gateway "192.168.5.1" ipv4.dns "8.8.8.8,114.114.114.114" connection.autoconnect yes connection.autoconnect-priority 50 connection.autoconnect-retries 0 802-11-wireless.powersave 2 802-11-wireless.mac-address "02:28:6a:10:5b:61" 2>&1')
    print(f"创建: {out.strip()}")
    
    # 降低5G连接优先级(保留但不优先)
    out = run('nmcli con mod "ZTE015G" connection.autoconnect-priority 10 2>&1')
    print(f"5G优先级降为10: {out.strip()}")
    
    # 2.4G优先级50(低于有线的100，但高于5G的10)
    out = run('nmcli con mod "ZTE01" connection.autoconnect-priority 50 2>&1')
    print(f"2.4G优先级设为50: {out.strip()}")
    
    # 禁用2.4G的gateway(双网模式下WiFi不设gateway，避免路由冲突)
    # 实际上保留gateway但用route-metric控制优先级更可靠
    out = run('nmcli con mod "ZTE01" ipv4.route-metric 200 2>&1')
    print(f"2.4G route-metric=200: {out.strip()}")
    
    print("\n=== WiFi连接优先级 ===")
    out = run('nmcli -t -f NAME,TYPE,AUTOCONNECT-PRIORITY con show 2>&1 | grep -i wifi')
    print(out.strip())
    
    print("\n=== 切换到2.4G WiFi ===")
    out = run('nmcli con down "ZTE015G" 2>&1 && sleep 2 && nmcli con up "ZTE01" 2>&1', timeout=30)
    print(f"切换: {out.strip()[:100]}")
else:
    print("无法获取WiFi密码!")

time.sleep(5)

# 验证
print("\n=== 验证 ===")
try:
    out = run('iw dev wlan0 link 2>&1 | head -5')
    print(out.strip())
    out = run('hostname -I')
    print(f"IP: {out.strip()}")
except:
    print("WiFi切换中，等待重连...")

ssh.close()