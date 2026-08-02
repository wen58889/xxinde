import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=10, allow_agent=False, look_for_keys=False)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=15)
    return stdout.read().decode('utf-8', errors='replace').strip()

# 1. 备份原配置
print("=== 备份moonraker.conf ===")
print(run("cp ~/printer_data/config/moonraker.conf ~/printer_data/config/moonraker.conf.bak"))

# 2. 检查是否已有websocket配置
existing = run("grep -i websocket ~/printer_data/config/moonraker.conf 2>/dev/null || echo NONE")
print(f"现有websocket配置: {existing}")

# 3. 添加websocket配置
# Moonraker的websocket配置项在[server]段下
# ws_ping_interval: ping间隔(秒)，默认10
# ws_ping_timeout: pong超时(秒)，默认5
# 增大这两个值可以避免Fluidd断连
print("\n=== 添加WebSocket心跳配置 ===")
result = run("""sed -i '/^\\[server\\]/a\\websocket_ping_interval: 30\\nwebsocket_ping_timeout: 60' ~/printer_data/config/moonraker.conf""")
print(f"sed结果: {result or 'OK'}")

# 4. 验证配置
print("\n=== 验证配置 ===")
print(run("cat ~/printer_data/config/moonraker.conf"))

# 5. 重启moonraker
print("\n=== 重启moonraker ===")
print(run("systemctl restart moonraker"))
import time; time.sleep(5)
print(run("systemctl is-active moonraker"))

# 6. 验证klippy状态
print("\n=== 验证klippy状态 ===")
import time; time.sleep(5)
print(run("curl -s http://localhost:7125/server/info 2>/dev/null | head -200"))

ssh.close()