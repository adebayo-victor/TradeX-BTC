import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from google import genai
from groq import Groq
import time
import json
import re
import requests # Added for News Fetching
import concurrent.futures
from datetime import datetime, timedelta

# ==========================================
# BLOCK 1: CONFIGURATION
# ==========================================
MT5_LOGIN = 435634528
MT5_PASSWORD = "Adebayo2@"
MT5_SERVER = "Exness-MT5Trial9"
MT5_PATH = "C:/Program Files/MetaTrader 5/terminal64.exe" 
SYMBOL = "BTCUSDm"           
MAGIC_NUMBER = 2026

# API KEYS
GEMINI_API_KEY = "AIzaSyAv6mXnbgTPLreluN_yqTJ5vXjNh5m7Htk"
GROQ_API_KEY = "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" 
NEWS_API_KEY = "1ad29d7351ef4869bc479232a266c3fa" # Get from newsapi.org

# Thresholds
LATENCY_LIMIT = 10.0     
PING_INTERVAL = 300     
MIN_KURTOSIS = 3.0      

# ==========================================
# BLOCK 2: SYSTEM DIAGNOSTICS
# ==========================================
def check_systems():
    if not mt5.initialize(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
        print(f"❌ MT5 CONNECTION FAILED: {mt5.last_error()}")
        return False
    print("✅ MT5 TERMINAL: ACTIVE")
    try:
        genai.Client(api_key=GEMINI_API_KEY)
        Groq(api_key=GROQ_API_KEY)
        print("✅ GOOGLE & GROQ SDKS: ACTIVE")
    except Exception as e:
        print(f"❌ API INITIALIZATION ERROR: {e}")
        return False
    return True

# ==========================================
# NEW FEATURE: FUNDAMENTAL NEWS WORKER
# ==========================================
def get_market_news():
    """Fetches top 3 impactful headlines for Gold/USD."""
    try:
        url = f"https://newsapi.org/v2/everything?q=Gold+AND+(Fed+OR+USD+OR+Inflation)&language=en&sortBy=publishedAt&pageSize=10&apiKey={NEWS_API_KEY}"
        response = requests.get(url, timeout=5)
        data = response.json()
        articles = data.get("articles", [])
        news_summary = ""
        for i, art in enumerate(articles):
            news_summary += f"{i+1}. {art['title']} ({art['description'][:100]}...)\n"
        return news_summary if news_summary else "No major news headlines found."
    except Exception as e:
        return f"News unavailable: {e}"

# ==========================================
# BLOCK 3: ATOMIC AI WORKERS (PARALLEL)
# ==========================================
def call_gemini_v3(prompt):
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(model="gemini-3-flash-preview", contents=prompt)
        raw = response.text.strip()
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        print(f"Bot1: {match}")
        return json.loads(match.group(0))
    except Exception as e: return {"prediction": "HOLD", "reason": f"Err: {e}", "sl": 0, "tp": 0}

def call_gemini_2_5(prompt):
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(model="gemini-2.5-pro", contents=prompt)
        raw = response.text.strip()
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        print(f"Bot2: {match}")
        return json.loads(match.group(0))
    except Exception as e: return {"prediction": "HOLD", "reason": f"Err: {e}", "sl": 0, "tp": 0}

def call_llama_ichimoku(prompt):
    try:
        client = Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role": "user", "content": prompt}])
        raw = response.choices[0].message.content.strip()
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        print(f"Bot3: {match}")
        return json.loads(match.group(0))
    except Exception as e: return {"prediction": "HOLD", "reason": f"Err: {e}", "sl": 0, "tp": 0}

# ==========================================
# BLOCK 4: EXECUTION & CONSENSUS
# ==========================================
def execute_trade(bias, lot, sl=0.0, tp=0.0):
    order_type = mt5.ORDER_TYPE_BUY if bias == "BUY" else mt5.ORDER_TYPE_SELL
    tick = mt5.symbol_info_tick(SYMBOL)
    price = tick.ask if bias == "BUY" else tick.bid
    
    sl = float(sl)
    tp = float(tp[0]) if hasattr(tp, "__len__") else float(tp)

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": float(lot),
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "magic": MAGIC_NUMBER,
        "comment": "GUIDED BULLET V7.3",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"❌ EXECUTION FAILED: {result.comment}")
    else:
        print(f"🚀 TRADE PLACED: {bias} {lot} lots at {price} | SL: {sl} | TP: {tp}")
    return result

def get_committee_consensus(tech_data):
    # INJECT NEWS INTO THE PROMPT
    prompt_base = (
        f"CONTEXT: BTCUSD past data for last 100 candles {tech_data}.\n"
        "price. Provide 1-sentence logic and JSON.\n"
        "Format: {'prediction': 'BUY/SELL/HOLD', 'reason': 'str', 'sl': float, 'tp': float}"
    )
    
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(call_gemini_v3, prompt_base): "G3",
            executor.submit(call_gemini_2_5, prompt_base): "G25",
            executor.submit(call_llama_ichimoku, prompt_base): "L33"
        }
        done, _ = concurrent.futures.wait(futures, timeout=LATENCY_LIMIT)
        for f in done:
            try:
                res = f.result()
                if res.get('prediction') != "HOLD": results.append(res)
            except: pass

    if not results: return "HOLD", 0.0, "Timeout", 0, 0

    preds = [r.get('prediction') for r in results]
    buy_v, sell_v = preds.count("BUY"), preds.count("SELL")
    
    final_bias = "HOLD"
    if buy_v > sell_v: final_bias = "BUY"
    elif sell_v > buy_v: final_bias = "SELL"
    
    if final_bias == "HOLD": return "HOLD", 0.0, "Neutral", 0, 0

    winning_bots = [r for r in results if r['prediction'] == final_bias]
    avg_sl = sum(r.get('sl', 0) for r in winning_bots) / len(winning_bots)
    raw_avg_tp = sum(r.get('tp', 0) for r in winning_bots) / len(winning_bots)
    current_price = tech_data['close']
    tp_distance = raw_avg_tp - current_price
    avg_tp = current_price + (tp_distance * 0.5) 
    
    lot_size = 0.05
    return final_bias, lot_size, f"Majority {final_bias}", avg_sl, avg_tp

# ==========================================
# BLOCK 5: MONITORING LOGIC
# ==========================================
def run_statistical_filter(df):
    returns = df['close'].pct_change().dropna().tail(50)
    k_val = returns.kurtosis() + 3
    return k_val > MIN_KURTOSIS, k_val

def monitor_trade(current_kurtosis):
    positions = mt5.positions_get(symbol=SYMBOL, magic=MAGIC_NUMBER)
    if not positions:
        return False

    for pos in positions:
        tick = mt5.symbol_info_tick(SYMBOL)
        if tick is None: continue
        current_price = tick.bid if pos.type == mt5.POSITION_TYPE_BUY else tick.ask
        
        if pos.type == mt5.POSITION_TYPE_BUY:
            price_distance = current_price - pos.price_open
        else:
            price_distance = pos.price_open - current_price

        threshold = 2.0 * current_kurtosis
        
        if price_distance >= threshold:
            buffer = max(1.5 * current_kurtosis, 0.3)
            
            if pos.type == mt5.POSITION_TYPE_BUY:
                calculated_sl = current_price - buffer
                new_sl = max(calculated_sl, pos.price_open + 0.10)
                if new_sl <= pos.sl: continue
            else:
                calculated_sl = current_price + buffer
                new_sl = min(calculated_sl, pos.price_open - 0.10)
                if pos.sl != 0 and new_sl >= pos.sl: continue

            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "symbol": SYMBOL,
                "sl": float(round(new_sl, 3)),
                "tp": pos.tp,
                "position": pos.ticket,
            }
            
            result = mt5.order_send(request)
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                log_msg = f"🛡️ MODIFICATION: Ticket {pos.ticket} SL moved to {new_sl:.3f} | Price Dist: {price_distance:.2f}"
                print(f"\n{log_msg}")
                with open("trading_logs.txt", "a", encoding="utf-8") as f:
                    f.write(f"{datetime.now()}: {log_msg}\n")
    return True

# ==========================================
# BLOCK 6: MASTER LOOP
# ==========================================
def run_snap_v7_live():
    if not check_systems(): return
    print("🚀 GUIDED BULLET V7.3 ACTIVE...")
    
    while True:
        rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_H1, 0, 100)
        if rates is None: continue
            
        df = pd.DataFrame(rates)
        is_active, kurt = run_statistical_filter(df)
        print(f"\n📡 [PING] {datetime.now().strftime('%H:%M:%S')} | Kurt: {kurt:.2f} | Gate: {'OPEN' if is_active else 'CLOSED'}")
        
        has_trade = monitor_trade(kurt)

        if is_active and not has_trade:
            print("📰 Fetching Global News...")
            #news_data = get_market_news()
            #print(f"🗞️ Top Headline: {news_data.splitlines()[0][:60]}...")
            
            print("🧠 Querying AI Committee...")
            bias, lot, reason, sl, tp = get_committee_consensus(rates)
            
            if bias != "HOLD":
                print(execute_trade(bias, lot, sl, tp))
                with open("trading_logs.txt", "a", encoding="utf-8") as f:
                    f.write(f"{datetime.now()}: OPENED {bias} | SL: {sl} | TP: {tp} | Reason: {reason}\n")

        # Dynamic Sleep Logic
        next_ping = datetime.now() + timedelta(seconds=PING_INTERVAL)
        while datetime.now() < next_ping:
            if monitor_trade(kurt):
                time.sleep(1)
                print(f"\r⚡ MONITORING ACTIVE POSITION... Kurt: {kurt:.2f}  ", end="", flush=True)
            else:
                rem = (next_ping - datetime.now()).total_seconds()
                print(f"\r⏳ Next Scan in: {int(rem)}s  ", end="", flush=True)
                time.sleep(1)

if __name__ == "__main__":
    run_snap_v7_live()