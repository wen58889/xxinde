import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=10, allow_agent=False, look_for_keys=False)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=15)
    return stdout.read().decode('utf-8', errors='replace').strip()

cmds = [
    'grep -n "websocket_ping\\|ping_interval\\|pong_timeout\\|PING_TIMEOUT\\|ping_timeout" ~/moonraker/moonraker/components/application.py 2>/dev/null',
    'sed -n "120,145p" ~/moonraker/moonraker/components/application.py 2>/dev/null',
    'grep -n "class WebSocketManager\\|def __init__\\|ping_interval\\|pong_timeout\\|PING" ~/moonraker/moonraker/components/websockets.py 2>/dev/null | head -20',
    'sed -n "1,50p" ~/moonraker/moonraker/components/websockets.py 2>/dev/null',
]

for cmd in cmds:
    print(f'=== {cmd} ===')
    print(run(cmd))
    print()

ssh.close()