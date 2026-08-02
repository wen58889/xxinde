import paramiko
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.108', username='root', password='1234', timeout=15)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=15)
    return stdout.read().decode('utf-8', errors='replace')

print("=== 5分钟稳定性测试 (192.168.5.108) ===")
print("时间     | 7125 | klippy  | Fluidd")
print("-" * 45)

errors = 0
for i in range(60):
    try:
        port = run('ss -tlnp | grep 7125 2>&1').strip()
        port_ok = "OK" if port else "NO"
        
        info = run('curl -s http://localhost:7125/server/info 2>&1')
        if '"klippy_state"' in info:
            klippy = info.split('"klippy_state":"')[1].split('"')[0]
        else:
            klippy = "ERR"; errors += 1
        
        fluidd = run('curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/ 2>&1').strip()
        
        if i % 6 == 0:
            t = time.strftime("%H:%M:%S")
            print(f"{t} | {port_ok}  | {klippy:7s} | {fluidd}")
    except:
        errors += 1
    
    time.sleep(5)

print(f"\n结果: {errors}次错误 / 60次测试")
klip_r = run('journalctl -u klipper --since "5 min ago" --no-pager 2>&1 | grep -c "Started klipper"')
mr_r = run('journalctl -u moonraker --since "5 min ago" --no-pager 2>&1 | grep -c "Started moonraker"')
print(f"Klipper重启(5min): {klip_r.strip()}")
print(f"Moonraker重启(5min): {mr_r.strip()}")

ssh.close()
