from django.db import migrations, models


def seed_trendline_retest_rule(apps, schema_editor):
    """Seed Trendline Breakout & Retest Confirmation strategy rule."""
    BacktestRule = apps.get_model('backtest', 'BacktestRule')

    rule_data = {
        "name": "Trendline Breakout & Retest Confirmation (Price Action Structure)",
        "rule_type": "trendline_retest",
        "description": "Identifies major and minor multi-touch trendline structural breakouts (ascending support breakdown or descending resistance breakout). Requires a decisive breakout candle followed by a secondary retest confirmation on the trendline slope before validating position entry, filtering aggressive false breakouts.",
        "prompt_directive": "Detect multi-touch trendline structures on price action candles. Upon a confirmed breakout through the trendline, reject immediate market chasing. Wait for a secondary pullback candle to touch and retest the broken trendline slope with rejection confirmation (wick rejection / price rejection). Execute Limit Order entry aligned with the breakout direction (CE on resistance breakout retest, PE on support breakdown retest). Seamlessly enforce defined Stop-Loss behind the retest swing pivot and target minimum 1:2 Risk-Reward ratio.",
        "parameters": {
            "min_trendline_touches": 3,
            "breakout_confirmation_candles": 1,
            "require_retest_touch": True,
            "retest_zone_tolerance_pts": 4.0,
            "rejection_wick_ratio_min": 0.35,
            "max_retest_candles": 5,
            "invalidation_below_pivot": True,
            "default_rr_ratio": 2.0,
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
        ('backtest', '0009_alter_backtestrule_rule_type_and_seed_rules'),
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
                    ('custom_prompt', 'AI Prompt Directive'),
                    ('technical', 'Technical / Indicator'),
                ],
                default='intraday',
                max_length=50,
            ),
        ),
        migrations.RunPython(seed_trendline_retest_rule, reverse_code=migrations.RunPython.noop),
    ]
