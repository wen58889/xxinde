import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.108', username='root', password='1234', timeout=15)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=15)
    return stdout.read().decode('utf-8', errors='replace')

cmds = [
    'cat /etc/modprobe.d/usb-no-autosuspend.conf 2>&1',
    'cat /etc/udev/rules.d/99-usb-no-autosuspend.rules 2>&1',
    'cat /boot/armbianEnv.txt 2>&1',
    'cat /sys/module/usbcore/parameters/autosuspend 2>&1',
    'cat /etc/default/grub 2>&1 | grep autosuspend',
]

for cmd in cmds:
    print(f'=== {cmd[:60]} ===')
    out = run(cmd)
    print(out[:300])
    print()

ssh.close()