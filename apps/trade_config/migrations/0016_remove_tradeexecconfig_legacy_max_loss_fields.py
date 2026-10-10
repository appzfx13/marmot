# Generated to drop orphaned database columns from legacy TradeExecConfig
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('trade_config', '0015_remove_livestrategy_frozen_rules_snapshot_and_more'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE trade_config_tradeexecconfig 
                DROP COLUMN IF EXISTS max_loss_percentage,
                DROP COLUMN IF EXISTS max_loss_reference,
                DROP COLUMN IF EXISTS max_loss_type;
            """,
            reverse_sql="",
        ),
    ]
