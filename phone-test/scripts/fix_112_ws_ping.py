import paramiko
import time
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.5.112', username='root', password='1234', timeout=10, allow_agent=False, look_for_keys=False)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=15)
    out = stdout.read().decode('utf-8', errors='replace').strip()
    err = stderr.read().decode('utf-8', errors='replace').strip()
    return out, err

# 1. 移除moonraker.conf中无效的配置
print("=== 1. 修复moonraker.conf ===")
out, err = run("sed -i '/^websocket_ping_interval:/d; /^websocket_ping_timeout:/d' ~/printer_data/config/moonraker.conf")
print("移除无效配置行")

# 2. 修改application.py源码：将ping_interval从10改为30
print("\n=== 2. 修改application.py源码 ===")
out, err = run("cp ~/moonraker/moonraker/components/application.py ~/moonraker/moonraker/components/application.py.bak")
print("备份完成")

# 替换 ping_interval 默认值
out, err = run("""sed -i "s/'websocket_ping_interval': None if tornado_ver < (6, 5) else 10\\./'websocket_ping_interval': None if tornado_ver < (6, 5) else 30./" ~/moonraker/moonraker/components/application.py""")
print(f"sed结果: out={out} err={err}")

# 验证修改
out, err = run("grep 'websocket_ping_interval' ~/moonraker/moonraker/components/application.py")
print(f"验证: {out}")

# 3. 重启moonraker
print("\n=== 3. 重启moonraker ===")
out, err = run("systemctl restart moonraker")
time.sleep(8)
out, err = run("systemctl is-active moonraker")
print(f"moonraker状态: {out}")

# 4. 验证
print("\n=== 4. 验证 ===")
time.sleep(5)
out, err = run("curl -s http://localhost:7125/server/info 2>/dev/null")
if '"klippy_state":"ready"' in out:
    print("klippy_state: ready")
else:
    print(f"状态异常: {out[:200]}")

# 检查warnings中是否还有unparsed config
if 'Unparsed' in out:
    print("WARNING: 仍有Unparsed配置")
else:
    print("无Unparsed配置警告")

# 5. 验证moonraker.conf
print("\n=== 5. moonraker.conf ===")
out, err = run("cat ~/printer_data/config/moonraker.conf")
print(out)

ssh.close()