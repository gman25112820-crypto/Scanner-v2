with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()
for i, line in enumerate(lines):
    if 'Reports' in line and ('elif' in line or 'if page' in line):
        print(f'{i+1}: {repr(line)}')