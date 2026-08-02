import paramiko
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.101', username='root', password='1234', timeout=10)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=15)
    return stdout.read().decode('utf-8', errors='replace'), stderr.read().decode('utf-8', errors='replace')

cmds = [
    # 1. Moonraker状态和日志
    'systemctl status moonraker --no-pager -l 2>&1 | head -25',
    'tail -50 /root/printer_data/logs/moonraker.log 2>&1',
    # 2. Klipper状态
    'systemctl status klipper --no-pager -l 2>&1 | head -15',
    'tail -30 /root/printer_data/logs/klippy.log 2>&1',
    # 3. Fluidd服务
    'systemctl status fluidd --no-pager -l 2>&1',
    'cat /etc/systemd/system/fluidd.service 2>&1',
    # 4. 网络状态
    'ip addr show 2>&1',
    'ip route show 2>&1',
    'ethtool eth0 2>&1 | head -10',
    # 5. Moonraker API测试
    'curl -s http://localhost:7125/server/info 2>&1',
    'curl -s http://192.168.5.101:7125/server/info 2>&1',
    # 6. Fluidd访问测试
    'curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/ 2>&1',
    'curl -s -o /dev/null -w "%{http_code}" http://192.168.5.101:8080/ 2>&1',
    # 7. WebSocket测试
    'curl -s -o /dev/null -w "%{http_code}" -H "Connection: Upgrade" -H "Upgrade: websocket" http://localhost:7125/websocket 2>&1',
    # 8. moonraker.conf
    'cat /root/printer_data/config/moonraker.conf 2>&1',
    # 9. 检查nginx
    'systemctl status nginx --no-pager -l 2>&1 | head -15',
    'cat /etc/nginx/sites-enabled/fluidd 2>&1 || cat /etc/nginx/conf.d/fluidd.conf 2>&1 || echo NO_NGINX_FLUIDD',
    # 10. 端口监听
    'ss -tlnp 2>&1',
]

for cmd in cmds:
    print(f'=== {cmd} ===')
    out, err = run(cmd)
    print(out)
    if err.strip():
        print(f'STDERR: {err}')
    print()

ssh.close()