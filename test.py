import requests
import pandas as pd
from datetime import datetime

def test_unblocked_stream():
    """Independent pipeline diagnostic using chrome headers to smash the firewall"""
    print("📡 DISPATCHING STREAM PROTOCOLS (CHROME MASK)...")
    
    # Open historic data stream for BTC/USDT (15-minute intervals)
    url = "https://min-api.cryptocompare.com/data/v2/histo Replaced-with-minute?fsym=BTC&tsym=USDT&limit=5&e=CCCAGG"
    # Alternative direct endpoint if the above handles strict limits:
    url = "https://min-api.cryptocompare.com/data/v2/histohour?fsym=BTC&tsym=USDT&limit=5"
    
    # The Magic Shield: Browser emulation headers
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            raw_json = response.json()
            candle_array = raw_json["Data"]["Data"]
            
            parsed_rows = []
            for item in candle_array:
                parsed_rows.append({
                    "time": datetime.fromtimestamp(item["time"]).strftime('%H:%M:%S'),
                    "open": float(item["open"]),
                    "high": float(item["high"]),
                    "low": float(item["low"]),
                    "close": float(item["close"])
                })
            
            df = pd.DataFrame(parsed_rows)
            print("\n✅ MATRIX ACCESSED CLEANLY! PIPELINE ONLINE.")
            print("--------------------------------------------------")
            print(df)
            print("--------------------------------------------------")
        else:
            print(f"❌ REJECTION: Status Code {response.status_code}")
    except Exception as err:
        print(f"❌ PIPELINE CRASH: {err}")

if __name__ == "__main__":
    test_unblocked_stream()