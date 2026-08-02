import paramiko
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.105', username='root', password='1234', timeout=10)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=15)
    return stdout.read().decode('utf-8', errors='replace'), stderr.read().decode('utf-8', errors='replace')

# 检查fluidd.service状态和配置
cmds = [
    'systemctl status fluidd.service --no-pager -l 2>&1',
    'cat /etc/systemd/system/fluidd.service 2>&1',
    'curl -s -o /dev/null -w "http_code=%{http_code} content_type=%{content_type}" http://localhost:8080/ 2>&1',
    'curl -s http://localhost:8080/ 2>&1 | head -15',
    # 从外部IP测试
    'curl -s -o /dev/null -w "http_code=%{http_code}" http://192.168.5.105:8080/ 2>&1',
    # 检查fluidd的config.json中API地址配置
    'cat /root/printer_data/fluidd/config.json 2>&1',
    # 检查Fluidd能否连接到Moonraker API
    'curl -s http://localhost:7125/server/info 2>&1 | python3 -m json.tool 2>&1 | head -10',
    # 检查防火墙
    'iptables -L -n 2>&1 | head -20',
    'ufw status 2>&1 || echo NO_UFW',
]

for cmd in cmds:
    print(f'=== {cmd} ===')
    out, err = run(cmd)
    print(out)
    if err.strip():
        print(f'STDERR: {err}')
    print()

ssh.close()