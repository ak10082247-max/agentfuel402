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

url = f"https://api.apify.com/v2/acts?token={APIFY_TOKEN}&limit=30"
req = urllib.request.Request(url)
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode())['data']
    items = data.get('items', [])
    print(f"Total actors on account: {len(items)}")
    for a in items:
        print(f"  ID: {a.get('id'):20} | Name: {a.get('name'):25} | Public: {a.get('isPublic')} | Created: {a.get('createdAt')}")
