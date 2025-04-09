# cron_runner.py
import requests

try:
    res = requests.get("https://backend-4xju.onrender.com/daily-check")
    print("✅ Daily check response:", res.json())
except Exception as e:
    print("❌ Cron job failed:", e)
