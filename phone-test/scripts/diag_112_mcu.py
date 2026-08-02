import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=10)

def run(cmd, timeout=15):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    stdout.channel.settimeout(timeout)
    return stdout.read().decode('utf-8', errors='replace')

print("=== printer.cfg中MCU配置 ===")
out = run("grep -A5 '\[mcu\]' /root/printer_data/config/printer.cfg 2>&1")
print(out.strip())

print("\n=== MCU串口设备 ===")
out = run("ls -la /dev/serial/by-id/ 2>&1")
print(out.strip())

print("\n=== ttyACM设备 ===")
out = run("ls -la /dev/ttyACM* 2>&1")
print(out.strip())

print("\n=== klippy.log详细错误 ===")
out = run("tail -50 /root/printer_data/logs/klippy.log 2>&1")
print(out.strip())

ssh.close()