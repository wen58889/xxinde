import paramiko
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.108', username='root', password='1234', timeout=15)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=15)
    return stdout.read().decode('utf-8', errors='replace')

# Step 1: 立即修改运行时autosuspend参数
print("=== Step 1: 立即修改autosuspend ===")
out = run('echo -1 > /sys/module/usbcore/parameters/autosuspend 2>&1; echo DONE')
print(out)

out = run('cat /sys/module/usbcore/parameters/autosuspend 2>&1')
print(f"autosuspend = {out.strip()}")

# Step 2: 确保所有USB设备control=on
print("\n=== Step 2: USB设备power control ===")
out = run('for d in /sys/bus/usb/devices/*/power/control; do echo on > "$d" 2>/dev/null; done')
out = run('for d in /sys/bus/usb/devices/*/power/control; do echo "$d=$(cat $d 2>/dev/null)"; done')
print(out)

# Step 3: 确保ttyACM设备power control=on
print("\n=== Step 3: ttyACM power control ===")
out = run('for d in /sys/class/tty/ttyACM*/device/power/control; do echo on > "$d" 2>/dev/null; done')
out = run('for d in /sys/class/tty/ttyACM*/device/power/control; do echo "$d=$(cat $d 2>/dev/null)"; done')
print(out)

# Step 4: 检查armbianEnv.txt是否正确
print("\n=== Step 4: armbianEnv.txt ===")
out = run('cat /boot/armbianEnv.txt 2>&1')
print(out)

# Step 5: 检查是否有其他地方覆盖了autosuspend
print("\n=== Step 5: 检查覆盖 ===")
out = run('grep -r "autosuspend" /etc/modprobe.d/ 2>&1')
print(f"modprobe.d: {out}")
out = run('grep -r "autosuspend" /etc/udev/rules.d/ 2>&1')
print(f"udev: {out}")

# Step 6: 重启klipper确保MCU干净连接
print("\n=== Step 6: 重启klipper ===")
run("systemctl restart klipper")
time.sleep(8)

out = run("curl -s http://localhost:7125/server/info 2>&1")
if '"klippy_state"' in out:
    state = out.split('"klippy_state":"')[1].split('"')[0]
    print(f"klippy_state: {state}")

ssh.close()