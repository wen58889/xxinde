import paramiko
import time
import datetime

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

print("=== 2分钟快速稳定性测试 ===")

errors = 0
success = 0

for i in range(12):  # 每10秒一次，共2分钟
    try:
        ssh.close()
    except:
        pass
    
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect('192.168.5.112', username='root', password='1234', timeout=5)
        
        stdin, stdout, stderr = ssh.exec_command('hostname -I && hostname && iw dev wlan0 link 2>&1 | grep "Connected to"', timeout=5)
        stdout.channel.settimeout(5)
        result = stdout.read().decode('utf-8', errors='replace').strip()
        
        now = datetime.datetime.now().strftime('%H:%M:%S')
        if '192.168.5.112' in result:
            success += 1
            print(f"  [{now}] #{i+1:2d} OK - {result.split(chr(10))[0]}")
        else:
            errors += 1
            print(f"  [{now}] #{i+1:2d} IP_CHANGED - {result[:60]}")
        
    except Exception as e:
        errors += 1
        now = datetime.datetime.now().strftime('%H:%M:%S')
        print(f"  [{now}] #{i+1:2d} FAIL - {str(e)[:40]}")
    
    time.sleep(10)

print(f"\n结果: 成功{success}/12 失败{errors}/12")

# 启动后台10分钟测试
print("\n=== 启动后台10分钟测试 ===")
try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect('192.168.5.112', username='root', password='1234', timeout=5)
    
    # 在112上运行本地10分钟测试
    test_script = r'''#!/bin/bash
LOG=/tmp/ip_stability_test.log
echo "=== 10分钟IP稳定性测试 ===" > $LOG
echo "开始: $(date)" >> $LOG
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
echo "=== 结果: OK=$OK FAIL=$FAIL ===" >> $LOG
echo "结束: $(date)" >> $LOG
'''
    sftp = ssh.open_sftp()
    with sftp.open('/tmp/ip_test.sh', 'w') as f:
        f.write(test_script)
    sftp.close()
    
    stdin, stdout, stderr = ssh.exec_command('chmod +x /tmp/ip_test.sh && nohup bash /tmp/ip_test.sh &>/dev/null & echo STARTED', timeout=5)
    stdout.channel.settimeout(5)
    print(stdout.read().decode().strip())
    
    ssh.close()
except Exception as e:
    print(f"启动后台测试失败: {e}")