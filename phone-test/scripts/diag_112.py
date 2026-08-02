import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=15)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=15)
    return stdout.read().decode('utf-8', errors='replace')

cmds = [
    'systemctl status fluidd --no-pager 2>&1 | head -15',
    'systemctl status moonraker --no-pager 2>&1 | head -10',
    'systemctl status klipper --no-pager 2>&1 | head -10',
    'ss -tlnp | grep -E "7125|8080|80" 2>&1',
    'curl -s http://localhost:7125/server/info 2>&1 | head -5',
    'curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/ 2>&1',
    'ls -la /root/printer_data/fluidd/ 2>&1 | head -10',
    'cat /usr/local/bin/fluidd-serve.sh 2>&1',
    'cat /etc/systemd/system/fluidd.service 2>&1',
    'journalctl -u fluidd --since "10 min ago" --no-pager 2>&1 | tail -15',
    'ls /dev/serial/by-id/ 2>&1',
    'ls -la /var/www/fluidd/ 2>&1 | head -5',
    'systemctl status nginx --no-pager 2>&1 | head -5',
]

for cmd in cmds:
    print(f'=== {cmd[:60]} ===')
    out = run(cmd)
    print(out[:400])
    print()

ssh.close()