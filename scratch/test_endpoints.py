import sys
import os

sys.path.insert(0, '/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'marmot.settings')

import django
django.setup()

from django.test import Client
from django.contrib.auth import get_user_model

User = get_user_model()
admin = User.objects.filter(is_superuser=True).first()
client = Client()
client.force_login(admin)

urls = [
    '/admins/dashboard/sandbox/',
    '/admins/dashboard/live/',
    '/admins/trade-configs/',
    '/admins/trade-configs/create/',
]

print("=== VERIFYING WEB ENDPOINTS ===")
for u in urls:
    resp = client.get(u)
    print(f"URL {u} -> HTTP {resp.status_code} (Length: {len(resp.content)} bytes)")
    assert resp.status_code in [200, 302], f"Failed with {resp.status_code}"

print("✅ All endpoints verified successfully!")
