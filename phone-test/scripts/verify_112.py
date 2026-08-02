import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=10)

def run(cmd, timeout=15):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    stdout.channel.settimeout(timeout)
    return stdout.read().decode('utf-8', errors='replace')

print("=== klippy_state ===")
out = run("curl -s http://localhost:7125/server/info 2>&1")
print(out.strip()[:200])

print("\n=== MCU检测 ===")
out = run("ls /dev/serial/by-id/ 2>&1")
print(out.strip())

print("\n=== klipper日志最后10行 ===")
out = run("journalctl -u klipper --no-pager -n 10 2>&1")
print(out.strip())

print("\n=== Fluidd验证 ===")
out = run("curl -s http://localhost:8080/ 2>&1 | head -3")
print(out.strip()[:100])

print("\n=== Moonraker验证 ===")
out = run("curl -s http://localhost:7125/ 2>&1 | head -3")
print(out.strip()[:100])

ssh.close()