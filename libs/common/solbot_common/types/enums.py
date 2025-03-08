from enum import Enum


class SwapDirection(str, Enum):
    Buy = "buy"
    Sell = "sell"


class SwapInType(str, Enum):
    Qty = "qty"  # 按数量交易
    Pct = "pct"  # 按百分比交易
