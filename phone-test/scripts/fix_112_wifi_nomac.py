import paramiko
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=10)

def run(cmd, timeout=15):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    stdout.channel.settimeout(timeout)
    return stdout.read().decode('utf-8', errors='replace')

# 删除旧WiFi连接
run('nmcli con delete "ZTE01-24g" 2>/dev/null || true')
run('nmcli con delete "ZTE015G-5g" 2>/dev/null || true')

# 查看wlan0当前MAC
out = run('cat /sys/class/net/wlan0/address 2>&1')
real_mac = out.strip()
print(f"wlan0真实MAC: {real_mac}")

psk = "18677350613"

# 创建2.4G连接(不指定mac-address，让NM自动匹配)
print("\n=== 创建2.4G ZTE01-24g ===")
out = run(f'nmcli con add con-name "ZTE01-24g" ifname wlan0 type wifi ssid "ZTE01" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "{psk}" ipv4.method manual ipv4.addresses "192.168.5.112/24" ipv4.gateway "192.168.5.1" ipv4.dns "8.8.8.8,114.114.114.114" connection.autoconnect yes connection.autoconnect-priority 50 connection.autoconnect-retries 0 802-11-wireless.powersave 2 ipv4.route-metric 200 2>&1')
print(f"2.4G: {out.strip()}")

# 创建5G连接
print("\n=== 创建5G ZTE015G-5g ===")
out = run(f'nmcli con add con-name "ZTE015G-5g" ifname wlan0 type wifi ssid "ZTE015G" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "{psk}" ipv4.method manual ipv4.addresses "192.168.5.112/24" ipv4.gateway "192.168.5.1" ipv4.dns "8.8.8.8,114.114.114.114" connection.autoconnect yes connection.autoconnect-priority 10 connection.autoconnect-retries 0 802-11-wireless.powersave 2 ipv4.route-metric 200 2>&1')
print(f"5G: {out.strip()}")

# 连接2.4G
print("\n=== 连接2.4G WiFi ===")
out = run('nmcli con up "ZTE01-24g" 2>&1', timeout=30)
print(f"2.4G: {out.strip()[:100]}")

time.sleep(5)

# 验证
print("\n=== 验证 ===")
out = run('iw dev wlan0 link 2>&1 | head -4')
print(out.strip())
out = run('nmcli dev status 2>&1')
print(out.strip())
out = run('hostname -I')
print(f"IP: {out.strip()}")

ssh.close()