import paramiko
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=10)

def run(cmd, timeout=10):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    stdout.channel.settimeout(timeout)
    return stdout.read().decode('utf-8', errors='replace')

# 验证当前状态
print("=== 当前状态 ===")
out = run('iw dev wlan0 link 2>&1 | head -4')
print(out.strip())
out = run('nmcli -t -f NAME,AUTOCONNECT-PRIORITY con show 2>&1 | grep -iE "ZTE|Wired"')
print(out.strip())

# 启动10分钟后台测试
print("\n=== 启动10分钟后台测试 ===")
sftp = ssh.open_sftp()
with sftp.open('/root/ip_test.sh', 'w') as f:
    f.write('''#!/bin/bash
LOG=/root/ip_test.log
echo "=== 10min IP Test ===" > $LOG
echo "Start: $(date)" >> $LOG
OK=0; FAIL=0
for i in $(seq 1 60); do
    IP=$(hostname -I | tr -d ' ')
    WIFI=$(iw dev wlan0 link 2>&1 | grep "SSID" | awk '{print $2}')
    if echo "$IP" | grep -q "192.168.5.112"; then
        echo "$(date +%H:%M:%S) #$i OK $IP WiFi=$WIFI" >> $LOG
        OK=$((OK+1))
    else
        echo "$(date +%H:%M:%S) #$i FAIL $IP WiFi=$WIFI" >> $LOG
        FAIL=$((FAIL+1))
    fi
    sleep 10
done
echo "=== RESULT: OK=$OK FAIL=$FAIL ===" >> $LOG
echo "End: $(date)" >> $LOG
''')
sftp.close()

run('chmod +x /root/ip_test.sh')
stdin, stdout, stderr = ssh.exec_command('nohup bash /root/ip_test.sh </dev/null &>/dev/null & echo STARTED', timeout=5)
stdout.channel.settimeout(5)
print(stdout.read().decode().strip())

ssh.close()