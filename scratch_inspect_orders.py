import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'marmot.settings')
django.setup()

from apps.admins.views import get_sandbox_simulated_orders
from django.contrib.auth import get_user_model

User = get_user_model()
user = User.objects.first()

orders = get_sandbox_simulated_orders(user_id=user.id)
if orders:
    print(orders[0])
    if len(orders) > 1:
        print(orders[1])
else:
    print("No orders found")
