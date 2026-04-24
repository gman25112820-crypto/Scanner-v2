with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix page title
content = content.replace(
    'page_title="Scanner v2 - V4"',
    'page_title="RAGE Engine"'
)

# Fix sidebar logo HTML
old_logo = 'SCANNER <span style="color:#00e5ff">V4</span>'
new_logo = '''RAGE <span style="background: linear-gradient(90deg, #ff4500, #ff8c00); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">ENGINE</span>'''
content = content.replace(old_logo, new_logo)

# Fix Scanner v2 subtitle
content = content.replace('Scanner v2', 'RAGE Engine')
content = content.replace('Scanner V2', 'RAGE Engine')

# Fix Platform Vision subheader
content = content.replace(
    'Scanner v2 - Platform Vision',
    'RAGE Engine - Platform Vision'
)

print('page_title remaining:', content.count('Scanner v2 - V4'))
print('Logo remaining:', content.count('SCANNER'))

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Saved.')