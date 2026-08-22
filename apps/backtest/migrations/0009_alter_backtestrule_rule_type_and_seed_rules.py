import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def seed_strategy_rules(apps, schema_editor):
    BacktestRule = apps.get_model('backtest', 'BacktestRule')

    rules_data = [
        {
            "name": "Strict SL & TP Bracket Placement (Pre-Defined Risk Management)",
            "rule_type": "risk_management",
            "description": "Enforces mandatory pre-defined Stop-Loss (SL) and Target (TP) order placement with every position entry. The backtest engine strictly monitors price levels on 1-min / tick data, executing instant exits on stop breaches or target fulfillment without letting positions float unprotected.",
            "prompt_directive": "Always pair trade entries with mandatory bracket orders containing explicit Stop-Loss (SL) and Take-Profit (TP) levels. Reject or invalidate any trade signal lacking a defined risk-to-reward ratio. Execute automated exit immediately when either price point is touched, prohibiting trailing without a minimum 1:2 risk-to-reward baseline.",
            "parameters": {
                "enforce_bracket_orders": True,
                "default_sl_points": 30.0,
                "default_rr_ratio": 2.0,
                "max_loss_per_trade_pct": 2.0,
                "auto_exit_on_sl": True,
                "auto_exit_on_tp": True,
                "trail_sl_to_breakeven_at_1r": True,
            },
            "is_system_preset": True,
            "is_active": True,
        },
        {
            "name": "Limit Entry on Retest Only (Zero Aggressive Market Chasing)",
            "rule_type": "retest_limit",
            "description": "Prohibits aggressive market order entries during breakout momentum spikes. Mandates placing resting Limit Orders exclusively at verified breakout retest zones, pullback support/resistance boundaries, or key level retests to minimize slippage and ensure high-probability entries.",
            "prompt_directive": "Never enter positions using aggressive market orders on breakout momentum candles. Wait for price action to pull back and retest the breakout boundary, VWAP, or key swing level. Submit resting Limit Orders only within the defined retest tolerance zone. If price surges ahead without a retest within 3 candles, cancel the order.",
            "parameters": {
                "order_type": "LIMIT",
                "entry_mode": "PULLBACK_RETEST",
                "retest_zone_tolerance_pts": 5.0,
                "allow_market_orders": False,
                "max_wait_candles": 3,
                "cancel_unfilled_orders": True,
                "min_pullback_pct": 38.2,
            },
            "is_system_preset": True,
            "is_active": True,
        },
        {
            "name": "Intraday Only (Auto Square-off 15:15 IST)",
            "rule_type": "intraday",
            "description": "Enforces strict intraday trade lifecycle. All open option positions are automatically squared off by 15:15 IST to eliminate overnight gap risks and theta decay over non-trading hours.",
            "prompt_directive": "Close all open positions by 15:15 IST without exception. Disallow any new entry signals generated after 15:00 IST.",
            "parameters": {
                "auto_square_off_time": "15:15:00",
                "no_entry_after": "15:00:00",
                "disallow_overnight": True,
            },
            "is_system_preset": True,
            "is_active": True,
        },
        {
            "name": "0DTE Expiry Gamma Blast Capture",
            "rule_type": "gamma_blast",
            "description": "Optimized for index expiry days (0DTE). Targets high gamma expansion during 13:30–15:15 IST with dynamic trailing stop loss and quick profit-taking thresholds.",
            "prompt_directive": "On 0DTE weekly/monthly expiry sessions, activate aggressive gamma capture rules post 13:30 IST. Trail stop-loss dynamically by 20% on every 50% option premium appreciation.",
            "parameters": {
                "session_start_time": "13:30:00",
                "dynamic_trail_pct": 20.0,
                "take_profit_threshold_pct": 50.0,
            },
            "is_system_preset": True,
            "is_active": True,
        },
    ]

    for item in rules_data:
        BacktestRule.objects.update_or_create(
            name=item["name"],
            defaults=item,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('backtest', '0008_alter_backtestrule_rule_type'),
    ]

    operations = [
        migrations.AlterField(
            model_name='backtestrule',
            name='rule_type',
            field=models.CharField(
                choices=[
                    ('intraday', 'Intraday Only'),
                    ('gamma_blast', 'Gamma Blast (0DTE Expiry)'),
                    ('morning_trend', 'Morning Trend Capture'),
                    ('gap_openings', 'Overnight Gap Prediction (BTST / STBT)'),
                    ('risk_management', 'Strict SL & TP Placement'),
                    ('retest_limit', 'Retest Limit Entry (No Market Orders)'),
                    ('custom_prompt', 'AI Prompt Directive'),
                    ('technical', 'Technical / Indicator'),
                ],
                default='intraday',
                max_length=50,
            ),
        ),
        migrations.RunPython(seed_strategy_rules, reverse_code=migrations.RunPython.noop),
    ]
