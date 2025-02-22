from typing import Literal
from pydantic import BaseModel

from typing_extensions import Self
from common.models.swap_record import SwapRecord
from common.types.tx import TxEvent

from enum import Enum

class SwapDirection(str, Enum):
    Buy = "buy"
    Sell = "sell"

class SwapInType(str, Enum):
    Qty = "qty"  # 按数量交易
    Pct = "pct"  # 按百分比交易

class SwapEvent(BaseModel):
    user_pubkey: str
    swap_direction: SwapDirection
    input_mint: str
    output_mint: str
    amount: int  # lamports
    ui_amount: float
    timestamp: int  # unix timestamp
    amount_pct: float | None = None  # 百分比 0-1
    swap_in_type: Literal["qty", "pct"] = "qty"
    priority_fee: float | None = None  # SOL
    slippage_bps: int | None = None  # basis points, 100 = 1%
    by: Literal["user", "copytrade"] = "user"  # 由用户发起或自动跟单发起
    # PREF: 待优化滑点设置
    # 如果由用户发起则使用标准滑点standrad_slippage_bps，如果由自动跟单发起则使用跟单滑点copytrade_slippage_bps
    # --- jupiter ---
    dynamic_slippage: bool = False
    min_slippage_bps: int | None = None  # basis points
    max_slippage_bps: int | None = None  # basis points
    program_id: str | None = None
    # --- copytrade, 如果 by 为 copytrade, 则不为空 ---
    tx_event: TxEvent | None = None

    def to_dict(self) -> dict:
        return self.model_dump()

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_dict(cls, d: dict) -> "Self":
        return cls.model_validate(d)

    @classmethod
    def from_json(cls, json_str: str) -> "Self":
        return cls.model_validate_json(json_str)


class SwapResult(BaseModel):
    swap_event: SwapEvent
    user_pubkey: str
    submmit_time: int  # unix timestamp
    by: Literal["user", "copytrade"] = "user"  # 由用户发起或自动跟单发起
    transaction_hash: str | None = None
    blocks_passed: int | None = None  # 添加区块数量字段
    swap_record: SwapRecord | None = None

    def to_dict(self) -> dict:
        return self.model_dump()

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_dict(cls, d: dict) -> "Self":
        return cls.model_validate(d)

    @classmethod
    def from_json(cls, json_str: str) -> "Self":
        return cls.model_validate_json(json_str)



