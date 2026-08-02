import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.105', username='root', password='1234', timeout=10)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=10)
    return stdout.read().decode('utf-8', errors='replace')

cmds = [
    'systemctl status moonraker --no-pager -l 2>&1 | head -20',
    'systemctl status klipper --no-pager -l 2>&1 | head -15',
    'ss -tlnp | grep -E "7125|8080|80" 2>&1',
    'curl -s http://localhost:7125/server/info 2>&1',
    'tail -40 /root/printer_data/logs/moonraker.log 2>&1',
    'tail -20 /root/printer_data/logs/klippy.log 2>&1',
    'ls /dev/serial/by-id/ 2>&1',
    'systemctl status usb-watchdog --no-pager 2>&1 | head -10',
    'cat /usr/local/bin/eth0-power-fix.sh 2>&1',
    'cat /etc/NetworkManager/dispatcher.d/99-eth0-stable.sh 2>&1',
    'ethtool eth0 2>&1 | grep -E "Link|Speed"',
    'journalctl -u moonraker --since "5 min ago" --no-pager 2>&1 | tail -20',
    'journalctl -u klipper --since "5 min ago" --no-pager 2>&1 | tail -15',
]

for cmd in cmds:
    print(f'=== {cmd[:70]} ===')
    out = run(cmd)
    print(out[:400])
    print()

ssh.close()