from django.db import migrations, models


def seed_candle_close_rule(apps, schema_editor):
    """Seed Candle Close Stop-Loss Execution & Anti-Wick Hunt strategy rule."""
    BacktestRule = apps.get_model('backtest', 'BacktestRule')

    rule_data = {
        "name": "Candle Close Stop-Loss Execution & Anti-Wick Hunt Guardrail",
        "rule_type": "candle_close_sl",
        "description": "Prevents premature stop-outs from transient intraday shadow wicks and liquidity sweeps. Mandates that Stop-Loss is only triggered upon a full 3m/5m candle body close beyond the structural pivot level (or 2 consecutive bar closes), filtering out false sub-second stop runs within 1.5x ATR tolerance.",
        "prompt_directive": "Enforce Candle Close Stop-Loss Execution. Do not trigger stop-loss exits on sub-candle intra-bar wick touches or transient liquidity sweeps. Only execute stop-loss when a 3-minute or 5-minute candle body closes decisively beyond the invalidation level. Place stop barriers behind major swing pivots plus a 0.25x ATR spread tolerance buffer to ensure the trade is not stopped out before the macro trend resumes.",
        "parameters": {
            "trigger_mode": "candle_body_close",
            "confirmation_timeframe_minutes": 3,
            "consecutive_bars_required": 2,
            "wick_reversal_ratio_min": 0.35,
            "spread_tolerance_buffer_pts": 5.0,
            "structural_pivot_sl": True,
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
        ('backtest', '0013_alter_backtestrule_rule_type_and_seed_atr_noise_rule'),
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
                    ('custom_prompt', 'AI Prompt Directive'),
                    ('technical', 'Technical / Indicator'),
                ],
                default='intraday',
                max_length=50,
            ),
        ),
        migrations.RunPython(seed_candle_close_rule, reverse_code=migrations.RunPython.noop),
    ]
