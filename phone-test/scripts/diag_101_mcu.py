import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.101', username='root', password='1234', timeout=10)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=10)
    return stdout.read().decode('utf-8', errors='replace')

cmds = [
    'lsusb 2>&1',
    'dmesg | grep -i "usb\\|serial\\|acm\\|klipper\\|rp2040" | tail -30',
    'cat /root/printer_data/config/printer.cfg 2>&1 | grep -A2 "mcu\\|serial"',
    'ls -la /dev/serial/ 2>&1',
    'systemctl status usb-watchdog --no-pager 2>&1 | head -15',
    'cat /usr/local/bin/usb-watchdog.sh 2>&1 || echo NO_FILE',
    'tail -5 /root/printer_data/logs/klippy.log 2>&1',
]

for cmd in cmds:
    print(f'=== {cmd} ===')
    out = run(cmd)
    print(out)
    print()

ssh.close()