from django.db import migrations, models


def seed_ict_rule(apps, schema_editor):
    """Seed ICT Institutional Smart Money Strategy rule."""
    BacktestRule = apps.get_model('backtest', 'BacktestRule')

    rule_data = {
        "name": "ICT Institutional Smart Money Strategy (Killzone, MSS, FVG & OTE Matrix)",
        "rule_type": "ict_smc_matrix",
        "description": "Institutional Inner Circle Trader (ICT) Framework: Executes high-probability setups during Indian Market Killzones (09:15-10:30 & 13:15-14:45). Requires Buy/Sell-Side Liquidity (BSL/SSL) Raid, followed by a Market Structure Shift (MSS) with Displacement and Fair Value Gap (FVG) creation. Enforces limit entries at the FVG Consequent Encroachment (50%) or Optimal Trade Entry (OTE 62%-79% Retracement) targeting External Draw on Liquidity with a strict 1:3.0+ Risk-to-Reward.",
        "prompt_directive": "ICT Institutional Smart Money Rule: 1. Time & Price Alignment: Only evaluate setups during institutional Killzone windows (Morning Open 09:15-10:30 IST and Afternoon Macro 13:15-14:45 IST). 2. Liquidity Sweep: Identify BSL (Buy-Side Liquidity above swing highs/PDH) or SSL (Sell-Side Liquidity below swing lows/PDL) purge. 3. Market Structure Shift (MSS): Require rapid energetic displacement candle breaking internal structure with large body ratio (> 70%) leaving a 3-candle Fair Value Gap (FVG / Imbalance). 4. Precision Entry: Place resting limit orders strictly at the FVG Consequent Encroachment (50% midpoint) or OTE (62%-79% Fibonacci discount/premium retracement). 5. Execution & Target: Target opposing external range liquidity pool (DOL) with pre-set 1:3.0 Minimum Risk-to-Reward and Stop-Loss protected behind the Displacement swing origin.",
        "parameters": {
            "killzone_morning_window": ["09:15", "10:30"],
            "killzone_afternoon_window": ["13:15", "14:45"],
            "min_displacement_body_ratio": 0.70,
            "fvg_consequent_encroachment_entry": True,
            "ote_fib_range": [0.62, 0.79],
            "target_min_rr": 3.0,
            "purge_bsl_ssl_first": True,
            "draw_on_liquidity_target": "opposing_external_swing",
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
        ('backtest', '0016_alter_backtestrule_rule_type_and_seed_pdh_pdl_rule'),
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
                    ('custom_prompt', 'AI Prompt Directive'),
                    ('technical', 'Technical / Indicator'),
                ],
                default='intraday',
                max_length=50,
            ),
        ),
        migrations.RunPython(seed_ict_rule, reverse_code=migrations.RunPython.noop),
    ]
