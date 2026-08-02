import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.108', username='root', password='1234', timeout=15)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=15)
    return stdout.read().decode('utf-8', errors='replace')

cmds = [
    'lsusb 2>&1',
    'dmesg | grep -i "usb\\|serial\\|klipper\\|stm32\\|rp2040" | tail -15',
    'cat /usr/local/bin/usb-watchdog.sh 2>&1 | head -20',
    'journalctl -u usb-watchdog --since "5 min ago" --no-pager 2>&1 | tail -15',
    'journalctl -u klipper --since "5 min ago" --no-pager 2>&1 | tail -10',
    'tail -10 /root/printer_data/logs/klippy.log 2>&1',
    'systemctl status klipper --no-pager 2>&1 | head -10',
    'systemctl status moonraker --no-pager 2>&1 | head -10',
    'ss -tlnp | grep 7125 2>&1',
    'curl -s http://localhost:7125/server/info 2>&1',
    'curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/ 2>&1',
]

for cmd in cmds:
    print(f'=== {cmd[:60]} ===')
    out = run(cmd)
    print(out[:400])
    print()

ssh.close()