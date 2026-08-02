import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=10, allow_agent=False, look_for_keys=False)

cmds = [
    'cat ~/printer_data/config/moonraker.conf 2>/dev/null',
    'journalctl -u moonraker --since "30 min ago" --no-pager 2>&1 | grep -iE "pong|websocket|close|timeout|ping" | tail -30',
    'cat /etc/systemd/system/moonraker.service 2>/dev/null',
    'ss -tlnp | grep -E "7125|8080|1984|8090" 2>/dev/null',
    'free -m 2>/dev/null',
    'cat /proc/uptime',
]

for cmd in cmds:
    print(f'=== {cmd} ===')
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=15)
    out = stdout.read().decode('utf-8', errors='replace').strip()
    print(out[:3000])
    print()

ssh.close()