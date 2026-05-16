#!/bin/bash
####################################################################################
# N1 设备SSH远程修复脚本 (在总控机上运行)
# 用途: 通过SSH修复103（和102）的部署问题
# 注意: 需要sshpass或手动输入密码 (root/1234)
# 用法: ./n1_remote_fix.sh 192.168.5.103
####################################################################################

IP=${1:?用法: $0 <设备IP>}
USER=root
PASS=1234

echo "=========================================="
echo "  N1 远程修复: $IP"
echo "=========================================="

ssh_cmd() {
    ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 "$USER@$IP" "$@"
}

echo "[1] 检查SSH连接..."
if ! ssh_cmd "echo OK" 2>/dev/null; then
    echo "ERROR: SSH连接失败，请确认设备可达且密码正确"
    exit 1
fi
echo "SSH连接OK"

echo ""
echo "[2] 检查MCU串口..."
ssh_cmd "ls -la /dev/serial/by-id/ 2>/dev/null || echo '无串口设备'"
echo ""

echo "[3] 检查Klipper状态..."
ssh_cmd "systemctl status klipper --no-pager -l 2>/dev/null | head -15"
echo ""

echo "[4] 检查MCU日志..."
ssh_cmd "journalctl -u klipper -n 20 --no-pager 2>/dev/null | tail -20"
echo ""

echo "[5] 检查Moonraker..."
ssh_cmd "curl -sf http://localhost:7125/server/info 2>/dev/null | python3 -c 'import sys,json; d=json.load(sys.stdin)[\"result\"]; print(f\"klippy_state={d[\"klippy_state\"]} connected={d[\"klippy_connected\"]}\")' 2>/dev/null || echo 'Moonraker无响应'"
echo ""

echo "[6] 检查go2rtc..."
ssh_cmd "curl -sf http://localhost:1984/api/streams 2>/dev/null | python3 -c 'import sys,json; print(list(json.load(sys.stdin).keys()))' 2>/dev/null || echo 'go2rtc无响应'"
echo ""

echo "[7] 检查WiFi..."
ssh_cmd "nmcli dev status 2>/dev/null | head -5"
echo ""

echo "=========================================="
echo "  如果MCU串口为空，需要:"
echo "    1. 编译固件: cd /root/klipper && make menuconfig && make -j4"
echo "    2. 刷写固件: make flash FLASH_DEVICE=/dev/serial/by-id/xxx"
echo "    3. 或BOOTSEL模式: cp out/klipper.elf.uf2 /media/root/RPI-RP2/"
echo ""
echo "  如果服务未启动:"
echo "    systemctl daemon-reload"
echo "    systemctl restart klipper moonraker go2rtc"
echo "=========================================="
