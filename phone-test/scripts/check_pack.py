import paramiko
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.101', username='root', password='1234', timeout=10)

def run(cmd, timeout=15):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    stdout.channel.settimeout(timeout)
    return stdout.read().decode('utf-8', errors='replace')

# 检查进程
print("=== 打包进程 ===")
out = run('pgrep -fa n1_golden_pack 2>&1 || echo "NO_PROCESS"')
print(out.strip())

# 检查文件
print("\n=== 打包文件 ===")
out = run('ls -lh /root/n1_golden_image.tar.gz 2>&1')
print(out.strip())

# 检查日志
print("\n=== 打包日志(最后20行) ===")
out = run('tail -20 /tmp/pack.log 2>&1')
print(out.strip())

ssh.close()