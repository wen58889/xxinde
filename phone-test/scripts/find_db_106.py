import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.106', username='root', password='1234', timeout=10)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=10)
    return stdout.read().decode('utf-8', errors='replace')

# 搜索数据库文件
cmds = [
    'find / -maxdepth 5 -name "*.db" -o -name "*.sqlite" -o -name "*.sqlite3" 2>/dev/null | grep -v proc | grep -v sys | head -20',
    'find / -maxdepth 5 -name "phone*" -type d 2>/dev/null | head -10',
    'find / -maxdepth 5 -name "*.db" 2>/dev/null | grep -i "phone\\|test\\|calib\\|app" | head -10',
    # 检查是否有phone-test后端运行
    'ps aux | grep -i "uvicorn\\|fastapi\\|phone" 2>&1 | grep -v grep',
    'ss -tlnp | grep -E "8080|8000|5000" 2>&1',
    # 检查docker
    'docker ps 2>&1 || echo NO_DOCKER',
    # 检查常见部署位置
    'ls -la /opt/ 2>&1',
    'ls -la /root/ 2>&1 | head -20',
    'ls -la /srv/ 2>&1',
]

for cmd in cmds:
    print(f'=== {cmd} ===')
    out = run(cmd)
    print(out)
    print()

ssh.close()