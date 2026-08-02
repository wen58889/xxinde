import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.106', username='root', password='1234', timeout=10)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=10)
    return stdout.read().decode('utf-8', errors='replace')

# 先归位
print("=== 归位 ===")
out = run('curl -s -X POST "http://localhost:7125/printer/gcode/script" -d \'{"script":"G28 X Y"}\' -H "Content-Type: application/json" 2>&1')
print(out)

import time
time.sleep(8)

# 移动到4个标定点位置并读取实际坐标
test_points = [
    ("TL", "G0 X62.994 Y7.994 F3000"),
    ("TR", "G0 X1.994 Y7.994 F3000"),
    ("BL", "G0 X62.994 Y149.994 F3000"),
    ("BR", "G0 X1.994 Y149.994 F3000"),
    ("Center", "G0 X32 Y75 F3000"),
]

for label, gcode in test_points:
    out = run(f'curl -s -X POST "http://localhost:7125/printer/gcode/script" -d \'{{"script":"{gcode}"}}\' -H "Content-Type: application/json" 2>&1')
    print(f"\n{label}: {gcode} -> {out}")
    time.sleep(2)

ssh.close()

# 同样在101上测试
print("\n\n=== 101 对比 ===")
ssh2 = paramiko.SSHClient()
ssh2.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh2.connect('192.168.5.101', username='root', password='1234', timeout=10)

def run2(cmd):
    stdin, stdout, stderr = ssh2.exec_command(cmd, timeout=10)
    return stdout.read().decode('utf-8', errors='replace')

# 归位
out = run2('curl -s -X POST "http://localhost:7125/printer/gcode/script" -d \'{"script":"G28 X Y"}\' -H "Content-Type: application/json" 2>&1')
print(f"归位: {out}")
time.sleep(8)

for label, gcode in test_points:
    out = run2(f'curl -s -X POST "http://localhost:7125/printer/gcode/script" -d \'{{"script":"{gcode}"}}\' -H "Content-Type: application/json" 2>&1')
    print(f"\n{label}: {gcode} -> {out}")
    time.sleep(2)

ssh2.close()