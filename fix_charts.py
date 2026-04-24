with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix nav - remove duplicate Charts entries
import re
# Fix the nav list to have only one Charts
content = re.sub(
    r'("Markets",\s*"Charts",?\s*)+("Charts",?\s*)*',
    '"Markets", "Charts", ',
    content
)

# Verify Charts handler exists
if content.count('elif page == "Charts"') > 1:
    # Remove duplicates keeping first
    first = content.find('elif page == "Charts"')
    second = content.find('elif page == "Charts"', first+1)
    while second > 0:
        # Find end of this duplicate block
        next_elif = content.find('\n    elif page ==', second+1)
        if next_elif > 0:
            content = content[:second] + content[next_elif+1:]
        second = content.find('elif page == "Charts"', first+1)

print(f'Charts in nav: {content.count("Charts")}')
print(f'Charts handlers: {content.count("elif page == \\"Charts\\"")}')

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed.')