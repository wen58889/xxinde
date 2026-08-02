import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

# 尝试从101获取WiFi信息
ssh.connect('192.168.5.101', username='root', password='1234', timeout=10)

def run(cmd, timeout=15):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    stdout.channel.settimeout(timeout)
    return stdout.read().decode('utf-8', errors='replace')

print("=== 101 WiFi扫描 ===")
out = run('nmcli -t -f SSID,SIGNAL,FREQ,BAND dev wifi list 2>&1 | grep -i ZTE | head -10')
print(out.strip())

print("\n=== 101当前WiFi ===")
out = run('iw dev wlan0 link 2>&1 | head -5')
print(out.strip())

print("\n=== 101 NM WiFi连接 ===")
out = run('nmcli -t -f NAME,TYPE con show 2>&1 | grep -i wifi')
print(out.strip())

ssh.close()