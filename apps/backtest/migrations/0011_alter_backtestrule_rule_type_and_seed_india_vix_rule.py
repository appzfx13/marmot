from django.db import migrations, models


def seed_india_vix_rule(apps, schema_editor):
    """Seed India VIX Volatility Regime Filter strategy rule."""
    BacktestRule = apps.get_model('backtest', 'BacktestRule')

    rule_data = {
        "name": "India VIX Volatility Regime & Momentum Filter (Dynamic IV Adaptation)",
        "rule_type": "india_vix",
        "description": "Incorporates date-matched India VIX volatility data into the RL decision policy. Adapts position sizing, strike selection (ITM vs OTM), and Risk-to-Reward targets across Low (<12), Normal (12-18), and High (>18) volatility regimes, preventing option decay traps in flat markets and capitalizing on momentum expansion.",
        "prompt_directive": "Evaluate date-matched India VIX volatility readings before trade validation. Only trigger option buying entries when India VIX is between 12.0 and 24.0, or during sudden intraday volatility expansion (> +3% daily surge) confirming institutional momentum. In low VIX environments (< 12.0), tighten Stop-Loss by 25% to avoid theta decay. In high VIX environments (> 18.0), expand target to 1:2.5 or 1:3 RR and choose ITM/ATM strikes to maximize delta and vega gain while avoiding high-decay far OTM options.",
        "parameters": {
            "min_vix_threshold": 12.0,
            "max_vix_threshold": 24.0,
            "vix_spike_momentum_trigger_pct": 3.0,
            "low_vix_sl_tighten_pct": 25.0,
            "high_vix_rr_expansion": 2.5,
            "high_vix_strike_bias": "ITM1",
            "date_matching_strict": True,
            "allow_vix_divergence_trades": True,
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
        ('backtest', '0010_alter_backtestrule_rule_type_and_seed_trendline_rule'),
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
                    ('custom_prompt', 'AI Prompt Directive'),
                    ('technical', 'Technical / Indicator'),
                ],
                default='intraday',
                max_length=50,
            ),
        ),
        migrations.RunPython(seed_india_vix_rule, reverse_code=migrations.RunPython.noop),
    ]
