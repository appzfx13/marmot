import os
import sys

sys.path.insert(0, '/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'marmot.settings')

import django
django.setup()

from django.test import Client
from django.contrib.auth import get_user_model
from apps.trade_config.models import TradeExecConfig
from apps.backtest.models import BacktestTask
from apps.market.models import MarketBackupTask
from apps.users.models import MemberRoleChoices
import re

User = get_user_model()
admin_user = User.objects.filter(is_superuser=True).first()
if not admin_user:
    admin_user = User.objects.create_superuser('testsuper', 'admin@example.com', 'password123')

client = Client()
client.force_login(admin_user)

urls_to_test = [
    ('/admins/trade-configs/create/', 'Trade Config Create'),
    ('/admins/traders/create/', 'Trader Create'),
    ('/market/backup/create/', 'Market Backup Create'),
    ('/backtest/create/', 'Backtest Create'),
]

config = TradeExecConfig.objects.first()
if config:
    urls_to_test.append((f'/admins/trade-configs/{config.pk}/', 'Trade Config Detail'))
    urls_to_test.append((f'/admins/trade-configs/{config.pk}/edit/', 'Trade Config Edit'))

trader = User.objects.filter(role=MemberRoleChoices.TRADERS).first()
if not trader:
    # If no TRADERS role user, temporarily create or set one for test
    trader = User.objects.filter(is_superuser=False).first()
    if trader:
        trader.role = MemberRoleChoices.TRADERS
        trader.save(update_fields=['role'])

if trader:
    urls_to_test.append((f'/admins/traders/{trader.pk}/', 'Trader Detail'))
    urls_to_test.append((f'/admins/traders/{trader.pk}/edit/', 'Trader Edit'))

backup = MarketBackupTask.objects.first()
if backup:
    urls_to_test.append((f'/market/backup/{backup.pk}/', 'Market Backup Detail'))

backtest = BacktestTask.objects.first()
if backtest:
    urls_to_test.append((f'/backtest/{backtest.pk}/', 'Backtest Detail'))

print(f"=== VERIFYING {len(urls_to_test)} FORM AND DETAIL PAGE HEADERS ===")
all_passed = True
for url, name in urls_to_test:
    resp = client.get(url)
    html = resp.content.decode('utf-8')
    has_top_bar_class = bool(re.search(r'class="[^"]*page-header-top-bar[^"]*"', html))
    has_left_group = ('d-flex align-items-center gap-3' in html) or ('page-title mb-1' in html) or ('page-title mb-0' in html)
    has_page_title = 'class="page-title' in html
    
    print(f"[{name}] URL: {url} | Status: {resp.status_code}")
    print(f"  Broken 'page-header-top-bar' element present: {has_top_bar_class}")
    print(f"  Left-aligned container: {has_left_group}")
    print(f"  Page-title present: {has_page_title}")
    if has_top_bar_class or not has_left_group or not has_page_title or resp.status_code != 200:
        all_passed = False
        print(f"  --> FAILED for {name}!")

if all_passed:
    print(f"\nALL {len(urls_to_test)} TESTED FORM & DETAIL HEADERS ARE CLEANLY LEFT-ALIGNED AND COMPLIANT!")
else:
    print("\nSOME HEADERS FAILED!")
    sys.exit(1)
