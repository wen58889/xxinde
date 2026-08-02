import paramiko
import time

def ssh_run(cmd, timeout=15):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect('192.168.5.101', username='root', password='1234', timeout=10)
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    ssh.close()
    return out, err

# 等klippy启动完成
time.sleep(15)

# 检查klippy状态
print("=== Klippy状态 ===")
out, _ = ssh_run("curl -s http://localhost:7125/server/info 2>&1")
print(out[:300])

# 检查MCU串口
print("\n=== MCU串口 ===")
out, _ = ssh_run("ls -la /dev/serial/by-id/ 2>&1")
print(out)

out, _ = ssh_run("ls -la /dev/ttyACM* 2>&1")
print(out)

# 检查klippy日志
print("\n=== Klippy日志(最后20行) ===")
out, _ = ssh_run("tail -20 /root/printer_data/logs/klippy.log 2>&1")
print(out)

# 检查usb-watchdog
print("\n=== USB watchdog ===")
out, _ = ssh_run("systemctl status usb-watchdog --no-pager -l 2>&1 | head -15")
print(out)

# 测试WebSocket连接(通过nginx)
print("\n=== WebSocket测试 ===")
out, _ = ssh_run("curl -s -o /dev/null -w '%{http_code}' -H 'Connection: Upgrade' -H 'Upgrade: websocket' -H 'Sec-WebSocket-Version: 13' -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' http://localhost:7125/websocket 2>&1")
print(f"WebSocket直接7125: {out}")

out, _ = ssh_run("curl -s -o /dev/null -w '%{http_code}' -H 'Connection: Upgrade' -H 'Upgrade: websocket' -H 'Sec-WebSocket-Version: 13' -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' http://localhost:80/websocket 2>&1")
print(f"WebSocket nginx 80: {out}")

# 检查Fluidd的config.json中API地址
print("\n=== Fluidd config ===")
out, _ = ssh_run("cat /var/www/fluidd/config.json 2>&1 || echo NO_FILE")
print(out[:200])

# 检查nginx fluidd配置
print("\n=== Nginx Fluidd配置 ===")
out, _ = ssh_run("cat /etc/nginx/sites-enabled/fluidd 2>&1")
print(out)

# 检查/var/www/fluidd是否存在
print("\n=== Fluidd文件 ===")
out, _ = ssh_run("ls -la /var/www/fluidd/ 2>&1 | head -10")
print(out)