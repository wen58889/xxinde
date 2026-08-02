import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=10, allow_agent=False, look_for_keys=False)

cmds = [
    'journalctl -u usb-watchdog --since "1 hour ago" --no-pager 2>&1 | tail -50',
    'journalctl -u klipper --since "1 hour ago" --no-pager 2>&1 | grep -iE "disconnect|lost|timeout|restart|MCU|serial" | tail -30',
    'journalctl -u moonraker --since "1 hour ago" --no-pager 2>&1 | grep -iE "disconnect|lost|connection|websocket" | tail -20',
    'cat /var/run/n1-health-status.json 2>/dev/null',
    'systemctl is-enabled usb-autosuspend-fix 2>/dev/null',
    'cat /etc/systemd/system/usb-autosuspend-fix.service 2>/dev/null',
    'systemctl status usb-autosuspend-fix 2>/dev/null | head -10',
    'ethtool eth0 2>/dev/null | head -10',
    'cat /etc/NetworkManager/dispatcher.d/99-eth0-stable.sh 2>/dev/null',
    'cat /usr/local/bin/eth0-power-fix.sh 2>/dev/null',
    'systemctl is-enabled eth0-power-fix n1-rfkill-persist net-check 2>/dev/null',
    'cat /etc/modprobe.d/brcmfmac.conf 2>/dev/null',
    'lsmod | grep brcmfmac',
]

for cmd in cmds:
    print(f'=== {cmd} ===')
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=15)
    out = stdout.read().decode('utf-8', errors='replace').strip()
    print(out)
    print()

ssh.close()