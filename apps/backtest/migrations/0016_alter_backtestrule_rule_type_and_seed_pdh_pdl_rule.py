from django.db import migrations, models


def seed_pdh_pdl_rule(apps, schema_editor):
    """Seed Previous Day High & Low (PDH / PDL) strategy rule."""
    BacktestRule = apps.get_model('backtest', 'BacktestRule')

    rule_data = {
        "name": "Previous Day High & Low (PDH / PDL) Breakout & Liquidity Sweep Guardrail",
        "rule_type": "pdh_pdl",
        "description": "Tracks institutional Previous Day High (PDH) and Previous Day Low (PDL) benchmarks. Mandates structural breakout acceptance above PDH / below PDL for continuation trades, and triggers asymmetric mean-reversion fades when false sweeps fail to sustain outside the prior day range.",
        "prompt_directive": "Previous Day High (PDH) & Previous Day Low (PDL) Strategy Rule: Benchmark each session's underlying spot against the exact PDH and PDL. On upside break of PDH with strong candle close > PDH, trigger Bullish CE continuation targeting PDH + 1.2x Daily ATR. On downside break of PDL with strong candle close < PDL, trigger Bearish PE continuation targeting PDL - 1.2x Daily ATR. If spot tests PDH/PDL with rejection wick (> 35%) and closes back inside the prior day's range, trigger a high-probability SMC Mean-Reversion trade targeting the Previous Day Mid-Point (POC/50% Equilibrium) with 1:2.0 RR.",
        "parameters": {
            "track_pdh_pdl": True,
            "breakout_atr_target_multiplier": 1.2,
            "fade_false_sweep": True,
            "rejection_wick_threshold": 0.35,
            "reversal_target_level": "50_percent_equilibrium",
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
        ('backtest', '0015_alter_backtestrule_rule_type_and_seed_liquidity_sweep_rule'),
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
                    ('custom_prompt', 'AI Prompt Directive'),
                    ('technical', 'Technical / Indicator'),
                ],
                default='intraday',
                max_length=50,
            ),
        ),
        migrations.RunPython(seed_pdh_pdl_rule, reverse_code=migrations.RunPython.noop),
    ]
