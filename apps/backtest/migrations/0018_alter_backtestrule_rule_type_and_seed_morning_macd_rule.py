from django.db import migrations, models


def seed_morning_macd_rule(apps, schema_editor):
    """Seed Morning 3-Min HTF Momentum & Option Strike MACD Retest Guardrail rule."""
    BacktestRule = apps.get_model('backtest', 'BacktestRule')

    rule_data = {
        "name": "Morning 3-Min HTF Momentum & Option Strike MACD Retest Guardrail",
        "rule_type": "morning_macd_retest",
        "description": "Captures high-velocity morning market momentum (09:18-10:30 IST) using a 3-minute Higher Timeframe (HTF) directional bias. Mandates a 1-min/5-min MACD bullish/bearish crossover, followed by a sharp option premium retest pullback to the breakout/VWAP zone before executing limit entry with 1:2.5 RR (eliminating aggressive FOMO market chasing).",
        "prompt_directive": "Morning 3-Min HTF Momentum & MACD Retest Rule: 1. HTF Directional Bias: Establish 3-minute HTF trend bias between 09:18 and 10:30 IST using EMA 9/21 alignment. 2. Momentum Confirmation: Confirm MACD (12, 26, 9) signal line crossover and expanding histogram in the direction of the 3-min HTF trend. 3. Sharp Retest Execution: Prohibit aggressive market buying at crossover peaks; require a sharp pullback/retest into the breakout level or option premium support band within 1.2x ATR. 4. Execution & Risk: Enter via resting limit order on retest confirmation with Stop-Loss placed below the retest pivot low/high and target asymmetric 1:2.5 Risk-to-Reward.",
        "parameters": {
            "morning_window": ["09:18", "10:30"],
            "htf_timeframe_minutes": 3,
            "macd_fast": 12,
            "macd_slow": 26,
            "macd_signal": 9,
            "require_sharp_retest": True,
            "retest_tolerance_atr": 1.2,
            "target_rr": 2.5,
            "prohibit_market_chasing": True,
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
        ('backtest', '0017_alter_backtestrule_rule_type_and_seed_ict_rule'),
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
                    ('pdh_pdl', 'PDH & PDL Breakout / Liquidity Sweep Filter'),
                    ('ict_smc_matrix', 'ICT Institutional Smart Money (Killzone, MSS, FVG & OTE)'),
                    ('morning_macd_retest', 'Morning 3-Min HTF & Option MACD Retest'),
                    ('custom_prompt', 'AI Prompt Directive'),
                    ('technical', 'Technical / Indicator'),
                ],
                default='intraday',
                max_length=50,
            ),
        ),
        migrations.RunPython(seed_morning_macd_rule, reverse_code=migrations.RunPython.noop),
    ]
