import paramiko
import time
import json

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=15)

def run(cmd, timeout=30):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    stdout.channel.settimeout(timeout)
    return stdout.read().decode('utf-8', errors='replace')

# Step 1: 获取Fluidd release信息
print("=== 获取Fluidd release信息 ===")
out = run('curl -s --connect-timeout 10 "https://api.github.com/repos/fluidd-core/fluidd/releases/latest" 2>&1')
try:
    release = json.loads(out)
    tag = release.get('tag_name', 'unknown')
    print(f"最新版本: {tag}")
    for asset in release.get('assets', []):
        print(f"  文件: {asset['name']} ({asset['size']//1024}KB) URL: {asset['browser_download_url'][:60]}...")
except:
    print(f"API解析失败: {out[:200]}")

# Step 2: 尝试从其他正常设备(101)复制Fluidd文件
print("\n=== 尝试从101设备复制Fluidd ===")
out = run('ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 root@192.168.5.101 "ls /root/printer_data/fluidd/index.html 2>&1" 2>&1', timeout=15)
print(f"101 Fluidd: {out.strip()}")

if 'index.html' in out:
    print("101有Fluidd文件，尝试scp复制...")
    out = run('scp -o StrictHostKeyChecking=no -o ConnectTimeout=5 root@192.168.5.101:/root/printer_data/fluidd/* /root/printer_data/fluidd/ 2>&1', timeout=60)
    print(f"scp结果: {out.strip()}")
    
    # 验证
    out = run('ls /root/printer_data/fluidd/index.html 2>&1')
    print(f"index.html: {out.strip()}")
else:
    print("101没有Fluidd文件")
    
    # 尝试105
    print("\n=== 尝试从105设备复制Fluidd ===")
    out = run('ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 root@192.168.5.105 "ls /root/printer_data/fluidd/index.html 2>&1" 2>&1', timeout=15)
    print(f"105 Fluidd: {out.strip()}")
    
    if 'index.html' in out:
        print("105有Fluidd文件，尝试scp复制...")
        out = run('scp -o StrictHostKeyChecking=no -o ConnectTimeout=5 root@192.168.5.105:/root/printer_data/fluidd/* /root/printer_data/fluidd/ 2>&1', timeout=60)
        print(f"scp结果: {out.strip()}")

# Step 3: 最终验证
out = run('ls /root/printer_data/fluidd/ 2>&1')
print(f"\nFluidd目录内容: {out.strip()}")

out = run('ls /root/printer_data/fluidd/index.html 2>&1')
print(f"index.html: {out.strip()}")

ssh.close()