import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=15)

def run(cmd, timeout=15):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    stdout.channel.settimeout(timeout)
    return stdout.read().decode('utf-8', errors='replace')

print("=== 下载日志 ===")
out = run('cat /tmp/fluidd_download.log 2>&1')
print(out)

print("=== 下载状态 ===")
out = run('cat /tmp/fluidd_download_status 2>&1')
print(out)

print("=== 测试GitHub下载(小文件) ===")
out = run('curl -sI --connect-timeout 10 -L https://github.com/fluidd-core/fluidd/releases/latest/download/fluidd.zip 2>&1 | head -15')
print(out)

print("=== 测试直接下载(release API) ===")
out = run('curl -sI --connect-timeout 10 "https://api.github.com/repos/fluidd-core/fluidd/releases/latest" 2>&1 | head -5')
print(out)

print("=== 检查pip是否可用 ===")
out = run('which pip3 && pip3 --version 2>&1')
print(out)

print("=== 检查是否有代理 ===")
out = run('echo $http_proxy; echo $https_proxy; cat /etc/environment 2>/dev/null | grep -i proxy')
print(out)

ssh.close()