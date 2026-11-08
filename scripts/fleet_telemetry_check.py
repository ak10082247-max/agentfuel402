import os
import json
import urllib.request

env_paths = [
    r"c:\Users\AK\Documents\money maker\.env",
    r"c:\Users\AK\Documents\money maker\.env.empire",
]

APIFY_TOKEN = None
for ep in env_paths:
    if os.path.exists(ep):
        with open(ep, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("APIFY_TOKEN="):
                    APIFY_TOKEN = line.strip().split("=", 1)[1].strip('"').strip("'")
                    break
    if APIFY_TOKEN:
        break

actors = [
    ('b2b-intent-leads-ppe', '2AbJGn42avqlwZo5V'),
    ('llm-clean-markdown-ppe', '2KWgMEUJOiSzDpxeW'),
    ('ecom-price-stock-ppe', 'JoVOb6vKPFaNhDDcj'),
    ('canaryguard-402', 'vtzNk9lbBdVUHGJKa'),
    ('rugshield-402', 'lb9cRH5Gbe5aw7Hqv'),
    ('reverse-engineer-anything', 'uOQ4jLOToRTwe10G1')
]

print("=== CURRENT APIFY FLEET TELEMETRY ===")
for name, act_id in actors:
    url = f"https://api.apify.com/v2/acts/{act_id}/runs?token={APIFY_TOKEN}&limit=100&desc=1"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req) as resp:
            items = json.loads(resp.read().decode())['data']['items']
            succeeded = sum(1 for r in items if r.get('status') == 'SUCCEEDED')
            failed = sum(1 for r in items if r.get('status') == 'FAILED')
            total = len(items)
            rate = (succeeded / total * 100.0) if total > 0 else 0
            print(f"{name:25} | Total Runs: {total:2} | Succeeded: {succeeded:2} | Failed: {failed:2} | Success Rate: {rate:5.1f}%")
    except Exception as e:
        print(f"{name}: error {e}")
