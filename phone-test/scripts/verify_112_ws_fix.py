import paramiko
import time
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=10, allow_agent=False, look_for_keys=False)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=15)
    return stdout.read().decode('utf-8', errors='replace').strip()

# 验证application.py修改
print("=== 验证application.py ===")
print(run("grep websocket_ping_interval /root/moonraker/moonraker/components/application.py"))

# 检查当前WebSocket状态
print("\n=== 当前WebSocket日志 ===")
print(run("journalctl -u moonraker --since '2 min ago' --no-pager 2>&1 | grep -iE 'websocket|pong|close|ping' | tail -10"))

# 验证klippy状态
print("\n=== klippy状态 ===")
out = run("curl -s http://localhost:7125/server/info 2>/dev/null")
if '"klippy_state":"ready"' in out:
    print("ready")
else:
    print(out[:200])

# 验证所有服务
print("\n=== 服务状态 ===")
print(run("systemctl is-active klipper moonraker go2rtc usb-watchdog link-monitor n1-health-monitor n1-health-api 2>/dev/null"))

ssh.close()