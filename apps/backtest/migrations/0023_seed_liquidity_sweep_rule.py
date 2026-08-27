from django.db import migrations


def seed_liquidity_sweep_rule(apps, schema_editor):
    BacktestRule = apps.get_model('backtest', 'BacktestRule')
    rule, created = BacktestRule.objects.get_or_create(
        rule_type='liquidity_sweep',
        defaults={
            'name': 'Liquidity Sweep & False Breakout Filter (SMC)',
            'market_type': 'FOREX_FUTURES',
            'prompt_directive': (
                'Add Rule: Apply Liquidity Sweep & False Breakout Filter (require >1.8x volume on breakout candles; fade false sweeps with 1:2.5 RR). '
                'Prohibit entering long/short breakouts when price sweeps previous swing highs/lows with extended rejection wicks (> 40% wick ratio) '
                'and closes back inside the prior range. Only validate breakout continuation if the breakout candle is backed by > 1.8x 20-period volume expansion '
                'with body ratio > 65%. When a liquidity trap is confirmed, trigger mean-reversion counter-entries targeting opposite swing liquidity with strict 1:2.5 Risk-to-Reward.'
            ),
            'description': (
                'Price swept a key swing high/low with an extended rejection wick (> 40%), trapping breakout buyers before reversing violently into resting stop pools. '
                'Detects and invalidates institutional liquidity sweeps (Turtle Soup / Stop Hunts) at key swing highs and lows. '
                'Mandates volume expansion (>1.8x SMA20) for breakout continuation and enables high-probability mean-reversion counter-trades when traps are confirmed.'
            ),
            'parameters': {
                'min_rejection_wick_ratio': 0.40,
                'min_breakout_volume_ratio': 1.80,
                'target_rr_sweep_reversal': 2.50,
                'min_candle_body_ratio': 0.65,
                'enable_fade_the_trap': True,
                'sweep_swing_lookback_bars': 20,
            },
            'is_active': True,
            'is_system_preset': True,
        }
    )
    if not created:
        rule.name = 'Liquidity Sweep & False Breakout Filter (SMC)'
        rule.market_type = 'FOREX_FUTURES'
        rule.prompt_directive = (
            'Add Rule: Apply Liquidity Sweep & False Breakout Filter (require >1.8x volume on breakout candles; fade false sweeps with 1:2.5 RR). '
            'Prohibit entering long/short breakouts when price sweeps previous swing highs/lows with extended rejection wicks (> 40% wick ratio) '
            'and closes back inside the prior range. Only validate breakout continuation if the breakout candle is backed by > 1.8x 20-period volume expansion '
            'with body ratio > 65%. When a liquidity trap is confirmed, trigger mean-reversion counter-entries targeting opposite swing liquidity with strict 1:2.5 Risk-to-Reward.'
        )
        rule.description = (
            'Price swept a key swing high/low with an extended rejection wick (> 40%), trapping breakout buyers before reversing violently into resting stop pools. '
            'Detects and invalidates institutional liquidity sweeps (Turtle Soup / Stop Hunts) at key swing highs and lows. '
            'Mandates volume expansion (>1.8x SMA20) for breakout continuation and enables high-probability mean-reversion counter-trades when traps are confirmed.'
        )
        rule.parameters = {
            'min_rejection_wick_ratio': 0.40,
            'min_breakout_volume_ratio': 1.80,
            'target_rr_sweep_reversal': 2.50,
            'min_candle_body_ratio': 0.65,
            'enable_fade_the_trap': True,
            'sweep_swing_lookback_bars': 20,
        }
        rule.is_active = True
        rule.is_system_preset = True
        rule.save()


def reverse_func(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('backtest', '0022_backtesttask_market_type'),
    ]

    operations = [
        migrations.RunPython(seed_liquidity_sweep_rule, reverse_func),
    ]
