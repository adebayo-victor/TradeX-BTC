#Scalper yin
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import time
import os
from datetime import datetime

# ==========================================
# BLOCK 1: CONFIGURATION & SHIELD PARAMS
# ==========================================
MT5_LOGIN = 435634528
MT5_PASSWORD = "Adebayo2@"
MT5_SERVER = "Exness-MT5Trial9"
SYMBOL = "XAUUSDm"            
MAGIC_NUMBER = 2026
MIN_KURTOSIS = 3.2
BASELINE_KURT = 4.25       # Your researched average vibration
SPIKE_MULTIPLIER = 2.0     # 2x Baseline = Market seizure (8.5)
MAX_ALLOWED_SPREAD = 45    # 4.5 Pips protection

prev_state = {"t": 0, "k": 0}

def close_all_positions():
    positions = mt5.positions_get(symbol=SYMBOL, magic=MAGIC_NUMBER)
    if not positions: return
    for pos in positions:
        tick = mt5.symbol_info_tick(SYMBOL)
        type_dict = {mt5.POSITION_TYPE_BUY: mt5.ORDER_TYPE_SELL, mt5.POSITION_TYPE_SELL: mt5.ORDER_TYPE_BUY}
        price_dict = {mt5.POSITION_TYPE_BUY: tick.bid, mt5.POSITION_TYPE_SELL: tick.ask}
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": pos.ticket,
            "symbol": SYMBOL,
            "volume": pos.volume,
            "type": type_dict[pos.type],
            "price": price_dict[pos.type],
            "magic": MAGIC_NUMBER,
            "comment": "SHIELD_PANIC_CLOSE",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        mt5.order_send(request)

def is_market_safe(current_kurt):
    symbol_info = mt5.symbol_info(SYMBOL)
    if symbol_info is None: return False
    
    # 1. Spread Check
    if symbol_info.spread > MAX_ALLOWED_SPREAD:
        print(f"🚨 [SHIELD] HALTED: Spread ({symbol_info.spread}) is toxic.")
        return False
        
    # 2. Volatility Spike Check
    upper_limit = BASELINE_KURT * SPIKE_MULTIPLIER
    if current_kurt > upper_limit:
        print(f"🌋 [SHIELD] HALTED: Vibration Spike ({current_kurt:.2f} > {upper_limit})")
        return False
        
    return True

# ==========================================
# BLOCK 2: LOCAL LOGIC & HUD
# ==========================================
# ==========================================
# BLOCK 2: LOCAL LOGIC (ABC TRIPLE CONFIRMATION)
# ==========================================
def get_local_technical_vote(df, kurt_val):
    global prev_state
    curr_price = df['close'].iloc[-1]
    vibe_buffer = kurt_val * 2 
    
    # Calculate base Ichimoku lines
    t_series = (df['high'].rolling(9).max() + df['low'].rolling(9).min()) / 2
    k_series = (df['high'].rolling(26).max() + df['low'].rolling(26).min()) / 2
    
    # CLOUD for position filtering
    span_a = ((t_series + k_series) / 2).shift(26)
    span_b = ((df['high'].rolling(52).max() + df['low'].rolling(52).min()) / 2).shift(26)
    cloud_top = max(span_a.iloc[-1], span_b.iloc[-1])
    cloud_bottom = min(span_a.iloc[-1], span_b.iloc[-1])

    # --- ABC SEQUENCE (3-Point Polling) ---
    # Tenkan points
    t_c, t_b, t_a = t_series.iloc[-1], t_series.iloc[-2], t_series.iloc[-3]
    # Kijun points
    k_c, k_b, k_a = k_series.iloc[-1], k_series.iloc[-2], k_series.iloc[-3]

    # STAIRCASE VALIDATION (No Ternary Operators)
    bullish_staircase = False
    if t_c > t_b:
        if t_b > t_a:
            if k_c > k_b:
                if k_b > k_a:
                    bullish_staircase = True

    bearish_staircase = False
    if t_c < t_b:
        if t_b < t_a:
            if k_c < k_b:
                if k_b < k_a:
                    bearish_staircase = True

    # --- HUD UPDATE ---
    os.system('cls' if os.name == 'nt' else 'clear')
    shield_status = "🟢 ACTIVE" if is_market_safe(kurt_val) else "🔴 HALTED"
    
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"🚀 SNIPER V10 (ABC) | {SYMBOL} | {shield_status}")
    print(f"🕒 {datetime.now().strftime('%H:%M:%S')} | Spread: {mt5.symbol_info(SYMBOL).spread}")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"Tenkan: [ {t_a:.1f} -> {t_b:.1f} -> {t_c:.1f} ]")
    print(f"Kijun:  [ {k_a:.1f} -> {k_b:.1f} -> {k_c:.1f} ]")
    print(f"Staircase: {'✅ BULLISH' if bullish_staircase else '✅ BEARISH' if bearish_staircase else '❌ NO TREND'}")
    
    prev_state['t'], prev_state['k'] = t_c, k_c

    # --- FINAL VOTE ---
    vote = "HOLD"
    if bullish_staircase:
        if curr_price > (cloud_top + vibe_buffer):
            vote = "BUY"
    elif bearish_staircase:
        if curr_price < (cloud_bottom - vibe_buffer):
            vote = "SELL"
    
    return vote, curr_price


# ==========================================
# BLOCK 3: POSITION MANAGEMENT (PEAK TRACKING V10)
# ==========================================
# Global tracker for trade peaks
trade_peaks = {} 

def manage_trailing(current_kurt):
    global trade_peaks
    positions = mt5.positions_get(symbol=SYMBOL, magic=MAGIC_NUMBER)
    
    # Cleanup dictionary if no positions exist
    if not positions:
        trade_peaks = {}
        return
    
    # --- PANIC CLOSE SHIELD ---
    if not is_market_safe(current_kurt):
        print("🧨 [SHIELD] EXECUTING PANIC CLOSE: Market conditions toxic.")
        close_all_positions()
        return

    tick = mt5.symbol_info_tick(SYMBOL)
    if tick is None: return
    
    dynamic_trigger = current_kurt * 3.5 

    for pos in positions:
        ticket = pos.ticket
        current_profit = pos.profit
        new_sl = pos.sl
        new_tp = pos.tp
        
        # Initialize peak for this ticket if not present
        if ticket not in trade_peaks:
            trade_peaks[ticket] = tick.bid if pos.type == mt5.POSITION_TYPE_BUY else tick.ask

        print(f"📈 PnL: [ ${current_profit:.2f} ] | Trigger: {dynamic_trigger:.2f}")

        # --- 1. KDS Logic (Preserved) ---
        # (Keeping your original KDS logic here as requested)
        total_risk_gap = abs(pos.price_open - pos.sl) if pos.sl != 0 else 5.0 # Fallback 5.0
        current_drawdown_dist = abs(tick.bid - pos.price_open)
        in_danger_zone = (tick.bid < pos.price_open) if pos.type == mt5.POSITION_TYPE_BUY else (tick.bid > pos.price_open)
        
        if in_danger_zone and current_drawdown_dist >= (total_risk_gap * 0.60):
            decay_step = abs(tick.bid - pos.sl) * 0.10
            if pos.type == mt5.POSITION_TYPE_BUY:
                new_sl = max(new_sl, pos.sl + decay_step)
            else:
                new_sl = (pos.sl - decay_step) if new_sl == 0 else min(new_sl, pos.sl - decay_step)
            print(f"🛡️ [KDS ACTIVE] 60% Threshold Met!")

        # --- 2. PEAK TRACKING (Replaces Slipstream) ---
        if current_profit >= dynamic_trigger:
            strength_mod = 1.6 if current_kurt > 4.0 else 1.0
            peak_buffer = 4.50 * strength_mod # How far behind the peak the SL sits
            
            if pos.type == mt5.POSITION_TYPE_BUY:
                # Track the highest peak
                if tick.bid > trade_peaks[ticket]:
                    trade_peaks[ticket] = tick.bid
                
                # Set SL relative to the HIGHEST peak reached
                calculated_sl = trade_peaks[ticket] - peak_buffer
                if calculated_sl > new_sl:
                    new_sl = calculated_sl
                    print(f"🏔️ [PEAK UP] SL Moved to: {new_sl:.2f}")
            
            else: # SELL POSITION
                # Track the lowest peak (trough)
                if tick.ask < trade_peaks[ticket]:
                    trade_peaks[ticket] = tick.ask
                
                # Set SL relative to the LOWEST peak reached
                calculated_sl = trade_peaks[ticket] + peak_buffer
                if new_sl == 0 or calculated_sl < new_sl:
                    new_sl = calculated_sl
                    print(f"🏔️ [PEAK DOWN] SL Moved to: {new_sl:.2f}")

        # --- 3. EXECUTION ---
        if (new_sl != pos.sl and new_sl != 0) or (new_tp != pos.tp):
            request = {
                "action": mt5.TRADE_ACTION_SLTP, 
                "symbol": SYMBOL, 
                "sl": float(new_sl), 
                "tp": float(new_tp), 
                "position": pos.ticket
            }
            result = mt5.order_send(request)
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                print(f"⚠️ [ERROR] SL Update Failed: {result.comment}")

# ==========================================
# BLOCK 4: THE MAIN LOOP
# ==========================================
def run_sniper_v9():
    if not mt5.initialize(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER): return
    while True:
        active_positions = mt5.positions_get(symbol=SYMBOL, magic=MAGIC_NUMBER)
        rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M15, 0, 100)
        tick = mt5.symbol_info_tick(SYMBOL)
        if rates is None or tick is None: continue

        df = pd.DataFrame(rates)
        returns = df['close'].pct_change().dropna().tail(20)
        kurt = (returns.kurtosis() + 3) if not returns.empty else 3
        
        local_vote, current_price = get_local_technical_vote(df, kurt)
        manage_trailing(kurt)

        if not active_positions:
            # ENTRY GUARD: Check Volatility Spike Shield before firing
            if local_vote != "HOLD" and MIN_KURTOSIS <= kurt:
                if is_market_safe(kurt):
                    tp_dist = kurt * 20
                    order_type = mt5.ORDER_TYPE_BUY if local_vote == "BUY" else mt5.ORDER_TYPE_SELL
                    price_exec = tick.ask if local_vote == "BUY" else tick.bid
                    take_profit = (current_price + tp_dist) if local_vote == "BUY" else (current_price - tp_dist)
                    
                    request = {
                        "action": mt5.TRADE_ACTION_DEAL, "symbol": SYMBOL, "volume": 0.1, "type": order_type,
                        "price": price_exec, "tp": float(take_profit), "magic": MAGIC_NUMBER,
                        "comment": "V9.5_SHIELD_SNIPER", "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC,
                    }
                    result = mt5.order_send(request)
                    if result.retcode == mt5.TRADE_RETCODE_DONE:
                        print(f"🏹 [FIRE] {local_vote} Executed at {price_exec}")
                else:
                    print(f"🚫 [SCAN] Entry Aborted: Market is too unstable.")

        time.sleep(1 if active_positions else 1)

if __name__ == "__main__":
    run_sniper_v9()