import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from strategytester5.trade_classes.Trade import CTrade
from strategytester5.MQL5.functions import PeriodSeconds

if not mt5.initialize():
    raise RuntimeError(f"Failed to initialize mt5. Error = {mt5.last_error()}")

SYMBOL = "XAUUSD"
TIMEFRAME = mt5.TIMEFRAME_H1
MAGIC_NUMBER = 2026
SLIPPAGE = 100


m_trade = CTrade(
    magic_number=MAGIC_NUMBER,
    filling_type_symbol=SYMBOL,
    deviation_points=SLIPPAGE,
    terminal=mt5
)

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

WINDOW = 24 # the window to check for highest and lowest (extremes)
SHIFT = 2
rates_df = None
RR_RATIO = 2

def main():

    global rates_df
    ticks =  mt5.symbol_info_tick(SYMBOL)
    if ticks is None:
        return

    if is_new_bar(tf=TIMEFRAME, current_time_seconds=ticks.time):

        rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, WINDOW)
        rates_df = pd.DataFrame(rates)

    if rates_df is None or len(rates_df) < WINDOW:
        return

    current_close = rates_df["close"].iloc[-1]

    rates_window = rates_df.iloc[:-SHIFT]
    support_line = np.min(rates_window["low"]) # lowest low in the window
    resistance_line = np.max(rates_window["high"]) # the highest high value in the window

    latest_tick_volume = rates_df["tick_volume"].iloc[-1]
    mean_tick_volume = rates_window["tick_volume"].mean()

    volume = 0.1

    if latest_tick_volume > mean_tick_volume: # increased volatility

        if current_close > resistance_line: # bullish breakout
            entry_price = ticks.ask
            sl_diff = entry_price - support_line

            m_trade.buy(volume=volume,
                        symbol=SYMBOL,
                        price=entry_price,
                        sl=support_line,
                        tp=entry_price+sl_diff*RR_RATIO
                        )

        if current_close < support_line: # bearish breakout

            entry_price = ticks.bid
            sl_diff = resistance_line - entry_price

            m_trade.sell(volume=volume,
                         symbol=SYMBOL,
                         price=entry_price,
                         sl=resistance_line,
                         tp=entry_price-sl_diff*RR_RATIO
                        )


while True:
    main()











