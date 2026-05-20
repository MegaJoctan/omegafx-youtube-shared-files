import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from strategytester5.MQL5.functions import PeriodSeconds
from strategytester5.trade_classes.SymbolInfo import CSymbolInfo
from strategytester5.trade_classes.Trade import CTrade
from typing import Any, Optional

if not mt5.initialize():
    raise RuntimeError(f"Failed to initialize mt5. Error = {mt5.last_error()}")

SYMBOL = "EURUSD"
TIMEFRAME = mt5.TIMEFRAME_H1
MAGIC_NUMBER = 12345
SLIPPAGE = 100

m_trade = CTrade(
    magic_number=MAGIC_NUMBER,
    filling_type_symbol=SYMBOL,
    terminal=mt5,
    deviation_points=SLIPPAGE
)

def is_new_bar(current_time_secs: int, tf: int=TIMEFRAME):

    tf_seconds = PeriodSeconds(tf)
    return current_time_secs % tf_seconds == 0 # new bar e.g., at 11:00, 12:000, etc.

def count_positions(which_mt5, type: int, magic: int=MAGIC_NUMBER, symbol: str=SYMBOL) -> int:

    cnt = 0
    positions = which_mt5.positions_get()
    if positions:
        for pos in positions:
            if pos.type == type and pos.symbol == symbol and pos.magic == magic:
                cnt += 1

    return cnt

def last_position(which_mt5, type: int, magic: int=MAGIC_NUMBER, symbol: str=SYMBOL):

    pos_time = -1
    last_pos = None

    positions = which_mt5.positions_get()
    if positions:
        for pos in positions:
            if pos.type == type and pos.symbol == symbol and pos.magic == magic:
                if pos.time > pos_time:
                    last_pos = pos
                    pos_time = pos.time

    return last_pos


def main(which_mt5: mt5,
         rates_cache: dict,
         symbol_info: Any,
         grid_window: int=48,
         grid_gap_points: int=100):

    if symbol_info is None:
        return

    ticks = which_mt5.symbol_info_tick(SYMBOL)

    if is_new_bar(ticks.time):

        rates = which_mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, grid_window)
        rates_cache["df"] = pd.DataFrame(rates)

    rates_df = rates_cache["df"]
    if rates_df is None or len(rates_df) < grid_window:
        return

    total_buys = count_positions(which_mt5.POSITION_TYPE_BUY)
    total_sells = count_positions(which_mt5.POSITION_TYPE_SELL)

    last_buy = last_position(which_mt5.POSITION_TYPE_BUY)
    last_sell = last_position(which_mt5.POSITION_TYPE_SELL)

    if total_buys == 0:
        highest_high = np.max(rates_df["high"])
    else:
        highest_high = last_buy.price_open

    if total_sells == 0:
        lowest_low = np.min(rates_df["low"])
    else:
        lowest_low = last_sell.price_open

    current_price = ticks.ask
    pts = symbol_info.point

    volume = 0.01

    if current_price < highest_high - grid_gap_points * pts: # buy signal
        m_trade.buy(volume=volume, symbol=SYMBOL, price=ticks.ask, tp=ticks.ask+grid_gap_points*pts)

    if current_price > lowest_low + grid_gap_points * pts: # sell signal
        m_trade.sell(volume=volume, symbol=SYMBOL, price=ticks.bid, tp=ticks.bid-grid_gap_points*pts)


rates_cache =  {
    "df": pd.DataFrame
}

while True:

    main(which_mt5=mt5,
         rates_cache=rates_cache,
         symbol_info=mt5.symbol_info(SYMBOL),
         )




mt5.shutdown()