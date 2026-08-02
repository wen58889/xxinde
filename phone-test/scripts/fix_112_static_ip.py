import paramiko
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

# 尝试多个IP
connected_ip = None
for ip in ['192.168.5.112', '192.168.5.106', '192.168.5.107', '192.168.5.108']:
    try:
        ssh.connect(ip, username='root', password='1234', timeout=5)
        connected_ip = ip
        print(f"连接成功: {ip}")
        break
    except:
        continue

if not connected_ip:
    print("无法连接任何IP!")
    exit(1)

def run(cmd, timeout=15):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    stdout.channel.settimeout(timeout)
    return stdout.read().decode('utf-8', errors='replace')

# Step 1: 查看当前WiFi连接
print("=== 当前WiFi连接 ===")
out = run('nmcli -t -f NAME,TYPE,DEVICE con show --active 2>&1')
print(out.strip())

# Step 2: 给WiFi连接设置静态IP 192.168.5.112
print("\n=== 设置WiFi静态IP: 192.168.5.112 ===")
out = run('nmcli con mod "ZTE015G" ipv4.method manual ipv4.addresses "192.168.5.112/24" ipv4.gateway "192.168.5.1" ipv4.dns "8.8.8.8,114.114.114.114" connection.autoconnect-priority 100 connection.autoconnect-retries 0 2>&1')
print(f"设置结果: {out.strip()}")

# Step 3: 设置WiFi的cloned-mac-address
print("\n=== 设置WiFi cloned-mac-address ===")
out = run('nmcli con mod "ZTE015G" 802-11-wireless.cloned-mac-address "02:28:6a:10:5b:61" 2>&1')
print(f"MAC设置: {out.strip()}")

# Step 4: 设置hostname
print("\n=== 设置hostname ===")
out = run('hostname n112 2>&1 && echo "n112" > /etc/hostname 2>&1 && echo "hostname set to n112"')
print(out.strip())

# Step 5: 验证配置
print("\n=== 验证WiFi配置 ===")
out = run('nmcli con show "ZTE015G" 2>&1 | grep -iE "ipv4.method|ipv4.address|autoconnect|cloned-mac|route-metric"')
print(out.strip())

# Step 6: 重启WiFi连接使配置生效
print("\n=== 重启WiFi连接 ===")
out = run('nmcli con down "ZTE015G" 2>&1 && sleep 3 && nmcli con up "ZTE015G" 2>&1')
print(f"重启结果: {out.strip()}")

time.sleep(5)

# Step 7: 验证新IP
print("\n=== 验证新IP ===")
out = run('ip addr show wlan0 2>&1 | grep "inet "')
print(out.strip())

out = run('hostname')
print(f"hostname: {out.strip()}")

ssh.close()