import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=10, allow_agent=False, look_for_keys=False)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=15)
    return stdout.read().decode('utf-8', errors='replace').strip()

cmds = [
    'top -bn1 | head -15',
    'ps aux --sort=-%cpu | head -10',
    'cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null',
    'journalctl -u moonraker --since "5 min ago" --no-pager 2>&1 | grep -iE "websocket|pong|close" | tail -20',
    # 检查Tornado版本和pong_timeout
    '/root/moonraker-env/bin/python -c "import tornado; print(tornado.version)" 2>/dev/null',
    'grep -n "pong_timeout" /root/moonraker-env/lib/python*/site-packages/tornado/websocket.py 2>/dev/null | head -5',
    'grep -n "ping_interval\\|pong_timeout" /root/moonraker-env/lib/python*/site-packages/tornado/websocket.py 2>/dev/null | head -10',
]

for cmd in cmds:
    print(f'=== {cmd} ===')
    print(run(cmd))
    print()

ssh.close()