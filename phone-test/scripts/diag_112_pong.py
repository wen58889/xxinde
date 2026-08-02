import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=10, allow_agent=False, look_for_keys=False)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=15)
    return stdout.read().decode('utf-8', errors='replace').strip()

# Tornado WebSocketHandler默认pong_timeout是ping_interval的3倍
# 但Moonraker可能覆盖了，检查WebSocket类
cmds = [
    'grep -n "pong_timeout\\|ping_timeout\\|PONG_TIMEOUT\\|on_pong\\|on_ping\\|on_close" ~/moonraker/moonraker/components/websockets.py 2>/dev/null | head -20',
    'sed -n "234,280p" ~/moonraker/moonraker/components/websockets.py 2>/dev/null',
    'python3 -c "import tornado; print(tornado.version)" 2>/dev/null',
    'grep -n "pong_timeout" ~/moonraker-env/lib/*/site-packages/tornado/websocket.py 2>/dev/null | head -5',
]

for cmd in cmds:
    print(f'=== {cmd} ===')
    print(run(cmd))
    print()

ssh.close()