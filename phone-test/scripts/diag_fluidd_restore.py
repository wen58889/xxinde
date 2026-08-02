import paramiko
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.105', username='root', password='1234', timeout=10)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=15)
    return stdout.read().decode('utf-8', errors='replace'), stderr.read().decode('utf-8', errors='replace')

# Step 1: 恢复原始moonraker.conf
print("=== Step 1: 恢复原始moonraker.conf ===")
out, _ = run("cp /root/printer_data/config/moonraker.conf.bak /root/printer_data/config/moonraker.conf")
print(f"恢复完成")

# Step 2: 重启moonraker
print("\n=== Step 2: 重启moonraker ===")
run("systemctl restart moonraker")
time.sleep(8)

out, _ = run("systemctl status moonraker --no-pager -l 2>&1 | head -10")
print(out)

# Step 3: 检查8080端口上是什么进程
print("\n=== Step 3: 检查8080端口 ===")
out, _ = run("ps aux | grep 1630 2>&1")
print(out)

out, _ = run("ss -tlnp | grep 8080 2>&1")
print(out)

out, _ = run("curl -s -o /dev/null -w 'http_code=%{http_code} content_type=%{content_type}' http://localhost:8080/ 2>&1")
print(f"8080端口: {out}")

out, _ = run("curl -s http://localhost:8080/ 2>&1 | head -10")
print(f"8080首页:\n{out}")

# Step 4: 检查所有可能提供Fluidd的端口
print("\n=== Step 4: 检查各端口 ===")
for port in [80, 4408, 7125, 8080]:
    out, _ = run(f"curl -s -o /dev/null -w '%{{http_code}}' http://localhost:{port}/ 2>&1")
    print(f"  端口{port}: HTTP {out}")

# Step 5: 检查是否有nginx/apache或其他web服务器
print("\n=== Step 5: 检查web服务器 ===")
out, _ = run("systemctl list-units --type=service --state=running 2>&1 | grep -iE 'nginx|apache|httpd|caddy|lighttpd|fluidd|mainsail'")
print(f"运行中的web服务: {out if out.strip() else '无'}")

# Step 6: 检查所有python进程
print("\n=== Step 6: 所有python进程 ===")
out, _ = run("ps aux | grep python 2>&1")
print(out)

# Step 7: 检查systemd服务列表
print("\n=== Step 7: 所有自定义systemd服务 ===")
out, _ = run("systemctl list-units --type=service --state=running 2>&1 | grep -vE 'systemd|dbus|ssh|cron|rsyslog|network|resolved|rpc|serial|getty|login|user|polkit|udev|fwupd|unattended|packagekit|ModemManager|accounts|wpa'")
print(out)

# Step 8: 检查7125端口是否现在提供Fluidd
print("\n=== Step 8: 7125端口Fluidd ===")
out, _ = run("curl -s http://localhost:7125/ 2>&1 | head -5")
print(f"7125首页:\n{out}")

# Step 9: 检查101设备的Fluidd配置作为参考
print("\n=== Step 9: 尝试连接101看配置 ===")

ssh.close()

# 连接101
try:
    ssh2 = paramiko.SSHClient()
    ssh2.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh2.connect('192.168.5.101', username='root', password='1234', timeout=10)
    
    cmds = [
        'cat /root/printer_data/config/moonraker.conf 2>&1 || cat /home/pi/printer_data/config/moonraker.conf 2>&1',
        'ss -tlnp 2>&1 | grep -E "80|4408|7125|8080"',
        'curl -s -o /dev/null -w "%{http_code}" http://localhost:7125/ 2>&1',
        'curl -s http://localhost:7125/ 2>&1 | head -5',
        'curl -s -o /dev/null -w "%{http_code}" http://localhost:80/ 2>&1',
        'systemctl list-units --type=service --state=running 2>&1 | grep -iE "nginx|apache|httpd|caddy|lighttpd|fluidd|mainsail"',
    ]
    
    for cmd in cmds:
        print(f'=== 101: {cmd} ===')
        stdin, stdout, stderr = ssh2.exec_command(cmd, timeout=15)
        out = stdout.read().decode('utf-8', errors='replace')
        print(out)
        print()
    
    ssh2.close()
except Exception as e:
    print(f"101连接失败: {e}")