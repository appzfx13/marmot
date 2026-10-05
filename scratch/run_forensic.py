
import json
import math
from datetime import datetime

trades_file = '/app/go-app/data/users/1/backtests/backtest_1.json'
trades = []
with open(trades_file, 'r') as f:
    for line in f:
        if line.strip():
            trades.append(json.loads(line.strip()))

total = len(trades)
audit_results = []
anomalies = []

# Engine ROE rules for EMA 9/21 Retest + MACD Momentum:
# EMAFast: 9, EMASlow: 21, RR: 2.0, SLPts: 15.0
# EntryWindow: 09:20 (560m) - 14:45 (885m)
# Cooldown: 300s
# TrailBreakeven: true, BreakevenAtR: 1.2 (18 pts profit)
# TSL2: At 1.6R (24 pts profit), Lock 0.8R (12 pts profit)

prev_entry_dt = None

for idx, t in enumerate(trades, 1):
    ts_str = t.get('timestamp') or t.get('entry_time') or ''
    exit_ts_str = t.get('exit_timestamp') or t.get('exit_time') or ''
    entry_dt = datetime.strptime(ts_str.replace('T', ' ')[:19], '%Y-%m-%d %H:%M:%S')
    exit_dt = datetime.strptime(exit_ts_str.replace('T', ' ')[:19], '%Y-%m-%d %H:%M:%S') if exit_ts_str else None
    
    mins_from_midnight = entry_dt.hour * 60 + entry_dt.minute
    window_ok = (560 <= mins_from_midnight <= 885)
    
    cooldown_ok = True
    cooldown_delta = None
    if prev_entry_dt and prev_entry_dt.date() == entry_dt.date():
        cooldown_delta = (entry_dt - prev_entry_dt).total_seconds()
        if cooldown_delta < 300:
            cooldown_ok = False
    prev_entry_dt = entry_dt
    
    trade_type = str(t.get('trade_type', '')).upper()
    is_ce = 'CE' in trade_type or 'CALL' in str(t.get('strike', '')).upper() or 'BUY' in trade_type
    
    strike = t.get('strike', '')
    index_entry = float(t.get('index_entry_price', 0))
    index_exit = float(t.get('index_exit_price', 0))
    opt_entry = float(t.get('entry_price', 0))
    opt_exit = float(t.get('exit_price', 0))
    target = float(t.get('target_price', 0))
    sl = float(t.get('stop_loss_price', 0))
    initial_sl = float(t.get('initial_stop_loss_price', sl))
    initial_target = float(t.get('initial_target_price', target))
    exit_reason = t.get('exit_reason', '')
    pnl = float(t.get('pnl', 0))
    status = t.get('status', '')
    qty = int(t.get('quantity', 0))
    reason_str = t.get('reason', '')
    
    # Mathematical checks:
    # 1. SL pts calculation check:
    expected_initial_sl = round(opt_entry - 15.0, 2)
    sl_fidelity = abs(initial_sl - expected_initial_sl) <= 0.05
    
    # 2. Target pts calculation check (1:2.0 RR -> +30.0 pts):
    expected_initial_target = round(opt_entry + 30.0, 2)
    target_fidelity = abs(initial_target - expected_initial_target) <= 0.05
    
    # 3. PnL calculation check:
    calc_gross_pnl = round((opt_exit - opt_entry) * qty, 2)
    pnl_fidelity = abs(pnl - calc_gross_pnl) <= 1.0 or abs(pnl - round(calc_gross_pnl)) <= 1.0
    
    # 4. Trailing breakeven check:
    # If exit_reason == 'STOP_LOSS_HIT' but opt_exit >= opt_entry, it was breakeven trailed
    was_breakeven_trailed = (sl > initial_sl)
    
    # 5. Strike rounding check:
    # Symbol is NIFTY, strike should be multiple of 50
    strike_num = None
    for p in strike.split():
        if p.isdigit():
            strike_num = int(p)
            break
    strike_fidelity = (strike_num is not None and strike_num % 50 == 0)
    
    checks = {
        'trade_num': idx,
        'date': str(entry_dt.date()),
        'entry_time': str(entry_dt.time()),
        'exit_time': str(exit_dt.time()) if exit_dt else '-',
        'strike': strike,
        'trade_type': trade_type,
        'index_entry': index_entry,
        'index_exit': index_exit,
        'opt_entry': opt_entry,
        'opt_exit': opt_exit,
        'initial_sl': initial_sl,
        'initial_target': initial_target,
        'final_sl': sl,
        'final_target': target,
        'exit_reason': exit_reason,
        'qty': qty,
        'pnl': pnl,
        'status': status,
        'window_ok': window_ok,
        'cooldown_ok': cooldown_ok,
        'cooldown_delta': cooldown_delta,
        'sl_fidelity': sl_fidelity,
        'target_fidelity': target_fidelity,
        'pnl_fidelity': pnl_fidelity,
        'strike_fidelity': strike_fidelity,
        'breakeven_trailed': was_breakeven_trailed,
        'reason': reason_str
    }
    audit_results.append(checks)
    
    # Identify anomalies:
    if not window_ok:
        anomalies.append(f'Trade #{idx}: Entry time {entry_dt.time()} outside window 09:20-14:45')
    if not cooldown_ok:
        anomalies.append(f'Trade #{idx}: Cooldown violation ({cooldown_delta}s < 300s)')
    if not sl_fidelity:
        anomalies.append(f'Trade #{idx}: Initial SL {initial_sl} != expected {expected_initial_sl}')
    if not target_fidelity:
        anomalies.append(f'Trade #{idx}: Initial Target {initial_target} != expected {expected_initial_target}')
    if not pnl_fidelity:
        anomalies.append(f'Trade #{idx}: PnL mismatch recorded={pnl} vs calc={calc_gross_pnl}')

print(f'Total trades analyzed: {len(audit_results)}')
print(f'Total anomalies detected: {len(anomalies)}')
for a in anomalies:
    print(' - ' + a)

with open('/tmp/forensic_results.json', 'w') as out:
    json.dump({'trades': audit_results, 'anomalies': anomalies}, out, indent=2)
print('Saved forensic results to /tmp/forensic_results.json')
