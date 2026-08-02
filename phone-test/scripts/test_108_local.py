import paramiko
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.108', username='root', password='1234', timeout=15)

# 在108上直接运行5分钟测试脚本
test_script = r'''#!/bin/bash
echo "=== 5分钟稳定性测试 ==="
echo "时间     | 7125 | klippy  | Fluidd"
echo "---------------------------------------------"
ERRORS=0
for i in $(seq 1 60); do
    PORT=$(ss -tlnp | grep 7125 | wc -l)
    [ "$PORT" -gt 0 ] && P="OK" || P="NO"
    
    STATE=$(curl -s http://localhost:7125/server/info 2>&1 | grep -oP '"klippy_state":"\K[^"]+' || echo "ERR")
    [ "$STATE" = "ERR" ] && ERRORS=$((ERRORS + 1))
    
    F=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8080/ 2>&1)
    
    if [ $((i % 6)) -eq 0 ]; then
        echo "$(date +%H:%M:%S) | $P   | $STATE | $F"
    fi
    sleep 5
done
echo ""
echo "结果: $ERRORS 次错误 / 60次测试"
KLIP=$(journalctl -u klipper --since "5 min ago" --no-pager 2>&1 | grep -c "Started klipper")
MR=$(journalctl -u moonraker --since "5 min ago" --no-pager 2>&1 | grep -c "Started moonraker")
echo "Klipper重启(5min): $KLIP"
echo "Moonraker重启(5min): $MR"
'''

sftp = ssh.open_sftp()
with sftp.open('/tmp/stability_test.sh', 'w') as f:
    f.write(test_script)
sftp.close()

stdin, stdout, stderr = ssh.exec_command("chmod +x /tmp/stability_test.sh && bash /tmp/stability_test.sh", timeout=360)
print("测试运行中，等待5分钟...")

out = stdout.read().decode('utf-8', errors='replace')
print(out)

ssh.close()