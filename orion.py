import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import time
from datetime import datetime

# ==========================================
# CONFIGURATION - TECHLITE ORION V1 (M15)
# ==========================================
MT5_LOGIN = 435634528
MT5_PASSWORD = "Adebayo2@"
MT5_SERVER = "Exness-MT5Trial9"
SYMBOL = "XAUUSDm"
MAGIC_NUMBER = 8888
LOT_SIZE = 0.05
MAX_SPREAD = 200

# Strategy Params
RSI_PERIOD = 14
BB_PERIOD = 20
BB_STD = 2.0

# ==========================================
# CORE ENGINE
# ==========================================

def get_orion_signals():
    # Fetch M15 data
    rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M15, 0, 100)
    if rates is None: return None
    
    df = pd.DataFrame(rates)
    
    # 1. RSI Calculation
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=RSI_PERIOD).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=RSI_PERIOD).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # 2. Bollinger Bands
    df['sma'] = df['close'].rolling(BB_PERIOD).mean()
    df['std'] = df['close'].rolling(BB_PERIOD).std()
    df['upper'] = df['sma'] + (BB_STD * df['std'])
    df['lower'] = df['sma'] - (BB_STD * df['std'])
    
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    
    # 3. Logic: Mean Reversion Strike
    signal = None
    # SELL: Price touches upper band AND RSI is Overbought
    if curr['close'] >= curr['upper'] and curr['rsi'] > 70:
        signal = "SELL"
    # BUY: Price touches lower band AND RSI is Oversold
    elif curr['close'] <= curr['lower'] and curr['rsi'] < 30:
        signal = "BUY"
        
    return {
        "signal": signal,
        "price": curr['close'],
        "rsi": curr['rsi'],
        "upper": curr['upper'],
        "lower": curr['lower'],
        "time": curr['time']
    }

def execute_orion():
    if not mt5.initialize(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER): return
    
    last_time = None
    print("🌌 Techlite Orion V1: ONLINE (M15)")

    while True:
        data = get_orion_signals()
        tick = mt5.symbol_info_tick(SYMBOL)
        
        if data and tick:
            spread = (tick.ask - tick.bid) / mt5.symbol_info(SYMBOL).point
            
            # Print Telemetry
            print(f"[{datetime.now().strftime('%H:%M')}] RSI: {data['rsi']:.1f} | SPREAD: {spread:.0f}")

            # New Candle Execution
            if data['time'] != last_time:
                if spread <= MAX_SPREAD and len(mt5.positions_get(magic=MAGIC_NUMBER)) == 0:
                    
                    if data['signal'] == "BUY":
                        # SL at Lower Band, TP at SMA (Middle Band)
                        send_order(mt5.ORDER_TYPE_BUY, tick.ask, data['lower'])
                    elif data['signal'] == "SELL":
                        send_order(mt5.ORDER_TYPE_SELL, tick.bid, data['upper'])
                
                last_time = data['time']
        
        time.sleep(15)

def send_order(otype, price, sl):
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": LOT_SIZE,
        "type": otype,
        "price": price,
        "sl": float(sl),
        "magic": MAGIC_NUMBER,
        "comment": "ORION_STRIKE",
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    print(f"🎯 ORION { 'BUY' if otype==0 else 'SELL' } EXECUTED")

if __name__ == "__main__":
    execute_orion()