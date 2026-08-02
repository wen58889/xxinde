import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=10)
stdin, stdout, stderr = ssh.exec_command('reboot', timeout=5)
try:
    stdout.read()
except:
    pass
ssh.close()
print('112 reboot command sent')