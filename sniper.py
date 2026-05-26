'''import time
import sys
import logging
import threading
from datetime import datetime
import MetaTrader5 as mt5
import pandas as pd
import numpy as np

# ====================================================================
# SYSTEM CONFIGURATION
# ====================================================================
MT5_LOGIN = 435634528
MT5_PASSWORD = "Adebayo2@"
MT5_SERVER = "Exness-MT5Trial9"
SYMBOL = "BTCUSDm"
MAGIC_NUMBER = 20260521  

# Dynamic Sizing Matrix Tiers
LOT_SCOUT = 0.05
LOT_STANDARD = 0.10
LOT_SPECTRAL_OVERDRIVE = 0.25

# Strategy Parameters
MOMENTUM_PERIOD = 4
ATR_PERIOD = 14
ATR_MULTIPLIER = 2.5
TENKAN_PERIOD = 9
KIJUN_PERIOD = 26
SENKOU_PERIOD = 52
KUMO_SAFETY_MULT = 1.5     # 1.5x ATR dynamic buffer protection shield

# High-Sensitivity M1 Momentum Trailing Configuration
M1_MOMENTUM_THRESHOLD = 10.00  # Exit threshold if M1 closes against position

BOT_RUNNING = True

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("techlite_spectral_matrix.log")]
)

TELEMETRY = {
    "ask": 0.0, "bid": 0.0, "spread": 0, "tick_dir": "⚡",
    "color_code": "\033[1;37m",  
    "m15_close": 0.0, "m15_mom": 0.0, "m15_tenkan": 0.0, "m15_kijun": 0.0,
    "h1_trend": "SCANNING 📡", "atr": 0.0, "h1_atr": 0.0, "status": "BOOTING CORE SYSTEMS...",
    "bias_h1_cloud": "❌ DISALIGNED",
    "bias_m15_cross": "❌ NO CROSS",
    "bias_m15_arch": "❌ FLAT",
    "bias_m15_mom": "❌ NO MOMENTUM",
    "bias_volatility": "❌ SECURE",
    "pos_active": "NONE 🏖️",
    "pos_pnl": 0.0,
    "pos_pnl_color": "\033[1;37m",
    "pos_entry": 0.0,
    "h1_cloud_top": 0.0,       
    "h1_cloud_bottom": 0.0,
    "h1_tenkan": 0.0,
    "h1_prev_tenkan": 0.0,
    "tracking_mode": "M1 MOMENTUM SNIPER TRACK",
    "m1_momentum": 0.0,
    "active_lot_size": 0.0
}

# ====================================================================
# BACKGROUND ENGINE 1: ASYNC REAL-TIME TICK FLUCTUATION STREAM
# ====================================================================
def tick_fluctuation_stream():
    global TELEMETRY, BOT_RUNNING
    while BOT_RUNNING:
        tick = mt5.symbol_info_tick(SYMBOL)
        if tick is not None:
            old_ask = TELEMETRY["ask"]
            TELEMETRY["ask"] = tick.ask
            TELEMETRY["bid"] = tick.bid
            TELEMETRY["spread"] = int((tick.ask - tick.bid) / mt5.symbol_info(SYMBOL).point)
            
            if tick.ask > old_ask:
                TELEMETRY["tick_dir"] = "🔺"
                TELEMETRY["color_code"] = "\033[1;32m"  
            elif tick.ask < old_ask:
                TELEMETRY["tick_dir"] = "🔻"
                TELEMETRY["color_code"] = "\033[1;31m"  
        time.sleep(0.1) 

# ====================================================================
# BACKGROUND ENGINE 2: STRATEGY MATRIX & CORE CALCULATIONS
# ====================================================================
def calculate_ichimoku(df, tenkan_p, kijun_p, senkou_p):
    df['tenkan'] = (df['high'].rolling(window=tenkan_p).max() + df['low'].rolling(window=tenkan_p).min()) / 2
    df['kijun'] = (df['high'].rolling(window=kijun_p).max() + df['low'].rolling(window=kijun_p).min()) / 2
    df['senkou_a'] = ((df['tenkan'] + df['kijun']) / 2).shift(kijun_p)
    df['senkou_b'] = ((df['high'].rolling(window=senkou_p).max() + df['low'].rolling(window=senkou_p).min()) / 2).shift(kijun_p)
    return df

def calculate_atr(df, period):
    high_low = df['high'] - df['low']
    high_cp = np.abs(df['high'] - df['close'].shift(1))
    low_cp = np.abs(df['low'] - df['close'].shift(1))
    df['atr'] = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1).rolling(window=period).mean()
    return df

def execution_logic_engine():
    global TELEMETRY, BOT_RUNNING
    threading.current_thread().name = "StrategyEngine"
    
    last_processed_bar_time = 0
    
    while BOT_RUNNING:
        m15_bars = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M15, 0, 100)
        h1_bars = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_H1, 0, 100)
        m1_bars = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M1, 0, 10)
        
        if m15_bars is None or h1_bars is None or m1_bars is None or len(m15_bars) < 60 or len(h1_bars) < 60 or len(m1_bars) < 5:
            TELEMETRY["status"] = "SYNCHRONIZING WITH MT5 LIQUIDITY POOLS..."
            time.sleep(2)
            continue
            
        df_m15 = calculate_atr(calculate_ichimoku(pd.DataFrame(m15_bars), TENKAN_PERIOD, KIJUN_PERIOD, SENKOU_PERIOD), ATR_PERIOD)
        df_h1 = calculate_atr(calculate_ichimoku(pd.DataFrame(h1_bars), TENKAN_PERIOD, KIJUN_PERIOD, SENKOU_PERIOD), ATR_PERIOD)
        df_m1 = pd.DataFrame(m1_bars)
        
        # Calculate Completed M1 Candle Momentum
        m1_momentum = df_m1.iloc[-2]['close'] - df_m1.iloc[-6]['close']
        TELEMETRY["m1_momentum"] = m1_momentum
        
        current_bar_time = df_m15.iloc[-1]['time']
        trigger_bar = df_m15.iloc[-2]
        prev_bar = df_m15.iloc[-3]
        h1_trigger = df_h1.iloc[-2]
        h1_prev_bar = df_h1.iloc[-3]
        
        TELEMETRY["m15_close"] = trigger_bar['close']
        TELEMETRY["m15_mom"] = trigger_bar['close'] - df_m15.iloc[-2 - MOMENTUM_PERIOD]['close']
        TELEMETRY["m15_tenkan"] = trigger_bar['tenkan']
        TELEMETRY["m15_kijun"] = trigger_bar['kijun']
        TELEMETRY["atr"] = trigger_bar['atr']
        TELEMETRY["h1_atr"] = h1_trigger['atr']
        TELEMETRY["h1_tenkan"] = h1_trigger['tenkan']
        TELEMETRY["h1_prev_tenkan"] = h1_prev_bar['tenkan']
        
        cloud_top = max(h1_trigger['senkou_a'], h1_trigger['senkou_b'])
        cloud_bottom = min(h1_trigger['senkou_a'], h1_trigger['senkou_b'])
        TELEMETRY["h1_cloud_top"] = cloud_top
        TELEMETRY["h1_cloud_bottom"] = cloud_bottom
        
        safety_buffer = h1_trigger['atr'] * KUMO_SAFETY_MULT
        
        h1_bullish_clear = h1_trigger['close'] > (cloud_top + safety_buffer)
        h1_bearish_clear = h1_trigger['close'] < (cloud_bottom - safety_buffer)
        
        if h1_bullish_clear:
            TELEMETRY["h1_trend"] = "🔥 STRONG BULLISH (CLEAR OF KUMO)"
            TELEMETRY["bias_h1_cloud"] = "✅ MATCHED [BUY BIAS]"
        elif h1_bearish_clear:
            TELEMETRY["h1_trend"] = "❄️ STRONG BEARISH (CLEAR OF KUMO)"
            TELEMETRY["bias_h1_cloud"] = "✅ MATCHED [SELL BIAS]"
        else:
            TELEMETRY["h1_trend"] = "💀 CHOPPENING DETECTED / INSIDE SAFETY CLOUD ZONE"
            TELEMETRY["bias_h1_cloud"] = "❌ DISALIGNED [INSIDE SAFETY BUFFER]"

        if trigger_bar['tenkan'] > trigger_bar['kijun']:
            TELEMETRY["bias_m15_cross"] = "🟩 TENKAN > KIJUN (BULLISH)"
        elif trigger_bar['tenkan'] < trigger_bar['kijun']:
            TELEMETRY["bias_m15_cross"] = "🟥 TENKAN < KIJUN (BEARISH)"
        else:
            TELEMETRY["bias_m15_cross"] = "⬜ EQUILIBRIUM SQUEEZE"
            
        m15_lines_up = trigger_bar['tenkan'] > prev_bar['tenkan']
        m15_lines_down = trigger_bar['tenkan'] < prev_bar['tenkan']
        
        if m15_lines_up:
            TELEMETRY["bias_m15_arch"] = "🟩 STEEP HOOK UPWARD"
        elif m15_lines_down:
            TELEMETRY["bias_m15_arch"] = "🟥 STEEP HOOK DOWNWARD"
        else:
            TELEMETRY["bias_m15_arch"] = "⬜ NO VELOCITY (FLAT LINES)"
            
        if TELEMETRY["m15_mom"] > 0:
            TELEMETRY["bias_m15_mom"] = f"🟩 POSITIVE (+{TELEMETRY['m15_mom']:.2f})"
        elif TELEMETRY["m15_mom"] < 0:
            TELEMETRY["bias_m15_mom"] = f"🟥 NEGATIVE ({TELEMETRY['m15_mom']:.2f})"
            
        candle_range = trigger_bar['high'] - trigger_bar['low']
        is_news = candle_range > (trigger_bar['atr'] * ATR_MULTIPLIER)
        
        if is_news:
            TELEMETRY["bias_volatility"] = "🚨 BLOCKED: NEWS SPIKE BREAKOUT"
        else:
            TELEMETRY["bias_volatility"] = "✅ SECURE (STABLE ATR STRUCTURE)"

        positions = mt5.positions_get(symbol=SYMBOL, magic=MAGIC_NUMBER)
        
        if len(positions) > 0:
            active_position = positions[0]
            TELEMETRY["active_lot_size"] = active_position.volume
            
            # --- HIGH-SENSITIVITY CLOSED-CANDLE M1 MOMENTUM PROFIT TRAILING EXIT ---
            m1_flush_triggered = False
            
            if active_position.type == mt5.ORDER_TYPE_BUY:
                if m1_momentum < (M1_MOMENTUM_THRESHOLD * -1):
                    close_type = mt5.ORDER_TYPE_SELL
                    close_price = mt5.symbol_info_tick(SYMBOL).bid
                    m1_flush_triggered = True
            elif active_position.type == mt5.ORDER_TYPE_SELL:
                if m1_momentum > M1_MOMENTUM_THRESHOLD:
                    close_type = mt5.ORDER_TYPE_BUY
                    close_price = mt5.symbol_info_tick(SYMBOL).ask
                    m1_flush_triggered = True
            
            if m1_flush_triggered:
                kill_request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": SYMBOL,
                    "volume": float(active_position.volume),
                    "type": close_type,
                    "position": active_position.ticket,
                    "price": float(close_price),
                    "deviation": 10,
                    "magic": MAGIC_NUMBER,
                    "comment": "⚡ M1 INSTANT MOMENTUM FLUSH",
                    "type_filling": mt5.ORDER_FILLING_IOC
                }
                mt5.order_send(kill_request)
                logging.info(f"⚡ VELOCITY SNIPER CUT: M1 momentum cracked ({m1_momentum:.2f}). Position terminated cleanly.")
                TELEMETRY["status"] = f"⚡ POSITION TERMINATED VIA M1 VELOCITY FLUSH ({m1_momentum:.2f} pts)."
                time.sleep(1)
                continue

            if active_position.type == mt5.ORDER_TYPE_BUY:
                pos_type = "BUY 🟢"
            else:
                pos_type = "SELL 🔴"
                
            TELEMETRY["pos_active"] = f"{pos_type} | TICKET: #{active_position.ticket}"
            TELEMETRY["pos_entry"] = active_position.price_open
            TELEMETRY["pos_pnl"] = active_position.profit
            
            if active_position.profit > 0:
                TELEMETRY["pos_pnl_color"] = "\033[1;32m"
            else:
                TELEMETRY["pos_pnl_color"] = "\033[1;31m"
                
            TELEMETRY["status"] = f"⏳ MONITORING M1 MOMENTUM CLOSE SYSTEM SPEED... CURRENT VELOCITY: {m1_momentum:.2f}"
        else:
            TELEMETRY["pos_active"] = "NONE 🏖️"
            TELEMETRY["pos_entry"] = 0.0
            TELEMETRY["pos_pnl"] = 0.0
            TELEMETRY["pos_pnl_color"] = "\033[1;37m"
            TELEMETRY["active_lot_size"] = 0.0
            
            if not h1_bullish_clear and not h1_bearish_clear:
                TELEMETRY["status"] = "❌ EXECUTION HALTED: STANDING BY FOR CLEAN DYNAMIC KUMO BREAKOUT."
            else:
                TELEMETRY["status"] = "👀 SPECTRAL GRID CALIBRATED. HUNTING ENTRIES..."

        if current_bar_time != last_processed_bar_time:
            if is_news:
                TELEMETRY["status"] = "⚠️ EXPANSION DETECTED! SILVER CANDLE NEWS SHIELD ACTIVE."
            elif len(positions) == 0:  
                
                target_volume = LOT_STANDARD
                
                # BUY DISPATCH
                if h1_bullish_clear and TELEMETRY["m15_mom"] > 0 and m15_lines_up:
                    if trigger_bar['tenkan'] > trigger_bar['kijun'] and trigger_bar['close'] > trigger_bar['open']:
                        
                        # Lot Scaling via H1 Kijun Slope
                        if h1_trigger['kijun'] > h1_prev_bar['kijun']:
                            target_volume = LOT_SPECTRAL_OVERDRIVE
                            logging.info(f"🔥 SPECTRAL OVERDRIVE ENGAGED: H1 Kijun sloped up. Scaling to {target_volume}")
                        
                        ask_price = mt5.symbol_info_tick(SYMBOL).ask
                        req = {
                            "action": mt5.TRADE_ACTION_DEAL, 
                            "symbol": SYMBOL, 
                            "volume": float(target_volume), 
                            "type": mt5.ORDER_TYPE_BUY, 
                            "price": float(ask_price), 
                            "sl": float(h1_trigger['kijun']),  
                            "deviation": 10, 
                            "magic": MAGIC_NUMBER, 
                            "comment": "SPECTRAL V3",
                            "type_filling": mt5.ORDER_FILLING_IOC,
                            "type_time": mt5.ORDER_TIME_GTC
                        }
                        mt5.order_send(req)
                        logging.info("⚡ CRITICAL ENTRY: Executed Adaptive Long Vector.")
                        last_processed_bar_time = current_bar_time
                            
                # SELL DISPATCH
                if h1_bearish_clear and TELEMETRY["m15_mom"] < 0 and m15_lines_down:
                    if trigger_bar['tenkan'] < trigger_bar['kijun'] and trigger_bar['close'] < trigger_bar['open']:
                        
                        # Lot Scaling via H1 Kijun Slope
                        if h1_trigger['kijun'] < h1_prev_bar['kijun']:
                            target_volume = LOT_SPECTRAL_OVERDRIVE
                            logging.info(f"🔥 SPECTRAL OVERDRIVE ENGAGED: H1 Kijun sloped down. Scaling to {target_volume}")
                        
                        bid_price = mt5.symbol_info_tick(SYMBOL).bid
                        req = {
                            "action": mt5.TRADE_ACTION_DEAL, 
                            "symbol": SYMBOL, 
                            "volume": float(target_volume), 
                            "type": mt5.ORDER_TYPE_SELL, 
                            "price": float(bid_price), 
                            "sl": float(h1_trigger['kijun']),  
                            "deviation": 10, 
                            "magic": MAGIC_NUMBER, 
                            "comment": "SPECTRAL V3",
                            "type_filling": mt5.ORDER_FILLING_IOC,
                            "type_time": mt5.ORDER_TIME_GTC
                        }
                        mt5.order_send(req)
                        logging.info("⚡ CRITICAL ENTRY: Executed Adaptive Short Vector.")
                        last_processed_bar_time = current_bar_time

        time.sleep(0.5)

# ====================================================================
# MAIN THREAD: THE EDGY SPECTRAL HUD INTERFACE
# ====================================================================
if __name__ == "__main__":
    if not mt5.initialize(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
        print("❌ CRITICAL REJECTION: MT5 TERMINAL LINK FAILURE.")
        sys.exit()

    threading.Thread(target=tick_fluctuation_stream, daemon=True).start()
    threading.Thread(target=execution_logic_engine, daemon=True).start()

    print("\033[2J\033[H", end="") 
    
    try:
        while BOT_RUNNING:
            sys.stdout.write("\033[H") 
            
            cloud_top = TELEMETRY["h1_cloud_top"]
            cloud_bottom = TELEMETRY["h1_cloud_bottom"]
            gate_padding = TELEMETRY['h1_atr'] * KUMO_SAFETY_MULT
            
            if TELEMETRY['m15_close'] > cloud_top:
                target_trigger = cloud_top + gate_padding
                distance_to_gate = target_trigger - TELEMETRY['m15_close']
                if distance_to_gate > 0:
                    gate_status = f"BREACHED! NEED {distance_to_gate:.2f} PTS TO CLEAR ATR GATE"
                else:
                    gate_status = "GATE CLEARED 🔓"
            elif TELEMETRY['m15_close'] < cloud_bottom:
                target_trigger = cloud_bottom - gate_padding
                distance_to_gate = TELEMETRY['m15_close'] - target_trigger
                if distance_to_gate > 0:
                    gate_status = f"BREACHED! NEED {distance_to_gate:.2f} PTS TO CLEAR ATR GATE"
                else:
                    gate_status = "GATE CLEARED 🔓"
            else:
                gate_status = "INSIDE CLOUD CHOP 🛑"

            hud = f"""\033[1;35m⚡========================================================================⚡\033[K
                    🪐 TECHLITE TREMOR SPECTRAL COMMAND HUD 🪐\033[K
   [ SYSTEM RUNTIME: {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]} ] | LINK STATUS: SECURE ✅\033[K
========================================================================⚡\033[0m\033[K
 \033[1;36m[TARGET CORE] 🌐 SYMBOL: {SYMBOL}\033[0m\033[K
    ↳ ASK: {TELEMETRY['color_code']}${TELEMETRY['ask']:.3f}\033[0m {TELEMETRY['tick_dir']} | BID: \033[1;31m${TELEMETRY['bid']:.3f}\033[0m | SPREAD: \033[1;33m{TELEMETRY['spread']} pts\033[0m\033[K
 \033[1;36m[📡 ACTIVE TRACKING PATROL - RUNNING POSITION PROPERTIES]\033[0m\033[K
    ↳ STATE: \033[1;33m{TELEMETRY['pos_active']}\033[0m | ENTRY: ${TELEMETRY['pos_entry']:.2f} | PNL: {TELEMETRY['pos_pnl_color']}${TELEMETRY['pos_pnl']:.2f}\033[0m\033[K
    ↳ TRAILING MODE: \033[1;35m{TELEMETRY['tracking_mode']}\033[0m | CLOSED M1 MOMENTUM: \033[1;34m{TELEMETRY['m1_momentum']:.2f}\033[0m\033[K
    ↳ VOL ALLOCATION: \033[1;32m{TELEMETRY['active_lot_size']:.2f} LOTS\033[0m\033[K
 \033[1;36m[MACRO REGIME ANALYSIS - H1 CLOUD LAYER]\033[0m\033[K
    ↳ VECTOR PATTERN 🧭: \033[1;34m{TELEMETRY['h1_trend']}\033[0m\033[K
    ↳ CLOUD BOUNDARIES : TOP: ${cloud_top:.2f} | BOTTOM: ${cloud_bottom:.2f}\033[K
    ↳ VOLATILITY GATE  : PADDING: {gate_padding:.2f} | STATE: \033[1;33m{gate_status}\033[0m\033[K
 \033[1;36m[QUANT TELEMETRY MATRIX - M15 WAVE LAYER]\033[0m\033[K
    ↳ CLOSE: ${TELEMETRY['m15_close']:.2f} | MOM: {TELEMETRY['m15_mom']:.4f} {"🟩" if TELEMETRY['m15_mom'] > 0 else "🟥"} | ATR: {TELEMETRY['atr']:.4f}\033[K
    ↳ TENKAN: {TELEMETRY['m15_tenkan']:.3f} | KIJUN: {TELEMETRY['m15_kijun']:.3f}\033[K
 \033[1;36m[🧬 INTERLOCK MTF STRATEGY BIAS DIAGNOSTICS - REASONING MATRIX]\033[0m\033[K
    ↳ [H1 Anchor Alignment] ➡️  \033[1;35m{TELEMETRY['bias_h1_cloud']}\033[0m\033[K
    ↳ [M15 Crossover State] ➡️  {TELEMETRY['bias_m15_cross']}\033[K
    ↳ [M15 Line Sharp Arch] ➡️  {TELEMETRY['bias_m15_arch']}\033[K
    ↳ [M15 Dynamic Momentum]➡️  {TELEMETRY['bias_m15_mom']}\033[K
    ↳ [Volatility Shield   ] ➡️  {TELEMETRY['bias_volatility']}\033[K
\033[1;35m------------------------------------------------------------------------\033[0m\033[K
 \033[1;33m🤖 [DECISION COMMAND ENGINE MATRIX MODE]\033[0m\033[K
    ↳ STATUS REPORT: \033[1;32m{TELEMETRY['status']}\033[0m\033[K
\033[1;35m⚡========================================================================⚡\033[K
 \033[30;47m[TERMINAL CONTROL CONFIG]: Press Ctrl+C to instantly sever trade linkages. \033[0m\033[K"""

            sys.stdout.write(hud)
            sys.stdout.flush()
            time.sleep(0.15) 
            
    except KeyboardInterrupt:
        BOT_RUNNING = False
        mt5.shutdown()
        print("\n\n\033[1;31m[SYSTEM SHUTDOWN CHANNELS DEPLOYED] Links severed cleanly.\033[0m\n") '''


import time
import sys
import logging
import threading
from datetime import datetime
import MetaTrader5 as mt5
import pandas as pd
import numpy as np

# ====================================================================
# SYSTEM CONFIGURATION
# ====================================================================
MT5_LOGIN = 435634528
MT5_PASSWORD = "Adebayo2@"
MT5_SERVER = "Exness-MT5Trial9"
SYMBOL = "BTCUSDm"
MAGIC_NUMBER = 20260521  

# Dynamic Sizing Matrix Tiers
LOT_SCOUT = 0.05
LOT_STANDARD = 0.10
LOT_SPECTRAL_OVERDRIVE = 0.25

# Strategy Parameters
MOMENTUM_PERIOD = 4
ATR_PERIOD = 14
ATR_MULTIPLIER = 2.5
TENKAN_PERIOD = 9
KIJUN_PERIOD = 26
SENKOU_PERIOD = 52
KUMO_SAFETY_MULT = 1.5     # 1.5x ATR dynamic buffer protection shield

# High-Sensitivity M15 Momentum Trailing Configuration (Replaced M1)
M15_MOMENTUM_THRESHOLD = 50.00  # Exit threshold if M15 closes heavily against position

BOT_RUNNING = True

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("techlite_spectral_matrix.log")]
)

TELEMETRY = {
    "ask": 0.0, "bid": 0.0, "spread": 0, "tick_dir": "⚡",
    "color_code": "\033[1;37m",  
    "h1_close": 0.0, "h1_mom": 0.0, "h1_tenkan": 0.0, "h1_kijun": 0.0,
    "h4_trend": "SCANNING 📡", "atr": 0.0, "h4_atr": 0.0, "status": "BOOTING CORE SYSTEMS...",
    "bias_h4_cloud": "❌ DISALIGNED",
    "bias_h1_cross": "❌ NO CROSS",
    "bias_h1_arch": "❌ FLAT",
    "bias_h1_mom": "❌ NO MOMENTUM",
    "bias_volatility": "❌ SECURE",
    "pos_active": "NONE 🏖️",
    "pos_pnl": 0.0,
    "pos_pnl_color": "\033[1;37m",
    "pos_entry": 0.0,
    "h4_cloud_top": 0.0,       
    "h4_cloud_bottom": 0.0,
    "h4_kijun": 0.0,
    "h4_prev_kijun": 0.0,
    "tracking_mode": "M15 MOMENTUM SNIPER TRACK",
    "m15_momentum": 0.0,
    "active_lot_size": 0.0
}

# ====================================================================
# BACKGROUND ENGINE 1: ASYNC REAL-TIME TICK FLUCTUATION STREAM
# ====================================================================
def tick_fluctuation_stream():
    global TELEMETRY, BOT_RUNNING
    while BOT_RUNNING:
        tick = mt5.symbol_info_tick(SYMBOL)
        if tick is not None:
            old_ask = TELEMETRY["ask"]
            TELEMETRY["ask"] = tick.ask
            TELEMETRY["bid"] = tick.bid
            TELEMETRY["spread"] = int((tick.ask - tick.bid) / mt5.symbol_info(SYMBOL).point)
            
            if tick.ask > old_ask:
                TELEMETRY["tick_dir"] = "🔺"
                TELEMETRY["color_code"] = "\033[1;32m"  
            elif tick.ask < old_ask:
                TELEMETRY["tick_dir"] = "🔻"
                TELEMETRY["color_code"] = "\033[1;31m"  
        time.sleep(0.1) 

# ====================================================================
# BACKGROUND ENGINE 2: STRATEGY MATRIX & CORE CALCULATIONS
# ====================================================================
def calculate_ichimoku(df, tenkan_p, kijun_p, senkou_p):
    df['tenkan'] = (df['high'].rolling(window=tenkan_p).max() + df['low'].rolling(window=tenkan_p).min()) / 2
    df['kijun'] = (df['high'].rolling(window=kijun_p).max() + df['low'].rolling(window=kijun_p).min()) / 2
    df['senkou_a'] = ((df['tenkan'] + df['kijun']) / 2).shift(kijun_p)
    df['senkou_b'] = ((df['high'].rolling(window=senkou_p).max() + df['low'].rolling(window=senkou_p).min()) / 2).shift(kijun_p)
    return df

def calculate_atr(df, period):
    high_low = df['high'] - df['low']
    high_cp = np.abs(df['high'] - df['close'].shift(1))
    low_cp = np.abs(df['low'] - df['close'].shift(1))
    df['atr'] = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1).rolling(window=period).mean()
    return df

def execution_logic_engine():
    global TELEMETRY, BOT_RUNNING
    threading.current_thread().name = "StrategyEngine"
    
    last_processed_bar_time = 0
    
    while BOT_RUNNING:
        h1_bars = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_H1, 0, 100)
        h4_bars = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_H4, 0, 100)
        m15_bars = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M15, 0, 20)
        
        if h1_bars is None or h4_bars is None or m15_bars is None or len(h1_bars) < 60 or len(h4_bars) < 60 or len(m15_bars) < 10:
            TELEMETRY["status"] = "SYNCHRONIZING WITH MT5 LIQUIDITY POOLS..."
            time.sleep(2)
            continue
            
        df_h1 = calculate_atr(calculate_ichimoku(pd.DataFrame(h1_bars), TENKAN_PERIOD, KIJUN_PERIOD, SENKOU_PERIOD), ATR_PERIOD)
        df_h4 = calculate_atr(calculate_ichimoku(pd.DataFrame(h4_bars), TENKAN_PERIOD, KIJUN_PERIOD, SENKOU_PERIOD), ATR_PERIOD)
        df_m15 = pd.DataFrame(m15_bars)
        
        # Smooth 4-Candle M15 Momentum Trailing
        m15_momentum = df_m15.iloc[-2]['close'] - df_m15.iloc[-6]['close']
        TELEMETRY["m15_momentum"] = m15_momentum
        
        current_bar_time = df_h1.iloc[-1]['time']
        trigger_bar = df_h1.iloc[-2]
        prev_bar = df_h1.iloc[-3]
        h4_trigger = df_h4.iloc[-2]
        h4_prev_bar = df_h4.iloc[-3]
        
        TELEMETRY["h1_close"] = trigger_bar['close']
        TELEMETRY["h1_mom"] = trigger_bar['close'] - df_h1.iloc[-2 - MOMENTUM_PERIOD]['close']
        TELEMETRY["h1_tenkan"] = trigger_bar['tenkan']
        TELEMETRY["h1_kijun"] = trigger_bar['kijun']
        TELEMETRY["atr"] = trigger_bar['atr']
        TELEMETRY["h4_atr"] = h4_trigger['atr']
        TELEMETRY["h4_kijun"] = h4_trigger['kijun']
        TELEMETRY["h4_prev_kijun"] = h4_prev_bar['kijun']
        
        cloud_top = max(h4_trigger['senkou_a'], h4_trigger['senkou_b'])
        cloud_bottom = min(h4_trigger['senkou_a'], h4_trigger['senkou_b'])
        TELEMETRY["h4_cloud_top"] = cloud_top
        TELEMETRY["h4_cloud_bottom"] = cloud_bottom
        
        safety_buffer = h4_trigger['atr'] * KUMO_SAFETY_MULT
        
        h4_bullish_clear = h4_trigger['close'] > (cloud_top + safety_buffer)
        h4_bearish_clear = h4_trigger['close'] < (cloud_bottom - safety_buffer)
        
        if h4_bullish_clear:
            TELEMETRY["h4_trend"] = "🔥 STRONG BULLISH (CLEAR OF KUMO)"
            TELEMETRY["bias_h4_cloud"] = "✅ MATCHED [BUY BIAS]"
        elif h4_bearish_clear:
            TELEMETRY["h4_trend"] = "❄️ STRONG BEARISH (CLEAR OF KUMO)"
            TELEMETRY["bias_h4_cloud"] = "✅ MATCHED [SELL BIAS]"
        else:
            TELEMETRY["h4_trend"] = "💀 CHOPPENING DETECTED / INSIDE SAFETY CLOUD ZONE"
            TELEMETRY["bias_h4_cloud"] = "❌ DISALIGNED [INSIDE SAFETY BUFFER]"

        if trigger_bar['tenkan'] > trigger_bar['kijun']:
            TELEMETRY["bias_h1_cross"] = "🟩 TENKAN > KIJUN (BULLISH)"
        elif trigger_bar['tenkan'] < trigger_bar['kijun']:
            TELEMETRY["bias_h1_cross"] = "🟥 TENKAN < KIJUN (BEARISH)"
        else:
            TELEMETRY["bias_h1_cross"] = "⬜ EQUILIBRIUM SQUEEZE"
            
        h1_lines_up = trigger_bar['tenkan'] > prev_bar['tenkan']
        h1_lines_down = trigger_bar['tenkan'] < prev_bar['tenkan']
        
        if h1_lines_up:
            TELEMETRY["bias_h1_arch"] = "🟩 STEEP HOOK UPWARD"
        elif h1_lines_down:
            TELEMETRY["bias_h1_arch"] = "🟥 STEEP HOOK DOWNWARD"
        else:
            TELEMETRY["bias_h1_arch"] = "⬜ NO VELOCITY (FLAT LINES)"
            
        if TELEMETRY["h1_mom"] > 0:
            TELEMETRY["bias_h1_mom"] = f"🟩 POSITIVE (+{TELEMETRY['h1_mom']:.2f})"
        elif TELEMETRY["h1_mom"] < 0:
            TELEMETRY["bias_h1_mom"] = f"🟥 NEGATIVE ({TELEMETRY['h1_mom']:.2f})"
            
        candle_range = trigger_bar['high'] - trigger_bar['low']
        is_news = candle_range > (trigger_bar['atr'] * ATR_MULTIPLIER)
        
        if is_news:
            TELEMETRY["bias_volatility"] = "🚨 BLOCKED: NEWS SPIKE BREAKOUT"
        else:
            TELEMETRY["bias_volatility"] = "✅ SECURE (STABLE ATR STRUCTURE)"

        positions = mt5.positions_get(symbol=SYMBOL, magic=MAGIC_NUMBER)
        
        if len(positions) > 0:
            active_position = positions[0]
            TELEMETRY["active_lot_size"] = active_position.volume
            
            # --- HIGH-SENSITIVITY CLOSED-CANDLE M15 MOMENTUM PROFIT TRAILING EXIT ---
            m15_flush_triggered = False
            
            if active_position.type == mt5.ORDER_TYPE_BUY:
                if m15_momentum < (M15_MOMENTUM_THRESHOLD * -1):
                    close_type = mt5.ORDER_TYPE_SELL
                    close_price = mt5.symbol_info_tick(SYMBOL).bid
                    m15_flush_triggered = True
            elif active_position.type == mt5.ORDER_TYPE_SELL:
                if m15_momentum > M15_MOMENTUM_THRESHOLD:
                    close_type = mt5.ORDER_TYPE_BUY
                    close_price = mt5.symbol_info_tick(SYMBOL).ask
                    m15_flush_triggered = True
            
            if m15_flush_triggered:
                kill_request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": SYMBOL,
                    "volume": float(active_position.volume),
                    "type": close_type,
                    "position": active_position.ticket,
                    "price": float(close_price),
                    "deviation": 10,
                    "magic": MAGIC_NUMBER,
                    "comment": "⚡ M15 INSTANT MOMENTUM FLUSH",
                    "type_filling": mt5.ORDER_FILLING_IOC
                }
                mt5.order_send(kill_request)
                logging.info(f"⚡ VELOCITY SNIPER CUT: M15 momentum cracked ({m15_momentum:.2f}). Position terminated cleanly.")
                TELEMETRY["status"] = f"⚡ POSITION TERMINATED VIA M15 VELOCITY FLUSH ({m15_momentum:.2f} pts)."
                time.sleep(1)
                continue

            if active_position.type == mt5.ORDER_TYPE_BUY:
                pos_type = "BUY 🟢"
            else:
                pos_type = "SELL 🔴"
                
            TELEMETRY["pos_active"] = f"{pos_type} | TICKET: #{active_position.ticket}"
            TELEMETRY["pos_entry"] = active_position.price_open
            TELEMETRY["pos_pnl"] = active_position.profit
            
            if active_position.profit > 0:
                TELEMETRY["pos_pnl_color"] = "\033[1;32m"
            else:
                TELEMETRY["pos_pnl_color"] = "\033[1;31m"
                
            TELEMETRY["status"] = f"⏳ MONITORING M15 MOMENTUM CLOSE SYSTEM SPEED... CURRENT VELOCITY: {m15_momentum:.2f}"
        else:
            TELEMETRY["pos_active"] = "NONE 🏖️"
            TELEMETRY["pos_entry"] = 0.0
            TELEMETRY["pos_pnl"] = 0.0
            TELEMETRY["pos_pnl_color"] = "\033[1;37m"
            TELEMETRY["active_lot_size"] = 0.0
            
            if not h4_bullish_clear and not h4_bearish_clear:
                TELEMETRY["status"] = "❌ EXECUTION HALTED: STANDING BY FOR CLEAN DYNAMIC KUMO BREAKOUT."
            else:
                TELEMETRY["status"] = "👀 SPECTRAL GRID CALIBRATED. HUNTING ENTRIES..."

        if current_bar_time != last_processed_bar_time:
            if is_news:
                TELEMETRY["status"] = "⚠️ EXPANSION DETECTED! SILVER CANDLE NEWS SHIELD ACTIVE."
            elif len(positions) == 0:  
                
                target_volume = LOT_STANDARD
                
                # BUY DISPATCH
                if h4_bullish_clear and TELEMETRY["h1_mom"] > 0 and h1_lines_up:
                    if trigger_bar['tenkan'] > trigger_bar['kijun'] and trigger_bar['close'] > trigger_bar['open']:
                        
                        # Lot Scaling via H4 Kijun Slope
                        if h4_trigger['kijun'] > h4_prev_bar['kijun']:
                            target_volume = LOT_SPECTRAL_OVERDRIVE
                            logging.info(f"🔥 SPECTRAL OVERDRIVE ENGAGED: H4 Kijun sloped up. Scaling to {target_volume}")
                        
                        ask_price = mt5.symbol_info_tick(SYMBOL).ask
                        req = {
                            "action": mt5.TRADE_ACTION_DEAL, 
                            "symbol": SYMBOL, 
                            "volume": float(target_volume), 
                            "type": mt5.ORDER_TYPE_BUY, 
                            "price": float(ask_price), 
                            "sl": float(h4_trigger['kijun']),  
                            "deviation": 10, 
                            "magic": MAGIC_NUMBER, 
                            "comment": "SPECTRAL V3",
                            "type_filling": mt5.ORDER_FILLING_IOC,
                            "type_time": mt5.ORDER_TIME_GTC
                        }
                        mt5.order_send(req)
                        logging.info("⚡ CRITICAL ENTRY: Executed Adaptive Long Vector.")
                        last_processed_bar_time = current_bar_time
                            
                # SELL DISPATCH
                if h4_bearish_clear and TELEMETRY["h1_mom"] < 0 and h1_lines_down:
                    if trigger_bar['tenkan'] < trigger_bar['kijun'] and trigger_bar['close'] < trigger_bar['open']:
                        
                        # Lot Scaling via H4 Kijun Slope
                        if h4_trigger['kijun'] < h4_prev_bar['kijun']:
                            target_volume = LOT_SPECTRAL_OVERDRIVE
                            logging.info(f"🔥 SPECTRAL OVERDRIVE ENGAGED: H4 Kijun sloped down. Scaling to {target_volume}")
                        
                        bid_price = mt5.symbol_info_tick(SYMBOL).bid
                        req = {
                            "action": mt5.TRADE_ACTION_DEAL, 
                            "symbol": SYMBOL, 
                            "volume": float(target_volume), 
                            "type": mt5.ORDER_TYPE_SELL, 
                            "price": float(bid_price), 
                            "sl": float(h4_trigger['kijun']),  
                            "deviation": 10, 
                            "magic": MAGIC_NUMBER, 
                            "comment": "SPECTRAL V3",
                            "type_filling": mt5.ORDER_FILLING_IOC,
                            "type_time": mt5.ORDER_TIME_GTC
                        }
                        mt5.order_send(req)
                        logging.info("⚡ CRITICAL ENTRY: Executed Adaptive Short Vector.")
                        last_processed_bar_time = current_bar_time

        time.sleep(0.5)

# ====================================================================
# MAIN THREAD: THE EDGY SPECTRAL HUD INTERFACE
# ====================================================================
if __name__ == "__main__":
    if not mt5.initialize(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
        print("❌ CRITICAL REJECTION: MT5 TERMINAL LINK FAILURE.")
        sys.exit()

    threading.Thread(target=tick_fluctuation_stream, daemon=True).start()
    threading.Thread(target=execution_logic_engine, daemon=True).start()

    print("\033[2J\033[H", end="") 
    
    try:
        while BOT_RUNNING:
            sys.stdout.write("\033[H") 
            
            cloud_top = TELEMETRY["h4_cloud_top"]
            cloud_bottom = TELEMETRY["h4_cloud_bottom"]
            gate_padding = TELEMETRY['h4_atr'] * KUMO_SAFETY_MULT
            
            if TELEMETRY['h1_close'] > cloud_top:
                target_trigger = cloud_top + gate_padding
                distance_to_gate = target_trigger - TELEMETRY['h1_close']
                if distance_to_gate > 0:
                    gate_status = f"BREACHED! NEED {distance_to_gate:.2f} PTS TO CLEAR ATR GATE"
                else:
                    gate_status = "GATE CLEARED 🔓"
            elif TELEMETRY['h1_close'] < cloud_bottom:
                target_trigger = cloud_bottom - gate_padding
                distance_to_gate = TELEMETRY['h1_close'] - target_trigger
                if distance_to_gate > 0:
                    gate_status = f"BREACHED! NEED {distance_to_gate:.2f} PTS TO CLEAR ATR GATE"
                else:
                    gate_status = "GATE CLEARED 🔓"
            else:
                gate_status = "INSIDE CLOUD CHOP 🛑"

            hud = f"""\033[1;35m⚡========================================================================⚡\033[K
                    🪐 TECHLITE TREMOR SPECTRAL COMMAND HUD 🪐\033[K
   [ SYSTEM RUNTIME: {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]} ] | LINK STATUS: SECURE ✅\033[K
========================================================================⚡\033[0m\033[K
 \033[1;36m[TARGET CORE] 🌐 SYMBOL: {SYMBOL}\033[0m\033[K
    ↳ ASK: {TELEMETRY['color_code']}${TELEMETRY['ask']:.3f}\033[0m {TELEMETRY['tick_dir']} | BID: \033[1;31m${TELEMETRY['bid']:.3f}\033[0m | SPREAD: \033[1;33m{TELEMETRY['spread']} pts\033[0m\033[K
 \033[1;36m[📡 ACTIVE TRACKING PATROL - RUNNING POSITION PROPERTIES]\033[0m\033[K
    ↳ STATE: \033[1;33m{TELEMETRY['pos_active']}\033[0m | ENTRY: ${TELEMETRY['pos_entry']:.2f} | PNL: {TELEMETRY['pos_pnl_color']}${TELEMETRY['pos_pnl']:.2f}\033[0m\033[K
    ↳ TRAILING MODE: \033[1;35m{TELEMETRY['tracking_mode']}\033[0m | CLOSED M15 MOMENTUM: \033[1;34m{TELEMETRY['m15_momentum']:.2f}\033[0m\033[K
    ↳ VOL ALLOCATION: \033[1;32m{TELEMETRY['active_lot_size']:.2f} LOTS\033[0m\033[K
 \033[1;36m[MACRO REGIME ANALYSIS - H4 CLOUD LAYER]\033[0m\033[K
    ↳ VECTOR PATTERN 🧭: \033[1;34m{TELEMETRY['h4_trend']}\033[0m\033[K
    ↳ CLOUD BOUNDARIES : TOP: ${cloud_top:.2f} | BOTTOM: ${cloud_bottom:.2f}\033[K
    ↳ VOLATILITY GATE  : PADDING: {gate_padding:.2f} | STATE: \033[1;33m{gate_status}\033[0m\033[K
 \033[1;36m[QUANT TELEMETRY MATRIX - H1 WAVE LAYER]\033[0m\033[K
    ↳ CLOSE: ${TELEMETRY['h1_close']:.2f} | MOM: {TELEMETRY['h1_mom']:.4f} {"🟩" if TELEMETRY['h1_mom'] > 0 else "🟥"} | ATR: {TELEMETRY['atr']:.4f}\033[K
    ↳ TENKAN: {TELEMETRY['h1_tenkan']:.3f} | KIJUN: {TELEMETRY['h1_kijun']:.3f}\033[K
 \033[1;36m[🧬 INTERLOCK MTF STRATEGY BIAS DIAGNOSTICS - REASONING MATRIX]\033[0m\033[K
    ↳ [H4 Anchor Alignment] ➡️  \033[1;35m{TELEMETRY['bias_h4_cloud']}\033[0m\033[K
    ↳ [H1 Crossover State] ➡️  {TELEMETRY['bias_h1_cross']}\033[K
    ↳ [H1 Line Sharp Arch] ➡️  {TELEMETRY['bias_h1_arch']}\033[K
    ↳ [H1 Dynamic Momentum]➡️  {TELEMETRY['bias_h1_mom']}\033[K
    ↳ [Volatility Shield   ] ➡️  {TELEMETRY['bias_volatility']}\033[K
\033[1;35m------------------------------------------------------------------------\033[0m\033[K
 \033[1;33m🤖 [DECISION COMMAND ENGINE MATRIX MODE]\033[0m\033[K
    ↳ STATUS REPORT: \033[1;32m{TELEMETRY['status']}\033[0m\033[K
\033[1;35m⚡========================================================================⚡\033[K
 \033[30;47m[TERMINAL CONTROL CONFIG]: Press Ctrl+C to instantly sever trade linkages. \033[0m\033[K"""

            sys.stdout.write(hud)
            sys.stdout.flush()
            time.sleep(0.15) 
            
    except KeyboardInterrupt:
        BOT_RUNNING = False
        mt5.shutdown()
        print("\n\n\033[1;31m[SYSTEM SHUTDOWN CHANNELS DEPLOYED] Links severed cleanly.\033[0m\n")