import paramiko
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=10)

def run(cmd, timeout=15):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    stdout.channel.settimeout(timeout)
    return stdout.read().decode('utf-8', errors='replace')

# 尝试firmware_restart
print("=== FIRMWARE_RESTART ===")
out = run("curl -s -X POST http://127.0.0.1:7125/printer/firmware_restart 2>&1")
print(out.strip()[:100])

time.sleep(10)

# 检查状态
print("\n=== 等待10秒后检查 ===")
out = run("curl -s http://localhost:7125/server/info 2>&1 | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d[\"result\"][\"klippy_state\"])' 2>&1")
print(f"klippy_state: {out.strip()}")

# 检查klippy.log
out = run("tail -10 /root/printer_data/logs/klippy.log 2>&1")
print(f"日志: {out.strip()}")

# 检查MCU是否真的在通信
print("\n=== 检查串口通信 ===")
out = run("stty -F /dev/ttyACM0 2>&1 | head -3")
print(out.strip())

out = run("cat /sys/bus/usb/devices/*/product 2>&1 | head -5")
print(out.strip())

ssh.close()