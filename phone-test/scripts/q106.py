import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.106', username='root', password='1234', timeout=10)

cmds = [
    'grep -E "dir_pin|rotation_distance|position_endstop|position_max" /root/printer_data/config/printer.cfg',
    'cat /etc/go2rtc/go2rtc.yaml',
    'curl -s http://localhost:7125/server/webcam/list 2>&1',
    'cat /root/n1_deploy_info.txt 2>&1',
]
for cmd in cmds:
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=8)
    print(f"--- {cmd[:50]} ---")
    print(stdout.read().decode('utf-8', errors='replace')[:300])
ssh.close()