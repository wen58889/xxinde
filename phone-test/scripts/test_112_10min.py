import paramiko
import time
import datetime

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

print("=== 10分钟IP稳定性测试 ===")
print(f"开始: {datetime.datetime.now().strftime('%H:%M:%S')}")

errors = 0
success = 0
last_ip = None

for i in range(60):  # 每10秒一次，共10分钟
    try:
        ssh.close()
    except:
        pass
    
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect('192.168.5.112', username='root', password='1234', timeout=5)
        
        stdin, stdout, stderr = ssh.exec_command('hostname -I 2>&1', timeout=5)
        stdout.channel.settimeout(5)
        ip = stdout.read().decode('utf-8', errors='replace').strip()
        
        stdin, stdout, stderr = ssh.exec_command('hostname 2>&1', timeout=5)
        stdout.channel.settimeout(5)
        hostname = stdout.read().decode('utf-8', errors='replace').strip()
        
        now = datetime.datetime.now().strftime('%H:%M:%S')
        
        if '192.168.5.112' in ip:
            status = "OK"
            success += 1
        else:
            status = f"IP_CHANGED: {ip}"
            errors += 1
        
        if ip != last_ip and last_ip is not None:
            status += " [IP CHANGED!]"
            errors += 1
        
        last_ip = ip
        print(f"  [{now}] #{i+1:2d} {hostname} {ip} {status}")
        
    except Exception as e:
        now = datetime.datetime.now().strftime('%H:%M:%S')
        errors += 1
        print(f"  [{now}] #{i+1:2d} CONNECTION FAILED: {str(e)[:40]}")
    
    time.sleep(10)

print(f"\n=== 测试结果 ===")
print(f"成功: {success}/60")
print(f"失败: {errors}/60")
print(f"结束: {datetime.datetime.now().strftime('%H:%M:%S')}")

try:
    ssh.close()
except:
    pass