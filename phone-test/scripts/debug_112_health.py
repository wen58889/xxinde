import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=10)

def run(cmd, timeout=15):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    stdout.channel.settimeout(timeout)
    return stdout.read().decode('utf-8', errors='replace').strip()

# 检查状态缓存文件内容
out = run("cat /var/run/n1-health-status.json 2>/dev/null")
print(f"状态缓存内容:\n{out}")

# 检查JSON是否有效
out = run("python3 -c \"import json; json.load(open('/var/run/n1-health-status.json'))\" 2>&1")
print(f"JSON验证: {out}")

# 查看health-monitor日志
out = run("journalctl -u n1-health-monitor --since '2 min ago' --no-pager 2>/dev/null | tail -20")
print(f"\nhealth-monitor日志:\n{out}")

ssh.close()