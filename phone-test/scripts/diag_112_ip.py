import paramiko
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

# 尝试多个IP
for ip in ['192.168.5.112', '192.168.5.106', '192.168.5.107']:
    try:
        ssh.connect(ip, username='root', password='1234', timeout=5)
        print(f"连接成功: {ip}")
        break
    except:
        continue
else:
    print("所有IP都无法连接!")
    exit(1)

def run(cmd, timeout=15):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    stdout.channel.settimeout(timeout)
    return stdout.read().decode('utf-8', errors='replace')

print("=== 当前IP ===")
out = run('hostname -I')
print(out.strip())

print("\n=== NetworkManager连接 ===")
out = run('nmcli con show 2>&1')
print(out.strip())

print("\n=== NM设备状态 ===")
out = run('nmcli dev status 2>&1')
print(out.strip())

print("\n=== eth0配置 ===")
out = run('nmcli con show "Wired connection 1" 2>&1 | head -20')
print(out.strip())

print("\n=== wlan0配置 ===")
out = run('nmcli con show "ZTE01" 2>&1 | head -20')
print(out.strip())

print("\n=== /etc/NetworkManager配置 ===")
out = run('cat /etc/NetworkManager/NetworkManager.conf 2>&1')
print(out.strip())

print("\n=== /etc/network/interfaces ===")
out = run('cat /etc/network/interfaces 2>&1')
print(out.strip())

print("\n=== n1-fixed-mac ===")
out = run('cat /etc/n1-fixed-mac 2>&1')
print(out.strip())

print("\n=== dhclient进程 ===")
out = run('ps aux | grep -i dhcp 2>&1')
print(out.strip())

print("\n=== IP地址历史(journalctl) ===")
out = run('journalctl -u NetworkManager --no-pager -n 30 2>&1 | grep -iE "ip|address|dhcp|connect|activ"')
print(out.strip())

print("\n=== 当前所有IP ===")
out = run('ip addr show 2>&1 | grep "inet "')
print(out.strip())

print("\n=== armbianEnv.txt网络配置 ===")
out = run('cat /boot/armbianEnv.txt 2>&1 | grep -iE "ip|dhcp|eth|net"')
print(out.strip())

ssh.close()