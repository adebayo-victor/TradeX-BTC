import time
import threading
import os
import math
from datetime import datetime
import requests
import pandas as pd
import numpy as np
from flask import Flask, render_template_string

app = Flask(__name__)

# ====================================================================
# SYSTEM CONFIGURATION
# ====================================================================
SYMBOL = "BTCUSDT"          # Binance public counterpart for BTCUSDm
PING_INTERVAL = 15.0        # System heartbeat check clock
ADX_THRESHOLD = 20.0        # Customized lower timeframe trend gatekeeper

# Strategy Parameters (Preserving your exact original math setup)
MOMENTUM_PERIOD = 4
ATR_PERIOD = 14
ATR_MULTIPLIER = 2.5
TENKAN_PERIOD = 9
KIJUN_PERIOD = 26
SENKOU_PERIOD = 52
KUMO_SAFETY_MULT = 1.5

# Simulation Matrix Storage
SIMULATED_ACCOUNT = {
    "balance": 10000.0,
    "active_position": None,  # None, "BUY", or "SELL"
    "entry_price": 0.0,
    "open_time": None,
    "trade_history": []       # Stores profit, opening time, closing time, exposure time
}

TELEMETRY = {
    "timestamp": "INITIALIZING...",
    "price": 0.0,
    "m15_close": 0.0,
    "m15_mom": 0.0,
    "m15_adx": 0.0,
    "m15_tenkan": 0.0,
    "m15_kijun": 0.0,
    "h1_trend": "SCANNING 📡",
    "atr": 0.0,
    "h1_atr": 0.0,
    "status": "BOOTING CORE SYSTEMS...",
    "bias_h1_cloud": "❌ DISALIGNED",
    "bias_m15_cross": "❌ NO CROSS",
    "bias_m15_arch": "❌ FLAT",
    "bias_m15_mom": "❌ NO MOMENTUM",
    "bias_volatility": "❌ SECURE",
    "pos_active": "NONE 🏖️",
    "pos_entry": 0.0,
    "pos_pnl": 0.0,
    "h1_cloud_top": 0.0,
    "h1_cloud_bottom": 0.0,
    "tracking_mode": "M15 ADX + MOMENTUM SNIPER TRACK"
}

# ====================================================================
# STRATEGY MATH MATRIX (PURE INDEPENDENT PANDAS INDICATORS)
# ====================================================================
def calculate_ichimoku(df):
    df['tenkan'] = (df['high'].rolling(window=TENKAN_PERIOD).max() + df['low'].rolling(window=TENKAN_PERIOD).min()) / 2
    df['kijun'] = (df['high'].rolling(window=KIJUN_PERIOD).max() + df['low'].rolling(window=KIJUN_PERIOD).min()) / 2
    df['senkou_a'] = ((df['tenkan'] + df['kijun']) / 2).shift(KIJUN_PERIOD)
    df['senkou_b'] = ((df['high'].rolling(window=SENKOU_PERIOD).max() + df['low'].rolling(window=SENKOU_PERIOD).min()) / 2).shift(KIJUN_PERIOD)
    return df

def calculate_atr(df):
    high_low = df['high'] - df['low']
    high_cp = np.abs(df['high'] - df['close'].shift(1))
    low_cp = np.abs(df['low'] - df['close'].shift(1))
    df['atr'] = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1).rolling(window=ATR_PERIOD).mean()
    return df

def calculate_adx(df, period=14):
    """Computes accurate ADX trend strength to safeguard lookback noise"""
    df['up_move'] = df['high'] - df['high'].shift(1)
    df['down_move'] = df['low'].shift(1) - df['low']
    
    df['+dm'] = np.where((df['up_move'] > df['down_move']) & (df['up_move'] > 0), df['up_move'], 0.0)
    df['-dm'] = np.where((df['down_move'] > df['up_move']) & (df['down_move'] > 0), df['down_move'], 0.0)
    
    # Calculate True Range components
    high_low = df['high'] - df['low']
    high_cp = np.abs(df['high'] - df['close'].shift(1))
    low_cp = np.abs(df['low'] - df['close'].shift(1))
    df['tr'] = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1)
    
    df['atr_smooth'] = df['tr'].rolling(window=period).mean()
    df['+di'] = 100 * (df['+dm'].rolling(window=period).mean() / df['atr_smooth'])
    df['-di'] = 100 * (df['-dm'].rolling(window=period).mean() / df['atr_smooth'])
    
    df['dx'] = 100 * (np.abs(df['+di'] - df['-di']) / (df['+di'] + df['-di'] + 1e-5))
    df['adx'] = df['dx'].rolling(window=period).mean()
    return df

def fetch_binance_candles(interval, limit=100):
    """Pulls historical candle streams cleanly using an unblocked data pipeline"""
    # Mapping Binance intervals to CryptoCompare endpoint targets
    timeframe_map = {
        "15m": "histominute",
        "1h": "histohour",
        "4h": "histohour"
    }
    tf_target = timeframe_map.get(interval, "histominute")
    
    # Adjust multiplier specifically for 4-hour requests since CryptoCompare uses hourly blocks
    fetch_limit = limit
    if interval == "4h":
        fetch_limit = limit * 4
        
    url = f"https://min-api.cryptocompare.com/data/v2/{tf_target}?fsym=BTC&tsym=USDT&limit={fetch_limit}"
    
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
                    "time": int(item["time"] * 1000), # Standardize to JS epoch timestamp format
                    "open": float(item["open"]),
                    "high": float(item["high"]),
                    "low": float(item["low"]),
                    "close": float(item["close"]),
                    "volume": float(item["volumefrom"])
                })
            
            df = pd.DataFrame(parsed_rows)
            
            # Resample hourly blocks into clear 4-Hour blocks if requested
            if interval == "4h":
                df['datetime'] = pd.to_datetime(df['time'], unit='ms')
                df.set_index('datetime', inplace=True)
                df = df.resample('4H').agg({
                    'time': 'first',
                    'open': 'first',
                    'high': 'max',
                    'low': 'min',
                    'close': 'last',
                    'volume': 'sum'
                }).dropna().reset_index(drop=True)
                
            return df.tail(limit)
        else:
            return pd.DataFrame()
    except Exception:
        return pd.DataFrame()

# ====================================================================
# BACKGROUND EXECUTION CORE ENGINE
# ====================================================================
def strategy_execution_worker():
    global TELEMETRY, SIMULATED_ACCOUNT
    
    last_processed_bar_time = 0
    
    while True:
        try:
            # Fetch MTF candle matrices via API
            df_h4 = calculate_atr(calculate_ichimoku(fetch_binance_candles("4h")))
            df_h1 = calculate_atr(calculate_ichimoku(fetch_binance_candles("1h")))
            df_m15 = calculate_adx(calculate_atr(calculate_ichimoku(fetch_binance_candles("15m"))))
            
            if len(df_h4) < 60 or len(df_h1) < 60 or len(df_m15) < 60:
                TELEMETRY["status"] = "SYNCHRONIZING WITH API LIQUIDITY FIELDS..."
                time.sleep(5)
                continue
                
            # Current price ticker simulation
            current_price = df_m15.iloc[-1]['close']
            TELEMETRY["price"] = current_price
            TELEMETRY["timestamp"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Extract target triggers (Using index shifts exactly mimicking your MT5 script)
            trigger_bar = df_m15.iloc[-2]
            prev_bar = df_m15.iloc[-3]
            h1_trigger = df_h1.iloc[-2]
            h1_prev_bar = df_h1.iloc[-3]
            h4_trigger = df_h4.iloc[-2]
            
            # Populating exact variables into Telemetry HUD Matrix
            TELEMETRY["m15_close"] = trigger_bar['close']
            TELEMETRY["m15_mom"] = trigger_bar['close'] - df_m15.iloc[-2 - MOMENTUM_PERIOD]['close']
            TELEMETRY["m15_adx"] = trigger_bar['adx']
            TELEMETRY["m15_tenkan"] = trigger_bar['tenkan']
            TELEMETRY["m15_kijun"] = trigger_bar['kijun']
            TELEMETRY["atr"] = trigger_bar['atr']
            TELEMETRY["h1_atr"] = h1_trigger['atr']
            
            # H4 Cloud Boundaries (Your macro anchor)
            cloud_top = max(h4_trigger['senkou_a'], h4_trigger['senkou_b'])
            cloud_bottom = min(h4_trigger['senkou_a'], h4_trigger['senkou_b'])
            TELEMETRY["h1_cloud_top"] = cloud_top
            TELEMETRY["h1_cloud_bottom"] = cloud_bottom
            
            safety_buffer = h4_trigger['atr'] * KUMO_SAFETY_MULT
            h4_bullish_clear = h4_trigger['close'] > (cloud_top + safety_buffer)
            h4_bearish_clear = h4_trigger['close'] < (cloud_bottom - safety_buffer)
            
            # Handle Macro Trend Diagnostic Strings
            if h4_bullish_clear:
                TELEMETRY["h1_trend"] = "🔥 STRONG BULLISH (CLEAR OF H4 KUMO)"
                TELEMETRY["bias_h1_cloud"] = "✅ MATCHED [BUY BIAS]"
            elif h4_bearish_clear:
                TELEMETRY["h1_trend"] = "❄️ STRONG BEARISH (CLEAR OF H4 KUMO)"
                TELEMETRY["bias_h1_cloud"] = "✅ MATCHED [SELL BIAS]"
            else:
                TELEMETRY["h1_trend"] = "💀 INSIDE SAFETY CLOUD ZONE / CONSOLIDATION"
                TELEMETRY["bias_h1_cloud"] = "❌ DISALIGNED"

            # Execution Layer Cross Bias Checks
            if trigger_bar['tenkan'] > trigger_bar['kijun']:
                TELEMETRY["bias_m15_cross"] = "🟩 TENKAN > KIJUN (BULLISH)"
            elif trigger_bar['tenkan'] < trigger_bar['kijun']:
                TELEMETRY["bias_m15_cross"] = "🟥 TENKAN < KIJUN (BEARISH)"
            else:
                TELEMETRY["bias_m15_cross"] = "⬜ SQUEEZE EQUILIBRIUM"
                
            m15_lines_up = trigger_bar['tenkan'] > prev_bar['tenkan']
            m15_lines_down = trigger_bar['tenkan'] < prev_bar['tenkan']
            
            if m15_lines_up:
                TELEMETRY["bias_m15_arch"] = "🟩 STEEP HOOK UPWARD"
            elif m15_lines_down:
                TELEMETRY["bias_m15_arch"] = "🟥 STEEP HOOK DOWNWARD"
            else:
                TELEMETRY["bias_m15_arch"] = "⬜ NO VELOCITY (FLAT)"
                
            if TELEMETRY["m15_mom"] > 0:
                TELEMETRY["bias_m15_mom"] = f"🟩 POSITIVE (+{TELEMETRY['m15_mom']:.2f})"
            elif TELEMETRY["m15_mom"] < 0:
                TELEMETRY["bias_m15_mom"] = f"🟥 NEGATIVE ({TELEMETRY['m15_mom']:.2f})"
                
            candle_range = trigger_bar['high'] - trigger_bar['low']
            is_news = candle_range > (trigger_bar['atr'] * ATR_MULTIPLIER)
            
            if is_news:
                TELEMETRY["bias_volatility"] = "🚨 BLOCKED: NEWS SPIKE VOLATILITY"
            else:
                TELEMETRY["bias_volatility"] = "✅ SECURE (STABLE ATR STRUCTURE)"

            # ================================================================
            # EXPOSURE TRACKING SIMULATION ENGINE
            # ================================================================
            current_bar_time = df_m15.iloc[-1]['time']
            active_type = SIMULATED_ACCOUNT["active_position"]
            
            if active_type is not None:
                # Track floating real-time calculations
                exposure_duration = time.time() - SIMULATED_ACCOUNT["open_time"]
                
                pnl = 0.0
                if active_type == "BUY":
                    pnl = current_price - SIMULATED_ACCOUNT["entry_price"]
                elif active_type == "SELL":
                    pnl = SIMULATED_ACCOUNT["entry_price"] - current_price
                    
                TELEMETRY["pos_active"] = f"{active_type} 🟢" if active_type == "BUY" else f"{active_type} 🔴"
                TELEMETRY["pos_entry"] = SIMULATED_ACCOUNT["entry_price"]
                TELEMETRY["pos_pnl"] = pnl
                
                # --- HIGH SENSITIVITY EXIT VECTOR INTEGRATING M15 ADX TWEAK ---
                flush_triggered = False
                if active_type == "BUY":
                    if TELEMETRY["m15_mom"] < 0 and TELEMETRY["m15_adx"] > ADX_THRESHOLD:
                        flush_triggered = True
                elif active_type == "SELL":
                    if TELEMETRY["m15_mom"] > 0 and TELEMETRY["m15_adx"] > ADX_THRESHOLD:
                        flush_triggered = True
                        
                if flush_triggered:
                    closing_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    opening_time_str = datetime.fromtimestamp(SIMULATED_ACCOUNT["open_time"]).strftime('%Y-%m-%d %H:%M:%S')
                    
                    # Store exact performance metric arrays requested
                    trade_record = {
                        "profit": pnl,
                        "open_time": opening_time_str,
                        "close_time": closing_time_str,
                        "exposure_time": f"{int(exposure_duration)} seconds"
                    }
                    SIMULATED_ACCOUNT["trade_history"].append(trade_record)
                    SIMULATED_ACCOUNT["balance"] += pnl
                    
                    # Reset storage variables
                    SIMULATED_ACCOUNT["active_position"] = None
                    SIMULATED_ACCOUNT["entry_price"] = 0.0
                    SIMULATED_ACCOUNT["open_time"] = None
                    
                    TELEMETRY["status"] = f"⚡ ADX FLUSH COMPLETED. PNL RECORDED: ${pnl:.2f}"
            else:
                TELEMETRY["pos_active"] = "NONE 🏖️"
                TELEMETRY["pos_entry"] = 0.0
                TELEMETRY["pos_pnl"] = 0.0
                
                # Check for entry triggers over bar transitions
                if current_bar_time != last_processed_bar_time and not is_news:
                    # BUY DISPATCH
                    if h4_bullish_clear and TELEMETRY["m15_mom"] > 0 and m15_lines_up:
                        if trigger_bar['tenkan'] > trigger_bar['kijun'] and trigger_bar['close'] > trigger_bar['open']:
                            SIMULATED_ACCOUNT["active_position"] = "BUY"
                            SIMULATED_ACCOUNT["entry_price"] = current_price
                            SIMULATED_ACCOUNT["open_time"] = time.time()
                            last_processed_bar_time = current_bar_time
                            TELEMETRY["status"] = f"🟩 SIMULATED LONG DISPATCHED AT ${current_price:.2f}"
                            
                    # SELL DISPATCH
                    elif h4_bearish_clear and TELEMETRY["m15_mom"] < 0 and m15_lines_down:
                        if trigger_bar['tenkan'] < trigger_bar['kijun'] and trigger_bar['close'] < trigger_bar['open']:
                            SIMULATED_ACCOUNT["active_position"] = "SELL"
                            SIMULATED_ACCOUNT["entry_price"] = current_price
                            SIMULATED_ACCOUNT["open_time"] = time.time()
                            last_processed_bar_time = current_bar_time
                            TELEMETRY["status"] = f"🟥 SIMULATED SHORT DISPATCHED AT ${current_price:.2f}"
                    else:
                        TELEMETRY["status"] = "👀 STANDING BY FOR REASONING MATRIX CROSSOVER OUTCOME..."

        except Exception as err:
            TELEMETRY["status"] = f"⚠️ API Interface Pipeline Error: {err}"
            
        time.sleep(PING_INTERVAL)

# ====================================================================
# WEB MOBILE HUD TEMPLATE LAYER
# ====================================================================
HTML_UI = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Techlite Tremor Dashboard</title>
    <style>
        body { background-color: #0d0e15; color: #e1e1e6; font-family: monospace; margin: 0; padding: 15px; }
        .wrapper { max-width: 650px; margin: 0 auto; border: 1px solid #3a3f58; padding: 10px; background: #090a0f; }
        .banner { text-align: center; color: #a15eff; font-weight: bold; font-size: 16px; border-bottom: 1px dashed #3a3f58; padding-bottom: 8px; margin-bottom: 15px; }
        .metric-group { margin-bottom: 12px; border: 1px solid #222533; padding: 8px; background: #12141f; }
        .title { color: #00ffff; font-weight: bold; font-size: 12px; text-transform: uppercase; margin-bottom: 4px; }
        .value { font-size: 14px; margin-left: 8px; margin-bottom: 4px; }
        .green { color: #50fa7b; } .red { color: #ff5555; } .yellow { color: #f1fa8c; }
        .table-box { max-height: 200px; overflow-y: auto; font-size: 11px; }
        table { width: 100%; border-collapse: collapse; margin-top: 5px; }
        th, td { border: 1px solid #282a36; padding: 5px; text-align: left; }
        th { background: #1a1c29; color: #6272a4; }
    </style>
    <script>
        // Automatic 15-Second Precision Fetch Engine
        async function updateTelemetry() {
            try {
                const response = await fetch('/api/telemetry');
                const data = await response.json();
                
                // Update text elements across the DOM matrix
                document.getElementById('timestamp').innerText = data.tel.timestamp;
                document.getElementById('price').innerText = '$' + data.tel.price.toFixed(2);
                document.getElementById('m15_close').innerText = '$' + data.tel.m15_close.toFixed(2);
                document.getElementById('m15_mom').innerText = data.tel.m15_mom.toFixed(4);
                document.getElementById('m15_adx').innerText = data.tel.m15_adx.toFixed(1);
                document.getElementById('m15_tk').innerText = data.tel.m15_tenkan.toFixed(2) + ' / ' + data.tel.m15_kijun.toFixed(2);
                
                document.getElementById('h4_trend').innerText = data.tel.h1_trend;
                document.getElementById('bias_h4').innerText = data.tel.bias_h1_cloud;
                document.getElementById('bias_cross').innerText = data.tel.bias_m15_cross;
                document.getElementById('bias_arch').innerText = data.tel.bias_m15_arch;
                document.getElementById('bias_mom').innerText = data.tel.bias_m15_mom;
                document.getElementById('bias_vol').innerText = data.tel.bias_volatility;
                
                document.getElementById('pos_active').innerText = data.tel.pos_active;
                document.getElementById('pos_entry').innerText = '$' + data.tel.pos_entry.toFixed(2);
                
                const pnlEl = document.getElementById('pos_pnl');
                pnlEl.innerText = '$' + data.tel.pos_pnl.toFixed(2);
                if (data.tel.pos_pnl >= 0) {
                    pnlEl.className = 'green';
                } else {
                    pnlEl.className = 'red';
                }
                
                document.getElementById('status').innerText = data.tel.status;
                document.getElementById('balance').innerText = '$' + data.acc.balance.toFixed(2);
                
                // Re-render execution history rows asynchronously
                let tableHtml = '';
                const reversedHistory = data.acc.trade_history.slice().reverse();
                reversedHistory.forEach(trade => {
                    const profitClass = trade.profit >= 0 ? 'green' : 'red';
                    tableHtml += `<tr>
                        <td>\${trade.open_time}</td>
                        <td>\${trade.close_time}</td>
                        <td class="yellow">\${trade.exposure_time}</td>
                        <td class="\${profitClass}">\$\${trade.profit.toFixed(2)}</td>
                    </tr>`;
                });
                document.getElementById('history_rows').innerHTML = tableHtml;
                
            } catch (err) {
                console.error("Telemetry fetch interruption:", err);
            }
        }
        setInterval(updateTelemetry, 15000); // 15000ms = 15 seconds synchronization lock
    </script>
</head>
<body>
    <div class="wrapper">
        <div class="banner">🪐 TECHLITE TREMOR SPECTRAL COMMAND WEB HUD</div>
        <div style="font-size: 11px; color: #6272a4; text-align: center; margin-bottom: 15px;">
            RUNTIME TELEMETRY TICK: <span id="timestamp">{{ tel.timestamp }}</span>
        </div>

        <div class="metric-group">
            <div class="title">[TARGET ASSET DATA]</div>
            <div class="value">SYMBOL: <span class="yellow">{{ symbol }}</span> | SPOT PRICE: <span id="price" class="green">${{ "%.2f"|format(tel.price) }}</span></div>
        </div>

        <div class="metric-group">
            <div class="title">[ACTIVE EXPOSURE TRACKER PROFILE]</div>
            <div class="value">POSITION STATE: <span id="pos_active" class="yellow">{{ tel.pos_active }}</span></div>
            <div class="value">ENTRY VECTOR  : <span id="pos_entry">${{ "%.2f"|format(tel.pos_entry) }}</span></div>
            <div class="value">FLOATING PNL  : <span id="pos_pnl" class="{% if tel.pos_pnl >= 0 %}green{% else %}red{% endif %}">${{ "%.2f"|format(tel.pos_pnl) }}</span></div>
        </div>

        <div class="metric-group">
            <div class="title">[QUANT SPECS - LOWER TIMEFRAME M15 LAYER]</div>
            <div class="value">M15 CLOSE: <span id="m15_close">${{ "%.2f"|format(tel.m15_close) }}</span> | MOMENTUM: <span id="m15_mom">{{ "%.4f"|format(tel.m15_mom) }}</span></div>
            <div class="value">TREND ADX : <span id="m15_adx" class="green">{{ "%.1f"|format(tel.m15_adx) }}</span> / {{ threshold }} (GATEKEEPER)</div>
            <div class="value">TENKAN/KIJUN: <span id="m15_tk">{{ "%.2f"|format(tel.m15_tenkan) }} / {{ "%.2f"|format(tel.m15_kijun) }}</span></div>
        </div>

        <div class="metric-group">
            <div class="title">[🧬 INTERLOCK MTF STRATEGY DIAGNOSTICS]</div>
            <div class="value">H4 CLOUD ALIGNMENT ➡️ <span id="bias_h4">{{ tel.bias_h1_cloud }}</span></div>
            <div class="value">M15 CROSSOVER STATE ➡️ <span id="bias_cross">{{ tel.bias_m15_cross }}</span></div>
            <div class="value">M15 LINE SHARP ARCH ➡️ <span id="bias_arch">{{ tel.bias_m15_arch }}</span></div>
            <div class="value">M15 DYNAMIC MOMENTUM ➡️ <span id="bias_mom">{{ tel.bias_m15_mom }}</span></div>
            <div class="value">VOLATILITY SHIELD    ➡️ <span id="bias_vol">{{ tel.bias_volatility }}</span></div>
        </div>

        <div class="metric-group">
            <div class="title">🤖 [ENGINE INTERACTION MESSAGE]</div>
            <div class="value yellow" id="status">{{ tel.status }}</div>
        </div>

        <div class="metric-group">
            <div class="title">💳 ACCOUNT MATRIX BALANCE: <span id="balance" class="green">${{ "%.2f"|format(acc.balance) }}</span></div>
        </div>

        <div class="metric-group">
            <div class="title">📜 PERSISTENT EXPOSURE EXECUTIONS LOG</div>
            <div class="table-box">
                <table>
                    <thead>
                        <tr>
                            <th>OPEN TIME</th>
                            <th>CLOSE TIME</th>
                            <th>DURATION</th>
                            <th>PROFIT ($)</th>
                        </tr>
                    </thead>
                    <tbody id="history_rows">
                        {% for trade in acc.trade_history[::-1] %}
                        <tr>
                            <td>{{ trade.open_time }}</td>
                            <td>{{ trade.close_time }}</td>
                            <td class="yellow">{{ trade.exposure_time }}</td>
                            <td class="{% if trade.profit >= 0 %}green{% else %}red{% endif %}">${{ "%.2f"|format(trade.profit) }}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
</body>
</html>
"""
@app.route("/")
def dashboard():
    return render_template_string(HTML_UI, tel=TELEMETRY, acc=SIMULATED_ACCOUNT, symbol=SYMBOL, threshold=ADX_THRESHOLD)
@app.route("/api/telemetry")
def api_telemetry():
    return {
        "tel": TELEMETRY,
        "acc": SIMULATED_ACCOUNT
    }

if __name__ == "__main__":
    threading.Thread(target=strategy_execution_worker, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))