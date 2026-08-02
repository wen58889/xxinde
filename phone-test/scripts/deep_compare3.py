import paramiko

def ssh_run(host, cmd):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username='root', password='1234', timeout=10)
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=8)
    out = stdout.read().decode('utf-8', errors='replace')
    ssh.close()
    return out

for name, ip in [('101', '192.168.5.101'), ('106', '192.168.5.106')]:
    print(f"\n=== {name} ===")
    
    # stepper方向
    out = ssh_run(ip, 'grep -E "dir_pin|rotation_distance|position_endstop|position_max" /root/printer_data/config/printer.cfg')
    print(f"stepper:\n{out}")
    
    # go2rtc
    out = ssh_run(ip, 'cat /etc/go2rtc/go2rtc.yaml')
    print(f"go2rtc:\n{out}")
    
    # 摄像头旋转
    out = ssh_run(ip, 'grep -ri "rotate" /etc/go2rtc/ 2>/dev/null; echo ---')
    print(f"rotate: {out}")
    
    # webcam
    out = ssh_run(ip, 'curl -s http://localhost:7125/server/webcam/list 2>&1')
    print(f"webcam: {out[:200]}")
    
    # deploy_info
    out = ssh_run(ip, 'cat /root/n1_deploy_info.txt 2>&1')
    print(f"deploy: {out}")