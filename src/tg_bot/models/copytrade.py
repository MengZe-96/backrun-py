from dataclasses import dataclass


@dataclass
class CopyTrade:
    owner: str
    chat_id: int
    pk: int | None = None  # primary key
    target_wallet: str | None = None
    wallet_alias: str | None = None
    is_fixed_buy: bool = True
    fixed_buy_amount: float = 0.05
    auto_follow: bool = True
    auto_buy_ratio: float = 0.1
    stop_loss: bool = False
    no_sell: bool = False
    priority: float = 0.002
    anti_sandwich: bool = False
    auto_slippage: bool = True
    custom_slippage: float = 10  # 0-100%
    active: bool = True


@dataclass
class CopyTradeSummary:
    pk: int
    target_wallet: str
    wallet_alias: str | None
    active: bool
