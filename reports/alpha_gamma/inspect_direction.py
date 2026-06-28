import pandas as pd
import numpy as np
from pathlib import Path

# Read alpha signals
signals = pd.read_csv(Path('reports/alpha_gamma/alpha_funding_switch_signals.csv') if Path('reports/alpha_gamma/alpha_funding_switch_signals.csv').exists() else Path('reports/alpha_gamma/alpha_funding_switch_trades.csv'))

# Actually signals aren't saved; let's re-run quickly to inspect
print('Need to inspect signal direction vs subsequent price move')
