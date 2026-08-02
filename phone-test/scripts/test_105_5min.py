import paramiko
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.105', username='root', password='1234', timeout=10)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=10)
    return stdout.read().decode('utf-8', errors='replace')

print("=== 5分钟稳定性测试 (192.168.5.105) ===")
print("时间     | Moonraker PID | 7125 | klippy_state | Fluidd 8080 | USB Watchdog")
print("-" * 80)

errors = 0
prev_pid = ""
restarts = 0
total = 60  # 5秒间隔 x 60次 = 300秒 = 5分钟

for i in range(total):
    pid = run("pgrep -f 'moonraker.py' 2>&1").strip()
    if pid and prev_pid and pid != prev_pid:
        restarts += 1
    prev_pid = pid
    
    port = run("ss -tlnp | grep 7125 2>&1").strip()
    port_ok = "YES" if port else "NO "
    
    state = run("curl -s http://localhost:7125/server/info 2>&1")
    if '"klippy_state"' in state:
        klippy_state = state.split('"klippy_state":"')[1].split('"')[0]
    else:
        klippy_state = "ERROR"
        errors += 1
    
    fluidd = run("curl -s -o /dev/null -w '%{http_code}' http://localhost:8080/ 2>&1").strip()
    
    wd_log = run("journalctl -u usb-watchdog --since '10s ago' --no-pager 2>&1 | grep -c 'MCU not detected' 2>&1").strip()
    wd_status = f"fail={wd_log}" if wd_log != "0" else "OK"
    
    t = time.strftime("%H:%M:%S")
    if i % 6 == 0:  # 每30秒打印一次
        print(f"{t} | PID={pid:6s} | {port_ok} | {klippy_state:10s} | HTTP {fluidd}    | {wd_status}")
    
    time.sleep(5)

# 最终检查
print(f"\n{'='*80}")
print(f"5分钟测试完成:")
print(f"  总测试次数: {total}")
print(f"  错误次数: {errors}")
print(f"  Moonraker重启次数: {restarts}")

# 检查usb-watchdog日志
wd_recent = run("journalctl -u usb-watchdog --since '5 min ago' --no-pager 2>&1 | grep -c 'MCU not detected' 2>&1").strip()
print(f"  USB watchdog MCU丢失次数(5min): {wd_recent}")

# 检查klipper/moonraker重启次数
klip_restarts = run("journalctl -u klipper --since '5 min ago' --no-pager 2>&1 | grep -c 'Started klipper' 2>&1").strip()
mr_restarts = run("journalctl -u moonraker --since '5 min ago' --no-pager 2>&1 | grep -c 'Started moonraker' 2>&1").strip()
print(f"  Klipper重启次数(5min): {klip_restarts}")
print(f"  Moonraker重启次数(5min): {mr_restarts}")

# 从外部测试
print(f"\n外部访问测试:")
import urllib.request
try:
    r = urllib.request.urlopen('http://192.168.5.105:7125/server/info', timeout=5)
    data = r.read().decode()
    state = data.split('"klippy_state":"')[1].split('"')[0]
    print(f"  API: {state}")
except Exception as e:
    print(f"  API: ERROR - {e}")

try:
    r = urllib.request.urlopen('http://192.168.5.105:8080/', timeout=5)
    print(f"  Fluidd: HTTP {r.status}")
except Exception as e:
    print(f"  Fluidd: ERROR - {e}")

ssh.close()