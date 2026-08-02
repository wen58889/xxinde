import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=10)

def run(cmd, timeout=15):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    stdout.channel.settimeout(timeout)
    return stdout.read().decode('utf-8', errors='replace').strip()

print("=== WiFi静态IP ===")
out = run("nmcli -t -f connection.id,ipv4.method,ipv4.addresses con show 'ZTE01-24g' 2>&1")
print(f"  ZTE01-24g: {out}")

out = run("nmcli -t -f connection.id,ipv4.method,ipv4.addresses con show 'Wired connection 1' 2>&1")
print(f"  Wired: {out}")

out = run("ip -4 addr show wlan0 | grep inet")
print(f"  wlan0 IP: {out}")

out = run("ip -4 addr show eth0 | grep inet")
print(f"  eth0 IP: {out}")

ssh.close()
