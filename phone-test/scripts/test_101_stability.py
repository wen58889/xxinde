import paramiko
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.101', username='root', password='1234', timeout=10)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=10)
    return stdout.read().decode('utf-8', errors='replace')

print("=== 60秒稳定性测试 ===")
print("时间  | Moonraker PID | 7125端口 | klippy_state | Fluidd 80")
print("-" * 70)

errors = 0
for i in range(12):  # 每5秒测一次，共60秒
    pid = run("pgrep -f 'moonraker.py' 2>&1").strip()
    port = run("ss -tlnp | grep 7125 2>&1").strip()
    port_ok = "YES" if port else "NO"
    state = run("curl -s http://localhost:7125/server/info 2>&1")
    if '"klippy_state"' in state:
        klippy_state = state.split('"klippy_state":"')[1].split('"')[0]
    else:
        klippy_state = "ERROR"
        errors += 1
    fluidd = run("curl -s -o /dev/null -w '%{http_code}' http://localhost:80/ 2>&1").strip()
    
    t = time.strftime("%H:%M:%S")
    print(f"{t} | PID={pid:5s} | 7125={port_ok} | {klippy_state:10s} | HTTP {fluidd}")
    time.sleep(5)

print(f"\n结果: {errors}次错误 / 12次测试")

# 从开发机测试
print("\n=== 从开发机测试 ===")
ssh.close()

import urllib.request
for i in range(3):
    try:
        r = urllib.request.urlopen('http://192.168.5.101:7125/server/info', timeout=5)
        data = r.read().decode()
        state = data.split('"klippy_state":"')[1].split('"')[0]
        print(f"外部API: {state}")
    except Exception as e:
        print(f"外部API: ERROR - {e}")
    try:
        r = urllib.request.urlopen('http://192.168.5.101:80/', timeout=5)
        print(f"外部Fluidd: HTTP {r.status}")
    except Exception as e:
        print(f"外部Fluidd: ERROR - {e}")
    time.sleep(2)