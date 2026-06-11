import sys
import time

import MetaTrader5 as parent_mt5
from strategytester5.trade_classes.Trade import CTrade
from strategytester5.MetaTrader5.api import VirtualMetaTrader5
from strategytester5.tester import run_backtesting
from strategytester5.MQL5.functions import PeriodSeconds
import pandas as pd
import numpy as np

if not parent_mt5.initialize():
    raise RuntimeError(f"Failed to initialize mt5. Error = {parent_mt5.last_error()}")

virtual_mt5 = VirtualMetaTrader5(parent_mt5=parent_mt5)
mt5 = parent_mt5

SCRIPT_ARGS = sys.argv[1:]  # Check the parent mode (whether a user wants to backtest, do live trading, or optimization)
if "--backtesting" in SCRIPT_ARGS or "--optimization" in SCRIPT_ARGS:
    mt5 = virtual_mt5  # simulated MetaTader5 instance

SYMBOLS = ["EURUSD",
           "GBPUSD",
           "AUDUSD",
           "USDCAD",
           "USDCHF",
           ]

TIMEFRAME = mt5.TIMEFRAME_H1
MAGIC_NUMBER = 2026
SLIPPAGE = 100

tester_config = {
    "bot_name": "Breakout multi-currency",
    "symbols": SYMBOLS,
    "timeframe": "H1",
    "start_date": "01.01.2025",
    "end_date": "01.06.2026",
    "modelling": "1 minute ohlc",
    "leverage": "1:100",
    "deposit": 1000,
    "visual_mode": True
}

m_trade_objects = [
    CTrade(magic_number=MAGIC_NUMBER, symbol=s, terminal=mt5, deviation_points=SLIPPAGE) for s in SYMBOLS
]


def pos_exists(symbol: str, magic_number: int, pos_type: int) -> bool:
    positions = mt5.positions_get()
    if positions is None:
        return False

    for pos in positions:
        if pos.symbol == symbol and pos.magic == magic_number and pos.type == pos_type:
            return True

    return False


def is_new_bar(tf: int, current_time_seconds: int) -> bool:
    tf_seconds = PeriodSeconds(tf)
    return current_time_seconds % tf_seconds == 0


def main(symbol: str,
         symbol_cache: dict,
         m_trade: CTrade,
         window: int = 24,
         shift: int = 2,
         rr_ratio: float = 2.0,
         ):
    ticks = mt5.symbol_info_tick(symbol)
    if ticks is None:
        return

    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        return

    if is_new_bar(tf=TIMEFRAME, current_time_seconds=ticks.time): # if a new bar has emerged

        rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, window)
        symbol_cache["rates_df"] = pd.DataFrame(rates)

        rates_df = symbol_cache["rates_df"]

        if rates_df is None or len(rates_df) < window:
            return

        rates_window = rates_df.iloc[:-shift]
        symbol_cache["support"] = np.min(rates_window["low"])  # lowest low in the window
        symbol_cache["resistance"] = np.max(rates_window["high"])  # the highest high value in the window
        symbol_cache["mean_tick_volume"] = rates_window["tick_volume"].mean()
        symbol_cache["tick_volume"] = rates_df["tick_volume"].iloc[-1]
        symbol_cache["current_close"] = rates_df["close"].iloc[-1]

    current_close = symbol_cache["current_close"]
    support_line = symbol_cache["support"]
    resistance_line = symbol_cache["resistance"]
    mean_tick_volume = symbol_cache["mean_tick_volume"]
    tick_volume = symbol_cache["tick_volume"]

    if current_close is None or support_line is None or resistance_line is None or mean_tick_volume is None or tick_volume is None:
        return

    volume = symbol_info.volume_min

    if tick_volume > mean_tick_volume:  # increased volatility

        if current_close > resistance_line:  # bullish breakout
            entry_price = ticks.ask
            sl_diff = entry_price - support_line

            if not pos_exists(symbol, MAGIC_NUMBER, mt5.POSITION_TYPE_BUY):
                m_trade.buy(volume=volume,
                            price=entry_price,
                            sl=support_line,
                            tp=entry_price + sl_diff * rr_ratio
                            )

        if current_close < support_line:  # bearish breakout

            entry_price = ticks.bid
            sl_diff = resistance_line - entry_price

            if not pos_exists(symbol, MAGIC_NUMBER, mt5.POSITION_TYPE_SELL):
                m_trade.sell(volume=volume,
                             price=entry_price,
                             sl=resistance_line,
                             tp=entry_price - sl_diff * rr_ratio
                             )


symbols_cache = {
    symbol: {
        "rates_df": None,
        "current_close": None,
        "support": None,
        "resistance": None,
        "mean_tick_volume": None,
        "tick_volume": None,
    } for symbol in SYMBOLS
}


def multicurrency(
        window: int = 24,
        shift: int = 2,
        rr_ratio: float = 2.0):

    # call the strategy on multiple instruments iteratively
    for i, symbol in enumerate(SYMBOLS):
        s_cache = symbols_cache[symbol]
        m_trade = m_trade_objects[i]

        main(symbol, s_cache, m_trade, window, shift, rr_ratio)


multicurrency_fn_call = lambda: multicurrency(window=24, shift=2, rr_ratio=2.0)

if "--backtesting" in SCRIPT_ARGS:

    # run backtesting

    tester_stats = run_backtesting(
        main_function=multicurrency_fn_call,
        tester_config=tester_config,
        virtual_mt5=mt5,
        dashboard_fps=60
    )
else:
    #live trading
    while True:
        multicurrency_fn_call()
        time.sleep(1)