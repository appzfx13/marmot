import os
import pyarrow.parquet as pq
import pandas as pd
import numpy as np

p = r'backup\1\49\dataset.parquet'
tbl = pq.read_table(p)
df = tbl.to_pandas()

spot_df = df[df['strike'] == 'SPOT'].sort_values('datetime').reset_index(drop=True)
opt_df = df[df['strike'] != 'SPOT'].copy()

# Index option lookup: (datetime, strike, option_type) -> snap
opt_map = {}
for _, row in opt_df.iterrows():
    k = (row['datetime'], str(row['strike']), str(row['option_type']))
    opt_map[k] = row

print(f"Loaded: {len(spot_df)} spot ticks, {len(opt_df)} option ticks")

for d, day_spot in spot_df.groupby(spot_df['datetime'].str[:10]):
    day_spot = day_spot.reset_index(drop=True)
    print(f"\n==================== DATE: {d} ====================")
    
    candle_buffer = []
    current_bar_min = None
    running_bar = None
    
    pending = None
    active_trade = None
    trades = []
    
    last_signal_time = None
    
    for i in range(len(day_spot)):
        tick = day_spot.iloc[i]
        t_str = tick['datetime']
        m_str = t_str[:16]
        m_of_d = int(t_str[11:13])*60 + int(t_str[14:16])
        
        # 1. Update running 1-minute candle
        if current_bar_min != m_str:
            if running_bar is not None:
                candle_buffer.append(running_bar)
                if len(candle_buffer) > 100:
                    candle_buffer.pop(0)
            current_bar_min = m_str
            running_bar = {
                'datetime': t_str[:19],
                'minute': m_str,
                'open': tick['open'],
                'high': tick['high'],
                'low': tick['low'],
                'close': tick['close']
            }
        else:
            running_bar['high'] = max(running_bar['high'], tick['high'])
            running_bar['low'] = min(running_bar['low'], tick['low'])
            running_bar['close'] = tick['close']
            
        # 2. Manage active trade
        if active_trade is not None:
            # Check exit on option
            k = (t_str, active_trade['strike_num'], active_trade['opt_type'])
            opt_snap = opt_map.get(k)
            opt_low = opt_snap['low'] if opt_snap is not None else active_trade['entry_price']
            opt_high = opt_snap['high'] if opt_snap is not None else active_trade['entry_price']
            opt_close = opt_snap['close'] if opt_snap is not None else active_trade['entry_price']
            
            is_closed = False
            exit_price = opt_close
            exit_reason = "TARGET_HIT"
            
            if opt_low <= active_trade['sl_price']:
                exit_price = active_trade['sl_price']
                exit_reason = "STOP_LOSS_HIT"
                is_closed = True
            elif opt_high >= active_trade['tp_price']:
                exit_price = active_trade['tp_price']
                exit_reason = "TARGET_HIT"
                is_closed = True
            elif i == len(day_spot) - 1:
                exit_price = opt_close
                exit_reason = "EOD_SQUAREOFF"
                is_closed = True
                
            if is_closed:
                pnl = round((exit_price - active_trade['entry_price']) * active_trade['qty'], 2)
                trades.append({
                    'signal_time': active_trade['signal_time'],
                    'entry_time': active_trade['entry_time'],
                    'exit_time': t_str,
                    'strike': f"{active_trade['strike_num']} {active_trade['opt_type']}",
                    'entry_p': active_trade['entry_price'],
                    'exit_p': exit_price,
                    'pnl': pnl,
                    'reason': exit_reason,
                    'sig_reason': active_trade['sig_reason']
                })
                active_trade = None
            continue
            
        # 3. Check pending limit order retest fill
        if pending is not None:
            # Check expiration (15 mins = 180 5s ticks)
            if i - pending['tick_idx'] > 180:
                pending = None
            else:
                k = (t_str, pending['strike_num'], pending['opt_type'])
                opt_snap = opt_map.get(k)
                is_filled = False
                fill_price = pending['limit_price']
                
                if opt_snap is not None and opt_snap['close'] > 0:
                    o_low = opt_snap['low']
                    if o_low <= pending['limit_price']:
                        is_filled = True
                else:
                    # spot check
                    if pending['opt_type'] == 'CALL' and tick['low'] <= pending['spot_limit']:
                        is_filled = True
                    elif pending['opt_type'] == 'PUT' and tick['high'] >= pending['spot_limit']:
                        is_filled = True
                        
                if is_filled:
                    active_trade = {
                        'signal_time': pending['signal_time'],
                        'entry_time': t_str,
                        'strike_num': pending['strike_num'],
                        'opt_type': pending['opt_type'],
                        'entry_price': fill_price,
                        'sl_price': round(fill_price - pending['sl_pts'], 2),
                        'tp_price': round(fill_price + (pending['sl_pts'] * pending['rr']), 2),
                        'qty': 25,
                        'sig_reason': pending['reason']
                    }
                    pending = None
                    continue
                    
        # 4. Evaluate entry signal (only at completed 1-minute candle boundaries)
        if m_of_d < (9*60+20) or m_of_d > (14*60+45):
            continue
            
        if len(candle_buffer) < 12:
            continue
            
        # Check cooldown
        if last_signal_time is not None and (i - last_signal_time) < 24: # 2 mins = 24 5s ticks
            continue
            
        cur = candle_buffer[-1]
        close_p = cur['close']
        open_p = cur['open']
        high_p = cur['high']
        low_p = cur['low']
        cand_body = abs(close_p - open_p)
        cand_range = max(1.0, high_p - low_p)
        disp_ratio = cand_body / cand_range
        
        lookback = min(12, len(candle_buffer) - 2)
        start_b = len(candle_buffer) - 2 - lookback
        bsl = max(c['high'] for c in candle_buffer[start_b:-2])
        ssl = min(c['low'] for c in candle_buffer[start_b:-2])
        
        is_bull = False
        is_bear = False
        sig_reason = ""
        
        for offset in [1, 2, 3]:
            if len(candle_buffer) <= offset:
                continue
            sb = candle_buffer[-1 - offset]
            sb_range = max(1.0, sb['high'] - sb['low'])
            sb_lw = min(sb['open'], sb['close']) - sb['low']
            sb_uw = sb['high'] - max(sb['open'], sb['close'])
            
            if sb['low'] < ssl and sb['close'] >= (ssl - 1.0) and (sb_lw / sb_range) >= 0.20:
                if close_p > open_p and close_p >= sb['high'] and disp_ratio >= 0.40:
                    is_bull = True
                    sig_reason = f"Bullish Sweep (SSL={ssl:.1f} swept to {sb['low']:.1f}) + CHoCH Break (Close={close_p:.1f} >= {sb['high']:.1f}) | Disp={disp_ratio*100:.1f}%"
                    break
                    
            if not is_bull and sb['high'] > bsl and sb['close'] <= (bsl + 1.0) and (sb_uw / sb_range) >= 0.20:
                if close_p < open_p and close_p <= sb['low'] and disp_ratio >= 0.40:
                    is_bear = True
                    sig_reason = f"Bearish Sweep (BSL={bsl:.1f} swept to {sb['high']:.1f}) + CHoCH Break (Close={close_p:.1f} <= {sb['low']:.1f}) | Disp={disp_ratio*100:.1f}%"
                    break
                    
        if is_bull or is_bear:
            opt_type = 'CALL' if is_bull else 'PUT'
            atm_strike = str(int(round(tick['close'] / 50.0) * 50))
            k = (t_str, atm_strike, opt_type)
            opt_snap = opt_map.get(k)
            if opt_snap is not None and opt_snap['close'] > 0:
                cmp_p = opt_snap['close']
                limit_p = round(cmp_p * 0.995, 2) # 0.5% limit retest
                spot_lim = (tick['close'] - 2.5) if is_bull else (tick['close'] + 2.5)
                pending = {
                    'signal_time': t_str,
                    'tick_idx': i,
                    'strike_num': atm_strike,
                    'opt_type': opt_type,
                    'limit_price': limit_p,
                    'spot_limit': spot_lim,
                    'sl_pts': 12.0,
                    'rr': 2.5,
                    'reason': sig_reason
                }
                last_signal_time = i

    print(f"Executed trades: {len(trades)}")
    win_cnt = sum(1 for t in trades if t['pnl'] > 0)
    total_pnl = sum(t['pnl'] for t in trades)
    print(f"Win Rate: {win_cnt}/{len(trades)} ({win_cnt/len(trades)*100:.1f}%) | Total Net PnL: INR {total_pnl:.2f}")
    for idx, t in enumerate(trades, 1):
        print(f"  Trade #{idx}: Signal={t['signal_time']} -> Entry={t['entry_time']} -> Exit={t['exit_time']} | {t['strike']} | Entry=INR {t['entry_p']} | Exit=INR {t['exit_p']} | PnL=INR {t['pnl']} ({t['reason']})")
