from django.db import migrations, models


def seed_liquidity_sweep_rule(apps, schema_editor):
    """Seed Liquidity Sweep & False Breakout Filter strategy rule."""
    BacktestRule = apps.get_model('backtest', 'BacktestRule')

    rule_data = {
        "name": "Liquidity Sweep Invalidation & False Breakout Filter (Smart Money SMC)",
        "rule_type": "liquidity_sweep",
        "description": "Detects and invalidates institutional liquidity sweeps (Turtle Soup / Stop Hunts) at key swing highs and lows. Prohibits buying breakout tops with >40% rejection wicks, mandates volume expansion (>1.8x SMA20) for breakout continuation, and enables high-probability mean-reversion counter-trades when traps are confirmed.",
        "prompt_directive": "Filter Liquidity Sweeps and False Breakout Traps. Prohibit entering long/short breakouts when price sweeps previous swing highs/lows with extended rejection wicks (> 40% wick ratio) and closes back inside the prior range. Only validate breakout continuation if the breakout candle is backed by > 1.8x 20-period volume expansion with body ratio > 65%. When a liquidity trap is confirmed, trigger mean-reversion counter-entries targeting opposite swing liquidity with strict 1:2.5 Risk-to-Reward.",
        "parameters": {
            "min_rejection_wick_ratio": 0.40,
            "min_breakout_volume_ratio": 1.8,
            "min_candle_body_ratio": 0.65,
            "enable_fade_the_trap": True,
            "sweep_swing_lookback_bars": 20,
            "target_rr_sweep_reversal": 2.5,
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
        ('backtest', '0014_alter_backtestrule_rule_type_and_seed_candle_close_rule'),
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
                    ('candle_close_sl', 'Candle Close SL & Anti-Wick Guardrail'),
                    ('liquidity_sweep', 'Liquidity Sweep & False Breakout Filter (SMC)'),
                    ('custom_prompt', 'AI Prompt Directive'),
                    ('technical', 'Technical / Indicator'),
                ],
                default='intraday',
                max_length=50,
            ),
        ),
        migrations.RunPython(seed_liquidity_sweep_rule, reverse_code=migrations.RunPython.noop),
    ]
