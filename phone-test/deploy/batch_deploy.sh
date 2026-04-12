#!/bin/bash
# 批量部署脚本 - 对所有N1节点执行安装和加固
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SSH_KEY="${SSH_KEY:-~/.ssh/id_rsa}"
SSH_USER="${SSH_USER:-root}"
START_IP="${START_IP:-101}"
END_IP="${END_IP:-122}"
SUBNET="${SUBNET:-192.168.1}"

echo "===== 批量部署 N1 节点 ====="
echo "范围: ${SUBNET}.${START_IP} - ${SUBNET}.${END_IP}"

for i in $(seq "$START_IP" "$END_IP"); do
  IP="${SUBNET}.${i}"
  echo ""
  echo ">>> 部署节点: ${IP}"

  # 检查是否可达
  if ! ping -c 1 -W 2 "$IP" > /dev/null 2>&1; then
    echo "    [跳过] ${IP} 不可达"
    continue
  fi

  # 上传脚本
  scp -i "$SSH_KEY" -o StrictHostKeyChecking=no \
    "${SCRIPT_DIR}/install_n1.sh" \
    "${SCRIPT_DIR}/harden_n1.sh" \
    "${SCRIPT_DIR}/go2rtc.yaml" \
    "${SSH_USER}@${IP}:~/" 2>/dev/null || {
    echo "    [失败] SCP 上传失败"
    continue
  }

  # 执行安装
  ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "${SSH_USER}@${IP}" \
    "cp ~/go2rtc.yaml /etc/go2rtc/go2rtc.yaml && bash ~/install_n1.sh && bash ~/harden_n1.sh" 2>/dev/null || {
    echo "    [失败] 远程执行失败"
    continue
  }

  echo "    [完成] ${IP} 部署成功"
done

echo ""
echo "===== 批量部署完成 ====="
