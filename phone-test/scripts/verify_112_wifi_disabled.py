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

print("=== 1. WiFi禁用持久化验证 ===")
out = run("rfkill list 2>/dev/null")
print(f"rfkill list:\n{out}")

out = run("nmcli radio wifi 2>/dev/null")
print(f"nmcli radio wifi: {out}")

out = run("lsmod | grep brcmfmac 2>/dev/null || echo '(无brcmfmac模块)'")
print(f"brcmfmac模块: {out}")

out = run("cat /etc/modprobe.d/brcmfmac.conf 2>/dev/null")
print(f"brcmfmac.conf: {out}")

print("\n=== 2. 网络状态 ===")
out = run("nmcli dev status 2>&1")
print(out)

out = run("ip -4 addr show eth0 | grep inet")
print(f"eth0 IP: {out}")

out = run("ethtool eth0 2>/dev/null | grep -E 'Speed|Link detected'")
print(f"eth0: {out}")

print("\n=== 3. MCU和Klipper ===")
out = run("ls /dev/serial/by-id/ 2>/dev/null")
print(f"MCU: {out}")

out = run("curl -s http://localhost:7125/server/info 2>&1 | grep -oP '\"klippy_state\":\"\\K[^\"]+' || echo ERR")
print(f"klippy_state: {out}")

print("\n=== 4. USB autosuspend ===")
out = run("cat /sys/module/usbcore/parameters/autosuspend 2>/dev/null")
print(f"autosuspend: {out}")

print("\n=== 5. Services ===")
for svc in ['usb-autosuspend-fix', 'net-check', 'n1-rfkill-persist', 'usb-watchdog', 'eth0-power-fix', 'fix-mac']:
    out = run(f"systemctl is-enabled {svc} 2>/dev/null || echo disabled")
    active = run(f"systemctl is-active {svc} 2>/dev/null || echo inactive")
    print(f"  {svc}: enabled={out} active={active}")

out = run("systemctl is-enabled wifi-watchdog 2>/dev/null || echo disabled")
print(f"  wifi-watchdog: {out} (期望disabled)")

print("\n=== 6. net-check.sh纯有线验证 ===")
out = run("grep -c 'iw dev wlan0\\|brcmfmac\\|roamoff' /usr/local/bin/net-check.sh 2>/dev/null || echo 0")
print(f"WiFi命令数: {out} (期望0)")

ssh.close()