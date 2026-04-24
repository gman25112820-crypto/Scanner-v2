import os
import glob
import re

print("=== STRATEGIES IN APP.PY ===")
with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()
strategies = re.findall(r'adx_trend|macd_rsi|mean_reversion|orb|breakout|double_breakout|momentum|rsi_|ema_cross', content)
unique = sorted(set(strategies))
for s in unique:
    print(f'  - {s}')

print("\n=== OUTPUT FILES ===")
for root, dirs, files in os.walk('output'):
    for file in files:
        if file.endswith('.csv') or file.endswith('.json'):
            print(f'  {os.path.join(root, file)}')

print("\n=== MAIN.PY STRATEGIES ===")
if os.path.exists('main.py'):
    with open('main.py', 'r', encoding='utf-8') as f:
        mc = f.read()
    strats = re.findall(r'adx_trend|macd_rsi|mean_reversion|orb|breakout|double_breakout|momentum', mc)
    for s in sorted(set(strats)):
        print(f'  - {s}')