import paramiko
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=10)

def run(cmd, timeout=15):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    stdout.channel.settimeout(timeout)
    return stdout.read().decode('utf-8', errors='replace')

# 删除所有WiFi连接
print("=== 删除所有WiFi连接 ===")
out = run('nmcli -t -f NAME,TYPE con show 2>&1 | grep wireless | cut -d: -f1')
wifi_cons = [l.strip() for l in out.strip().split('\n') if l.strip()]
print(f"现有WiFi连接: {wifi_cons}")
for con in wifi_cons:
    out = run(f'nmcli con delete "{con}" 2>&1')
    print(f"删除 {con}: {out.strip()}")

# 获取WiFi密码
out = run('grep -r "psk=" /etc/NetworkManager/system-connections/ 2>/dev/null | head -1')
psk = ''
if 'psk=' in out:
    psk = out.strip().split('psk=')[-1].strip()
print(f"WiFi密码: {'***' if psk else 'NOT_FOUND'}")

if psk:
    # 创建2.4G连接 (优先级50)
    print("\n=== 创建2.4G ZTE01 ===")
    out = run(f'nmcli con add con-name "ZTE01-24g" ifname wlan0 type wifi ssid "ZTE01" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "{psk}" ipv4.method manual ipv4.addresses "192.168.5.112/24" ipv4.gateway "192.168.5.1" ipv4.dns "8.8.8.8,114.114.114.114" connection.autoconnect yes connection.autoconnect-priority 50 connection.autoconnect-retries 0 802-11-wireless.powersave 2 802-11-wireless.mac-address "02:28:6a:10:5b:61" ipv4.route-metric 200 2>&1')
    print(f"2.4G: {out.strip()}")
    
    # 创建5G连接 (优先级10，备用)
    print("\n=== 创建5G ZTE015G ===")
    out = run(f'nmcli con add con-name "ZTE015G-5g" ifname wlan0 type wifi ssid "ZTE015G" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "{psk}" ipv4.method manual ipv4.addresses "192.168.5.112/24" ipv4.gateway "192.168.5.1" ipv4.dns "8.8.8.8,114.114.114.114" connection.autoconnect yes connection.autoconnect-priority 10 connection.autoconnect-retries 0 802-11-wireless.powersave 2 802-11-wireless.mac-address "02:28:6a:10:5b:61" ipv4.route-metric 200 2>&1')
    print(f"5G: {out.strip()}")
    
    # 连接2.4G
    print("\n=== 连接2.4G WiFi ===")
    out = run('nmcli con up "ZTE01-24g" 2>&1', timeout=30)
    print(f"连接: {out.strip()[:100]}")
    
    time.sleep(5)
    
    # 验证
    print("\n=== 验证 ===")
    out = run('iw dev wlan0 link 2>&1 | head -3')
    print(out.strip())
    out = run('nmcli dev status 2>&1')
    print(out.strip())

ssh.close()