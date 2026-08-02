import paramiko
import time
import os

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.101', username='root', password='1234', timeout=10)

def run(cmd, timeout=30):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    stdout.channel.settimeout(timeout)
    return stdout.read().decode('utf-8', errors='replace')

# Step 1: 检查101的Fluidd
print("=== 检查101 Fluidd ===")
out = run('ls /root/printer_data/fluidd/index.html 2>&1 && ls /root/printer_data/fluidd/ | wc -l')
print(out.strip())

# Step 2: 上传打包脚本
print("\n=== 上传n1_golden_pack.sh到101 ===")
local_script = r'D:\Users\59520\IDEProjects\xxinde\phone-test\n1_golden_pack.sh'
sftp = ssh.open_sftp()
sftp.put(local_script, '/root/n1_golden_pack.sh')
sftp.close()
run('chmod +x /root/n1_golden_pack.sh')
print("上传完成")

# Step 3: 运行打包脚本（后台）
print("\n=== 运行打包脚本 ===")
run('nohup bash /root/n1_golden_pack.sh > /tmp/pack.log 2>&1 & echo $!')
print("打包已在后台启动，等待完成...")

# Step 4: 轮询等待
for i in range(60):
    time.sleep(10)
    out = run('cat /tmp/pack_done 2>/dev/null || echo PENDING', timeout=10)
    status = out.strip()
    
    # 检查进程是否还在运行
    proc = run('pgrep -f n1_golden_pack.sh 2>/dev/null || echo DONE', timeout=5)
    
    # 检查输出文件
    size_out = run('ls -lh /root/n1_golden_image.tar.gz 2>/dev/null || echo NO_FILE', timeout=5)
    
    print(f"  [{(i+1)*10}s] 进程:{proc.strip()[:20]} 文件:{size_out.strip()[:30]}")
    
    if 'DONE' in proc and 'NO_FILE' not in size_out:
        print("打包完成!")
        break
    if i == 59:
        print("等待超时，检查日志...")
        log = run('tail -20 /tmp/pack.log 2>&1')
        print(log)

# Step 5: 检查结果
print("\n=== 打包结果 ===")
out = run('ls -lh /root/n1_golden_image.tar.gz 2>&1')
print(out.strip())

# Step 6: 验证镜像内容
print("\n=== 验证镜像中Fluidd文件 ===")
out = run('tar tzf /root/n1_golden_image.tar.gz 2>&1 | grep fluidd | head -10')
print(out.strip())

out = run('tar tzf /root/n1_golden_image.tar.gz 2>&1 | grep "fluidd/index.html"')
print(f"index.html: {'存在' if 'index.html' in out else '不存在'}")

# Step 7: 查看打包日志
print("\n=== 打包日志(最后20行) ===")
out = run('tail -20 /tmp/pack.log 2>&1')
print(out.strip())

ssh.close()