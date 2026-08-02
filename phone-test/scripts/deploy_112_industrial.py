import paramiko
import time
import os

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=10)

def run(cmd, timeout=30):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    stdout.channel.settimeout(timeout)
    return stdout.read().decode('utf-8', errors='replace').strip()

def upload_file(local_path, remote_path):
    sftp = ssh.open_sftp()
    sftp.put(local_path, remote_path)
    sftp.close()

BASE = r"D:\Users\59520\IDEProjects\xxinde\phone-test\n1"

# 1. alert-push.sh
print("=== 1. 部署alert-push.sh ===")
upload_file(os.path.join(BASE, "alert-push.sh"), "/usr/local/bin/alert-push.sh")
run("chmod +x /usr/local/bin/alert-push.sh")
run("mkdir -p /var/run/n1-alert-dedup")
out = run("source /usr/local/bin/alert-push.sh && type alert_push 2>&1 | head -1")
print(f"  alert_push: {out}")

# 2. link-monitor.sh
print("\n=== 2. 部署link-monitor.sh ===")
upload_file(os.path.join(BASE, "link-monitor.sh"), "/usr/local/bin/link-monitor.sh")
run("chmod +x /usr/local/bin/link-monitor.sh")
run(r"""cat > /etc/systemd/system/link-monitor.service << 'EOF'
[Unit]
Description=Wired Link Monitor for eth0
After=NetworkManager.service
Wants=NetworkManager.service

[Service]
Type=simple
ExecStart=/usr/local/bin/link-monitor.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable link-monitor.service 2>/dev/null || true
systemctl start link-monitor.service 2>/dev/null || true""")
out = run("systemctl is-active link-monitor 2>/dev/null")
print(f"  link-monitor: {out}")

# 3. n1-health-monitor.sh
print("\n=== 3. 部署n1-health-monitor.sh ===")
upload_file(os.path.join(BASE, "n1-health-monitor.sh"), "/usr/local/bin/n1-health-monitor.sh")
run("chmod +x /usr/local/bin/n1-health-monitor.sh")
run(r"""cat > /etc/systemd/system/n1-health-monitor.service << 'EOF'
[Unit]
Description=N1 Health Monitor (Disk/Memory/Temp/Services)
After=NetworkManager.service klipper.service moonraker.service
Wants=NetworkManager.service

[Service]
Type=simple
ExecStart=/usr/local/bin/n1-health-monitor.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable n1-health-monitor.service 2>/dev/null || true
systemctl start n1-health-monitor.service 2>/dev/null || true""")
out = run("systemctl is-active n1-health-monitor 2>/dev/null")
print(f"  n1-health-monitor: {out}")

# 4. n1-health-api.py
print("\n=== 4. 部署n1-health-api.py ===")
upload_file(os.path.join(BASE, "n1-health-api.py"), "/usr/local/bin/n1-health-api.py")
run("chmod +x /usr/local/bin/n1-health-api.py")
run(r"""cat > /etc/systemd/system/n1-health-api.service << 'EOF'
[Unit]
Description=N1 Health Status API (Port 8090)
After=n1-health-monitor.service
Wants=n1-health-monitor.service

[Service]
Type=simple
ExecStart=/usr/bin/python3 /usr/local/bin/n1-health-api.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable n1-health-api.service 2>/dev/null || true
systemctl start n1-health-api.service 2>/dev/null || true""")
out = run("systemctl is-active n1-health-api 2>/dev/null")
print(f"  n1-health-api: {out}")

# 5. 等待health-monitor写入状态缓存
print("\n=== 5. 等待状态缓存... ===")
time.sleep(35)

# 6. 验证健康状态API
print("\n=== 6. 验证健康状态API ===")
out = run("curl -s http://localhost:8090/api/health 2>/dev/null | head -500")
print(f"  /api/health: {out[:300]}...")

# 7. 验证所有service
print("\n=== 7. 验证所有service ===")
for svc in ['link-monitor', 'n1-health-monitor', 'n1-health-api', 'usb-watchdog', 'net-check', 'usb-autosuspend-fix', 'n1-rfkill-persist', 'eth0-power-fix']:
    enabled = run(f"systemctl is-enabled {svc} 2>/dev/null || echo disabled")
    active = run(f"systemctl is-active {svc} 2>/dev/null || echo inactive")
    print(f"  {svc}: enabled={enabled} active={active}")

wifi = run("systemctl is-enabled wifi-watchdog 2>/dev/null || echo disabled")
print(f"  wifi-watchdog: {wifi} (期望disabled)")

# 8. 验证NTP
print("\n=== 8. 验证NTP ===")
out = run("timedatectl status 2>/dev/null | grep -i 'ntp\|synchronized' || echo N/A")
print(f"  {out}")

# 9. 验证logrotate
print("\n=== 9. 验证logrotate ===")
out = run("logrotate -d /etc/logrotate.d/n1-stability 2>&1 | head -5 || echo 'not found'")
print(f"  {out}")

# 10. 验证硬件看门狗
print("\n=== 10. 验证硬件看门狗 ===")
out = run("ls /dev/watchdog 2>/dev/null && echo 'exists' || echo 'not found'")
print(f"  /dev/watchdog: {out}")
out = run("grep WatchdogSec /etc/systemd/system.conf 2>/dev/null || echo 'not configured'")
print(f"  WatchdogSec: {out}")

ssh.close()
print("\n✅ 工业级组件部署完成!")