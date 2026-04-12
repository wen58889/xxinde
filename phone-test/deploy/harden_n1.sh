#!/bin/bash
# N1 节点安全加固脚本
set -euo pipefail

echo "===== N1 安全加固 ====="

# 禁用密码登录，仅SSH密钥
if ! grep -q "^PasswordAuthentication no" /etc/ssh/sshd_config; then
  sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
  systemctl restart sshd
fi

# 防火墙 - 只开放必要端口
apt-get install -y ufw
ufw default deny incoming
ufw default allow outgoing
ufw allow from 192.168.1.0/24 to any port 22    # SSH
ufw allow from 192.168.1.0/24 to any port 7125  # Moonraker
ufw allow from 192.168.1.0/24 to any port 1984  # go2rtc
ufw --force enable

# 禁用不必要的服务
systemctl disable --now bluetooth 2>/dev/null || true
systemctl disable --now cups 2>/dev/null || true
systemctl disable --now avahi-daemon 2>/dev/null || true

# 内核参数加固
cat > /etc/sysctl.d/99-hardening.conf << 'SYSCTL'
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.default.rp_filter = 1
net.ipv4.icmp_echo_ignore_broadcasts = 1
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.default.accept_redirects = 0
kernel.randomize_va_space = 2
SYSCTL
sysctl -p /etc/sysctl.d/99-hardening.conf

# 限制 Moonraker/go2rtc 仅监听局域网
echo "===== 加固完成 ====="
