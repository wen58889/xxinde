import paramiko

def ssh_run(host, cmd):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username='root', password='1234', timeout=10)
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=10)
    out = stdout.read().decode('utf-8', errors='replace')
    ssh.close()
    return out

# 获取完整printer.cfg
cfg101 = ssh_run('192.168.5.101', 'cat /root/printer_data/config/printer.cfg')
cfg106 = ssh_run('192.168.5.106', 'cat /root/printer_data/config/printer.cfg')

# 保存到临时文件做diff
with open('D:/Users/59520/IDEProjects/xxinde/phone-test/scripts/cfg101.txt', 'w') as f:
    f.write(cfg101)
with open('D:/Users/59520/IDEProjects/xxinde/phone-test/scripts/cfg106.txt', 'w') as f:
    f.write(cfg106)

print(f"101 cfg: {len(cfg101)} bytes")
print(f"106 cfg: {len(cfg106)} bytes")

# go2rtc配置
go2rtc101 = ssh_run('192.168.5.101', 'cat /etc/go2rtc/go2rtc.yaml')
go2rtc106 = ssh_run('192.168.5.106', 'cat /etc/go2rtc/go2rtc.yaml')

print(f"\n=== 101 go2rtc ===")
print(go2rtc101)
print(f"\n=== 106 go2rtc ===")
print(go2rtc106)

# 测试实际移动: G0 X30 Y75 (中心点)
print("\n=== 测试移动到中心点(30,75) ===")
# 101
out = ssh_run('192.168.5.101', 'curl -s -X POST http://localhost:7125/printer/gcode/script -d \'{"script":"G0 X30 Y75 F3000"}\' -H "Content-Type: application/json" 2>&1')
print(f"101 移动结果: {out}")

# 106
out = ssh_run('192.168.5.106', 'curl -s -X POST http://localhost:7125/printer/gcode/script -d \'{"script":"G0 X30 Y75 F3000"}\' -H "Content-Type: application/json" 2>&1')
print(f"106 移动结果: {out}")