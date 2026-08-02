with open(r'D:\Users\59520\IDEProjects\xxinde\phone-test\n1_network.sh', 'r', encoding='utf-8') as f:
    lines = f.readlines()
for i, line in enumerate(lines[712:726], start=713):
    print(f'{i}: {repr(line)}')