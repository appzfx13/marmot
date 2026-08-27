from django.db import migrations


def update_index_rules_market_type(apps, schema_editor):
    """Categorize Index/F&O specific preset rules under INDEX_FO market_type."""
    BacktestRule = apps.get_model('backtest', 'BacktestRule')

    index_rule_types = [
        'intraday',
        'gamma_blast',
        'morning_trend',
        'gap_openings',
        'india_vix',
        'pdh_pdl',
        'morning_macd_retest',
    ]

    BacktestRule.objects.filter(rule_type__in=index_rule_types).update(market_type='INDEX_FO')


class Migration(migrations.Migration):

    dependencies = [
        ('backtest', '0020_seed_forex_orderflow_rules'),
    ]

    operations = [
        migrations.RunPython(update_index_rules_market_type, reverse_code=migrations.RunPython.noop),
    ]
