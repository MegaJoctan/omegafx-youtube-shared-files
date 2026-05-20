import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from strategytester5.MQL5.functions import PeriodSeconds
from strategytester5.trade_classes.Trade import CTrade
from strategytester5.tester import StrategyTester
from typing import Any
import optuna

if not mt5.initialize():
    raise RuntimeError(f"Failed to initialize mt5. Error = {mt5.last_error()}")

SYMBOL = "US500"
TIMEFRAME = mt5.TIMEFRAME_H1
MAGIC_NUMBER = 12345
SLIPPAGE = 100

tester_configs = {
        "bot_name": "Grid Bot",
        "symbols": [SYMBOL],
        "timeframe": "H1",
        "start_date": "01.01.2025 00:00",
        "end_date": "01.03.2025 00:00",
        "modelling" : "1 minute OHLC",
        "deposit": 3000,
        "leverage": "1:100",
        "visual_mode": True
    }


def is_new_bar(current_time_secs: int, tf: int = TIMEFRAME):
    tf_seconds = PeriodSeconds(tf)
    return current_time_secs % tf_seconds == 0  # new bar e.g., at 11:00, 12:000, etc.


def count_positions(which_mt5, pos_type: int, magic: int = MAGIC_NUMBER, symbol: str = SYMBOL) -> int:
    cnt = 0
    positions = which_mt5.positions_get()
    if positions:
        for pos in positions:
            if pos.type == pos_type and pos.symbol == symbol and pos.magic == magic:
                cnt += 1

    return cnt


def last_position(which_mt5, pos_type: int, magic: int = MAGIC_NUMBER, symbol: str = SYMBOL):
    pos_time = -1
    last_pos = None

    positions = which_mt5.positions_get()
    if positions:
        for pos in positions:
            if pos.type == pos_type and pos.symbol == symbol and pos.magic == magic:
                if pos.time > pos_time:
                    last_pos = pos
                    pos_time = pos.time

    return last_pos


def main(which_mt5: mt5,
         m_trade: CTrade,
         rates_cache: dict,
         symbol_info: Any,
         lot_multiplier: int=2,
         grid_window: int = 48,
         grid_gap_points: int = 100,
         max_orders_each_direction=5,
         ):
    if symbol_info is None:
        return

    ticks = which_mt5.symbol_info_tick(SYMBOL)

    if is_new_bar(ticks.time):
        rates = which_mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, grid_window)
        rates_cache["df"] = pd.DataFrame(rates)

    rates_df = rates_cache["df"]
    if rates_df is None or len(rates_df) < grid_window:
        return

    total_buys = count_positions(which_mt5=which_mt5, pos_type=which_mt5.POSITION_TYPE_BUY)
    total_sells = count_positions(which_mt5=which_mt5, pos_type=which_mt5.POSITION_TYPE_SELL)

    last_buy = last_position(which_mt5=which_mt5, pos_type=which_mt5.POSITION_TYPE_BUY)
    last_sell = last_position(which_mt5=which_mt5, pos_type=which_mt5.POSITION_TYPE_SELL)

    buy_volume = symbol_info.volume_min
    sell_volume = symbol_info.volume_min

    if total_buys == 0:
        highest_high = np.max(rates_df["high"])
    else:
        highest_high = last_buy.price_open
        buy_volume = last_buy.volume * lot_multiplier

    if total_sells == 0:
        lowest_low = np.min(rates_df["low"])
    else:
        lowest_low = last_sell.price_open
        sell_volume = last_sell.volume * lot_multiplier

    current_price = ticks.ask
    pts = symbol_info.point

    if current_price < highest_high - grid_gap_points * pts:  # buy signal
        if total_buys < max_orders_each_direction:
            m_trade.buy(volume=buy_volume, symbol=SYMBOL, price=ticks.ask, tp=ticks.ask + grid_gap_points * pts)

    if current_price > lowest_low + grid_gap_points * pts:  # sell signal
        if total_sells < max_orders_each_direction:
            m_trade.sell(volume=sell_volume, symbol=SYMBOL, price=ticks.bid, tp=ticks.bid - grid_gap_points * pts)


def objective(trial):

    grid_gap_points = trial.suggest_int("grid_gap_points", 1000, 10000, step=500)
    grid_window = trial.suggest_int("grid_window", 5, 100, step=1)
    max_orders_each_direction = trial.suggest_int("max_orders_each_direction", 3, 15)

    tester = StrategyTester(
        tester_config=tester_configs,
        mt5_instance=mt5,
        optimization_mode=True,
        margin_stopout=True
    )

    simulated_mt5 = tester.simulated_mt5

    m_trade = CTrade(
        magic_number=MAGIC_NUMBER,
        filling_type_symbol=SYMBOL,
        terminal=simulated_mt5,
        deviation_points=SLIPPAGE
    )

    rates_cache = {
        "df": None
    }

    strategy = lambda: main(which_mt5=simulated_mt5,
                            m_trade=m_trade,
                            rates_cache=rates_cache,
                            symbol_info=simulated_mt5.symbol_info(SYMBOL),
                            grid_gap_points=grid_gap_points,
                            grid_window=grid_window,
                            max_orders_each_direction=max_orders_each_direction
                    )

    tester_stats = tester.run(strategy)
    if tester_stats is None:
        return -np.inf

    return tester_stats.net_profit # net profit


study = optuna.create_study(direction="maximize", study_name="grid_bot_optimization")
study.optimize(objective, n_trials=20)

print(f"Best grid settings for {SYMBOL}\n: {study.best_params}")
print("Maximum net profit value = ", study.best_value)

df = study.trials_dataframe()
df.to_csv("grid_bot_optimization.csv")


mt5.shutdown()