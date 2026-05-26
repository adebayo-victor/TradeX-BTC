import os
import time
import numpy as np
import pandas as pd
import MetaTrader5 as mt5
from datetime import datetime

# Current execution time: 2026-05-20 16:38:26 🕒
MT5_LOGIN = 37325074
MT5_PASSWORD = "Adebayo2@"
MT5_SERVER = "RoboForex-Pro"

# ==============================================================================
# 📜 1. LOGGING AND PERSISTENT STORAGE SYSTEM
# ==============================================================================
def write_and_print_log(message, filename="techlite_engine_runtime.txt"):
    """Synchronizes live console outputs with local text files."""
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_message = f"[{current_time}] {message}"
    print(formatted_message)
    
    if not os.path.exists(filename):
        with open(filename, "w", encoding="utf-8") as f:
            f.write("=== TECHLITE INSTITUTIONAL FUNCTIONAL ENGINE LOG SYSTEM ===\n\n")
            
    with open(filename, "a", encoding="utf-8") as f:
        f.write(formatted_message + "\n")

# ==============================================================================
# 🧠 2. ENGINE MATHEMATICAL AND CALCULATION FUNCTIONS
# ==============================================================================
def calculate_kurtosis_vibration(series, kurt_period=20):
    """Computes excess kurtosis for localized market vibration mechanics."""
    if len(series) < kurt_period:
        return 0.0
    
    mean = np.mean(series)
    std = np.std(series)
    
    if std == 0:
        return 0.0
        
    excess_kurt = (np.mean((series - mean) ** 4) / (std ** 4)) - 3.0
    return excess_kurt

def process_market_data(df, kurt_period=20):
    """Calculates directional structural pushes and kurtosis arrays."""
    df = df.copy()
    df['vibration'] = 0.0
    df['direction_bias'] = "NEUTRAL"
    df['returns'] = np.log(df['close'] / df['close'].shift(1))
    
    for i in range(kurt_period, len(df)):
        window_returns = df['returns'].iloc[i - kurt_period + 1 : i + 1]
        df.loc[df.index[i], 'vibration'] = calculate_kurtosis_vibration(window_returns, kurt_period)
        
        window_data = df.iloc[i - kurt_period + 1 : i + 1]
        total_upward = (window_data['high'] - window_data['open']).sum()
        total_downward = (window_data['open'] - window_data['low']).sum()
        
        if total_upward > total_downward:
            df.loc[df.index[i], 'direction_bias'] = "GREEN"
        if total_downward > total_upward:
            df.loc[df.index[i], 'direction_bias'] = "RED"
            
    return df

def check_ichimoku_filter(df, idx, tenkan_period=9, tenkan_lookback=3, tenkan_threshold=0.0005):
    """Validates structural speed gradient filters calibrated for the H1 timeframe."""
    if idx < tenkan_period + tenkan_lookback:
        return {"direction": "FLAT", "steep_enough": False, "value": 0.0}
        
    w1 = df.iloc[idx - tenkan_period + 1 : idx + 1]
    current_tenkan = (w1['high'].max() + w1['low'].min()) / 2.0
    
    w2 = df.iloc[idx - tenkan_period : idx]
    prev_tenkan = (w2['high'].max() + w2['low'].min()) / 2.0
    
    w3 = df.iloc[idx - tenkan_period + 1 - tenkan_lookback : idx + 1 - tenkan_lookback]
    hist_tenkan = (w3['high'].max() + w3['low'].min()) / 2.0
    
    direction = "FLAT"
    if current_tenkan > prev_tenkan:
        direction = "UP"
    if current_tenkan < prev_tenkan:
        direction = "DOWN"
        
    current_price = df['close'].iloc[idx]
    normalized_steepness = abs(current_tenkan - hist_tenkan) / current_price
    
    steep_enough = False
    if normalized_steepness >= tenkan_threshold:
        steep_enough = True
        
    return {"direction": direction, "steep_enough": steep_enough, "value": normalized_steepness}

def scan_smc_traps(df, idx, direction, current_trough, current_peak, ote_low=0.618, ote_high=0.786):
    """Scans for FVG, Breaker Blocks, and OTE discount entry signatures."""
    signals = {"FVG": False, "Breaker": False, "OTE": False, "Entry_Price": None}
    if idx < 3:
        return signals

    if direction == "GREEN":
        if df['high'].iloc[idx-2] < df['low'].iloc[idx]:
            signals["FVG"] = True
            signals["Entry_Price"] = df['high'].iloc[idx-2]
    if direction == "RED":
        if df['low'].iloc[idx-2] > df['high'].iloc[idx]:
            signals["FVG"] = True
            signals["Entry_Price"] = df['low'].iloc[idx-2]

    if direction == "GREEN":
        if df['close'].iloc[idx] > df['high'].iloc[idx-1]:
            signals["Breaker"] = True
            if signals["Entry_Price"] is None:
                signals["Entry_Price"] = df['high'].iloc[idx-1]
    if direction == "RED":
        if df['close'].iloc[idx] < df['low'].iloc[idx-1]:
            signals["Breaker"] = True
            if signals["Entry_Price"] is None:
                signals["Entry_Price"] = df['low'].iloc[idx-1]

    if current_peak > current_trough and current_peak != 0:
        total_range = current_peak - current_trough
        current_price = df['close'].iloc[idx]
        ote_start = current_peak - (total_range * ote_low)
        ote_end = current_peak - (total_range * ote_high)
        
        if ote_end <= current_price <= ote_start:
            signals["OTE"] = True
            if signals["Entry_Price"] is None:
                signals["Entry_Price"] = current_price
                
    return signals

# ==============================================================================
# 🛡️ 3. RISK ALLOCATION AND PROTECTION CALCULATIONS
# ==============================================================================
def calculate_vibration_sl(df, idx, trade_type, vib_mult=1.5, min_lb=5, max_lb=30):
    """Derives multi-bar lookback dynamically scaling via raw kurtosis values."""
    raw_vibration = abs(df['vibration'].iloc[idx])
    calculated_lookback = int(np.round(raw_vibration * vib_mult))
    
    lookback_window = calculated_lookback
    if lookback_window < min_lb:
        lookback_window = min_lb
    if lookback_window > max_lb:
        lookback_window = max_lb
        
    history_slice = df.iloc[idx - lookback_window + 1 : idx + 1]
    
    stop_loss_price = 0.0
    if trade_type == "BUY":
        stop_loss_price = history_slice['low'].min()
    if trade_type == "SELL":
        stop_loss_price = history_slice['high'].max()
        
    return stop_loss_price

def manage_open_trade(processed_df, last_idx, active_trade, current_peak, current_trough, symbol="XAUUSD"):
    """
    Tracks an open position, dynamically logs live profit telemetry, and executes
    immediate break-even/green trailing stop updates. Reversion exits are omitted.
    """
    ticket = active_trade['ticket']
    trade_type = active_trade['type']
    current_sl = active_trade['current_sl']
    entry_price = active_trade['entry_price']
    
    tick_info = mt5.symbol_info_tick(symbol)
    if tick_info is None:
        return active_trade

    # --------------------------------------------------------------------------
    # 💵 REAL-TIME PROFIT CALCULATION & TELEMETRY
    # --------------------------------------------------------------------------
    current_price = tick_info.bid if trade_type == "BUY" else tick_info.ask
    
    if trade_type == "BUY":
        pip_diff = (current_price - entry_price) * 10  
    else:
        pip_diff = (entry_price - current_price) * 10

    estimated_cent_profit = pip_diff * 1.0  
    profit_emoji = "🟢 PROFIT" if pip_diff >= 0 else "🔴 LOSS"
    
    write_and_print_log(
        f"🛰️ POSITION TELEMETRY | Ticket #{ticket} | {trade_type} | "
        f"Entry: {entry_price:.2f} ➡️ Live: {current_price:.2f} | "
        f"{profit_emoji}: {pip_diff:+.2f} Pips ({estimated_cent_profit:+.2f} Cents)"
    )

    # --------------------------------------------------------------------------
    # 🎯 CONDITION: MINIMUM DYNAMIC GREEN PROFIT LOCK
    # --------------------------------------------------------------------------
    latest_vibration = processed_df['vibration'].iloc[last_idx]
    vibration_offset = latest_vibration * 1.5
    
    new_sl_target = current_sl
    modify_required = False
    
    if trade_type == "BUY":
        calculated_floor = current_trough + vibration_offset
        if tick_info.bid > (entry_price + vibration_offset) and current_sl < entry_price:
            new_sl_target = entry_price + 0.10  
            modify_required = True
        elif calculated_floor > current_sl and calculated_floor > entry_price:
            new_sl_target = calculated_floor
            modify_required = True
            
    if trade_type == "SELL":
        calculated_ceiling = current_peak - vibration_offset
        if tick_info.ask < (entry_price - vibration_offset) and current_sl > entry_price:
            new_sl_target = entry_price - 0.10  
            modify_required = True
        elif calculated_ceiling < current_sl and calculated_ceiling < entry_price:
            new_sl_target = calculated_ceiling
            modify_required = True
            
    # --------------------------------------------------------------------------
    # 🖥️ TRAILING EXECUTION ENGINE
    # --------------------------------------------------------------------------
    if modify_required:
        new_sl_target = round(new_sl_target, 2)
        
        modification_request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "sl": new_sl_target,
            "tp": 0.0,
        }
        
        mod_result = mt5.order_send(modification_request)
        if mod_result is not None and mod_result.retcode == mt5.TRADE_RETCODE_DONE:
            write_and_print_log(f"🔄 SAFETY LOCKED: Stop Loss updated to {new_sl_target:.2f} ✅")
            active_trade['current_sl'] = new_sl_target
            active_trade['is_trailing_active'] = True

    return active_trade

# ==============================================================================
# 🔌 4. METATRADER 5 LIVE NETWORK INTERACTION FUNCTIONS
# ==============================================================================
def connect_mt5_terminal(symbol):
    """Establishes execution pipelines with backend server networks."""
    if not mt5.initialize(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
        return False
    mt5.symbol_select(symbol, True)
    return True

def fetch_live_dataframe(symbol, timeframe, max_bars=200):
    """Pulls current live data pools into clean pandas structures."""
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, max_bars)
    if rates is None:
        return pd.DataFrame()
        
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df

def execute_market_order(symbol, action_type, volume, stop_loss_price, deviation=20):
    """Dispatches algorithmic execution commands straight to market nodes."""
    tick_info = mt5.symbol_info_tick(symbol)
    order_type = mt5.ORDER_TYPE_BUY
    entry_price = tick_info.ask
    
    if action_type == "SELL":
        order_type = mt5.ORDER_TYPE_SELL
        entry_price = tick_info.bid

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(volume),
        "type": order_type,
        "price": float(entry_price),
        "sl": float(stop_loss_price),
        "deviation": int(deviation),
        "magic": 20260520,
        "comment": "Techlite H1 Core",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    return result

# ==============================================================================
# 🏃‍♂️ 5. MAIN CORE PRODUCTION LOOP RUNTIME (ADVANCED PRO-PATCH)
# ==============================================================================
SYMBOL = "XAUUSD"  
TIMEFRAME = mt5.TIMEFRAME_H1  
LOT_SIZE = 0.10
KURTOSIS_BREAKOUT_THRESHOLD = 1.5  # 🛡️ BANS ALL CLOUD/EQUILIBRIUM TRADES

write_and_print_log(f"📞 SYSTEM INITIATION: Running H1 single-entry core engine for [{SYMBOL}]...")

if connect_mt5_terminal(SYMBOL):
    write_and_print_log("✅ CONNECTION ESTABLISHED: MT5 data stream pipe open. 🚀")
    active_trade = None
    last_processed_candle_time = None
    last_trade_candle_time = None  
    
    # 🕵️‍♂️ AUTO-DETECTION: Immediately hijack active trades found on terminal startup
    existing_positions = mt5.positions_get(symbol=SYMBOL)
    if existing_positions is not None and len(existing_positions) > 0:
        open_pos = existing_positions[0]
        trade_dir = "BUY"
        if open_pos.type == mt5.POSITION_TYPE_SELL:
            trade_dir = "SELL"
            
        active_trade = {
            "ticket": open_pos.ticket,
            "type": trade_dir,
            "entry_price": open_pos.price_open,
            "initial_sl": open_pos.sl,
            "current_sl": open_pos.sl,
            "is_trailing_active": False
        }
        write_and_print_log(f"🛰️ HIJACK SUCCESS: Tracking existing open Ticket #{active_trade['ticket']} ({trade_dir}) at {active_trade['entry_price']:.2f}")
    else:
        write_and_print_log("🛰️ SCANNERS ENGAGED: Standing by for high-volatility H1 updates...")
    
    try:
        while True:
            raw_data = fetch_live_dataframe(SYMBOL, TIMEFRAME)
            
            if not raw_data.empty:
                latest_candle_time = raw_data['time'].iloc[-1]
                processed_df = process_market_data(raw_data)
                last_idx = len(processed_df) - 1
                
                structural_window = processed_df.iloc[-30:]
                current_peak = structural_window['high'].max()
                current_trough = structural_window['low'].min()
                
                latest_close = processed_df['close'].iloc[last_idx]
                latest_vibration = processed_df['vibration'].iloc[last_idx]
                latest_bias = processed_df['direction_bias'].iloc[last_idx]

                # 📑 1. TRACKING MODE: Prioritized status checks
                if active_trade is not None:
                    check_pos = mt5.positions_get(ticket=active_trade['ticket'])
                    if check_pos is not None and len(check_pos) > 0:
                        active_trade = manage_open_trade(processed_df, last_idx, active_trade, current_peak, current_trough)
                    else:
                        write_and_print_log(f"🚫 STOP HIT / MANUAL CLOSE: Clearing trade tracking metrics. 🏁")
                        active_trade = None

                # 🕯️ 2. SCANNING MODE: Zero duplication guard
                if active_trade is None:
                    if latest_candle_time != last_processed_candle_time:
                        
                        if latest_candle_time == last_trade_candle_time:
                            time.sleep(1)
                            continue
                            
                        write_and_print_log(f"🎬 NEW H1 CANDLE DETECTED: [{latest_candle_time}] - Scanning Matrix...")
                        last_processed_candle_time = latest_candle_time
                        
                        ichimoku = check_ichimoku_filter(processed_df, last_idx, tenkan_threshold=0.0005)
                        traps = scan_smc_traps(processed_df, last_idx, latest_bias, current_trough, current_peak)
                        
                        direction_emoji = "↗️ GREEN" if latest_bias == "GREEN" else "↘️ RED"
                        write_and_print_log(f"📊 H1 EVAL - Close: {latest_close:.2f} | Bias: {direction_emoji} | Kurtosis: {latest_vibration:.4f}")
                        
                        can_enter = False
                        trade_dir = "BUY"
                        
                        # Apply strict Kurtosis threshold checks to stay clear of the Kumo cloud range
                        if latest_bias == "GREEN" and ichimoku['direction'] == "UP" and ichimoku['steep_enough']:
                            if abs(latest_vibration) >= KURTOSIS_BREAKOUT_THRESHOLD:
                                if traps['FVG'] or traps['Breaker'] or traps['OTE']:
                                    can_enter = True
                                    trade_dir = "BUY"
                                
                        if latest_bias == "RED" and ichimoku['direction'] == "DOWN" and ichimoku['steep_enough']:
                            if abs(latest_vibration) >= KURTOSIS_BREAKOUT_THRESHOLD:
                                if traps['FVG'] or traps['Breaker'] or traps['OTE']:
                                    can_enter = True
                                    trade_dir = "SELL"

                        if can_enter:
                            write_and_print_log(f"💥 CONFLUENCE VALIDATED: Dispatching single {trade_dir} order...")
                            sl_target = calculate_vibration_sl(processed_df, last_idx, trade_dir)
                            order_receipt = execute_market_order(SYMBOL, trade_dir, LOT_SIZE, sl_target)
                            
                            if order_receipt is not None and order_receipt.retcode == mt5.TRADE_RETCODE_DONE:
                                active_trade = {
                                    "ticket": order_receipt.order,
                                    "type": trade_dir,
                                    "entry_price": order_receipt.price,
                                    "initial_sl": sl_target,
                                    "current_sl": sl_target,
                                    "is_trailing_active": False
                                }
                                last_trade_candle_time = latest_candle_time
                                write_and_print_log(f"✅ EXECUTED: Ticket #{active_trade['ticket']} loaded. Tracking active.")
                            else:
                                ret_code = order_receipt.retcode if order_receipt else "No Response"
                                write_and_print_log(f"❌ FAILURE: Server rejected request. Code: {ret_code}")

            time.sleep(1)
            
    except KeyboardInterrupt:
        write_and_print_log("🚫 SHUTDOWN COMMAND: Safely shutting down system terminals.")
        mt5.shutdown()
else:
    write_and_print_log("❌ ERROR: Initialization pipelines could not lock connections.")