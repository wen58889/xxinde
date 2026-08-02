import paramiko
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=10)

def run(cmd, timeout=10):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    stdout.channel.settimeout(timeout)
    return stdout.read().decode('utf-8', errors='replace')

# 快速5次验证
print("=== 快速验证 ===")
for i in range(5):
    ip = run('hostname -I').strip()
    hn = run('hostname').strip()
    print(f"  #{i+1} {hn} {ip}")
    time.sleep(2)

# 验证配置
print("\n=== 配置验证 ===")
out = run('nmcli con show "ZTE015G" 2>&1 | grep -iE "ipv4.method|ipv4.address|autoconnect-priority|cloned-mac|powersave"')
print(out.strip())

# 启动后台10分钟测试
print("\n=== 启动10分钟后台测试 ===")
test_script = '''#!/bin/bash
LOG=/tmp/ip_test.log
echo "=== 10min IP Test ===" > $LOG
OK=0; FAIL=0
for i in $(seq 1 60); do
    IP=$(hostname -I | tr -d ' ')
    if echo "$IP" | grep -q "192.168.5.112"; then
        echo "$(date +%H:%M:%S) #$i OK $IP" >> $LOG
        OK=$((OK+1))
    else
        echo "$(date +%H:%M:%S) #$i FAIL $IP" >> $LOG
        FAIL=$((FAIL+1))
    fi
    sleep 10
done
echo "=== RESULT: OK=$OK FAIL=$FAIL ===" >> $LOG
'''
sftp = ssh.open_sftp()
with sftp.open('/tmp/ip_test.sh', 'w') as f:
    f.write(test_script)
sftp.close()
run('chmod +x /tmp/ip_test.sh && nohup bash /tmp/ip_test.sh &')
print("后台测试已启动(10分钟)")

ssh.close()