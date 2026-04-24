import pandas as pd
import glob
import os

results = []
for f in glob.glob('output\\backtest\\*\\metrics.csv'):
    try:
        # Get folder name e.g. "adx_trend_AAPL"
        folder = os.path.basename(os.path.dirname(f))
        
        df = pd.read_csv(f, header=None, names=['metric','value'])
        row = {'strategy':'unknown','symbol':'unknown','folder':folder}
        for _, r in df.iterrows():
            row[str(r['metric']).strip()] = r['value']
        
        for strat in ['adx_trend','macd_rsi','mean_reversion','orb','breakout']:
            if folder.startswith(strat):
                row['strategy'] = strat
                row['symbol'] = folder[len(strat)+1:]
                break
        results.append(row)
    except Exception as e:
        print(f'Error: {f} — {e}')

all_df = pd.DataFrame(results)
all_df = all_df.sort_values(['strategy','symbol'])
pd.set_option('display.max_rows', 999)
pd.set_option('display.width', 200)
pd.set_option('display.float_format', '{:.4f}'.format)
print(f'Total: {len(all_df)} results\n')
print(all_df.to_string(index=False))
all_df.to_csv('output/all_backtest_results.csv', index=False)
print('\nSaved to output/all_backtest_results.csv')