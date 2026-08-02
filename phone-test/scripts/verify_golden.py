import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.101', username='root', password='1234', timeout=10)

def run(cmd, timeout=30):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    stdout.channel.settimeout(timeout)
    return stdout.read().decode('utf-8', errors='replace')

print("=== 验证新黄金镜像 ===")

# Fluidd文件
print("\n--- Fluidd文件 ---")
out = run('tar tzf /root/n1_golden_image.tar.gz 2>&1 | grep "fluidd/" | head -15')
print(out.strip())

out = run('tar tzf /root/n1_golden_image.tar.gz 2>&1 | grep "fluidd/" | wc -l')
print(f"Fluidd文件总数: {out.strip()}")

out = run('tar tzf /root/n1_golden_image.tar.gz 2>&1 | grep "fluidd/index.html"')
print(f"index.html: {'存在' if 'index.html' in out else '不存在！'}")

# 关键文件
print("\n--- 关键配置文件 ---")
for f in ['printer.cfg', 'moonraker.conf', 'go2rtc.yaml', 'usb-watchdog.sh', 'fluidd-serve.sh']:
    out = run(f'tar tzf /root/n1_golden_image.tar.gz 2>&1 | grep "{f}" | head -1')
    print(f"  {f}: {'存在' if out.strip() else '缺失'}")

# 元数据
print("\n--- 元数据 ---")
out = run('tar xzf /root/n1_golden_image.tar.gz -O n1_golden_meta.txt 2>&1')
print(out.strip())

ssh.close()