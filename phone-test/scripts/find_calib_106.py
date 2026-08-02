import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.106', username='root', password='1234', timeout=10)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=10)
    return stdout.read().decode('utf-8', errors='replace')

cmds = [
    # 搜索标定相关文件
    'find / -maxdepth 5 -name "*calib*" -o -name "*affine*" -o -name "*transform*" -o -name "*mapping*" 2>/dev/null | grep -v proc | grep -v sys | head -20',
    # 搜索phone-test项目目录
    'find / -maxdepth 4 -name "phone-test" -type d 2>/dev/null | head -5',
    'find / -maxdepth 4 -name "config" -type d 2>/dev/null | grep -i "phone\\|test\\|n1" | head -10',
    # 搜索yaml/json/npz/npy/pkl等标定数据文件
    'find / -maxdepth 5 \\( -name "*.npz" -o -name "*.npy" -o -name "*.pkl" -o -name "*.calib" \\) 2>/dev/null | grep -v proc | head -20',
    # 搜索printer_data配置
    'ls -la /root/printer_data/config/ 2>&1',
    'cat /root/printer_data/config/printer.cfg 2>&1 | grep -i "calib\\|affine\\|transform\\|mapping\\|pixel\\|camera" | head -20',
    # 搜索phone-test后端配置
    'find / -maxdepth 5 -name "config.py" -o -name "config.yaml" -o -name "config.json" 2>/dev/null | grep -v proc | grep -v sys | head -10',
    # 搜索包含affine/transform关键词的配置文件
    'grep -rl "affine\\|transform\\|calibration\\|pixel_to_mm\\|camera_to_arm" /root/ --include="*.py" --include="*.yaml" --include="*.json" --include="*.cfg" 2>/dev/null | head -20',
    # 检查phone-test项目
    'ls -la /root/phone-test/ 2>&1 || ls -la /opt/phone-test/ 2>&1 || echo NO_PHONE_TEST',
    'find / -maxdepth 3 -name "*.py" -path "*/phone*test*" 2>/dev/null | head -10',
]

for cmd in cmds:
    print(f'=== {cmd} ===')
    out = run(cmd)
    print(out)
    print()

ssh.close()