from django.db import migrations, models


def seed_forex_orderflow_rules(apps, schema_editor):
    """Seed 4 high-winrate Forex & CME Micro Futures Order Flow Strategy Rules."""
    BacktestRule = apps.get_model('backtest', 'BacktestRule')

    forex_rules = [
        {
            "name": "Institutional CVD (Cumulative Volume Delta) Divergence & Delta Exhaustion",
            "market_type": "FOREX_FUTURES",
            "rule_type": "forex_cvd_divergence",
            "description": "Compares price movement against order flow Cumulative Volume Delta (CVD). Rejects false breakout traps when buy/sell market order delta exhausts, and enters high-probability reversal positions on CVD divergence at key support/resistance levels.",
            "prompt_directive": "Institutional CVD Divergence Rule: 1. CVD Tracking: Monitor 1-min & 5-min Cumulative Volume Delta (CVD). 2. Divergence Filter: Only enter long positions when price sweeps key support while CVD flips net positive with aggressive buy market orders. Reject long trades when price makes a higher high with negative delta divergence. 3. Delta Exhaustion: Exit immediately if buying delta drops by >35% at resistance.",
            "parameters": {
                "min_delta_divergence_pct": 35.0,
                "cvd_lookback_bars": 20,
                "confirmation_schema": "mbp-10",
                "prohibit_exhaustion_chase": True,
            },
            "is_system_preset": True,
            "is_active": True,
        },
        {
            "name": "Level-10 DOM Depth Liquidity Stack & Iceberg Order Absorption",
            "market_type": "FOREX_FUTURES",
            "rule_type": "forex_dom_absorption",
            "description": "Analyzes Databento MBP-10 (10-Level Order Book Depth) and MBO order flow. Identifies institutional passive limit order walls absorbing aggressive market orders at session highs and lows.",
            "prompt_directive": "DOM Level-10 Absorption Rule: 1. Depth Analysis: Calculate bid/ask liquidity ratio across 10 DOM depth levels. 2. Iceberg Absorption: Enter reversal trades when heavy passive bid/ask limit walls (>2.5x volume ratio) absorb aggressive market orders at session extremes. 3. Execution: Place tight 1:2.5 RR limit orders behind the DOM absorption wall.",
            "parameters": {
                "min_bid_ask_ratio": 2.5,
                "dom_levels": 10,
                "min_iceberg_volume": 50,
                "target_rr": 2.5,
            },
            "is_system_preset": True,
            "is_active": True,
        },
        {
            "name": "London & New York Session Order Flow Killzone Surge",
            "market_type": "FOREX_FUTURES",
            "rule_type": "forex_killzone_delta",
            "description": "Restricts execution strictly to high-volume institutional liquidity windows: London Open (07:00-10:00 UTC) and New York Open (13:00-16:00 UTC). Eliminates low-volume Asian consolidation noise.",
            "prompt_directive": "Session Order Flow Killzone Rule: 1. Time Windows: Execute order flow trades strictly within London Open (07:00-10:00 UTC) and NY Open (13:00-16:00 UTC) killzone windows. 2. Volume Spike Guard: Require 1.8x volume multiplier over Asian session baseline before trade initialization. 3. Strict Auto-Close: Auto-close positions before NY session close.",
            "parameters": {
                "london_killzone": ["07:00", "10:00"],
                "ny_killzone": ["13:00", "16:00"],
                "min_volume_multiplier": 1.8,
                "auto_close_time_utc": "20:00",
            },
            "is_system_preset": True,
            "is_active": True,
        },
        {
            "name": "SMC Order Flow Displacement & 50% Fair Value Gap (FVG) Retest",
            "market_type": "FOREX_FUTURES",
            "rule_type": "forex_smc_displacement",
            "description": "Monitors rapid institutional order flow displacement candles with large delta bodies that create Fair Value Gaps (FVG). Enters limit orders at 50% FVG retracement for asymmetric risk-reward.",
            "prompt_directive": "SMC Order Flow Displacement Rule: 1. Displacement Identification: Spot institutional displacement candles (body > 75% of range) with order flow delta surges. 2. FVG Entry: Mark 3-candle Fair Value Gap (FVG) and place limit order at 50% equilibrium level. 3. Risk Control: Invalidate trade if FVG is fully closed before limit fill.",
            "parameters": {
                "min_body_ratio": 0.75,
                "fvg_retest_depth": 0.50,
                "target_rr": 2.5,
                "invalidate_on_full_fill": True,
            },
            "is_system_preset": True,
            "is_active": True,
        },
    ]

    for rule_data in forex_rules:
        BacktestRule.objects.update_or_create(
            name=rule_data["name"],
            defaults=rule_data,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('backtest', '0019_backtestrule_market_type'),
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
                    ('forex_cvd_divergence', 'Forex CVD (Cumulative Volume Delta) Divergence'),
                    ('forex_dom_absorption', 'Forex Level-10 DOM Depth & Iceberg Absorption'),
                    ('forex_killzone_delta', 'Forex London & NY Killzone Order Flow Surge'),
                    ('forex_smc_displacement', 'Forex SMC Displacement & FVG Retest'),
                    ('custom_prompt', 'AI Prompt Directive'),
                    ('technical', 'Technical / Indicator'),
                ],
                default='intraday',
                max_length=50,
            ),
        ),
        migrations.RunPython(seed_forex_orderflow_rules, reverse_code=migrations.RunPython.noop),
    ]
