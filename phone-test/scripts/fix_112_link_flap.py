import paramiko
import time
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=10, allow_agent=False, look_for_keys=False)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=15)
    return stdout.read().decode('utf-8', errors='replace').strip()

# 1. 修复 /etc/n1-fixed-iface (wlan0 -> eth0)
print("=== 1. 修复 /etc/n1-fixed-iface ===")
print(f"修复前: {run('cat /etc/n1-fixed-iface 2>/dev/null')}")
run("echo eth0 > /etc/n1-fixed-iface")
print(f"修复后: {run('cat /etc/n1-fixed-iface 2>/dev/null')}")

# 2. 创建 /etc/n1_network_info.txt
print("\n=== 2. 创建 /etc/n1_network_info.txt ===")
run("cat > /etc/n1_network_info.txt << 'EOF'\nN1_IP=192.168.5.112\nSERVER_IP=192.168.5.8\nEOF")
print(run("cat /etc/n1_network_info.txt"))

# 3. 修复 link-monitor.sh - 移除while循环中的local关键字
print("\n=== 3. 修复 link-monitor.sh (移除while中的local) ===")
# 查看当前link-monitor.sh中的问题行
out = run("cat /usr/local/bin/link-monitor.sh")
# 修复: 将while循环中的local替换为普通变量赋值
fixed = out.replace("local link_status=", "link_status=")
fixed = fixed.replace("local now=", "now=")
fixed = fixed.replace("local downtime=", "downtime=")
fixed = fixed.replace("local rx_delta=", "rx_delta=")
fixed = fixed.replace("local tx_delta=", "tx_delta=")
fixed = fixed.replace("local rd_delta=", "rd_delta=")
fixed = fixed.replace("local td_delta=", "td_delta=")
fixed = fixed.replace("local total_delta=", "total_delta=")

sftp = ssh.open_sftp()
with sftp.file("/usr/local/bin/link-monitor.sh", 'w') as f:
    f.write(fixed)
sftp.close()
run("chmod +x /usr/local/bin/link-monitor.sh")
print("link-monitor.sh已修复 (移除while中的local)")

# 4. 移除99-wired-stability.sh (和link-monitor冲突，造成反复重连)
print("\n=== 4. 移除99-wired-stability.sh (和link-monitor冲突) ===")
run("rm -f /etc/NetworkManager/dispatcher.d/99-wired-stability.sh")
print("已移除")

# 5. 重启link-monitor
print("\n=== 5. 重启link-monitor ===")
run("systemctl restart link-monitor")
time.sleep(3)
print(f"link-monitor状态: {run('systemctl is-active link-monitor')}")

# 6. 验证
print("\n=== 6. 验证 ===")
time.sleep(5)
print(f"klippy: {run('curl -s http://localhost:7125/server/info 2>/dev/null | grep -oP \'\"klippy_state\":\"\\K[^\"]+\' || echo ERR')}")
print(f"eth0 speed: {run('ethtool eth0 2>/dev/null | grep Speed')}")
print(f"n1-fixed-iface: {run('cat /etc/n1-fixed-iface')}")

ssh.close()