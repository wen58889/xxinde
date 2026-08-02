import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=15)

def run(cmd, timeout=15):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    stdout.channel.settimeout(timeout)
    return stdout.read().decode('utf-8', errors='replace')

print("=== 测试GitHub连通性 ===")
out = run('curl -sI --connect-timeout 5 https://github.com 2>&1 | head -3')
print(out)

print("=== 测试ghfast.top镜像 ===")
out = run('curl -sI --connect-timeout 5 https://ghfast.top 2>&1 | head -3')
print(out)

print("=== 检查fluidd目录 ===")
out = run('ls -la /root/printer_data/fluidd/ 2>&1 | head -10')
print(out)

print("=== 检查fluidd服务 ===")
out = run('systemctl status fluidd 2>&1 | head -10')
print(out)

ssh.close()