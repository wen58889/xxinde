import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=10, allow_agent=False, look_for_keys=False)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=15)
    return stdout.read().decode('utf-8', errors='replace').strip()

# 查看Tornado WebSocketHandler的ping/pong超时逻辑
cmds = [
    'sed -n "280,330p" /root/moonraker-env/lib/python3.12/site-packages/tornado/websocket.py 2>/dev/null',
    'sed -n "120,145p" /root/moonraker-env/lib/python3.12/site-packages/tornado/websocket.py 2>/dev/null',
    'grep -n "ping_timeout\\|websocket_ping_timeout\\|PONG\\|pong_timeout\\|close.*pong\\|on_close" /root/moonraker-env/lib/python3.12/site-packages/tornado/websocket.py 2>/dev/null | head -20',
]

for cmd in cmds:
    print(f'=== {cmd} ===')
    print(run(cmd))
    print()

ssh.close()