import paramiko
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=15)

def run(cmd, timeout=15):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    stdout.channel.settimeout(timeout)
    return stdout.read().decode('utf-8', errors='replace')

# 扫描局域网中其他N1设备
print("=== 扫描局域网N1设备 ===")
out = run('for ip in 192.168.5.{101,105,106,108,110,111,113,114,115}; do ping -c1 -W1 $ip 2>/dev/null | grep -q "1 received" && echo "ONLINE: $ip" || echo "OFFLINE: $ip"; done', timeout=30)
print(out.strip())

# 检查108是否有Fluidd
print("\n=== 检查108 Fluidd ===")
out = run('ssh -o StrictHostKeyChecking=no -o ConnectTimeout=3 root@192.168.5.108 "ls /root/printer_data/fluidd/index.html 2>&1" 2>&1', timeout=10)
print(f"108: {out.strip()}")

# 检查106
print("\n=== 检查106 Fluidd ===")
out = run('ssh -o StrictHostKeyChecking=no -o ConnectTimeout=3 root@192.168.5.106 "ls /root/printer_data/fluidd/index.html 2>&1" 2>&1', timeout=10)
print(f"106: {out.strip()}")

ssh.close()