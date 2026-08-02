import paramiko
import time
import os

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=10)

def run(cmd, timeout=15):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    stdout.channel.settimeout(timeout)
    return stdout.read().decode('utf-8', errors='replace').strip()

# 上传修复后的n1-health-monitor.sh
sftp = ssh.open_sftp()
sftp.put(r"D:\Users\59520\IDEProjects\xxinde\phone-test\n1\n1-health-monitor.sh", "/usr/local/bin/n1-health-monitor.sh")
sftp.close()
run("chmod +x /usr/local/bin/n1-health-monitor.sh")
run("systemctl restart n1-health-monitor 2>/dev/null || true")
print("n1-health-monitor.sh 已更新并重启")

# 等待状态缓存刷新
time.sleep(35)

# 验证健康状态API
print("\n=== 验证健康状态API ===")
out = run("curl -s http://localhost:8090/api/health 2>/dev/null")
print(out[:500])

# 验证JSON有效性
out = run("python3 -c \"import json; d=json.load(open('/var/run/n1-health-status.json')); print('status:', d.get('status')); print('mcu:', d.get('mcu')); print('disk:', d.get('disk')); print('memory:', d.get('memory')); print('services:', d.get('services'))\" 2>&1")
print(f"\n解析结果:\n{out}")

ssh.close()