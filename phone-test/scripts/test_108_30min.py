import paramiko
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.108', username='root', password='1234', timeout=15)

test_script = r'''#!/bin/bash
echo "=== 30分钟全面稳定性测试 (192.168.5.108) ==="
echo "时间     | 7125 | klippy  | Fluidd | MCU串口 | USB autosuspend"
echo "----------------------------------------------------------------------"

ERRORS=0
MCU_LOSS=0
WS_DISCONNECT=0
PREV_STATE=""

for i in $(seq 1 360); do
    # 7125端口
    PORT=$(ss -tlnp | grep 7125 | wc -l)
    [ "$PORT" -gt 0 ] && P="OK" || P="NO"
    
    # klippy状态
    STATE=$(curl -s http://localhost:7125/server/info 2>&1 | grep -oP '"klippy_state":"\K[^"]+' || echo "ERR")
    [ "$STATE" = "ERR" ] && ERRORS=$((ERRORS + 1))
    
    # 检测状态变化(ready→非ready = 断连)
    if [ -n "$PREV_STATE" ] && [ "$PREV_STATE" = "ready" ] && [ "$STATE" != "ready" ]; then
        WS_DISCONNECT=$((WS_DISCONNECT + 1))
    fi
    PREV_STATE=$STATE
    
    # Fluidd
    F=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8080/ 2>&1)
    
    # MCU串口
    MCU=$(ls /dev/serial/by-id/ 2>/dev/null | grep -c Klipper)
    [ "$MCU" -eq 0 ] && MCU_LOSS=$((MCU_LOSS + 1))
    
    # USB autosuspend
    AUTOSUSPEND=$(cat /sys/module/usbcore/parameters/autosuspend 2>/dev/null || echo "?")
    
    # 每30秒(6次)打印一次
    if [ $((i % 6)) -eq 0 ]; then
        echo "$(date +%H:%M:%S) | $P   | $STATE | $F    | mcu=$MCU     | as=$AUTOSUSPEND"
    fi
    
    sleep 5
done

echo ""
echo "================================================================"
echo "30分钟测试完成:"
echo "  总测试次数: 360 (每5秒)"
echo "  错误次数: $ERRORS"
echo "  MCU串口丢失次数: $MCU_LOSS"
echo "  klippy状态断连次数(ready→非ready): $WS_DISCONNECT"

# 服务重启统计
KLIP=$(journalctl -u klipper --since "30 min ago" --no-pager 2>&1 | grep -c "Started klipper")
MR=$(journalctl -u moonraker --since "30 min ago" --no-pager 2>&1 | grep -c "Started moonraker")
WD=$(journalctl -u usb-watchdog --since "30 min ago" --no-pager 2>&1 | grep -c "MCU not detected")
echo "  Klipper重启(30min): $KLIP"
echo "  Moonraker重启(30min): $MR"
echo "  USB watchdog MCU丢失(30min): $WD"

# WebSocket断连统计
WS_LOST=$(grep -c "ping timed out\|Websocket closed" /root/printer_data/logs/moonraker.log 2>&1 || echo "0")
echo "  WebSocket断连(日志): $WS_LOST"

# USB断连统计
USB_DISC=$(dmesg | grep -c "USB disconnect" 2>&1 || echo "0")
echo "  USB disconnect(dmesg): $USB_DISC"

# 最终状态
echo ""
echo "最终状态:"
FINAL_STATE=$(curl -s http://localhost:7125/server/info 2>&1 | grep -oP '"klippy_state":"\K[^"]+' || echo "ERR")
echo "  klippy_state: $FINAL_STATE"
echo "  autosuspend: $(cat /sys/module/usbcore/parameters/autosuspend 2>/dev/null)"
echo "  MCU: $(ls /dev/serial/by-id/ 2>/dev/null | grep Klipper)"
echo "  USB power: $(for d in /sys/bus/usb/devices/*/power/control; do echo -n "$(basename $(dirname $d))=$(cat $d 2>/dev/null) "; done)"
'''

sftp = ssh.open_sftp()
with sftp.open('/tmp/stability_test_30min.sh', 'w') as f:
    f.write(test_script)
sftp.close()

stdin, stdout, stderr = ssh.exec_command("chmod +x /tmp/stability_test_30min.sh && bash /tmp/stability_test_30min.sh", timeout=1920)
print("30分钟测试运行中...")

out = stdout.read().decode('utf-8', errors='replace')
print(out)

ssh.close()