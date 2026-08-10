import json
import urllib.request
import urllib.error
import time


def fetch_ngrok_url(timeout=2, retries=5, delay=1):
    """Fetch public ngrok URL from local ngrok API endpoints."""
    endpoints = [
        "http://ngrok_tunnel:4040/api/tunnels",
        "http://ngrok:4040/api/tunnels",
        "http://127.0.0.1:4040/api/tunnels",
        "http://localhost:4040/api/tunnels",
    ]
    for attempt in range(retries):
        for endpoint in endpoints:
            try:
                req = urllib.request.Request(endpoint, headers={"User-Agent": "DjangoApp"})
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    if response.status == 200:
                        data = json.loads(response.read().decode("utf-8"))
                        tunnels = data.get("tunnels", [])
                        for tunnel in tunnels:
                            public_url = tunnel.get("public_url")
                            if public_url and public_url.startswith("https"):
                                return public_url
                        if tunnels and tunnels[0].get("public_url"):
                            return tunnels[0].get("public_url")
            except Exception:
                pass
        if attempt < retries - 1:
            time.sleep(delay)
    return None
