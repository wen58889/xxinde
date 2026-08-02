import paramiko
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.101', username='root', password='1234', timeout=10)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=15)
    return stdout.read().decode('utf-8', errors='replace'), stderr.read().decode('utf-8', errors='replace')

# 等待moonraker完全启动
time.sleep(10)

cmds = [
    'systemctl status moonraker --no-pager -l 2>&1 | head -20',
    'ss -tlnp | grep 7125 2>&1',
    'curl -s http://localhost:7125/server/info 2>&1',
    'curl -s http://192.168.5.101:7125/server/info 2>&1',
    # 检查moonraker日志中是否有错误
    'tail -80 /root/printer_data/logs/moonraker.log 2>&1',
    # 检查moonraker是否反复重启
    'journalctl -u moonraker --since "5 min ago" --no-pager 2>&1 | tail -30',
    # 检查eth0网线状态
    'ethtool eth0 2>&1 | grep -E "Link|Speed" ',
    'cat /etc/n1-eth0-speed-mode 2>&1 || echo NO_SPEED_MODE_FILE',
    # 检查之前修复脚本是否留下了什么
    'cat /usr/local/bin/eth0-power-fix.sh 2>&1',
    'cat /etc/NetworkManager/dispatcher.d/99-eth0-stable.sh 2>&1',
    'systemctl status eth0-power-fix.service 2>&1 | head -10',
    'systemctl status wired-watchdog 2>&1 | head -10',
    # 检查rc.local
    'cat /etc/rc.local 2>&1 || echo NO_RC_LOCAL',
]

for cmd in cmds:
    print(f'=== {cmd} ===')
    out, err = run(cmd)
    print(out)
    if err.strip():
        print(f'STDERR: {err}')
    print()

ssh.close()