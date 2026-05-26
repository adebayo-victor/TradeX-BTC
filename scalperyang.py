import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import time
from datetime import datetime

# ==========================================
# CONFIGURATION - TECHLITE PHOENIX V2 (PRO)
# ==========================================
MT5_LOGIN = 37325074
MT5_PASSWORD = "your_password_here"
MT5_SERVER = "RoboForex-Pro"
SYMBOL = "XAUUSD"
MAGIC_NUMBER = 2026
LOT_SIZE = 0.05
MAX_SPREAD = 35 # Filter for Gold volatility

# Session Windows (Lagos/London Time)
# 8 AM to 5 PM covers London and the heavy NY Overlap
START_HOUR = 8 
END_HOUR = 17

# Momentum & Elasticity
ATR_PERIOD = 14
MIN_SPEED_PCT = 0.20
MAX_SPEED_PCT = 0.85
SNAP_RECLAIM_PCT = 0.50

# Global storage for peak tracking
trade_peak = 0.0

# ==========================================
# CORE UTILITIES
# ==========================================

def is_trading_session():
    current_hour = datetime.now().hour
    if START_HOUR <= current_hour < END_HOUR:
        return True
    return False

def get_market_physics():
    rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_H1, 0, 100)
    if rates is None: return None
    
    df = pd.DataFrame(rates)
    
    # ATR & Ichimoku
    df['tr'] = pd.concat([df['high']-df['low'], 
                         abs(df['high']-df['close'].shift()), 
                         abs(df['low']-df['close'].shift())], axis=1).max(axis=1)
    atr = df['tr'].rolling(ATR_PERIOD).mean().iloc[-1]
    
    df['tenkan'] = (df['high'].rolling(9).max() + df['low'].rolling(9).min()) / 2
    df['kijun'] = (df['high'].rolling(26).max() + df['low'].rolling(26).min()) / 2
    
    return {
        "price": df['close'].iloc[-1],
        "t_curr": df['tenkan'].iloc[-1], "t_prev": df['tenkan'].iloc[-2],
        "k_curr": df['kijun'].iloc[-1],
        "atr": atr,
        "time": df['time'].iloc[-1] # For "New Candle" check
    }

# ==========================================
# ACTIVE TRADE MANAGEMENT (REAL PEAK)
# ==========================================

def manage_active_elasticity(physics):
    global trade_peak
    positions = mt5.positions_get(symbol=SYMBOL, magic=MAGIC_NUMBER)
    
    if not positions:
        trade_peak = 0.0 # Reset when no trade
        return
    
    p = positions[0]
    curr_price = physics['price']
    tenkan = physics['t_curr']
    atr = physics['atr']

    # 1. TRACK REAL PEAK (The Fix)
    if p.type == mt5.POSITION_TYPE_BUY:
        if trade_peak == 0.0: trade_peak = p.price_open
        if curr_price > trade_peak: trade_peak = curr_price
        
        # Elasticity Math
        stretch = trade_peak - tenkan
        reclaim = trade_peak - curr_price
        
        # The SNAP
        if stretch > 0:
            if reclaim > (stretch * SNAP_RECLAIM_PCT):
                close_trade(p, "ELASTIC SNAP (50%)")
        
        # Equilibrium Breach
        if curr_price < tenkan:
            close_trade(p, "TENKAN BREACH")

    elif p.type == mt5.POSITION_TYPE_SELL:
        if trade_peak == 0.0: trade_peak = p.price_open
        if curr_price < trade_peak or trade_peak == 0.0: trade_peak = curr_price
        
        stretch = tenkan - trade_peak
        reclaim = curr_price - trade_peak
        
        if stretch > 0:
            if reclaim > (stretch * SNAP_RECLAIM_PCT):
                close_trade(p, "ELASTIC SNAP (50%)")
        
        if curr_price > tenkan:
            close_trade(p, "TENKAN BREACH")

# ==========================================
# EXECUTION ENGINE
# ==========================================

def run_phoenix_v2():
    if not mt5.initialize(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
        return

    last_processed_candle = None
    print("🔥 Techlite Phoenix V2: DEPLOYED")

    while True:
        physics = get_market_physics()
        tick = mt5.symbol_info_tick(SYMBOL)
        if physics is None or tick is None: continue
        
        # 1. ALWAYS Manage Exits (Every loop)
        manage_active_elasticity(physics)
        
        # 2. EVALUATE ENTRIES ONLY ON NEW H1 CANDLE (The Fix)
        if physics['time'] != last_processed_candle:
            
            if is_trading_session():
                spread = (tick.ask - tick.bid) / mt5.symbol_info(SYMBOL).point
                
                if spread <= MAX_SPREAD:
                    # Entry Checklist
                    speed = abs(physics['t_curr'] - physics['t_prev'])
                    intensity_ok = (physics['atr'] * MIN_SPEED_PCT) < speed < (physics['atr'] * MAX_SPEED_PCT)
                    
                    if intensity_ok and len(mt5.positions_get(symbol=SYMBOL, magic=MAGIC_NUMBER)) == 0:
                        # Bullish
                        if physics['t_curr'] > physics['k_curr'] and physics['t_curr'] > physics['t_prev']:
                            if physics['price'] > physics['t_curr']:
                                open_trade(mt5.ORDER_TYPE_BUY, physics['k_curr'])
                        # Bearish
                        elif physics['t_curr'] < physics['k_curr'] and physics['t_curr'] < physics['t_prev']:
                            if physics['price'] < physics['t_curr']:
                                open_trade(mt5.ORDER_TYPE_SELL, physics['k_curr'])
            
            last_processed_candle = physics['time']
            
        time.sleep(5)

def open_trade(otype, sl):
    tick = mt5.symbol_info_tick(SYMBOL)
    price = tick.ask if otype == mt5.ORDER_TYPE_BUY else tick.bid
    mt5.order_send({
        "action": mt5.TRADE_ACTION_DEAL, "symbol": SYMBOL, "volume": LOT_SIZE,
        "type": otype, "price": price, "sl": float(sl), "magic": MAGIC_NUMBER,
        "type_filling": mt5.ORDER_FILLING_IOC
    })
    print(f"🚀 PHOENIX ENTRY: {'BUY' if otype==0 else 'SELL'}")

def close_trade(p, reason):
    tick = mt5.symbol_info_tick(SYMBOL)
    otype = mt5.ORDER_TYPE_SELL if p.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
    price = tick.bid if p.type == mt5.POSITION_TYPE_BUY else tick.ask
    mt5.order_send({
        "action": mt5.TRADE_ACTION_DEAL, "symbol": SYMBOL, "volume": p.volume,
        "type": otype, "position": p.ticket, "price": price, "magic": MAGIC_NUMBER,
        "type_filling": mt5.ORDER_FILLING_IOC
    })
    print(f"🗡️ PHOENIX EXIT: {reason}")

if __name__ == "__main__":
    run_phoenix_v2()