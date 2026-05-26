import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import time
import os
from datetime import datetime

# ==========================================
# CONFIGURATION
# ==========================================
MT5_LOGIN = 37325074
MT5_PASSWORD = "Adebayo2@" 
MT5_SERVER = "RoboForex-Pro"
SYMBOL = "XAUUSD"          
MAGIC_NUMBER = 2026
BASELINE_KURT = 4.25       
HARD_TARGET = 1.50       

LOT_BC = 0.01   # Weak Signal (BC Rise/Fall)
LOT_ABC = 0.05  # Strong Signal (Confirmed ABC)

# ==========================================
# SENSOR & ALIGNMENT LOGIC
# ==========================================

def get_alignment_state(df):
    # Calculate Ichimoku Components
    t_series = (df['high'].rolling(9).max() + df['low'].rolling(9).min()) / 2
    k_series = (df['high'].rolling(26).max() + df['low'].rolling(26).min()) / 2
    
    # Current and Past Values
    t_c, t_b, t_a = t_series.iloc[-1], t_series.iloc[-2], t_series.iloc[-3]
    k_c, k_b, k_a = k_series.iloc[-1], k_series.iloc[-2], k_series.iloc[-3]
    
    # 1. BC Movement (Most Recent)
    bull_bc = (t_c > t_b) and (k_c > k_b)
    bear_bc = (t_c < t_b) and (k_c < k_b)
    
    # 2. ABC Movement (Confirmation)
    bull_abc = bull_bc and (t_b > t_a) and (k_b > k_a)
    bear_abc = bear_bc and (t_b < t_a) and (k_b < k_a)
    
    vote = "HOLD"
    lot = 0.0
    status = "WAITING"

    # Directional Filtering
    if t_c > k_c: # Bullish Territory
        if bull_abc: 
            vote, lot, status = "BUY", LOT_ABC, "FULL ABC BULL"
        elif bull_bc: 
            vote, lot, status = "BUY", LOT_BC, "BC MOMENTUM"
    elif t_c < k_c: # Bearish Territory
        if bear_abc: 
            vote, lot, status = "SELL", LOT_ABC, "FULL ABC BEAR"
        elif bear_bc: 
            vote, lot, status = "SELL", LOT_BC, "BC MOMENTUM"
        
    return vote, lot, status, bull_bc, bear_bc, t_series, k_series

# ==========================================
# DETAILED DASHBOARD & MGMT
# ==========================================

def update_dashboard(pnl, count, status, kurt, t_val, k_val, vote, lot):
    os.system('cls' if os.name == 'nt' else 'clear')
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"🛰️  TECHLITE SURGICAL SNIPER | {datetime.now().strftime('%H:%M:%S')}")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f" MARKET DATA:")
    print(f"  Tenkan: {t_val:.3f} | Kijun: {k_val:.3f}")
    print(f"  Gap:    {abs(t_val - k_val):.3f}")
    print(f"  Kurt:   {kurt:.2f} ({'SAFE' if kurt < 8.5 else '⚠️ HIGH VOL'})")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f" STRATEGY STATE:")
    print(f"  Mode:   {status}")
    print(f"  Vote:   {vote} (Lot: {lot})")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f" ACCOUNT STATUS:")
    print(f"  Active Trades: {count}")
    print(f"  Float PNL:     ${pnl:.2f} / Target: ${HARD_TARGET}")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

def manage_trade(t_series, k_series, bull_bc, bear_bc):
    positions = mt5.positions_get(symbol=SYMBOL, magic=MAGIC_NUMBER)
    total_pnl = sum(p.profit for p in positions) if positions else 0.0
    
    if not positions:
        return total_pnl, 0
    
    tick = mt5.symbol_info_tick(SYMBOL)
    basket_type = "BUY" if positions[0].type == mt5.POSITION_TYPE_BUY else "SELL"
    t_val = t_series.iloc[-1]
    k_val = k_series.iloc[-1]
    
    # 1. PROFIT TARGET
    if total_pnl >= HARD_TARGET:
        close_all_now(positions, f"TARGET HIT: +${total_pnl:.2f}")
        return 0, 0

    # 2. AGGRESSIVE MOMENTUM KILL-SWITCH
    # If the trend stops rising/falling OR price breaks the Tenkan line
    if basket_type == "BUY":
        if not bull_bc or tick.bid < t_val:
            close_all_now(positions, "REASON: BULLISH SUPPORT LOST / PRICE CROSS")
            return 0, 0
    elif basket_type == "SELL":
        if not bear_bc or tick.ask > t_val:
            close_all_now(positions, "REASON: BEARISH SUPPORT LOST / PRICE CROSS")
            return 0, 0

    # 3. KIJUN TRAILING SYNC
    for p in positions:
        if abs(p.sl - k_val) > 0.02:
            mt5.order_send({"action": mt5.TRADE_ACTION_SLTP, "symbol": SYMBOL, "sl": float(k_val), "position": p.ticket})
            
    return total_pnl, len(positions)

def close_all_now(positions, reason):
    tick = mt5.symbol_info_tick(SYMBOL)
    print(f"🗡️ [EXEC] {reason}")
    for p in positions:
        ct = mt5.ORDER_TYPE_SELL if p.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
        px = tick.bid if p.type == mt5.POSITION_TYPE_BUY else tick.ask
        mt5.order_send({"action": mt5.TRADE_ACTION_DEAL, "position": p.ticket, "symbol": SYMBOL,
                        "volume": p.volume, "type": ct, "price": px, "magic": MAGIC_NUMBER, "type_filling": mt5.ORDER_FILLING_IOC})

# ==========================================
# MAIN LOOP
# ==========================================

def run_sniper_v11():
    if not mt5.initialize(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
        print("MT5 Init Failed")
        return
    
    while True:
        # Pulling 100 bars of M1 data for Ichimoku
        rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M1, 0, 100)
        tick = mt5.symbol_info_tick(SYMBOL)
        if rates is None or tick is None: continue

        df = pd.DataFrame(rates)
        returns = df['close'].pct_change().dropna().tail(20)
        kurt = (returns.kurtosis() + 3) if not returns.empty else 3
        
        vote, lot, status, bull_bc, bear_bc, t_series, k_series = get_alignment_state(df)
        pnl, count = manage_trade(t_series, k_series, bull_bc, bear_bc)

        update_dashboard(pnl, count, status, kurt, t_series.iloc[-1], k_series.iloc[-1], vote, lot)

        # Entry Logic: Single trade at a time
        if count == 0 and vote != "HOLD":
            # Safety filter: Avoid entries during extreme kurtosis spikes
            if kurt <= (BASELINE_KURT * 2):
                order_type = mt5.ORDER_TYPE_BUY if vote == "BUY" else mt5.ORDER_TYPE_SELL
                price_exec = tick.ask if vote == "BUY" else tick.bid
                mt5.order_send({"action": mt5.TRADE_ACTION_DEAL, "symbol": SYMBOL, "volume": lot, 
                                "type": order_type, "price": price_exec, "sl": float(k_series.iloc[-1]), 
                                "magic": MAGIC_NUMBER, "type_filling": mt5.ORDER_FILLING_IOC})
        
        time.sleep(1)

if __name__ == "__main__":
    run_sniper_v11()