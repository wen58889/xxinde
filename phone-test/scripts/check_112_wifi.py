import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=5)
stdin, stdout, stderr = ssh.exec_command('iw dev wlan0 link 2>&1 | head -5; echo "---"; hostname -I; echo "---"; nmcli -t -f NAME,DEVICE con show --active 2>&1', timeout=5)
stdout.channel.settimeout(5)
print(stdout.read().decode())
ssh.close()