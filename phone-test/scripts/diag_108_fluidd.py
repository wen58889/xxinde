import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.108', username='root', password='1234', timeout=15)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=15)
    return stdout.read().decode('utf-8', errors='replace')

cmds = [
    # MCU USB断连历史
    'dmesg | grep -i "usb.*disconnect\\|usb.*new.*device\\|stm32\\|cdc_acm" | tail -30',
    # Klipper状态变化
    'journalctl -u klipper --since "10 min ago" --no-pager 2>&1 | tail -20',
    # Moonraker WebSocket断连
    'grep -i "disconnect\\|websocket.*close\\|connection.*lost\\|klippy_state" /root/printer_data/logs/moonraker.log 2>&1 | tail -20',
    # 当前klippy状态
    'curl -s http://localhost:7125/server/info 2>&1',
    # MCU串口是否存在
    'ls -la /dev/serial/by-id/ 2>&1',
    'ls -la /dev/ttyACM* 2>&1',
    # Fluidd服务状态
    'systemctl status fluidd --no-pager 2>&1 | head -10',
    # 检查是否有nginx
    'systemctl status nginx --no-pager 2>&1 | head -5',
    'ss -tlnp | grep -E "80|8080|7125" 2>&1',
    # printer.cfg中MCU串口配置
    'grep -A3 "mcu" /root/printer_data/config/printer.cfg | head -5',
    # 检查USB设备树
    'lsusb -t 2>&1',
    # 检查USB电源管理
    'for d in /sys/bus/usb/devices/*/power/control; do echo "$d=$(cat $d 2>/dev/null)"; done 2>&1',
    # 检查autosuspend
    'for d in /sys/bus/usb/devices/*/power/autosuspend; do echo "$d=$(cat $d 2>/dev/null)"; done 2>&1',
]

for cmd in cmds:
    print(f'=== {cmd[:65]} ===')
    out = run(cmd)
    print(out[:500])
    print()

ssh.close()