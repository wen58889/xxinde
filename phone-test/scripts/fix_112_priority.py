import paramiko
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=10)

def run(cmd, timeout=10):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    stdout.channel.settimeout(timeout)
    return stdout.read().decode('utf-8', errors='replace')

# 修复priority
print("=== 修复autoconnect-priority ===")
out = run('nmcli con mod "ZTE015G" connection.autoconnect-priority 100 2>&1')
print(f"priority: {out.strip()}")

# cloned-mac-address对WiFi不生效，用wifi.mac-address代替
print("\n=== 修复MAC ===")
out = run('nmcli con mod "ZTE015G" 802-11-wireless.mac-address "02:28:6a:10:5b:61" 2>&1 || nmcli con mod "ZTE015G" wifi.mac-address "02:28:6a:10:5b:61" 2>&1 || echo "mac-set-failed"')
print(f"mac: {out.strip()}")

# 验证
print("\n=== 验证 ===")
out = run('nmcli con show "ZTE015G" 2>&1 | grep -iE "autoconnect-priority|mac-address|ipv4.method|ipv4.address|powersave"')
print(out.strip())

# 写入后台测试脚本并启动
print("\n=== 启动10分钟后台测试 ===")
sftp = ssh.open_sftp()
with sftp.open('/tmp/ip_test.sh', 'w') as f:
    f.write('''#!/bin/bash
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
''')
sftp.close()

run('chmod +x /tmp/ip_test.sh')
# 用nohup后台启动
stdin, stdout, stderr = ssh.exec_command('nohup bash /tmp/ip_test.sh </dev/null &>/dev/null & echo STARTED', timeout=5)
stdout.channel.settimeout(5)
print(stdout.read().decode().strip())

ssh.close()