#!/usr/bin/env python3
"""
N1 盒子一键配置脚本
用法: python3 setup_n1.py
"""
import paramiko, sys, time

HOST, USER, PASS, PORT = "192.168.5.101", "root", "1234", 22

# go2rtc 配置内容
GO2RTC_YAML = """api:
  listen: ":1984"

streams:
  camera0:
    - exec:ffmpeg -f v4l2 -input_format mjpeg -video_size 1280x720 -i /dev/video1 -frames:v 1 -f image2pipe -vcodec mjpeg -
"""

def wait_online(timeout=60):
    import socket
    print(f"等待 N1 ({HOST}) 上线...", end="", flush=True)
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            s = socket.create_connection((HOST, PORT), timeout=2)
            s.close()
            print(" ✅")
            return True
        except OSError:
            print(".", end="", flush=True)
            time.sleep(2)
    print(" ❌ 超时")
    return False

def run(ssh, cmd, timeout=30):
    _, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    return out, err

def main():
    if not wait_online():
        sys.exit(1)

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, port=PORT, username=USER, password=PASS, timeout=10)
    print("✅ SSH 连接成功\n")

    # ── 1. 检查服务状态 ──
    print("=== 服务状态 ===")
    out, _ = run(ssh, "systemctl is-active go2rtc moonraker klipper 2>&1")
    print(out)

    # ── 2. 开放防火墙 ──
    print("\n=== 开放防火墙端口 ===")
    cmds = [
        "ufw allow 22/tcp",
        "ufw allow 1984/tcp",
        "ufw allow 7125/tcp",
        "ufw --force enable",
        "ufw reload",
    ]
    for cmd in cmds:
        out, err = run(ssh, cmd)
        status = out or err
        print(f"  {cmd[:40]:<40} → {status[:50] if status else 'ok'}")

    # ── 3. 写入 go2rtc 配置 ──
    print("\n=== 写入 go2rtc 配置 ===")
    run(ssh, "mkdir -p /etc/go2rtc")
    sftp = ssh.open_sftp()
    with sftp.open("/etc/go2rtc/go2rtc.yaml", "w") as f:
        f.write(GO2RTC_YAML)
    sftp.close()
    print("  /etc/go2rtc/go2rtc.yaml 写入完成")

    # ── 4. 确认 go2rtc 二进制存在 ──
    out, _ = run(ssh, "which go2rtc || ls /usr/local/bin/go2rtc 2>/dev/null || echo MISSING")
    if "MISSING" in out:
        print("\n  go2rtc 未安装，正在下载...")
        dl_cmd = (
            "curl -fsSL https://github.com/AlexxIT/go2rtc/releases/latest/download/go2rtc_linux_arm64"
            " -o /usr/local/bin/go2rtc && chmod +x /usr/local/bin/go2rtc && echo DONE"
        )
        out, err = run(ssh, dl_cmd, timeout=120)
        print(f"  {out or err}")
    else:
        print(f"  go2rtc 已存在: {out}")

    # ── 5. 创建/更新 systemd 服务 ──
    print("\n=== 配置 systemd 服务 ===")
    service_unit = """[Unit]
Description=go2rtc camera service
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/go2rtc -config /etc/go2rtc/go2rtc.yaml
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
"""
    sftp = ssh.open_sftp()
    with sftp.open("/etc/systemd/system/go2rtc.service", "w") as f:
        f.write(service_unit)
    sftp.close()

    for cmd in [
        "systemctl daemon-reload",
        "systemctl enable go2rtc",
        "systemctl restart go2rtc",
        "systemctl enable moonraker",
        "systemctl restart moonraker",
    ]:
        out, err = run(ssh, cmd)
        print(f"  {cmd:<40} → {(out or err or 'ok')[:50]}")

    # ── 6. 等待服务启动再验证 ──
    print("\n=== 等待服务启动 (5s) ===")
    time.sleep(5)

    out, _ = run(ssh, "systemctl is-active go2rtc moonraker")
    print(f"服务状态:\n{out}")

    # ── 7. 本机测试截图 ──
    print("\n=== 测试截图 ===")
    out, err = run(ssh, 
        'curl -s -o /tmp/test_frame.jpg --max-time 15 '
        '"http://localhost:1984/api/frame.jpeg?src=camera0" '
        '&& file /tmp/test_frame.jpg || echo "FAIL"',
        timeout=20
    )
    print(f"  {out or err}")

    # ── 8. 测试 Moonraker ──
    print("\n=== 测试 Moonraker ===")
    out, err = run(ssh,
        'curl -s --max-time 5 "http://localhost:7125/server/info" | python3 -c '
        '"import sys,json; d=json.load(sys.stdin); '
        'print(\'klippy:\', d[\'result\'][\'klippy_connected\'])" 2>/dev/null || echo "moonraker未响应"'
    )
    print(f"  {out or err}")

    ssh.close()
    print("\n✅ N1 配置完成！")
    print(f"   截图接口: http://{HOST}:1984/api/frame.jpeg?src=camera0")
    print(f"   Moonraker: http://{HOST}:7125/server/info")

if __name__ == "__main__":
    main()
