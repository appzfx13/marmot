import os
import re
import time
from pathlib import Path


def fetch_tunnel_url(timeout=2, retries=6, delay=1):
    """Fetch public tunnel URL (Cloudflare Quick Tunnel or environment override)."""
    env_url = os.environ.get("CLOUDFLARE_TUNNEL_URL") or os.environ.get("TUNNEL_URL")
    if env_url:
        return env_url

    log_paths = [
        Path("/app/logs/cloudflared.log"),
        Path("/app/logs/cloudflared/cloudflared.log"),
        Path("logs/cloudflared.log"),
        Path(__file__).resolve().parent.parent.parent / "logs" / "cloudflared.log",
    ]

    for attempt in range(retries):
        for log_path in log_paths:
            if log_path.exists():
                try:
                    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    matches = re.findall(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", content)
                    if matches:
                        return matches[-1]
                except Exception:
                    pass
        if attempt < retries - 1:
            time.sleep(delay)
    return None


fetch_cloudflare_url = fetch_tunnel_url
fetch_ngrok_url = fetch_tunnel_url

