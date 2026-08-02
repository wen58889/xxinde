import paramiko
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=15)

def run(cmd, timeout=15):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    stdout.channel.settimeout(timeout)
    return stdout.read().decode('utf-8', errors='replace')

print("=== 扫描局域网N1设备 ===")
out = run('for ip in 192.168.5.{101,105,106,108,110,111,113,114,115}; do ping -c1 -W1 $ip 2>/dev/null | grep -q "1 received" && echo "ONLINE: $ip" || echo "OFFLINE: $ip"; done', timeout=30)
print(out.strip())

# 检查在线设备的Fluidd
print("\n=== 检查各设备Fluidd ===")
for ip in ['101', '105', '106', '108', '110', '111', '113', '114', '115']:
    full_ip = f'192.168.5.{ip}'
    out = run(f'ssh -o StrictHostKeyChecking=no -o ConnectTimeout=3 root@{full_ip} "ls /root/printer_data/fluidd/index.html 2>&1" 2>&1', timeout=8)
    result = out.strip()
    if 'index.html' in result:
        print(f"  {full_ip}: 有Fluidd!")
    elif 'Connection timed out' in result or 'No route' in result:
        pass
    else:
        print(f"  {full_ip}: {result[:50]}")

ssh.close()