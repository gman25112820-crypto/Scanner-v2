with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find Reports page handler
idx = content.find('"Reports"')
while idx > 0:
    snippet = content[idx-20:idx+30]
    if 'elif' in snippet or 'if page' in snippet:
        print(f'At {idx}: {repr(snippet)}')
    idx = content.find('"Reports"', idx+1)