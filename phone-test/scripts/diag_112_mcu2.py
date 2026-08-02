import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=10)

def run(cmd, timeout=15):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    stdout.channel.settimeout(timeout)
    return stdout.read().decode('utf-8', errors='replace')

print("=== printer.cfg MCU配置 ===")
out = run(r"grep -A5 '^\[mcu\]' /root/printer_data/config/printer.cfg 2>&1")
print(out.strip())

print("\n=== MCU串口 ===")
out = run("ls -la /dev/serial/by-id/ 2>&1")
print(out.strip())

print("\n=== klippy.log最后30行 ===")
out = run("tail -30 /root/printer_data/logs/klippy.log 2>&1")
print(out.strip())

print("\n=== klippy_state ===")
out = run("curl -s http://localhost:7125/server/info 2>&1 | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d[\"result\"][\"klippy_state\"])' 2>&1")
print(out.strip())

ssh.close()