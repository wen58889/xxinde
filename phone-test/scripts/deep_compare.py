import paramiko
import time

def ssh_run(host, cmd):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username='root', password='1234', timeout=10)
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=10)
    out = stdout.read().decode('utf-8', errors='replace')
    ssh.close()
    return out

hosts = {'101': '192.168.5.101', '106': '192.168.5.106'}

for name, ip in hosts.items():
    print(f"\n{'='*60}")
    print(f"=== {name} ({ip}) ===")
    print(f"{'='*60}")
    
    cmds = {
        # 1. 归位状态和当前位置
        'homed_pos': 'curl -s http://localhost:7125/printer/objects/query?toolhead 2>&1',
        # 2. 归位方向配置
        'homing_cfg': 'grep -i "homing\\|home\\|position_endstop\\|position_min\\|position_max" /root/printer_data/config/printer.cfg',
        # 3. 摄像头实际抓图方向 - 通过go2rtc抓图看分辨率
        'cam_snap': 'curl -s http://localhost:7125/server/webcam/list 2>&1',
        # 4. go2rtc完整配置
        'go2rtc': 'cat /etc/go2rtc/go2rtc.yaml 2>&1',
        # 5. 摄像头USB位置（物理端口不同=摄像头朝向可能不同）
        'cam_usb': 'lsusb -t 2>&1',
        # 6. 摄像头旋转设置（关键！）
        'cam_rotate': 'grep -ri "rotate\\|flip\\|mirror\\|transpose" /etc/go2rtc/ /root/printer_data/config/ 2>/dev/null || echo NO_ROTATE_SETTING',
        # 7. 后端.env中的SCREEN_CROP
        'screen_crop': 'grep -i "screen_crop\\|camera\\|rotate\\|flip" /root/phone-test/backend/.env 2>/dev/null; find / -maxdepth 4 -name ".env" 2>/dev/null | xargs grep -i "screen_crop\\|camera\\|rotate" 2>/dev/null | head -5; echo DONE',
        # 8. 实际测试: 归位后移动到X=30 Y=75，读实际位置
        'test_move': 'curl -s -X POST "http://localhost:7125/printer/gcode/script" -d \'{"script":"G28 X Y\\nG0 X30 Y75 F3000"}\' -H "Content-Type: application/json" 2>&1',
        # 9. stepper方向和rotation_distance
        'stepper': 'grep -A5 "stepper_x\\|stepper_y" /root/printer_data/config/printer.cfg | grep -E "dir_pin|rotation_distance|position_endstop|position_max"',
        # 10. 检查是否有[homing_override]等覆盖
        'homing_override': 'grep -A10 "homing_override\\|safe_z_home\\|homing_only" /root/printer_data/config/printer.cfg 2>&1 || echo NO_OVERRIDE',
        # 11. 检查摄像头图像 - 抓一帧看实际方向
        'cam_img': 'curl -s http://localhost:1984/api/camera0 2>&1 | head -c 100; echo',
        # 12. 检查后端config.py中的camera相关
        'backend_cfg': 'find / -maxdepth 5 -name "config.py" -path "*/phone*" 2>/dev/null | xargs grep -i "camera\\|rotate\\|flip\\|crop" 2>/dev/null | head -10; echo DONE',
    }
    
    for key, cmd in cmds.items():
        out = ssh_run(ip, cmd)
        print(f"\n--- {key} ---")
        print(out[:400])