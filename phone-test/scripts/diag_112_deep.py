import paramiko
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

connected_ip = None
for ip in ['192.168.5.112', '192.168.5.106', '192.168.5.107', '192.168.5.108', '192.168.5.109', '192.168.5.110']:
    try:
        ssh.connect(ip, username='root', password='1234', timeout=3)
        connected_ip = ip
        print(f"连接: {ip}")
        break
    except:
        continue

if not connected_ip:
    print("无法连接!")
    exit(1)

def run(cmd, timeout=15):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    stdout.channel.settimeout(timeout)
    return stdout.read().decode('utf-8', errors='replace')

print(f"hostname: {run('hostname').strip()}")
print(f"当前IP: {run('hostname -I').strip()}")

print("\n=== 所有NM连接配置 ===")
out = run('nmcli con show 2>&1')
print(out.strip())

print("\n=== ZTE015G配置(关键项) ===")
out = run('nmcli con show "ZTE015G" 2>&1 | grep -iE "ipv4.method|ipv4.address|ipv4.gateway|ipv4.dns|autoconnect|cloned-mac|route-metric"')
print(out.strip())

print("\n=== NM日志(最近IP变化) ===")
out = run('journalctl -u NetworkManager --no-pager -n 50 --since "5 min ago" 2>&1 | grep -iE "ip|address|dhcp|activ|deactiv|disconnect|connect"')
print(out.strip())

print("\n=== 所有WiFi连接配置文件 ===")
out = run('nmcli -t -f NAME,TYPE con show 2>&1 | grep -i wireless')
print(out.strip())

print("\n=== /etc/NetworkManager/conf.d/ 所有配置 ===")
out = run('for f in /etc/NetworkManager/conf.d/*.conf; do echo "--- $f ---"; cat "$f" 2>/dev/null; done')
print(out.strip())

print("\n=== fix-mac.sh ===")
out = run('cat /usr/local/bin/fix-mac.sh 2>/dev/null || echo "NOT FOUND"')
print(out.strip()[:500])

print("\n=== dispatcher脚本 ===")
out = run('ls -la /etc/NetworkManager/dispatcher.d/ 2>&1')
print(out.strip())

print("\n=== WiFi连接状态 ===")
out = run('iw dev wlan0 link 2>&1')
print(out.strip()[:300])

print("\n=== brcmfmac参数 ===")
out = run('cat /sys/module/brcmfmac/parameters/roamoff 2>&1')
print(f"roamoff: {out.strip()}")

print("\n=== dmesg WiFi错误 ===")
out = run('dmesg | grep -iE "brcmfmac|wlan|wifi" | tail -10')
print(out.strip())

ssh.close()