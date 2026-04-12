#!/bin/bash
# N1 节点初始化安装脚本
# 用法: scp install_n1.sh root@192.168.1.10x:~ && ssh root@192.168.1.10x 'bash install_n1.sh'
set -euo pipefail

echo "===== N1 节点初始化安装 ====="

# 基础依赖
apt-get update && apt-get install -y \
  git wget curl python3 python3-pip \
  v4l-utils libusb-1.0-0-dev \
  gcc-arm-none-eabi

# 安装 Klipper
if [ ! -d ~/klipper ]; then
  git clone https://github.com/Klipper3d/klipper.git ~/klipper
  cd ~/klipper
  pip3 install -r scripts/klippy-requirements.txt
fi

# 安装 Moonraker
if [ ! -d ~/moonraker ]; then
  git clone https://github.com/Arksine/moonraker.git ~/moonraker
  cd ~/moonraker
  pip3 install -r scripts/moonraker-requirements.txt
fi

# 安装 go2rtc
GO2RTC_VER="1.9.4"
ARCH=$(dpkg --print-architecture)
if [ ! -f /usr/local/bin/go2rtc ]; then
  wget -O /usr/local/bin/go2rtc \
    "https://github.com/AlexxIT/go2rtc/releases/download/v${GO2RTC_VER}/go2rtc_linux_${ARCH}"
  chmod +x /usr/local/bin/go2rtc
fi

# 创建配置目录
mkdir -p /etc/go2rtc /etc/klipper /etc/moonraker

# 配置 Klipper printer.cfg (CoreXY 模板)
cat > /etc/klipper/printer.cfg << 'PRINTER'
[mcu]
serial: /dev/serial/by-id/usb-Klipper_rp2040_*

[printer]
kinematics: corexy
max_velocity: 300
max_accel: 3000
max_z_velocity: 50
max_z_accel: 200

[stepper_x]
step_pin: gpio2
dir_pin: gpio3
enable_pin: !gpio4
microsteps: 16
rotation_distance: 40
endstop_pin: ^gpio5
position_endstop: 0
position_max: 200

[stepper_y]
step_pin: gpio6
dir_pin: gpio7
enable_pin: !gpio8
microsteps: 16
rotation_distance: 40
endstop_pin: ^gpio9
position_endstop: 0
position_max: 200

[stepper_z]
step_pin: gpio10
dir_pin: gpio11
enable_pin: !gpio12
microsteps: 16
rotation_distance: 8
endstop_pin: ^gpio13
position_endstop: 0
position_max: 50
position_min: -2
PRINTER

# 配置 Moonraker
cat > /etc/moonraker/moonraker.conf << 'MOONRAKER'
[server]
host: 0.0.0.0
port: 7125

[authorization]
trusted_clients:
    192.168.1.0/24
cors_domains:
    *

[machine]
provider: none
MOONRAKER

# systemd 服务
cat > /etc/systemd/system/klipper.service << 'SVC'
[Unit]
Description=Klipper 3D Printer Firmware
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/bin/python3 /root/klipper/klippy/klippy.py /etc/klipper/printer.cfg -l /tmp/klippy.log
Restart=always

[Install]
WantedBy=multi-user.target
SVC

cat > /etc/systemd/system/moonraker.service << 'SVC'
[Unit]
Description=Moonraker API Server
After=klipper.service

[Service]
Type=simple
User=root
ExecStart=/usr/bin/python3 /root/moonraker/moonraker/moonraker.py -c /etc/moonraker/moonraker.conf
Restart=always

[Install]
WantedBy=multi-user.target
SVC

cat > /etc/systemd/system/go2rtc.service << 'SVC'
[Unit]
Description=go2rtc streaming server
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/go2rtc -config /etc/go2rtc/go2rtc.yaml
Restart=always

[Install]
WantedBy=multi-user.target
SVC

# 启用服务
systemctl daemon-reload
systemctl enable --now klipper moonraker go2rtc

echo "===== N1 安装完成 ====="
echo "Moonraker: http://$(hostname -I | awk '{print $1}'):7125"
echo "go2rtc:    http://$(hostname -I | awk '{print $1}'):1984"
