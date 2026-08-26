from django.db import migrations, models


def seed_atr_noise_rule(apps, schema_editor):
    """Seed Dynamic ATR Volatility Buffer & Anti-Noise strategy rule."""
    BacktestRule = apps.get_model('backtest', 'BacktestRule')

    rule_data = {
        "name": "Dynamic ATR Volatility Buffer & Spread Protection (Anti-Noise Filter)",
        "rule_type": "atr_noise_filter",
        "description": "Prevents premature stop-outs caused by normal intraday market noise, sub-second wick spikes, and bid-ask spread friction. Dynamically scales Stop-Loss buffers to 1.5x ATR (14-period 5m), requires candle close confirmation below structural swing pivots, and enforces highly liquid ATM/ITM strikes to eliminate slippage.",
        "prompt_directive": "Eliminate market noise and spread whipsaws by dynamically scaling Stop-Loss distances using a 1.5x ATR volatility buffer instead of static point stops. Reject stop execution on single transient wick spikes; require candle body close confirmation beyond the stop barrier. Filter entries during low-volume midday consolidation (11:30–13:00 IST) unless volume exceeds 1.5x 20-SMA. Enforce liquid ATM / ITM strike selection with bid-ask spread < 1.0% of option premium.",
        "parameters": {
            "atr_multiplier": 1.5,
            "atr_period": 14,
            "require_candle_close_sl": True,
            "filter_midday_lull": True,
            "midday_lull_start": "11:30:00",
            "midday_lull_end": "13:00:00",
            "min_volume_expansion_ratio": 1.5,
            "max_spread_slippage_pct": 1.0,
            "strike_liquid_bias": "ATM",
        },
        "is_system_preset": True,
        "is_active": True,
    }

    BacktestRule.objects.update_or_create(
        name=rule_data["name"],
        defaults=rule_data,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('backtest', '0012_alter_backtestrule_rule_type_and_seed_loss_rca_rule'),
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
                    ('trendline_retest', 'Trendline Breakout & Retest'),
                    ('india_vix', 'India VIX Volatility Regime'),
                    ('loss_rca', 'Stop-Loss RCA & Learning Engine'),
                    ('atr_noise_filter', 'Dynamic ATR Volatility Buffer (Anti-Noise)'),
                    ('custom_prompt', 'AI Prompt Directive'),
                    ('technical', 'Technical / Indicator'),
                ],
                default='intraday',
                max_length=50,
            ),
        ),
        migrations.RunPython(seed_atr_noise_rule, reverse_code=migrations.RunPython.noop),
    ]
