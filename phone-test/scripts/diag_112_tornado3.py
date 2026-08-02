import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=10, allow_agent=False, look_for_keys=False)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=15)
    return stdout.read().decode('utf-8', errors='replace').strip()

cmds = [
    'grep -n "ping_timeout\\|websocket_ping_timeout\\|pong_timeout\\|Pong Time\\|on_pong\\|_ping\\|_pong" /root/moonraker-env/lib/python3.13/site-packages/tornado/websocket.py 2>/dev/null | head -30',
    'sed -n "295,330p" /root/moonraker-env/lib/python3.13/site-packages/tornado/websocket.py 2>/dev/null',
]

for cmd in cmds:
    print(f'=== {cmd} ===')
    print(run(cmd))
    print()

ssh.close()