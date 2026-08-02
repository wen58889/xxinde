import paramiko
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

for attempt in range(5):
    try:
        ssh.connect('192.168.5.112', username='root', password='1234', timeout=10)
        break
    except:
        print(f"连接失败, 等待10s重试... (attempt {attempt+1}/5)")
        time.sleep(10)
else:
    print("无法连接112设备!")
    exit(1)

def run(cmd, timeout=15):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    stdout.channel.settimeout(timeout)
    return stdout.read().decode('utf-8', errors='replace').strip()

print("=== 1. USB autosuspend ===")
out = run('cat /sys/module/usbcore/parameters/autosuspend')
print(f"  autosuspend = {out} (期望: -1)")

print("\n=== 2. systemd services ===")
for svc in ['usb-autosuspend-fix', 'net-check', 'fix-mac', 'usb-watchdog', 'eth0-power-fix']:
    out = run(f'systemctl is-enabled {svc} 2>&1')
    active = run(f'systemctl is-active {svc} 2>&1')
    print(f"  {svc}: enabled={out} active={active}")

print("\n=== 3. WiFi ===")
out = run('nmcli dev status 2>&1 | grep -E "eth0|wlan0"')
print(f"  {out}")

out = run('nmcli -t -f NAME,DEVICE con show --active 2>&1 | grep wlan0')
print(f"  活跃WiFi连接: {out}")

out = run('iw dev wlan0 link 2>&1 | head -2')
print(f"  WiFi链路: {out}")

print("\n=== 4. WiFi省电 ===")
out = run('iw dev wlan0 get power_save 2>&1')
print(f"  power_save: {out}")

print("\n=== 5. 有线网络 ===")
out = run('ethtool eth0 2>&1 | grep -E "Speed|Link detected"')
print(f"  {out}")

print("\n=== 6. brcmfmac roamoff ===")
out = run('cat /sys/module/brcmfmac/parameters/roamoff 2>&1')
print(f"  roamoff: {out} (期望: 1)")

print("\n=== 7. WiFi静态IP ===")
out = run("nmcli -t -f NAME,ipv4.method,ipv4.addresses con show 'ZTE01-24g' 2>&1")
print(f"  ZTE01-24g: {out}")

out = run("nmcli -t -f NAME,ipv4.method,ipv4.addresses con show 'Wired connection 1' 2>&1 || echo N/A")
print(f"  Wired: {out}")

print("\n=== 8. MCU ===")
out = run('ls /dev/serial/by-id/ 2>&1')
print(f"  {out}")

print("\n=== 9. Klipper状态 ===")
out = run('curl -s http://localhost:7125/server/info 2>&1 | grep -oP \'"klippy_state":"\\K[^"]+\' || echo ERR')
print(f"  klippy_state: {out}")

ssh.close()