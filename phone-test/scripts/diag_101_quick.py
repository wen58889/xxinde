import paramiko
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.101', username='root', password='1234', timeout=10)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=10)
    return stdout.read().decode('utf-8', errors='replace')

# 检查klippy状态
out = run("curl -s http://localhost:7125/server/info 2>&1")
print(f"server/info: {out[:300]}")

# MCU串口
out = run("ls /dev/serial/by-id/ 2>&1")
print(f"串口: {out}")

out = run("ls /dev/ttyACM* 2>&1")
print(f"ttyACM: {out}")

# WebSocket
out = run("curl -s -o /dev/null -w '%{http_code}' -H 'Connection: Upgrade' -H 'Upgrade: websocket' http://localhost:7125/websocket 2>&1")
print(f"WS 7125: {out}")

out = run("curl -s -o /dev/null -w '%{http_code}' -H 'Connection: Upgrade' -H 'Upgrade: websocket' http://localhost:80/websocket 2>&1")
print(f"WS nginx: {out}")

# Nginx Fluidd
out = run("cat /etc/nginx/sites-enabled/fluidd 2>&1")
print(f"Nginx: {out}")

ssh.close()