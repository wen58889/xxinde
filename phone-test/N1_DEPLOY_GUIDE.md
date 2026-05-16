# N1 设备部署方案 — 稳定性第一

## 问题根因

**102的G28必然触发MCU Shutdown**，根因是 Klipper 版本不一致：

| 设备 | Klipper | 日期 | G28 |
|------|---------|------|-----|
| 101 (稳定) | `35ace5297` | 2026-01-25 | 正常 |
| 102 (异常) | `4767a8e` | 2026-05-03 | 必崩 |

**102使用的是main分支最新代码（包含未发布改动）**，`n1_deploy.sh`中 `git clone --depth 1` 拉取的就是最新main，没有任何版本锁定。

## 最稳定版本（黄金版本）

| 组件 | Commit | 日期 | 来源 |
|------|--------|------|------|
| **Klipper** | `35ace5297` | 2026-01-25 | 101设备验证通过 |
| **Moonraker** | `1ed102e` | - | 101设备验证通过 |

> 这两个版本在101设备上经过长期验证，G28、移动、截图全部稳定。

## 三种部署方案（推荐度从高到低）

### 方案1：黄金镜像打包部署（最推荐 ★★★★★）

**原理：** 从已验证的101设备打包所有文件，新设备直接解压，版本100%一致。

```bash
# 1. 在101上打包（只需做一次）
ssh root@192.168.5.101 'bash -s' < n1_golden_pack.sh
# 输出: /root/n1_golden_image.tar.gz

# 2. 传到新设备
scp root@192.168.5.101:/root/n1_golden_image.tar.gz root@192.168.5.103:/root/

# 3. 在新设备上部署
ssh root@192.168.5.103
chmod +x n1_golden_deploy.sh && ./n1_golden_deploy.sh
```

**优点：**
- 版本100%一致（Klipper/Moonraker/python依赖/固件/配置全部打包）
- 不依赖外网git（N1设备无外网HTTP）
- 部署速度快（解压 vs git clone + pip install）
- 包含预编译RP2040固件，新设备直接刷写

**缺点：**
- 打包文件较大（约200-500MB，含python venv）
- 不同架构设备不能互用

### 方案2：版本锁定的n1_deploy.sh（推荐 ★★★★）

**原理：** n1_deploy.sh中锁定Klipper/Moonraker的commit hash。

```bash
# n1_deploy.sh 中已修复：
KLIPPER_COMMIT="35ace5297"    # 锁定!
MOONRAKER_COMMIT="1ed102e"    # 锁定!

# 部署流程不变
./n1_network.sh && reboot
./n1_deploy.sh
```

**优点：**
- 版本锁定，不会因为git main更新而不稳定
- 已有设备也能通过重新运行脚本修正版本
- 部署脚本已有完整逻辑

**缺点：**
- 仍需外网git（N1设备可能无外网）
- pip install依赖需编译，耗时长
- 固件需重新编译

### 方案3：离线deb包（备选 ★★★）

预打包所有依赖为deb文件，完全离线部署。适合无外网环境，但维护成本较高。

## 修复102的步骤

102需要重刷Klipper固件到与101一致版本：

```bash
ssh root@192.168.5.102  # 密码: 1234

# 方案A: 用黄金镜像
cd / && tar xzf /root/n1_golden_image.tar.gz
# 修改serial
vi /root/printer_data/config/printer.cfg  # 改serial
# 重启
systemctl daemon-reload && systemctl restart klipper moonraker

# 方案B: 重新运行n1_deploy.sh（现在已锁定版本）
./n1_deploy.sh  # 会自动checkout到35ace5297
```

## 批量22台设备部署流程

```bash
# 1. 从101打包一次
ssh root@192.168.5.101 'bash -s' < n1_golden_pack.sh

# 2. 批量部署
for ip in 192.168.5.{101..122}; do
    echo "=== 部署 $ip ==="
    # Phase 1: 网络（只需首次）
    scp n1_network.sh root@$ip:/root/ && ssh root@$ip 'bash /root/n1_network.sh'
    # 等待重启
    sleep 60
    # Phase 2: 黄金镜像
    scp n1_golden_image.tar.gz root@$ip:/root/
    scp n1_golden_deploy.sh root@$ip:/root/
    ssh root@$ip 'bash /root/n1_golden_deploy.sh'
done
```

## 版本管理规范

1. **所有N1设备必须使用同一Klipper/Moonraker版本**
2. **n1_deploy.sh中的KLIPPER_COMMIT/MOONRAKER_COMMIT是唯一版本源**
3. **升级版本前必须在101设备验证G28稳定性**
4. **每次验证通过后更新n1_deploy.sh中的commit hash并重新打包黄金镜像**
