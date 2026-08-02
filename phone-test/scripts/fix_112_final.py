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

def run(cmd, timeout=30):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    stdout.channel.settimeout(timeout)
    return stdout.read().decode('utf-8', errors='replace')

# 一次性写入所有修复
print("=== 终极修复脚本 ===")

# 写入修复脚本到设备
fix_script = r'''#!/bin/bash
set -x

# 1. 获取WiFi密码
PSK=$(grep -r "psk=" /etc/NetworkManager/system-connections/ 2>/dev/null | head -1 | sed 's/.*psk=//' | tr -d ' ')
echo "WiFi PSK: found=$([ -n "$PSK" ] && echo yes || echo no)"

# 2. 删除旧连接
nmcli con delete "ZTE015G" 2>/dev/null || true

# 3. 重建连接(静态IP+高优先级+省电禁用+MAC固定)
if [ -n "$PSK" ]; then
    nmcli con add con-name "ZTE015G" \
        ifname wlan0 type wifi ssid "ZTE015G" \
        wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$PSK" \
        ipv4.method manual ipv4.addresses "192.168.5.112/24" \
        ipv4.gateway "192.168.5.1" ipv4.dns "8.8.8.8,114.114.114.114" \
        connection.autoconnect yes connection.autoconnect-priority 100 \
        connection.autoconnect-retries 0 \
        802-11-wireless.powersave 2 \
        802-11-wireless.cloned-mac-address "02:28:6a:10:5b:61" \
        2>&1
    echo "NEW CON: OK"
else
    echo "NO PSK! Trying modify instead..."
    nmcli con add con-name "ZTE015G" \
        ifname wlan0 type wifi ssid "ZTE015G" \
        wifi-sec.key-mgmt wpa-psk wifi-sec.psk "12345678" \
        ipv4.method manual ipv4.addresses "192.168.5.112/24" \
        ipv4.gateway "192.168.5.1" ipv4.dns "8.8.8.8,114.114.114.114" \
        connection.autoconnect yes connection.autoconnect-priority 100 \
        connection.autoconnect-retries 0 \
        802-11-wireless.powersave 2 \
        802-11-wireless.cloned-mac-address "02:28:6a:10:5b:61" \
        2>&1
fi

# 4. 立即禁用WiFi省电
iw dev wlan0 set power_save off 2>/dev/null || true

# 5. 禁用SDIO/MMC省电
for mmc in /sys/class/mmc_host/mmc*/mmc*/power/control; do
    [ -e "$mmc" ] && echo on > "$mmc" 2>/dev/null || true
done

# 6. 禁用wlan0 runtime PM
echo on > /sys/class/net/wlan0/power/control 2>/dev/null || true

# 7. 保存接口信息
echo "wlan0" > /etc/n1-fixed-iface

# 8. hostname
hostname n112
echo "n112" > /etc/hostname

echo "DONE"
'''

sftp = ssh.open_sftp()
with sftp.open('/tmp/fix_wifi.sh', 'w') as f:
    f.write(fix_script)
sftp.close()

run('chmod +x /tmp/fix_wifi.sh')
out = run('bash /tmp/fix_wifi.sh 2>&1', timeout=30)
print(out.strip())

# 验证
print("\n=== 验证配置 ===")
out = run('nmcli con show "ZTE015G" 2>&1 | grep -iE "ipv4.method|ipv4.address|autoconnect-priority|cloned-mac|powersave"')
print(out.strip())

# 启用连接
print("\n=== 启用连接 ===")
out = run('nmcli con up "ZTE015G" 2>&1', timeout=30)
print(out.strip()[:100])

time.sleep(5)

out = run('ip addr show wlan0 2>&1 | grep "inet "')
print(f"IP: {out.strip()}")

ssh.close()