import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=10, allow_agent=False, look_for_keys=False)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=15)
    return stdout.read().decode('utf-8', errors='replace').strip()

# 查看Moonraker版本和WebSocket相关源码
cmds = [
    'cd ~/moonraker && git log --oneline -5 2>/dev/null',
    'grep -r "ping" ~/moonraker/moonraker/websockets.py 2>/dev/null | head -20',
    'grep -r "pong" ~/moonraker/moonraker/websockets.py 2>/dev/null | head -20',
    'grep -r "PING" ~/moonraker/moonraker/websockets.py 2>/dev/null | head -20',
    'grep -rn "ping_interval\\|ping_timeout\\|ws_ping\\|pong_timeout\\|PONG" ~/moonraker/moonraker/ 2>/dev/null | head -20',
    'grep -rn "class WebSocket" ~/moonraker/moonraker/ 2>/dev/null | head -10',
    'grep -rn "websocket_ping\\|ping_interval\\|pong_timeout" ~/moonraker/moonraker/ 2>/dev/null | head -10',
]

for cmd in cmds:
    print(f'=== {cmd} ===')
    print(run(cmd))
    print()

ssh.close()