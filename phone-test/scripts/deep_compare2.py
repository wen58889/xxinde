import paramiko

def ssh_run(host, cmd):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username='root', password='1234', timeout=10)
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=10)
    out = stdout.read().decode('utf-8', errors='replace')
    ssh.close()
    return out

for name, ip in [('101', '192.168.5.101'), ('106', '192.168.5.106')]:
    print(f"\n{'='*50}")
    print(f"=== {name} ===")
    print(f"{'='*50}")
    
    # go2rtc
    out = ssh_run(ip, 'cat /etc/go2rtc/go2rtc.yaml')
    print(f"go2rtc: {out}")
    
    # stepper方向
    out = ssh_run(ip, 'grep -E "dir_pin|rotation_distance|position_endstop|position_max|homing_speed" /root/printer_data/config/printer.cfg')
    print(f"stepper: {out}")
    
    # 摄像头旋转
    out = ssh_run(ip, 'grep -ri "rotate\\|flip\\|mirror\\|transpose" /etc/go2rtc/ /root/printer_data/config/ 2>/dev/null; echo ---')
    print(f"rotate: {out}")
    
    # 摄像头USB端口
    out = ssh_run(ip, 'lsusb -t 2>&1')
    print(f"usb_tree: {out}")
    
    # webcam列表
    out = ssh_run(ip, 'curl -s http://localhost:7125/server/webcam/list 2>&1')
    print(f"webcam: {out[:300]}")
    
    # 当前toolhead位置
    out = ssh_run(ip, 'curl -s "http://localhost:7125/printer/objects/query?toolhead" 2>&1')
    print(f"toolhead: {out[:300]}")
    
    # 检查后端.env
    out = ssh_run(ip, 'find / -maxdepth 4 -name ".env" 2>/dev/null | head -5')
    print(f"env_files: {out}")
    
    # 检查n1_deploy_info
    out = ssh_run(ip, 'cat /root/n1_deploy_info.txt 2>&1')
    print(f"deploy_info: {out}")