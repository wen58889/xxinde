import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.105', username='root', password='1234', timeout=10)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=10)
    return stdout.read().decode('utf-8', errors='replace')

cmds = [
    # usb-watchdog日志 - 是否在反复恢复
    'journalctl -u usb-watchdog --since "30 min ago" --no-pager 2>&1 | tail -30',
    # moonraker重启历史
    'journalctl -u moonraker --since "30 min ago" --no-pager 2>&1 | grep -E "Started|Stopped|SIGTERM|restart" | tail -20',
    # klipper重启历史
    'journalctl -u klipper --since "30 min ago" --no-pager 2>&1 | grep -E "Started|Stopped|SIGTERM|restart" | tail -20',
    # usb-watchdog脚本内容
    'cat /usr/local/bin/usb-watchdog.sh 2>&1',
    # WiFi状态
    'iw dev wlan0 link 2>&1 | head -5',
    'ip addr show wlan0 2>&1 | grep inet',
    # 网络稳定性
    'ping -c 5 192.168.5.1 2>&1',
]

for cmd in cmds:
    print(f'=== {cmd[:70]} ===')
    out = run(cmd)
    print(out[:500])
    print()

ssh.close()