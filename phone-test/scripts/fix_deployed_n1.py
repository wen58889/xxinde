#!/usr/bin/env python3
"""
已部署N1设备批量修复脚本 v4.0 (Python版 - Windows可运行)
用法: python fix_deployed_n1.py 192.168.5.101 192.168.5.105
      python fix_deployed_n1.py --ip-list ips.txt
      python fix_deployed_n1.py 192.168.5.112 --steps 1,2,7
"""

import sys
import os
import time
import argparse
import paramiko

PASSWORD = "1234"
USER = "root"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
N1_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "n1")

USB_WATCHDOG_V5 = r'''#!/bin/bash
source /usr/local/bin/alert-push.sh 2>/dev/null || true

MCU_ID="usb-Klipper"
CHECK_INTERVAL=5
MAX_FAIL=3
FAIL_COUNT=0
RECOVERY_LEVEL=0
MAX_RECOVERY_LEVEL=5
COOLDOWN=300
LAST_RECOVERY=0
XHCI_FAIL_COUNT=0
XHCI_REBOOT_THRESHOLD=6
MCU_DOWN_SINCE=0
log() { logger -t usb-watchdog "$1"; }

check_xhci_error() {
    dmesg | tail -30 | grep -qiE 'HC died|xHCI host controller not responding'
}

check_xhci_timeout() {
    dmesg | tail -30 | grep -qiE 'Timeout while waiting for setup device|unable to enumerate USB device|device descriptor read.*error -1[12]0|device not accepting address.*error -62'
}

xhci_preventive_reset() {
    for dev in /sys/bus/pci/drivers/xhci_hcd/*/; do
        [ -d "$dev" ] || continue
        dn=$(basename "$dev")
        echo "$dn" > /sys/bus/pci/drivers/xhci_hcd/unbind 2>/dev/null || true
        sleep 2
        echo "$dn" > /sys/bus/pci/drivers/xhci_hcd/bind 2>/dev/null || true
        sleep 3
    done
}

verify_klippy_ready() {
    local retries=0
    while [ $retries -lt 6 ]; do
        local state=$(curl -s -m 3 http://127.0.0.1:7125/server/info 2>/dev/null | grep -oP '"klippy_state":"\K[^"]+' || echo "")
        if [ "$state" = "ready" ]; then
            return 0
        fi
        retries=$((retries + 1))
        sleep 5
    done
    return 1
}

while true; do
    sleep $CHECK_INTERVAL

    if check_xhci_error; then
        log "CRITICAL: XHCI HC died! Rebooting"
        type alert_push &>/dev/null && alert_push "xhci_died" "critical" "XHCI host controller died, rebooting"
        sleep 1
        reboot
    fi

    if check_xhci_timeout; then
        XHCI_FAIL_COUNT=$((XHCI_FAIL_COUNT + 1))
        log "XHCI timeout detected (count=$XHCI_FAIL_COUNT/$XHCI_REBOOT_THRESHOLD)"
        if [ $XHCI_FAIL_COUNT -ge $XHCI_REBOOT_THRESHOLD ]; then
            log "XHCI timeout threshold reached, rebooting"
            type alert_push &>/dev/null && alert_push "xhci_timeout" "critical" "XHCI timeout threshold reached, rebooting"
            sleep 1
            reboot
        fi
    else
        if [ $XHCI_FAIL_COUNT -gt 0 ]; then
            XHCI_FAIL_COUNT=$((XHCI_FAIL_COUNT - 1))
        fi
    fi

    if ls /dev/serial/by-id/ 2>/dev/null | grep -q "$MCU_ID"; then
        if [ $FAIL_COUNT -gt 0 ]; then
            local down_duration=0
            if [ $MCU_DOWN_SINCE -gt 0 ]; then
                down_duration=$(( $(date +%s) - MCU_DOWN_SINCE ))
            fi
            log "MCU recovered (was down ${down_duration}s)"
            type alert_resolved &>/dev/null && alert_resolved "mcu_disconnected" "$down_duration"
            FAIL_COUNT=0
            RECOVERY_LEVEL=0
            MCU_DOWN_SINCE=0
        fi
        continue
    fi
    FAIL_COUNT=$((FAIL_COUNT + 1))
    if [ $MCU_DOWN_SINCE -eq 0 ]; then
        MCU_DOWN_SINCE=$(date +%s)
        type alert_push &>/dev/null && alert_push "mcu_disconnected" "critical" "MCU not detected at /dev/serial/by-id/, starting recovery"
    fi
    log "MCU not detected! fail=$FAIL_COUNT level=$RECOVERY_LEVEL"
    if [ $FAIL_COUNT -ge $MAX_FAIL ]; then
        NOW=$(date +%s)
        ELAPSED=$((NOW - LAST_RECOVERY))
        if [ $ELAPSED -lt $COOLDOWN ]; then
            log "Cooldown active (${ELAPSED}s/${COOLDOWN}s), skip recovery"
            FAIL_COUNT=0
            continue
        fi
        if [ $RECOVERY_LEVEL -ge $MAX_RECOVERY_LEVEL ]; then
            log "Max recovery level reached, stop trying until MCU reappears"
            type alert_push &>/dev/null && alert_push "mcu_recovery_exhausted" "critical" "All recovery levels exhausted, MCU still disconnected"
            FAIL_COUNT=0
            sleep 60
            continue
        fi
        RECOVERY_LEVEL=$((RECOVERY_LEVEL + 1))
        LAST_RECOVERY=$NOW
        if [ $RECOVERY_LEVEL -eq 1 ]; then
            log "Recovery L1: firmware_restart"
            curl -s -X POST http://127.0.0.1:7125/printer/firmware_restart 2>/dev/null
            sleep 5
        elif [ $RECOVERY_LEVEL -eq 2 ]; then
            log "Recovery L2: restart klipper"
            systemctl restart klipper 2>/dev/null
            sleep 8
        elif [ $RECOVERY_LEVEL -eq 3 ]; then
            log "Recovery L3: USB port authorized reset (skip hub)"
            for port in /sys/bus/usb/devices/*/authorized; do
                devpath=$(dirname "$port")
                devnum=$(cat "$devpath/devnum" 2>/dev/null || echo "0")
                if [ "$devnum" = "1" ]; then continue; fi
                echo 0 > "$port" 2>/dev/null
                sleep 1
                echo 1 > "$port" 2>/dev/null
            done
            sleep 5
            systemctl restart klipper 2>/dev/null
            sleep 5
        elif [ $RECOVERY_LEVEL -eq 4 ]; then
            log "Recovery L4: xhci_hcd preventive unbind/rebind + service restart"
            xhci_preventive_reset
            systemctl restart klipper moonraker 2>/dev/null
            sleep 8
        else
            log "Recovery L5: full reboot"
            type alert_push &>/dev/null && alert_push "mcu_reboot" "critical" "MCU recovery L5: full reboot"
            sleep 2
            reboot
        fi
        if [ $RECOVERY_LEVEL -lt $MAX_RECOVERY_LEVEL ]; then
            if verify_klippy_ready; then
                log "Klipper verified ready after L$RECOVERY_LEVEL"
            else
                log "Klipper NOT ready after L$RECOVERY_LEVEL"
                type alert_push &>/dev/null && alert_push "klipper_not_ready" "warning" "Klipper not ready after recovery L$RECOVERY_LEVEL"
            fi
        fi
        FAIL_COUNT=0
    fi
done
'''

USB_AUTOSUSPEND_FIX = r'''#!/bin/bash
echo -1 > /sys/module/usbcore/parameters/autosuspend 2>/dev/null || true
for d in /sys/bus/usb/devices/*/power/control; do echo on > "$d" 2>/dev/null; done
for d in /sys/bus/usb/devices/*/power/autosuspend; do echo -1 > "$d" 2>/dev/null; done
logger -t usb-autosuspend-fix 'autosuspend=-1 + USB PM=on'
'''

USB_AUTOSUSPEND_SERVICE = """[Unit]
Description=Force USB autosuspend=-1 (sysinit stage)
DefaultDependencies=no
After=sysinit.target
Before=basic.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/usb-autosuspend-fix.sh
RemainAfterExit=yes

[Install]
WantedBy=sysinit.target
"""

ETH0_POWER_FIX = r'''#!/bin/bash
sleep 2
IFACE=$(cat /etc/n1-fixed-iface 2>/dev/null || echo "eth0")
[ -e "/sys/class/net/$IFACE" ] || IFACE="eth0"
ethtool --set-eee $IFACE eee off 2>/dev/null || true
ethtool -s $IFACE wol d 2>/dev/null || true
echo on > /sys/class/net/$IFACE/power/control 2>/dev/null || true
logger -t eth0-power-fix "$IFACE: EEE off + WoL off + PM on (no speed force)"
'''

NM_DISPATCHER_ETH0 = r'''#!/bin/bash
IFACE="$1"
ACTION="$2"
if [ "$IFACE" = "eth0" ] && [ "$ACTION" = "up" ]; then
    ethtool --set-eee eth0 eee off 2>/dev/null || true
    ethtool -s eth0 wol d 2>/dev/null || true
    echo on > /sys/class/net/eth0/power/control 2>/dev/null || true
    logger -t eth0-stable "eth0 up: EEE off + WoL off + PM on (no speed force)"
fi
'''

NET_CHECK = r'''#!/bin/bash
sleep 10
echo -1 > /sys/module/usbcore/parameters/autosuspend 2>/dev/null || true
for d in /sys/bus/usb/devices/*/power/control; do echo on > "$d" 2>/dev/null; done
for d in /sys/bus/usb/devices/*/power/autosuspend; do echo -1 > "$d" 2>/dev/null; done
IFACE=$(cat /etc/n1-fixed-iface 2>/dev/null || echo "eth0")
[ -e "/sys/class/net/$IFACE" ] || IFACE="eth0"
ethtool --set-eee $IFACE eee off 2>/dev/null || true
ethtool -s $IFACE wol d 2>/dev/null || true
echo on > /sys/class/net/$IFACE/power/control 2>/dev/null || true
logger -t net-check 'Network integrity check completed (wired-only)'
'''

NET_CHECK_SERVICE = """[Unit]
Description=Network Integrity Check (post-boot, wired-only)
After=NetworkManager.service
Wants=NetworkManager.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/net-check.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
"""

RFKILL_BLOCK = r'''#!/bin/bash
rfkill block wlan 2>/dev/null || true
logger -t rfkill-wifi-block 'WiFi rfkill block applied'
'''

RFKILL_PERSIST_SERVICE = """[Unit]
Description=Persist WiFi rfkill block state
After=NetworkManager.service
Wants=NetworkManager.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/rfkill-wifi-block.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
"""


LOGROTATE_CONF = """/var/log/syslog
/var/log/kern.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
    create 0640 root adm
}

/root/printer_data/logs/*.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
    copytruncate
}

"""

NTP_CONF = """[Time]
NTP=ntp.aliyun.com ntp.tencent.com
FallbackNTP=pool.ntp.org
"""


def log(msg):
    print(f"[N1-FIX] {time.strftime('%H:%M:%S')} {msg}")


def warn(msg):
    print(f"[N1-FIX] {time.strftime('%H:%M:%S')} [WARN] {msg}")


def create_ssh_client(ip, password=PASSWORD, timeout=10):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(ip, username=USER, password=password, timeout=timeout,
                       allow_agent=False, look_for_keys=False)
        return client
    except Exception as e:
        warn(f"{ip}: SSH连接失败: {e}")
        return None


def run_cmd(client, cmd, timeout=30):
    try:
        stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode('utf-8', errors='replace').strip()
        err = stderr.read().decode('utf-8', errors='replace').strip()
        return out, err, stdout.channel.recv_exit_status()
    except Exception as e:
        return "", str(e), -1


def upload_text(client, remote_path, content):
    try:
        sftp = client.open_sftp()
        with sftp.file(remote_path, 'w') as f:
            f.write(content)
        sftp.close()
        return True
    except Exception as e:
        warn(f"上传 {remote_path} 失败: {e}")
        return False


def upload_local_file(client, local_path, remote_path):
    if not os.path.exists(local_path):
        warn(f"本地文件不存在: {local_path}")
        return False
    try:
        sftp = client.open_sftp()
        sftp.put(local_path, remote_path)
        sftp.close()
        return True
    except Exception as e:
        warn(f"上传 {local_path} -> {remote_path} 失败: {e}")
        return False


def make_executable(client, path):
    run_cmd(client, f"chmod +x {path}")


def deploy_service(client, name, service_content, enable=True, start=True):
    svc_path = f"/etc/systemd/system/{name}.service"
    upload_text(client, svc_path, service_content)
    run_cmd(client, "systemctl daemon-reload")
    if enable:
        run_cmd(client, f"systemctl enable {name}.service 2>/dev/null || true")
    if start:
        run_cmd(client, f"systemctl restart {name}.service 2>/dev/null || true")


ALL_STEPS = list(range(1, 14))


def fix_device(ip, steps=None, password=PASSWORD):
    if steps is None:
        steps = ALL_STEPS

    log(f"========== 修复 {ip} ==========")

    client = create_ssh_client(ip, password)
    if client is None:
        return False

    try:
        out, _, rc = run_cmd(client, "echo connected")
        if rc != 0:
            warn(f"{ip}: SSH验证失败")
            return False
        log(f"{ip}: SSH连接成功")

        if 1 in steps:
            log(f"{ip}: [1/13] 部署USB watchdog v5...")
            upload_text(client, "/usr/local/bin/usb-watchdog.sh", USB_WATCHDOG_V5)
            make_executable(client, "/usr/local/bin/usb-watchdog.sh")
            run_cmd(client, "systemctl restart usb-watchdog 2>/dev/null || true")
            log(f"{ip}: USB watchdog v5已更新")

        if 2 in steps:
            log(f"{ip}: [2/17] 修复USB autosuspend=-1...")
            run_cmd(client, "echo -1 > /sys/module/usbcore/parameters/autosuspend 2>/dev/null || true")
            run_cmd(client, """for d in /sys/bus/usb/devices/*/power/control; do echo on > "$d" 2>/dev/null; done""")
            upload_text(client, "/usr/local/bin/usb-autosuspend-fix.sh", USB_AUTOSUSPEND_FIX)
            make_executable(client, "/usr/local/bin/usb-autosuspend-fix.sh")
            deploy_service(client, "usb-autosuspend-fix", USB_AUTOSUSPEND_SERVICE, enable=True, start=False)
            run_cmd(client, "echo 'options usbcore autosuspend=-1' > /etc/modprobe.d/usb-no-autosuspend.conf 2>/dev/null || true")
            out, _, _ = run_cmd(client, "cat /sys/module/usbcore/parameters/autosuspend 2>/dev/null")
            log(f"{ip}: autosuspend={out} (期望-1)")

        if 3 in steps:
            log(f"{ip}: [3/17] 修复eth0省电...")
            upload_text(client, "/usr/local/bin/eth0-power-fix.sh", ETH0_POWER_FIX)
            make_executable(client, "/usr/local/bin/eth0-power-fix.sh")
            upload_text(client, "/etc/NetworkManager/dispatcher.d/99-eth0-stable.sh", NM_DISPATCHER_ETH0)
            make_executable(client, "/etc/NetworkManager/dispatcher.d/99-eth0-stable.sh")
            run_cmd(client, """LINK=$(ethtool eth0 2>/dev/null | grep 'Link detected' | awk '{print $3}')
if [ "$LINK" = "no" ]; then ethtool -s eth0 autoneg on 2>/dev/null || true; logger -t n1-fix 'eth0 PHY卡死已恢复(autoneg=on)'; fi""")
            log(f"{ip}: eth0省电已修复")

        if 4 in steps:
            log(f"{ip}: [4/17] 修复NM speed=0...")
            run_cmd(client, """CON=$(nmcli -t -f NAME,DEVICE con show --active 2>/dev/null | grep eth0 | head -1 | cut -d: -f1)
if [ -n "$CON" ]; then nmcli con mod "$CON" 802-3-ethernet.speed 0 2>/dev/null || true; fi""")
            log(f"{ip}: NM speed=0已设置")

        if 5 in steps:
            log(f"{ip}: [5/17] 禁用wired-watchdog...")
            run_cmd(client, "systemctl disable wired-watchdog 2>/dev/null || true; systemctl stop wired-watchdog 2>/dev/null || true")
            log(f"{ip}: wired-watchdog已禁用")

        if 6 in steps:
            log(f"{ip}: [6/17] 部署net-check.service...")
            upload_text(client, "/usr/local/bin/net-check.sh", NET_CHECK)
            make_executable(client, "/usr/local/bin/net-check.sh")
            deploy_service(client, "net-check", NET_CHECK_SERVICE, enable=True, start=False)
            log(f"{ip}: net-check.service已部署")

        if 7 in steps:
            log(f"{ip}: [7/17] WiFi三层禁用...")
            run_cmd(client, "rfkill block wlan 2>/dev/null || true")
            run_cmd(client, "nmcli radio wifi off 2>/dev/null || true")
            run_cmd(client, "echo 'blacklist brcmfmac' > /etc/modprobe.d/brcmfmac.conf")
            log(f"{ip}: WiFi三层禁用已执行")

        if 8 in steps:
            log(f"{ip}: [8/17] WiFi服务清理...")
            run_cmd(client, "systemctl disable wifi-watchdog 2>/dev/null || true; systemctl stop wifi-watchdog 2>/dev/null || true")
            run_cmd(client, "rm -f /etc/NetworkManager/dispatcher.d/99-wifi-stability.sh 2>/dev/null || true")
            run_cmd(client, "rm -f /etc/NetworkManager/conf.d/no-p2p.conf 2>/dev/null || true")
            run_cmd(client, "rm -f /etc/NetworkManager/conf.d/wifi-no-bgscan.conf 2>/dev/null || true")
            run_cmd(client, "rm -f /etc/NetworkManager/conf.d/wifi-no-mac-random.conf 2>/dev/null || true")
            log(f"{ip}: WiFi服务已清理")

        if 9 in steps:
            log(f"{ip}: [9/17] 部署rfkill持久化service...")
            upload_text(client, "/usr/local/bin/rfkill-wifi-block.sh", RFKILL_BLOCK)
            make_executable(client, "/usr/local/bin/rfkill-wifi-block.sh")
            deploy_service(client, "n1-rfkill-persist", RFKILL_PERSIST_SERVICE, enable=True, start=False)
            log(f"{ip}: rfkill持久化service已部署")

        if 10 in steps:
            log(f"{ip}: [10/13] 配置硬件看门狗...")
            run_cmd(client, """if [ -e /dev/watchdog ]; then
    if grep -q '^WatchdogSec=' /etc/systemd/system.conf 2>/dev/null; then
        sed -i 's/^WatchdogSec=.*/WatchdogSec=60/' /etc/systemd/system.conf 2>/dev/null || true
    elif grep -q '^#WatchdogSec=' /etc/systemd/system.conf 2>/dev/null; then
        sed -i 's/^#WatchdogSec=.*/WatchdogSec=60/' /etc/systemd/system.conf 2>/dev/null || true
    else
        echo 'WatchdogSec=60' >> /etc/systemd/system.conf 2>/dev/null || true
    fi
fi""")
            log(f"{ip}: 硬件看门狗已配置")

        if 11 in steps:
            log(f"{ip}: [11/13] 配置NTP + logrotate...")
            run_cmd(client, """if command -v timedatectl &>/dev/null; then
    systemctl enable systemd-timesyncd 2>/dev/null || true
    systemctl start systemd-timesyncd 2>/dev/null || true
fi""")
            upload_text(client, "/etc/systemd/timesyncd.conf", NTP_CONF)
            upload_text(client, "/etc/logrotate.d/n1-stability", LOGROTATE_CONF)
            log(f"{ip}: NTP + logrotate已配置")

        if 12 in steps:
            log(f"{ip}: [12/13] 重启usb-watchdog...")
            run_cmd(client, "systemctl restart usb-watchdog 2>/dev/null || true")
            log(f"{ip}: usb-watchdog已重启")

        if 13 in steps:
            log(f"{ip}: [13/13] 修复Fluidd WebSocket周期性断连 (ping_interval 10s→30s)...")
            out, _, rc = run_cmd(client,
                "grep -q 'websocket_ping_interval.*else 10\\.' "
                "/root/moonraker/moonraker/components/application.py 2>/dev/null && echo NEED_FIX || echo OK")
            if "NEED_FIX" in out:
                run_cmd(client,
                    "sed -i \"s/'websocket_ping_interval': None if tornado_ver < (6, 5) else 10\\./"
                    "'websocket_ping_interval': None if tornado_ver < (6, 5) else 30./\" "
                    "/root/moonraker/moonraker/components/application.py")
                run_cmd(client, "systemctl restart moonraker 2>/dev/null || true")
                log(f"{ip}: Fluidd WebSocket ping_interval已修复 (10s→30s)")
            else:
                log(f"{ip}: Fluidd WebSocket ping_interval已是30s或文件不存在，跳过")

        # 验证
        log(f"{ip}: 验证修复结果...")
        state, _, _ = run_cmd(client, """curl -s http://localhost:7125/server/info 2>&1 | grep -oP '"klippy_state":"\\K[^"]+' || echo ERR""")
        mcu, _, _ = run_cmd(client, "ls /dev/serial/by-id/ 2>/dev/null | grep -c Klipper || echo 0")
        autosuspend, _, _ = run_cmd(client, "cat /sys/module/usbcore/parameters/autosuspend 2>/dev/null || echo ?")
        rfkill, _, _ = run_cmd(client, "rfkill list 2>/dev/null | grep -A2 wlan | grep 'Soft blocked' | awk '{print $3}' || echo unknown")
        nm_wifi, _, _ = run_cmd(client, "nmcli radio wifi 2>/dev/null || echo unknown")
        svc_as, _, _ = run_cmd(client, "systemctl is-enabled usb-autosuspend-fix 2>/dev/null || echo disabled")

        log(f"{ip}: klippy={state} | mcu={mcu} | autosuspend={autosuspend} | rfkill={rfkill}")
        log(f"{ip}: usb-autosuspend-fix={svc_as} | nmcli_wifi={nm_wifi}")


        if state == "ready" and autosuspend == "-1" and svc_as == "enabled" and rfkill == "yes":
            log(f"{ip}: 修复成功!")
        else:
            warn(f"{ip}: 需要关注 (klippy={state} autosuspend={autosuspend} rfkill={rfkill})")

        log(f"{ip}: ========== 完成 ==========")
        return True

    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(description="N1设备批量修复脚本 v4.0 (Python版)")
    parser.add_argument("ips", nargs="*", help="N1设备IP列表")
    parser.add_argument("--ip-list", help="IP列表文件路径")
    parser.add_argument("--password", default=PASSWORD, help="SSH密码 (默认: 1234)")
    parser.add_argument("--steps", help="只执行指定步骤，逗号分隔 (如: 1,2,7)")
    args = parser.parse_args()

    ips = list(args.ips)
    if args.ip_list:
        with open(args.ip_list, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    ips.append(line)

    steps = ALL_STEPS
    if args.steps:
        steps = [int(s.strip()) for s in args.steps.split(',')]

    if not ips:
        print("用法: python fix_deployed_n1.py 192.168.5.101 192.168.5.105")
        print("      python fix_deployed_n1.py --ip-list ips.txt")
        print("      python fix_deployed_n1.py 192.168.5.112 --steps 1,2,7")
        print("")
        print("修复内容 (v4.0):")
        print("  1.  USB watchdog v5 (告警通知+XHCI预防+Klipper双重验证+冷却防抖)")
        print("  2.  USB autosuspend=-1 (运行时+systemd持久化)")
        print("  3.  eth0省电修复 (EEE/WoL/PM, 不设speed)")
        print("  4.  NM连接属性 speed=0 (自由协商)")
        print("  5.  wired-watchdog默认禁用")
        print("  6.  net-check.service (纯有线版)")
        print("  7.  WiFi三层禁用 (rfkill+nmcli+黑名单)")
        print("  8.  WiFi服务清理")
        print("  9.  rfkill持久化service")
        print("  10. alert-push.sh 告警推送函数库")
        print("  11. link-monitor.service 有线链路监控")
        print("  12. n1-health-monitor.service 系统资源监控")
        print("  13. n1-health-api.service 健康状态HTTP API (端口8090)")
        print("  14. n1-diagnose.sh 一键诊断收集")
        print("  15. 硬件看门狗配置 (WatchdogSec=60)")
        print("  16. NTP + logrotate配置")
        print("  17. 重启usb-watchdog (加载alert-push)")
        print("  18. 修复Fluidd WebSocket周期性断连 (ping_interval 10s→30s)")
        sys.exit(1)

    print(f"目标设备: {len(ips)}台, 步骤: {steps}")
    print("=" * 50)

    success = 0
    fail = 0

    for ip in ips:
        try:
            if fix_device(ip, steps=steps, password=args.password):
                success += 1
            else:
                fail += 1
        except Exception as e:
            warn(f"{ip}: 异常: {e}")
            fail += 1

    print()
    print("=" * 50)
    print(f"修复完成: 成功={success} 失败={fail}")
    print("=" * 50)


if __name__ == "__main__":
    main()