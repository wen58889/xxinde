import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=10, allow_agent=False, look_for_keys=False)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=15)
    return stdout.read().decode('utf-8', errors='replace').strip()

# 找到正确的tornado路径
cmds = [
    'find /root/moonraker-env -name "websocket.py" -path "*/tornado/*" 2>/dev/null',
    '/root/moonraker-env/bin/python -c "import tornado.websocket; print(tornado.websocket.__file__)" 2>/dev/null',
]

for cmd in cmds:
    print(f'=== {cmd} ===')
    print(run(cmd))
    print()

ssh.close()