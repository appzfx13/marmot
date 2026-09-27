import time
import urllib.request
import urllib.parse
import json

def post(url):
    req = urllib.request.Request(url, data=b'', method='POST')
    with urllib.request.urlopen(req) as resp:
        return resp.status, resp.read().decode('utf-8')

def get(url):
    req = urllib.request.Request(url, method='GET')
    with urllib.request.urlopen(req) as resp:
        return resp.status, resp.read().decode('utf-8')

# 1. Select file 1/13/dataset.parquet
code, body = post('http://127.0.0.1:8088/mock/api/streamer/select?file=1/13/dataset.parquet')
print("Select response:", code)

# 2. Set profile to HIGH_COMPRESS
code, body = post('http://127.0.0.1:8088/mock/api/streamer/profile?key=HIGH_COMPRESS')
print("Profile response:", code)

# 3. Start replay
code, body = post('http://127.0.0.1:8088/mock/api/streamer/restart')
print("Restart response:", code)

# Let it stream for 2.5 seconds
time.sleep(2.5)

# Check status
code, body = get('http://127.0.0.1:8088/mock/api/streamer/status')
status = json.loads(body)
print("Replay status:", status)

# Check option chain HTML from emulator
code, oc_html = get('http://127.0.0.1:8088/mock/dashboard/option-chain?index=NIFTY')
print("Option chain HTML length:", len(oc_html))

# Check for visible strikes and ATM
import re
strikes = re.findall(r'₹(\d{5})', oc_html)
print("Strikes present in HTML:", sorted(list(set(strikes))))

if "ATM" in oc_html:
    print("ATM badge found in HTML!")
if "Weekly Expiry" in oc_html or "18 JAN" in oc_html or "18 Jan" in oc_html:
    print("Weekly Expiry found in HTML!")

# Check Django live feed
try:
    code, df = get('http://127.0.0.1:8050/admins/dashboard/live-option-chain/?index=NIFTY')
    print("Django Live Option Chain status:", code, "Length:", len(df))
except Exception as e:
    print("Django check exception:", e)
