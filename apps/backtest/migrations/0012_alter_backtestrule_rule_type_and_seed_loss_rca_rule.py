from django.db import migrations, models


def seed_loss_rca_rule(apps, schema_editor):
    """Seed Stop-Loss Root Cause Analysis & Learning Engine strategy rule."""
    BacktestRule = apps.get_model('backtest', 'BacktestRule')

    rule_data = {
        "name": "Stop-Loss Root Cause Analysis (Loss RCA & Adaptive Rule Generation)",
        "rule_type": "loss_rca",
        "description": "Performs automated multi-factor Root Cause Analysis (RCA) on every losing trade hitting Stop-Loss. Analyzes 200 EMA macro trend violations, low-volatility chop traps (compressed India VIX), FII/DII institutional net selling absorption, and event spikes to synthesize actionable preventive rule guardrails.",
        "prompt_directive": "Execute multi-factor Root Cause Analysis (RCA) across all losing trades hitting Stop-Loss. Cross-examine trade failure conditions against 200 EMA trend alignment, India VIX compression regimes (< 12.0), FII/DII institutional net flow divergence, and macro liquidity traps. Generate structured loss diagnostic summaries for each trade and automatically synthesize preventive rule constraints for future backtesting and live RL policy optimization.",
        "parameters": {
            "analyze_200_ema_bias": True,
            "analyze_vix_compression": True,
            "analyze_fii_dii_flows": True,
            "analyze_liquidity_sweeps": True,
            "auto_generate_future_rules": True,
            "loss_severity_threshold_pts": 20.0,
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
        ('backtest', '0011_alter_backtestrule_rule_type_and_seed_india_vix_rule'),
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
                    ('custom_prompt', 'AI Prompt Directive'),
                    ('technical', 'Technical / Indicator'),
                ],
                default='intraday',
                max_length=50,
            ),
        ),
        migrations.RunPython(seed_loss_rca_rule, reverse_code=migrations.RunPython.noop),
    ]
