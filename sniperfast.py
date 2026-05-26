import time
import sys
import os
import logging
import threading
import msvcrt
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

# Strategy Parameters
MOMENTUM_PERIOD = 4
ATR_PERIOD = 14
ATR_MULTIPLIER = 2.5
TENKAN_PERIOD = 9
KIJUN_PERIOD = 26
SENKOU_PERIOD = 52
BASE_VIBRATION_MULT = 2.0  
KUMO_SAFETY_MULT = 1.5     

BOT_RUNNING = True

# HUD Navigation Matrix Pages
VIEWS = ["OVERVIEW", "ACTIVE_TRADES", "M1_CORE", "M15_CORE", "H1_CORE", "H4_CORE"]
view_index = 0

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("techlite_spectral_matrix.log")]
)

# Shared Multi-Threaded Telemetry Cache
TELEMETRY = {
    "ask": 0.0, "bid": 0.0, "spread": 0, "tick_dir": "⚡", "color_code": "\033[1;37m",
    "status": "BOOTING CORE SYSTEMS...",
    
    # M1 Thread Storage
    "m1_close": 0.0, "m1_mom": 0.0, "m1_bias": "NEUTRAL", "m1_tenkan": 0.0, "m1_kijun": 0.0,
    
    # M15 Thread Storage
    "m15_close": 0.0, "m15_mom": 0.0, "m15_bias": "NEUTRAL", "m15_tenkan": 0.0, "m15_kijun": 0.0, "m15_atr": 0.0,
    "bias_m15_cross": "❌ NO CROSS", "bias_m15_arch": "❌ FLAT", "bias_m15_mom": "❌ NO MOMENTUM",
    
    # H1 Thread Storage
    "h1_close": 0.0, "h1_bias": "NEUTRAL", "h1_tenkan": 0.0, "h1_kijun": 0.0, "h1_prev_tenkan": 0.0,
    "h1_cloud_top": 0.0, "h1_cloud_bottom": 0.0, "h1_atr": 0.0, "h1_trend": "SCANNING 📡", "bias_h1_cloud": "❌ DISALIGNED",
    
    # H4 Thread Storage
    "h4_close": 0.0, "h4_bias": "NEUTRAL", "h4_tenkan": 0.0, "h4_kijun": 0.0, "h4_cloud_top": 0.0, "h4_cloud_bottom": 0.0,
    
    # Risk/Position States
    "pos_active": "NONE 🏖️", "pos_entry": 0.0, "pos_pnl": 0.0, "pos_pnl_color": "\033[1;37m", "current_buffer": 0.0,
    "bias_volatility": "✅ SECURE"
}

# ====================================================================
# HELPER MATHEMATICAL UTILITIES
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

# ====================================================================
# DYNAMIC HUD KEYBOARD NAVIGATION LISTENER
# ====================================================================
def check_hud_navigation():
    global view_index
    if msvcrt.kbhit():
        key = msvcrt.getch()
        if key in (b'\x00', b'\xe0'):
            arrow = msvcrt.getch()
            if arrow == b'M':    # Right Arrow Key
                view_index += 1
                if view_index >= len(VIEWS):
                    view_index = 0
                return True
            elif arrow == b'K':  # Left Arrow Key
                view_index -= 1
                if view_index < 0:
                    view_index = len(VIEWS) - 1
                return True
    return False

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
# BACKGROUND ENGINE 2: ADAPTIVE VIBRATION TRAILING ENGINE
# ====================================================================
def adaptive_vibration_trailing_engine():
    global BOT_RUNNING, TELEMETRY
    while BOT_RUNNING:
        if not mt5.initialize():
            time.sleep(2)
            continue
            
        positions = mt5.positions_get(symbol=SYMBOL, magic=MAGIC_NUMBER)
        if len(positions) > 0:
            pos = positions[0]
            current_atr = TELEMETRY["m15_atr"]
            abs_momentum = abs(TELEMETRY["m15_mom"])
            
            if current_atr > 0:
                adaptive_breathing_space = (current_atr * BASE_VIBRATION_MULT) + (abs_momentum * 0.2)
                TELEMETRY["current_buffer"] = adaptive_breathing_space
                point = mt5.symbol_info(SYMBOL).point
                
                if pos.type == mt5.ORDER_TYPE_BUY:
                    new_sl = TELEMETRY["bid"] - adaptive_breathing_space
                    if new_sl > pos.sl + (10 * point) and new_sl > pos.price_open:
                        req = {"action": mt5.TRADE_ACTION_SLTP, "position": pos.ticket, "sl": round(new_sl, 2), "tp": pos.tp}
                        mt5.order_send(req)
                elif pos.type == mt5.ORDER_TYPE_SELL:
                    new_sl = TELEMETRY["ask"] + adaptive_breathing_space
                    if (pos.sl == 0.0 or new_sl < pos.sl - (10 * point)) and new_sl < pos.price_open:
                        req = {"action": mt5.TRADE_ACTION_SLTP, "position": pos.ticket, "sl": round(new_sl, 2), "tp": pos.tp}
                        mt5.order_send(req)
        else:
            TELEMETRY["current_buffer"] = 0.0
        time.sleep(0.5)

# ====================================================================
# TIMEFRAME CORE ENGINE THREADS (4 INDEPENDENT ENGINE BLOCKS)
# ====================================================================
def m1_analysis_thread():
    global TELEMETRY, BOT_RUNNING
    while BOT_RUNNING:
        bars = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M1, 0, 100)
        if bars is not None and len(bars) >= 60:
            df = calculate_ichimoku(pd.DataFrame(bars), TENKAN_PERIOD, KIJUN_PERIOD, SENKOU_PERIOD)
            trigger = df.iloc[-2]
            
            TELEMETRY["m1_close"] = trigger['close']
            TELEMETRY["m1_tenkan"] = trigger['tenkan']
            TELEMETRY["m1_kijun"] = trigger['kijun']
            TELEMETRY["m1_mom"] = trigger['close'] - df.iloc[-2 - MOMENTUM_PERIOD]['close']
            
            if trigger['tenkan'] > trigger['kijun'] and TELEMETRY["m1_mom"] > 0:
                TELEMETRY["m1_bias"] = "BUY"
            elif trigger['tenkan'] < trigger['kijun'] and TELEMETRY["m1_mom"] < 0:
                TELEMETRY["m1_bias"] = "SELL"
            else:
                TELEMETRY["m1_bias"] = "NEUTRAL"
        time.sleep(0.5)

def m15_analysis_thread():
    global TELEMETRY, BOT_RUNNING
    while BOT_RUNNING:
        bars = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M15, 0, 100)
        if bars is not None and len(bars) >= 60:
            df = calculate_atr(calculate_ichimoku(pd.DataFrame(bars), TENKAN_PERIOD, KIJUN_PERIOD, SENKOU_PERIOD), ATR_PERIOD)
            trigger = df.iloc[-2]
            prev_bar = df.iloc[-3]
            
            TELEMETRY["m15_close"] = trigger['close']
            TELEMETRY["m15_tenkan"] = trigger['tenkan']
            TELEMETRY["m15_kijun"] = trigger['kijun']
            TELEMETRY["m15_atr"] = trigger['atr']
            TELEMETRY["m15_mom"] = trigger['close'] - df.iloc[-2 - MOMENTUM_PERIOD]['close']
            
            # Diagnostic String Formats
            if trigger['tenkan'] > trigger['kijun']:
                TELEMETRY["bias_m15_cross"] = "🟩 TENKAN > KIJUN (BULLISH)"
            else:
                TELEMETRY["bias_m15_cross"] = "🟥 TENKAN < KIJUN (BEARISH)"
                
            m15_lines_up = (trigger['tenkan'] > prev_bar['tenkan']) and (trigger['kijun'] > prev_bar['kijun'])
            m15_lines_down = (trigger['tenkan'] < prev_bar['tenkan']) and (trigger['kijun'] < prev_bar['kijun'])
            
            if m15_lines_up:
                TELEMETRY["bias_m15_arch"] = "🟩 STEEP HOOK UPWARD"
                TELEMETRY["m15_bias"] = "BUY"
            elif m15_lines_down:
                TELEMETRY["bias_m15_arch"] = "🟥 STEEP HOOK DOWNWARD"
                TELEMETRY["m15_bias"] = "SELL"
            else:
                TELEMETRY["bias_m15_arch"] = "⬜ NO VELOCITY (FLAT LINES)"
                TELEMETRY["m15_bias"] = "NEUTRAL"
                
            if TELEMETRY["m15_mom"] > 0:
                TELEMETRY["bias_m15_mom"] = f"🟩 POSITIVE (+{TELEMETRY['m15_mom']:.2f})"
            else:
                TELEMETRY["bias_m15_mom"] = f"🟥 NEGATIVE ({TELEMETRY['m15_mom']:.2f})"
                
            candle_range = trigger['high'] - trigger['low']
            if candle_range > (trigger['atr'] * ATR_MULTIPLIER):
                TELEMETRY["bias_volatility"] = "🚨 BLOCKED: NEWS SPIKE BREAKOUT"
            else:
                TELEMETRY["bias_volatility"] = "✅ SECURE (STABLE ATR STRUCTURE)"
        time.sleep(0.5)

def h1_analysis_thread():
    global TELEMETRY, BOT_RUNNING
    while BOT_RUNNING:
        bars = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_H1, 0, 100)
        if bars is not None and len(bars) >= 60:
            df = calculate_atr(calculate_ichimoku(pd.DataFrame(bars), TENKAN_PERIOD, KIJUN_PERIOD, SENKOU_PERIOD), ATR_PERIOD)
            trigger = df.iloc[-2]
            prev_trigger = df.iloc[-3]
            
            TELEMETRY["h1_close"] = trigger['close']
            TELEMETRY["h1_tenkan"] = trigger['tenkan']
            TELEMETRY["h1_kijun"] = trigger['kijun']
            TELEMETRY["h1_prev_tenkan"] = prev_trigger['tenkan']
            TELEMETRY["h1_atr"] = trigger['atr']
            
            cloud_top = max(trigger['senkou_a'], trigger['senkou_b'])
            cloud_bottom = min(trigger['senkou_a'], trigger['senkou_b'])
            TELEMETRY["h1_cloud_top"] = cloud_top
            TELEMETRY["h1_cloud_bottom"] = cloud_bottom
            
            safety_buffer = trigger['atr'] * KUMO_SAFETY_MULT
            
            if trigger['close'] > (cloud_top + safety_buffer):
                TELEMETRY["h1_trend"] = "🔥 STRONG BULLISH (CLEAR OF KUMO)"
                TELEMETRY["bias_h1_cloud"] = "✅ MATCHED [BUY BIAS]"
                TELEMETRY["h1_bias"] = "BUY"
            elif trigger['close'] < (cloud_bottom - safety_buffer):
                TELEMETRY["h1_trend"] = "❄️ STRONG BEARISH (CLEAR OF KUMO)"
                TELEMETRY["bias_h1_cloud"] = "✅ MATCHED [SELL BIAS]"
                TELEMETRY["h1_bias"] = "SELL"
            else:
                TELEMETRY["h1_trend"] = "💀 CHOPPENING / SAFETY ZONE"
                TELEMETRY["bias_h1_cloud"] = "❌ DISALIGNED"
                TELEMETRY["h1_bias"] = "NEUTRAL"
        time.sleep(1.0)

def h4_analysis_thread():
    global TELEMETRY, BOT_RUNNING
    while BOT_RUNNING:
        bars = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_H4, 0, 100)
        if bars is not None and len(bars) >= 60:
            df = calculate_ichimoku(pd.DataFrame(bars), TENKAN_PERIOD, KIJUN_PERIOD, SENKOU_PERIOD)
            trigger = df.iloc[-2]
            
            TELEMETRY["h4_close"] = trigger['close']
            TELEMETRY["h4_tenkan"] = trigger['tenkan']
            TELEMETRY["h4_kijun"] = trigger['kijun']
            TELEMETRY["h4_cloud_top"] = max(trigger['senkou_a'], trigger['senkou_b'])
            TELEMETRY["h4_cloud_bottom"] = min(trigger['senkou_a'], trigger['senkou_b'])
            
            if trigger['close'] > TELEMETRY["h4_cloud_top"] and trigger['tenkan'] > trigger['kijun']:
                TELEMETRY["h4_bias"] = "BUY"
            elif trigger['close'] < TELEMETRY["h4_cloud_bottom"] and trigger['tenkan'] < trigger['kijun']:
                TELEMETRY["h4_bias"] = "SELL"
            else:
                TELEMETRY["h4_bias"] = "NEUTRAL"
        time.sleep(2.0)

# ====================================================================
# EXECUTION ROUTER & INTERLOCK SENTINEL ENGINE
# ====================================================================
def order_routing_management_engine():
    global TELEMETRY, BOT_RUNNING
    while BOT_RUNNING:
        if not mt5.initialize():
            time.sleep(1)
            continue
            
        positions = mt5.positions_get(symbol=SYMBOL, magic=MAGIC_NUMBER)
        
        # 🛡️ SYSTEM A: OPEN POSITION MONITORING via H1 TENKAN DYNAMICS
        if len(positions) > 0:
            pos = positions[0]
            pos_type_str = "BUY 🟢" if pos.type == mt5.ORDER_TYPE_BUY else "SELL 🔴"
            TELEMETRY["pos_active"] = f"{pos_type_str} | TICKET: #{pos.ticket}"
            TELEMETRY["pos_entry"] = pos.price_open
            TELEMETRY["pos_pnl"] = pos.profit
            TELEMETRY["pos_pnl_color"] = "\033[1;32m" if pos.profit > 0 else "\033[1;31m"
            TELEMETRY["status"] = "⏳ H1 SENTINEL WATCHING LIVE PROFILE TREND HEALTH..."
            
            # Monitor H1 Tenkan Vector Direction against open position
            if pos.type == mt5.ORDER_TYPE_BUY:
                if TELEMETRY["h1_tenkan"] < TELEMETRY["h1_prev_tenkan"]:
                    # H1 Tenkan curves down against our long position -> FORCE EARLY DISPATCH
                    req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": SYMBOL, "volume": pos.volume,
                           "type": mt5.ORDER_TYPE_SELL, "position": pos.ticket, "price": mt5.symbol_info_tick(SYMBOL).bid,
                           "deviation": 10, "magic": MAGIC_NUMBER, "comment": "H1 SENTINEL EMERGENCY SHIELD"}
                    mt5.order_send(req)
                    logging.info("🚨 RISK EXIT: H1 Tenkan curved downward against Long position.")
                    
            elif pos.type == mt5.ORDER_TYPE_SELL:
                if TELEMETRY["h1_tenkan"] > TELEMETRY["h1_prev_tenkan"]:
                    # H1 Tenkan curves up against our short position -> FORCE EARLY DISPATCH
                    req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": SYMBOL, "volume": pos.volume,
                           "type": mt5.ORDER_TYPE_BUY, "position": pos.ticket, "price": mt5.symbol_info_tick(SYMBOL).ask,
                           "deviation": 10, "magic": MAGIC_NUMBER, "comment": "H1 SENTINEL EMERGENCY SHIELD"}
                    mt5.order_send(req)
                    logging.info("🚨 RISK EXIT: H1 Tenkan curved upward against Short position.")
        
        # 🦅 SYSTEM B: MULTI-TIMEFRAME ENTRY LAYER MANAGEMENT
        else:
            TELEMETRY["pos_active"] = "NONE 🏖️"
            TELEMETRY["pos_entry"] = 0.0
            TELEMETRY["pos_pnl"] = 0.0
            TELEMETRY["pos_pnl_color"] = "\033[1;37m"
            TELEMETRY["status"] = "👀 PATROL SENSORS ALIGNED. SCANNING LIQUIDITY MATRIX ENGINES..."
            
            # Check core multi-timeframe structural agreements
            m1_agree = TELEMETRY["m1_bias"]
            m15_agree = TELEMETRY["m15_bias"]
            h1_agree = TELEMETRY["h1_bias"]
            h4_agree = TELEMETRY["h4_bias"]
            
            if TELEMETRY["bias_volatility"] == "✅ SECURE (STABLE ATR STRUCTURE)":
                allocated_volume = 0.0
                order_type = None
                price = 0.0
                
                # Check directional alignment
                if m1_agree == "BUY" and m15_agree == "BUY":
                    order_type = mt5.ORDER_TYPE_BUY
                    price = mt5.symbol_info_tick(SYMBOL).ask
                    allocated_volume = 0.01
                    if h1_agree == "BUY":
                        allocated_volume = 0.10
                        if h4_agree == "BUY":
                            allocated_volume = 0.20
                            
                elif m1_agree == "SELL" and m15_agree == "SELL":
                    order_type = mt5.ORDER_TYPE_SELL
                    price = mt5.symbol_info_tick(SYMBOL).bid
                    allocated_volume = 0.01
                    if h1_agree == "SELL":
                        allocated_volume = 0.10
                        if h4_agree == "SELL":
                            allocated_volume = 0.20
                
                if allocated_volume > 0.0 and order_type is not None:
                    # Execute position based on multi-tier lot assignment rules
                    req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": SYMBOL, "volume": allocated_volume,
                           "type": order_type, "price": price, "deviation": 10, "magic": MAGIC_NUMBER, "comment": f"TREMOR MTF V2 L:{allocated_volume}"}
                    mt5.order_send(req)
                    logging.info(f"⚡ ORDER DISPATCHED: Vol={allocated_volume} Type={order_type}")
                    time.sleep(5) # Cooldown buffer to let MT5 register the trade
                    
        time.sleep(0.2)

# ====================================================================
# CORE RE-ENGINEERED VIEW HUD CONTROLLER SYSTEM
# ====================================================================
# ====================================================================
# UNCONDITIONAL RAW PARAMETER DISPLAY HUB (RE-ENGINEERED)
# ====================================================================
# ====================================================================
# UNCONDITIONAL TARGET METRIC DISPLAY HUB (DYNAMIC TEMPLATE ARCHITECTURE)
# ====================================================================
def run_command_display_loop():
    global BOT_RUNNING
    print("\033[2J\033[H", end="")
    
    try:
        while BOT_RUNNING:
            sys.stdout.write("\033[H")
            current_view = VIEWS[view_index]
            
            # 1. DYNAMIC DATA ROUTING FILLERS FOR THE CHOSEN PROFILE VIEW
            if current_view == "OVERVIEW":
                layer_1_title = "OVERVIEW: SYSTEM MATRIX DIAGNOSTICS"
                l1_r1 = f"M1 ALIGNMENT: {TELEMETRY['m1_bias']:<10} | M15 ALIGNMENT: {TELEMETRY['m15_bias']:<10}"
                l1_r2 = f"H1 ALIGNMENT: {TELEMETRY['h1_bias']:<10} | H4 ALIGNMENT : {TELEMETRY['h4_bias']:<10}"
                l1_r3 = f"VOLATILITY MODE: {TELEMETRY['bias_volatility']}"
                
                layer_2_title = "QUANT TELEMETRY MATRIX - INTERLOCK BIAS RATIOS"
                l2_r1 = f"H1 REASONING: {TELEMETRY['bias_h1_cloud']}"
                l2_r2 = f"M15 REASONING: {TELEMETRY['bias_m15_cross']} | {TELEMETRY['bias_m15_arch']}"
                
            elif current_view == "ACTIVE_TRADES":
                layer_1_title = "📡 ACTIVE RISK INSPECTION PATROL - OPERATION MATRIX"
                l1_r1 = f"STATE: \033[1;33m{TELEMETRY['pos_active']}\033[0m"
                l1_r2 = f"ENTRY PRICE: ${TELEMETRY['pos_entry']:.3f} | CURRENT PNL: {TELEMETRY['pos_pnl_color']}${TELEMETRY['pos_pnl']:.2f}\033[0m"
                l1_r3 = f"TRAILING GAP LEVEL: {TELEMETRY['current_buffer']:.4f} price points"
                
                layer_2_title = "🛡️ POSITION PROTECTION LAYER - SENTINEL METRICS"
                l2_r1 = f"CURRENT H1 TENKAN VALUE : ${TELEMETRY['h1_tenkan']:.3f}"
                l2_r2 = f"PREVIOUS H1 TENKAN VALUE: ${TELEMETRY['h1_prev_tenkan']:.3f} | GUARD STATUS: ACTIVE"

            elif current_view == "M1_CORE":
                layer_1_title = "📡 QUANT TELEMETRY MATRIX - M1 SCALPING WAVE LAYER"
                l1_r1 = f"CLOSE: ${TELEMETRY['m1_close']:.3f} | MOMENTUM: {TELEMETRY['m1_mom']:.4f}"
                l1_r2 = f"TENKAN: ${TELEMETRY['m1_tenkan']:.3f} | KIJUN: ${TELEMETRY['m1_kijun']:.3f}"
                l1_r3 = f"SEPARATION FROM KIJUN BASELINE: {(TELEMETRY['m1_close'] - TELEMETRY['m1_kijun']):.3f} pts"
                
                layer_2_title = "🧬 INTERNAL STRATEGY ANALYSIS RULES"
                l2_r1 = f"TRIGGER BIAS DIRECTION: {TELEMETRY['m1_bias']}"
                l2_r2 = f"CROSSOVER STATE VALUE : {'🟩 BULLISH SQUEEZE' if TELEMETRY['m1_tenkan'] > TELEMETRY['m1_kijun'] else '🟥 BEARISH SQUEEZE'}"

            elif current_view == "M15_CORE":
                layer_1_title = "QUANT TELEMETRY MATRIX - M15 WAVE LAYER"
                l1_r1 = f"CLOSE: ${TELEMETRY['m15_close']:.3f} | MOM: {TELEMETRY['m15_mom']:.4f} {'🟩' if TELEMETRY['m15_mom'] > 0 else '🟥'} | ATR: {TELEMETRY['m15_atr']:.4f}"
                l1_r2 = f"TENKAN: ${TELEMETRY['m15_tenkan']:.3f} | KIJUN: ${TELEMETRY['m15_kijun']:.3f}"
                l1_r3 = f"VOLATILITY PROFILE RANGE: {TELEMETRY['bias_volatility']}"
                
                layer_2_title = "🧬 STRATEGY BIAS DIAGNOSTICS - SPECIFIC MATRIX"
                l2_r1 = f"CROSSOVER: {TELEMETRY['bias_m15_cross']}"
                l2_r2 = f"ARCH LINE: {TELEMETRY['bias_m15_arch']} | WAVE STATE: {TELEMETRY['bias_m15_mom']}"

            elif current_view == "H1_CORE":
                layer_1_title = "MACRO REGIME ANALYSIS - H1 CLOUD LAYER"
                l1_r1 = f"VECTOR PATTERN 🧭: \033[1;34m{TELEMETRY['h1_trend']}\033[0m"
                l1_r2 = f"CLOUD BOUNDARIES : TOP: ${TELEMETRY['h1_cloud_top']:.3f} | BOTTOM: ${TELEMETRY['h1_cloud_bottom']:.3f}"
                gate_padding = TELEMETRY['h1_atr'] * KUMO_SAFETY_MULT
                l1_r3 = f"VOLATILITY GATE  : PADDING: {gate_padding:.3f} | CLOSE PRICE: ${TELEMETRY['h1_close']:.3f}"
                
                layer_2_title = "🧬 ANCHOR REGIME INTERLOCK - HIGHER DATA RECORD"
                l2_r1 = f"ALIGNMENT REASONING ENGINE MATCH: {TELEMETRY['bias_h1_cloud']}"
                l2_r2 = f"H1 CLOUD THICKNESS SPREAD VALUES: {(TELEMETRY['h1_cloud_top'] - TELEMETRY['h1_cloud_bottom']):.3f} points"

            elif current_view == "H4_CORE":
                layer_1_title = "🌌 DEEPEST TREND STRUCTURE - H4 GRID FRAME"
                l1_r1 = f"CLOSE: ${TELEMETRY['h4_close']:.3f} | MATRIX ASSIGNED BIAS: \033[1;34m{TELEMETRY['h4_bias']}\033[0m"
                l1_r2 = f"BOUNDARIES : TOP: ${TELEMETRY['h4_cloud_top']:.3f} | BOTTOM: ${TELEMETRY['h4_cloud_bottom']:.3f}"
                l1_r3 = f"TENKAN LINE: ${TELEMETRY['h4_tenkan']:.3f} | KIJUN LINE MAP: ${TELEMETRY['h4_kijun']:.3f}"
                
                layer_2_title = "🧬 HIGHEST ORDER REASONING PROFILE"
                l2_r1 = f"H4 ANCHOR DIRECTIONAL CONTROL: {TELEMETRY['h4_bias']}"
                l2_r2 = f"CROSSOVER: {'🟩 TENKAN > KIJUN' if TELEMETRY['h4_tenkan'] > TELEMETRY['h4_kijun'] else '🟥 TENKAN < KIJUN'}"

            # 2. RUNNING UNIFIED CODES TEMPLATE RE-RENDER
            hud = f"""\033[1;35m⚡========================================================================⚡\033[K
                   🪐 TECHLITE TREMOR SPECTRAL COMMAND HUD 🪐\033[K
   [ SYSTEM RUNTIME: {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]} ] | ACTIVE PANEL focus: \033[1;33m{current_view:<12}\033[1;35m ✅\033[K
========================================================================⚡\033[0m\033[K
 \033[1;36m[TARGET CORE] 🌐 SYMBOL: {SYMBOL}\033[0m\033[K
   ↳ ASK: {TELEMETRY['color_code']}${TELEMETRY['ask']:.3f}\033[0m {TELEMETRY['tick_dir']} | BID: \033[1;31m${TELEMETRY['bid']:.3f}\033[0m | SPREAD: \033[1;33m{TELEMETRY['spread']} pts\033[0m\033[K
 \033[1;36m[{layer_1_title}]\033[0m\033[K
   ↳ {l1_r1}\033[K
   ↳ {l1_r2}\033[K
   ↳ {l1_r3}\033[K
 \033[1;36m[{layer_2_title}]\033[0m\033[K
   ↳ [H4 Anchor Grid Layer Status]  ➡️  \033[1;34m{TELEMETRY['h4_bias']}\033[0m\033[K
   ↳ [H1 Anchor Alignment Profile]  ➡️  \033[1;35m{TELEMETRY['bias_h1_cloud']}\033[0m\033[K
   ↳ [M15 Trend Line Crossover State]➡️  {TELEMETRY['bias_m15_cross']}\033[K
   ↳ [M15 Line Volatility Arch Slope]➡️  {TELEMETRY['bias_m15_arch']}\033[K
   ↳ [M15 Dynamic Candlestick Wave] ➡️  {TELEMETRY['bias_m15_mom']}\033[K
   ↳ [M1 Fast Entry Trigger Status] ➡️  \033[1;32m{TELEMETRY['m1_bias']}\033[0m\033[K
\033[1;35m------------------------------------------------------------------------\033[0m\033[K
 \033[1;33m🤖 [DECISION COMMAND ENGINE MATRIX MODE]\033[0m\033[K
   ↳ STATUS REPORT: \033[1;32m{TELEMETRY['status']}\033[0m\033[K
\033[1;35m⚡========================================================================⚡\033[K
 \033[30;47m[HUD CONTROL HUB]: Press [⬅️] or [➡️] Arrow Keys to Flip Console Pages Screen. \033[0m\033[K"""

            sys.stdout.write(hud)
            sys.stdout.flush()
            
            # Key sampling timing matrix
            for _ in range(3):
                if check_hud_navigation():
                    break
                time.sleep(0.05)
                
    except KeyboardInterrupt:
        BOT_RUNNING = False
        mt5.shutdown()
        print("\n\n\033[1;31m[SYSTEM SHUTDOWN CHANNELS DEPLOYED] Links severed cleanly.\033[0m\n")

# ====================================================================
# SYSTEM CORE THREAD SPUR RUNTIME
# ====================================================================
if __name__ == "__main__":
    if not mt5.initialize(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
        print("❌ CRITICAL LINK REJECTION: SYSTEM SEVERED.")
        sys.exit()

    # Launching Independent Data Pipeline Streams
    threading.Thread(target=tick_fluctuation_stream, daemon=True).start()
    threading.Thread(target=adaptive_vibration_trailing_engine, daemon=True).start()
    
    # Spinning the 4 Independent Engine Threads
    threading.Thread(target=m1_analysis_thread, daemon=True).start()
    threading.Thread(target=m15_analysis_thread, daemon=True).start()
    threading.Thread(target=h1_analysis_thread, daemon=True).start()
    threading.Thread(target=h4_analysis_thread, daemon=True).start()
    
    # Launching Order Routing Engine Thread
    threading.Thread(target=order_routing_management_engine, daemon=True).start()

    # Boot console UI display loop on main execution path
    run_command_display_loop()