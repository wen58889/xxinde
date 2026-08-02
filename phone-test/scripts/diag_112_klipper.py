import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=10)

def run(cmd, timeout=15):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    stdout.channel.settimeout(timeout)
    return stdout.read().decode('utf-8', errors='replace')

print("=== klipper日志(最后30行) ===")
out = run("journalctl -u klipper --no-pager -n 30 2>&1")
print(out.strip())

print("\n=== MCU状态 ===")
out = run("ls -la /dev/serial/by-id/ 2>&1")
print(out.strip())

print("\n=== klippy.log错误 ===")
out = run("grep -iE 'error|fail|traceback' /root/printer_data/logs/klippy.log 2>&1 | tail -10")
print(out.strip())

ssh.close()