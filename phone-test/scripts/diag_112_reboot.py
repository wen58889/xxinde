import paramiko
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=10)

def run(cmd, timeout=15):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    stdout.channel.settimeout(timeout)
    return stdout.read().decode('utf-8', errors='replace')

print("=== USB设备 ===")
out = run('lsusb 2>&1')
print(out.strip())

print("\n=== /dev/serial ===")
out = run('ls -la /dev/serial/by-id/ 2>&1; ls -la /dev/ttyACM* /dev/ttyUSB* 2>&1')
print(out.strip())

print("\n=== dmesg USB ===")
out = run('dmesg | grep -iE "usb|tty|stm32|acm|cp210" | tail -15')
print(out.strip())

print("\n=== WiFi状态 ===")
out = run('nmcli dev status 2>&1')
print(out.strip())

print("\n=== WiFi连接 ===")
out = run('nmcli -t -f NAME,TYPE,DEVICE,AUTOCONNECT-PRIORITY con show 2>&1 | grep -i wifi')
print(out.strip())

print("\n=== WiFi扫描(ZTE) ===")
out = run('nmcli dev wifi list 2>&1 | grep -i ZTE')
print(out.strip())

print("\n=== NM日志WiFi ===")
out = run('journalctl -u NetworkManager --no-pager -n 20 2>&1 | grep -iE "wifi|wlan|connect|activ|fail|error"')
print(out.strip())

print("\n=== usbcore autosuspend ===")
out = run('cat /sys/module/usbcore/parameters/autosuspend 2>&1')
print(f"autosuspend: {out.strip()}")

print("\n=== usb-watchdog ===")
out = run('systemctl status usb-watchdog 2>&1 | head -8')
print(out.strip())

ssh.close()