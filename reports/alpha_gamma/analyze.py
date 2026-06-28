import pandas as pd
from pathlib import Path

for name in ['alpha_funding_switch', 'gamma_settlement_compression']:
    df = pd.read_csv(Path('reports/alpha_gamma') / f'{name}_trades.csv')
    print(f'=== {name} ===')
    print(f'n_trades: {len(df)}')
    print(df['exit_reason'].value_counts())
    wins = (df['pnl_R'] > 0).sum()
    print(f'win_rate: {wins/len(df):.3f}')
    print(f'ev_R: {df["pnl_R"].mean():.3f}')
    if len(df) > 0:
        sum_wins = df[df['pnl_R'] > 0]['pnl_R'].sum()
        sum_losses = abs(df[df['pnl_R'] <= 0]['pnl_R'].sum())
        pf = sum_wins / sum_losses if sum_losses > 0 else float('inf')
        print(f'profit_factor: {pf:.3f}')
    print()
