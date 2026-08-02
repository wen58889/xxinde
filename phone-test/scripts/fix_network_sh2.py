with open(r'D:\Users\59520\IDEProjects\xxinde\phone-test\n1_network.sh', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 替换行713-726 (0-indexed: 712-725)
new_lines = lines[:712]
new_lines.append('# L7: NM dispatcher 有线重连 (已移除: 和link-monitor.sh冲突, 会造成链路抖动循环)\n')
new_lines.append('# link-monitor.sh已包含断线自动重连逻辑，无需NM dispatcher重复\n')
new_lines.append('rm -f /etc/NetworkManager/dispatcher.d/99-wired-stability.sh 2>/dev/null || true\n')
new_lines.append('log_info "  L7: 有线重连由link-monitor.sh负责 (已移除NM dispatcher避免冲突)"\n')
new_lines.extend(lines[726:])

with open(r'D:\Users\59520\IDEProjects\xxinde\phone-test\n1_network.sh', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
print("替换成功")