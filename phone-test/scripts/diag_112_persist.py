import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=10)

def run(cmd, timeout=15):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    stdout.channel.settimeout(timeout)
    return stdout.read().decode('utf-8', errors='replace')

checks = [
    ("WiFi连接", 'nmcli -t -f NAME,TYPE,AUTOCONNECT-PRIORITY con show 2>&1 | grep -iE "ZTE|Wired"'),
    ("WiFi状态", 'nmcli dev status 2>&1 | grep -E "wlan0|eth0"'),
    ("autosuspend", 'cat /sys/module/usbcore/parameters/autosuspend 2>&1'),
    ("modprobe.d", 'cat /etc/modprobe.d/usb-no-autosuspend.conf 2>&1'),
    ("armbianEnv", 'grep autosuspend /boot/armbianEnv.txt 2>&1 || echo "NOT_FOUND"'),
    ("udev规则", 'cat /etc/udev/rules.d/99-usb-no-autosuspend.rules 2>&1 || echo "NOT_FOUND"'),
    ("brcmfmac roamoff", 'cat /sys/module/brcmfmac/parameters/roamoff 2>&1'),
    ("brcmfmac.conf", 'cat /etc/modprobe.d/brcmfmac.conf 2>&1 || echo "NOT_FOUND"'),
    ("WiFi省电", 'iw dev wlan0 get power_save 2>&1'),
    ("WiFi bgscan", 'cat /etc/NetworkManager/conf.d/wifi-no-bgscan.conf 2>&1 || echo "NOT_FOUND"'),
    ("WiFi P2P", 'cat /etc/NetworkManager/conf.d/no-p2p.conf 2>&1 || echo "NOT_FOUND"'),
    ("WiFi MAC随机", 'cat /etc/NetworkManager/conf.d/wifi-no-mac-random.conf 2>&1 || echo "NOT_FOUND"'),
    ("fix-mac.service", 'systemctl is-enabled fix-mac 2>&1'),
    ("usb-watchdog", 'systemctl is-enabled usb-watchdog 2>&1'),
    ("MCU检测", 'ls /dev/serial/by-id/ 2>&1'),
    ("n1-fixed-mac", 'cat /etc/n1-fixed-mac 2>&1 || echo "NOT_FOUND"'),
    ("n1-fixed-iface", 'cat /etc/n1-fixed-iface 2>&1 || echo "NOT_FOUND"'),
    ("eth0省电service", 'systemctl is-enabled eth0-power-fix 2>&1'),
    ("WiFi dispatcher", 'ls -la /etc/NetworkManager/dispatcher.d/ 2>&1'),
    ("有线静态IP", 'nmcli con show "Wired connection 1" 2>&1 | grep -iE "ipv4.method|ipv4.address"'),
]

for name, cmd in checks:
    out = run(cmd).strip()
    print(f"  {name}: {out[:80]}")

ssh.close()