import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=10, allow_agent=False, look_for_keys=False)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=15)
    return stdout.read().decode('utf-8', errors='replace').strip()

cmds = [
    'journalctl -u link-monitor --since "30 min ago" --no-pager 2>&1 | tail -30',
    'dmesg | grep -iE "eth0|link|down|up" | tail -20',
    'ethtool eth0 2>/dev/null',
    'cat /etc/n1-fixed-iface 2>/dev/null',
    'cat /etc/n1_network_info.txt 2>/dev/null',
    'nmcli -t -f NAME,DEVICE,TYPE con show --active 2>/dev/null',
    'cat /etc/NetworkManager/dispatcher.d/99-eth0-stable.sh 2>/dev/null',
    'cat /etc/NetworkManager/dispatcher.d/99-wired-stability.sh 2>/dev/null',
    'systemctl is-active eth0-power-fix 2>/dev/null',
    'ethtool --show-eee eth0 2>/dev/null',
]

for cmd in cmds:
    print(f'=== {cmd} ===')
    print(run(cmd))
    print()

ssh.close()