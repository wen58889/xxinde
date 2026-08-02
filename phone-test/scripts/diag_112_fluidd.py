import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=10, allow_agent=False, look_for_keys=False)

cmds = [
    'cat /sys/module/usbcore/parameters/autosuspend',
    'ls /dev/serial/by-id/ 2>/dev/null',
    'curl -s http://localhost:7125/server/info 2>/dev/null',
    'journalctl -u usb-watchdog --since "10 min ago" --no-pager 2>&1 | tail -30',
    'journalctl -u klipper --since "10 min ago" --no-pager 2>&1 | tail -20',
    'dmesg | tail -30',
    'rfkill list 2>/dev/null',
    'nmcli radio wifi 2>/dev/null',
    'systemctl is-active usb-watchdog klipper moonraker go2rtc link-monitor n1-health-monitor n1-health-api 2>/dev/null',
    'head -5 /usr/local/bin/usb-watchdog.sh 2>/dev/null',
    'cat /sys/bus/usb/devices/*/power/control 2>/dev/null',
    'for d in /sys/bus/usb/devices/*/power/autosuspend; do echo "$d=$(cat $d 2>/dev/null)"; done 2>/dev/null',
]

for cmd in cmds:
    print(f'=== {cmd} ===')
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=15)
    print(stdout.read().decode('utf-8', errors='replace').strip())
    print()

ssh.close()