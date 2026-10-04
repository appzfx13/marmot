import os
import sys
import json
import math
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'marmot.settings')
django.setup()

from apps.backtest.models import BacktestTask
from apps.common.constants import calculate_trade_charges


def audit_results(task_id=12):
    task = BacktestTask.objects.get(id=task_id)
    print(f"================================================================================")
    print(f"📊 ALGO TRADER & AI AUTOMATION AUDIT: Backtest Task #{task.id}")
    print(f"   Strategy: {task.strategy_name} | Index: {task.index_name}")
    print(f"   Period: {task.start_date} to {task.end_date} (1 Week)")
    print(f"   Initial Capital: ₹{task.initial_capital:,.2f}")
    print(f"================================================================================\n")

    json_path = f"/app/go-app/data/users/1/backtests/backtest_{task_id}.json"
    if not os.path.exists(json_path):
        json_path = f"/app/data/users/1/backtests/backtest_{task_id}.json"

    trades = []
    with open(json_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line:
                trades.append(json.loads(line))

    print(f"Total Trades Logged: {len(trades)}")
    
    total_gross_pnl = 0.0
    total_charges = 0.0
    total_net_pnl = 0.0
    
    wins = []
    losses = []
    trailing_wins = []
    target_hits = []
    sl_hits = []
    eod_squareoffs = []

    print(f"\n{'#':<3} | {'Entry Time':<19} | {'Strike':<16} | {'Type':<4} | {'Entry':<8} | {'Exit':<8} | {'Pts':<6} | {'Qty':<4} | {'Gross PnL':<10} | {'Charges':<8} | {'Net PnL':<10} | {'Exit Reason':<15}")
    print("-" * 135)

    for idx, t in enumerate(trades, 1):
        entry_p = t.get('entry_price', 0.0)
        exit_p = t.get('exit_price', 0.0)
        qty = t.get('quantity', 0)
        pts = round(exit_p - entry_p, 2)
        gross_pnl = t.get('pnl', round(pts * qty, 2))
        
        # Calculate exchange & brokerage statutory charges (Rule 10)
        charges_breakdown = calculate_trade_charges(
            entry_price=entry_p,
            exit_price=exit_p,
            quantity=qty,
            is_option=True,
            is_forex=False,
        )
        trade_charges = charges_breakdown.get('total_charges', 0.0)
        net_trade_pnl = round(gross_pnl - trade_charges, 2)

        total_gross_pnl += gross_pnl
        total_charges += trade_charges
        total_net_pnl += net_trade_pnl

        exit_reason = t.get('exit_reason', '')
        status = t.get('status', '')

        if gross_pnl > 0:
            wins.append(t)
        else:
            losses.append(t)

        if exit_reason == 'TARGET_HIT':
            target_hits.append(t)
        elif exit_reason == 'TRAILING_SL_HIT':
            trailing_wins.append(t)
        elif exit_reason == 'STOP_LOSS_HIT':
            sl_hits.append(t)
        elif exit_reason == 'EOD_SQUAREOFF':
            eod_squareoffs.append(t)

        print(f"{idx:<3} | {t.get('timestamp', ''):<19} | {t.get('strike', ''):<16} | {t.get('trade_type', ''):<4} | ₹{entry_p:<7.2f} | ₹{exit_p:<7.2f} | {pts:+6.1f} | {qty:<4} | ₹{gross_pnl:+9.2f} | ₹{trade_charges:<7.2f} | ₹{net_trade_pnl:+9.2f} | {exit_reason:<15}")

    print("-" * 135)
    print(f"TOTAL: Gross PnL = ₹{total_gross_pnl:+,.2f} | Total Charges = ₹{total_charges:,.2f} | Net PnL = ₹{total_net_pnl:+,.2f}")
    
    print("\n" + "="*80)
    print("📈 DETAILED PERFORMANCE & AUDIT BREAKDOWN")
    print("="*80)
    win_rate = (len(wins) / len(trades) * 100) if trades else 0.0
    profit_factor = (sum(w['pnl'] for w in wins) / abs(sum(l['pnl'] for l in losses))) if losses and sum(l['pnl'] for l in losses) != 0 else 99.9

    print(f"• Total Trades:              {len(trades)}")
    print(f"• Winning Trades:            {len(wins)} ({win_rate:.1f}%)")
    print(f"• Losing Trades:             {len(losses)} ({100 - win_rate:.1f}%)")
    print(f"• Target Hits (+30 pts / 2R):{len(target_hits)}")
    print(f"• Trailing SL Locked (+1.0): {len(trailing_wins)}")
    print(f"• Full SL Hits (-15 pts):    {len(sl_hits)}")
    print(f"• EOD Square-offs:           {len(eod_squareoffs)}")
    print(f"• Profit Factor (Gross):     {profit_factor:.2f}")
    print(f"• Total Brokerage & Taxes:   ₹{total_charges:,.2f}")
    print(f"• Net PnL After Taxes:       ₹{total_net_pnl:+,.2f}")

    # Inspect Reason logs of all trades to verify entry condition fidelity
    print("\n" + "="*120)
    print("🔍 COMPREHENSIVE TRADE SIGNAL & EXECUTION AUDIT (All 20 Trades)")
    print("="*120)
    for idx, t in enumerate(trades, 1):
        print(f"Trade #{idx:02d}: {t.get('timestamp')} | {t.get('strike')} | Spot: {t.get('index_entry_price')} | Entry: ₹{t.get('entry_price')} -> Exit: ₹{t.get('exit_price')} ({t.get('exit_reason')}) | PnL: ₹{t.get('pnl')}")
        print(f"         Reason: {t.get('reason')}")



if __name__ == '__main__':
    audit_results(14)
