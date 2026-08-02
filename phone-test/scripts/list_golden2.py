import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=15)

def run(cmd, timeout=30):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    stdout.channel.settimeout(timeout)
    return stdout.read().decode('utf-8', errors='replace')

print("=== 黄金镜像中fluidd相关文件 ===")
out = run('tar tzf /root/n1_golden_image.tar.gz 2>&1 | grep -i fluidd')
print(out.strip() if out.strip() else "(无)")

print("\n=== 黄金镜像中printer_data相关文件 ===")
out = run('tar tzf /root/n1_golden_image.tar.gz 2>&1 | grep printer_data')
print(out.strip() if out.strip() else "(无)")

print("\n=== 黄金镜像顶层目录 ===")
out = run('tar tzf /root/n1_golden_image.tar.gz 2>&1 | cut -d/ -f1-3 | sort -u | head -30')
print(out.strip())

ssh.close()