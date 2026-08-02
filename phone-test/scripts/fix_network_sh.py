with open(r'D:\Users\59520\IDEProjects\xxinde\phone-test\n1_network.sh', 'r', encoding='utf-8') as f:
    content = f.read()

old = """# L7: NM dispatcher 有线事件加固
cat > /etc/NetworkManager/dispatcher.d/99-wired-stability.sh << WDISP
#!/bin/bash
IFACE="\\$1"
ACTION="\\$2"
if [ "\\$IFACE" = "$SELECTED_IFACE" ] && [ "\\$ACTION" = "down" ]; then
    logger -t wired-stability "有线接口\\$IFACE断开, 3s后重连"
    sleep 3
    CON=\\$(nmcli -t -f NAME,DEVICE con show 2>/dev/null | grep "\\$IFACE" | head -1 | cut -d: -f1)
    [ -n "\\$CON" ] && nmcli con up "\\$CON" 2>/dev/null || true
fi
WDISP
chmod +x /etc/NetworkManager/dispatcher.d/99-wired-stability.sh 2>/dev/null || true
log_info "  L7: 有线dispatcher (断线自动重连)" """

new = """# L7: NM dispatcher 有线重连 (已移除: 和link-monitor.sh冲突, 会造成链路抖动循环)
# link-monitor.sh已包含断线自动重连逻辑，无需NM dispatcher重复
rm -f /etc/NetworkManager/dispatcher.d/99-wired-stability.sh 2>/dev/null || true
log_info "  L7: 有线重连由link-monitor.sh负责 (已移除NM dispatcher避免冲突)" """

if old in content:
    content = content.replace(old, new)
    with open(r'D:\Users\59520\IDEProjects\xxinde\phone-test\n1_network.sh', 'w', encoding='utf-8') as f:
        f.write(content)
    print("替换成功")
else:
    print("未找到匹配文本")
    # 尝试找到L7的行号
    for i, line in enumerate(content.split('\n'), 1):
        if 'L7' in line and 'dispatcher' in line:
            print(f"  行{i}: {line}")