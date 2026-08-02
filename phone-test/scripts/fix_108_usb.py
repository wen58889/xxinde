import paramiko
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.108', username='root', password='1234', timeout=15)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=15)
    return stdout.read().decode('utf-8', errors='replace')

# Step 1: 禁用USB autosuspend
print("=== Step 1: 禁用USB autosuspend ===")
# 立即禁用
out = run('for d in /sys/bus/usb/devices/*/power/autosuspend; do echo -1 > "$d" 2>/dev/null; done; echo DONE')
print(f"立即禁用: {out}")

# 确认
out = run('for d in /sys/bus/usb/devices/*/power/autosuspend; do echo "$d=$(cat $d 2>/dev/null)"; done')
print(f"确认: {out}")

# Step 2: 持久化 — 通过udev规则和kernel参数
print("\n=== Step 2: 持久化USB autosuspend禁用 ===")

# udev规则：USB设备永远不自动挂起
udev_rule = '''# 禁用所有USB设备autosuspend (工业级稳定性)
# MCU(STM32)被autosuspend后串口中断→Klipper断连→Fluidd刷新
ACTION=="add", SUBSYSTEM=="usb", ATTR{power/autosuspend}="-1"
ACTION=="add", SUBSYSTEM=="usb", TEST=="power/control", ATTR{power/control}="on"
'''

sftp = ssh.open_sftp()
with sftp.open('/etc/udev/rules.d/99-usb-no-autosuspend.rules', 'w') as f:
    f.write(udev_rule)
sftp.close()
run("chmod 644 /etc/udev/rules.d/99-usb-no-autosuspend.rules")
print("udev规则已写入")

# kernel启动参数
out = run('grep "usbcore.autosuspend" /etc/default/grub 2>&1')
if 'usbcore.autosuspend' not in out:
    run("sed -i 's/GRUB_CMDLINE_LINUX_DEFAULT=\"/GRUB_CMDLINE_LINUX_DEFAULT=\"usbcore.autosuspend=-1 /' /etc/default/grub")
    run("update-grub 2>/dev/null || true")
    print("GRUB参数已添加(usbcore.autosuspend=-1)")
else:
    print("GRUB参数已存在")

# Step 3: 禁用MCU串口的runtime PM
print("\n=== Step 3: 禁用ttyACM runtime PM ===")
out = run('for d in /sys/class/tty/ttyACM*/device/power/control; do echo on > "$d" 2>/dev/null; done; echo DONE')
print(f"立即禁用: {out}")

# Step 4: 增加Moonraker WebSocket ping间隔
print("\n=== Step 4: 检查moonraker.conf ===")
out = run('cat /root/printer_data/config/moonraker.conf 2>&1')
print(out)

# Step 5: 重启klipper让MCU重新连接
print("\n=== Step 5: 重启klipper ===")
run("systemctl restart klipper")
time.sleep(8)

out = run("curl -s http://localhost:7125/server/info 2>&1")
if '"klippy_state"' in out:
    state = out.split('"klippy_state":"')[1].split('"')[0]
    print(f"klippy_state: {state}")

# Step 6: 验证USB autosuspend已禁用
print("\n=== Step 6: 验证 ===")
out = run('for d in /sys/bus/usb/devices/*/power/autosuspend; do echo "$d=$(cat $d 2>/dev/null)"; done')
print(f"autosuspend: {out}")
out = run('for d in /sys/bus/usb/devices/*/power/control; do echo "$d=$(cat $d 2>/dev/null)"; done')
print(f"control: {out}")

ssh.close()