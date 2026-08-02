import paramiko

def ssh_run(host, cmds):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username='root', password='1234', timeout=10)
    results = {}
    for cmd in cmds:
        stdin, stdout, stderr = ssh.exec_command(cmd, timeout=10)
        results[cmd] = stdout.read().decode('utf-8', errors='replace')
    ssh.close()
    return results

cmds = [
    'cat /root/printer_data/config/printer.cfg',
    'cat /root/printer_data/config/moonraker.conf',
    # go2rtc摄像头配置
    'cat /root/printer_data/config/go2rtc.yaml 2>&1 || cat /etc/go2rtc.yaml 2>&1 || cat /usr/local/bin/go2rtc.yaml 2>&1 || echo NO_GO2RTC_CONFIG',
    # 摄像头设备
    'ls -la /dev/video* 2>&1',
    'v4l2-ctl --list-devices 2>&1 || echo NO_V4L2',
    # go2rtc进程和参数
    'ps aux | grep go2rtc 2>&1 | grep -v grep',
    'cat /etc/systemd/system/go2rtc.service 2>&1',
    # 测试移动到标定点位置
    'curl -s http://localhost:7125/printer/info 2>&1 | head -5',
    # 当前位置
    'curl -s http://localhost:7125/printer/gcode/help 2>&1 | head -3',
    # MCU信息
    'ls /dev/serial/by-id/ 2>&1',
    # hostname
    'hostname',
]

print("=" * 60)
print("=== 192.168.5.101 ===")
print("=" * 60)
r101 = ssh_run('192.168.5.101', cmds)
for k, v in r101.items():
    label = k[:60]
    print(f"\n--- {label} ---")
    print(v[:500])

print("\n\n" + "=" * 60)
print("=== 192.168.5.106 ===")
print("=" * 60)
r106 = ssh_run('192.168.5.106', cmds)
for k, v in r106.items():
    label = k[:60]
    print(f"\n--- {label} ---")
    print(v[:500])