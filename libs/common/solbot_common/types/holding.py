from dataclasses import dataclass


@dataclass
class HoldingToken:
    mint: str
    balance: float
    balance_str: str  # 带有单位的余额
    symbol: str
    # usd_value: float
    # price: float
    # total_profit: float = 0
    # total_profit_pnl: float = 0
    # last_active_timestamp: int | None = None


@dataclass
class TokenAccountBalance:
    balance: float
    decimals: int

@dataclass
class Holding:
    cp_pk: int
    target_alias : str
    target_wallet : str
    mint : str
    symbol : str
    decimals : int
    my_amount : int
    target_amount : int
    current_position: int
    max_position: int
    buy_time : int
    max_buy_time : int
    sol_sold : int
    sol_earned : int
    latest_trade_timestamp: int # 用于快速交易识别时间戳

    @property
    def ui_my_amount(self) -> float:
        return self.my_amount / 10 ** self.decimals

    @property
    def ui_target_amount(self) -> float:
        return self.target_amount / 10 ** self.decimals

    @property
    def ui_sol_sold(self) -> float:
        return self.sol_sold / 10 ** 9

    @property
    def ui_sol_earned(self) -> float:
        return self.sol_earned / 10 ** 9

    @property
    def ui_current_position(self) -> float:
        return self.current_position / 10 ** 9

    @property
    def ui_max_position(self) -> float:
        return self.max_position / 10 ** 9


@dataclass
class HoldingSummary:
    target_alias: str
    target_wallet: str
    ui_sol_sold: float
    ui_sol_earned: float
    ui_current_position: float
    ui_max_position: float
    token_number: int
    failed_time: int
    filtered_time: int