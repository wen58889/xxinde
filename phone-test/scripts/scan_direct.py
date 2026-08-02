import paramiko
import time

def check_device(ip):
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(ip, username='root', password='1234', timeout=5)
        stdin, stdout, stderr = ssh.exec_command('ls /root/printer_data/fluidd/index.html 2>&1', timeout=5)
        stdout.channel.settimeout(5)
        result = stdout.read().decode('utf-8', errors='replace').strip()
        ssh.close()
        if 'index.html' in result:
            return 'HAS_FLUIDD'
        else:
            return f'NO_FLUIDD ({result[:40]})'
    except Exception as e:
        return f'OFFLINE ({str(e)[:30]})'

print("=== 扫描N1设备 ===")
for ip_suffix in ['101', '105', '106', '108', '110', '111', '112', '113', '114', '115']:
    ip = f'192.168.5.{ip_suffix}'
    status = check_device(ip)
    print(f"  {ip}: {status}")