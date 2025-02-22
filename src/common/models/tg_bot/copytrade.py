from sqlmodel import Field
from sqlalchemy import BIGINT
from common.models.base import Base


class CopyTrade(Base, table=True):
    __tablename__ = "bot_copytrade"  # type: ignore
    owner: str = Field(nullable=False, index=True, description="所属钱包")
    chat_id: int = Field(
        nullable=False, index=True, sa_type=BIGINT, description="用户 ID"
    )
    target_wallet: str = Field(nullable=False, index=True)
    wallet_alias: str | None = Field(nullable=True)
    is_fixed_buy: bool = Field(nullable=False, description="是否固定买入")
    fixed_buy_amount: float | None = Field(nullable=True, description="固定买入金额")
    auto_follow: bool = Field(nullable=False, description="是否跟随自动买入卖出")
    auto_buy_ratio: float = Field(nullable=False, description="自动买入比例")
    stop_loss: bool = Field(nullable=False, description="是否设置止盈止损")
    no_sell: bool = Field(nullable=False, description="只跟买")
    priority: float = Field(nullable=False, description="优先费用(单位 SOL)")
    anti_sandwich: bool = Field(nullable=False, description="是否开启防夹")
    auto_slippage: bool = Field(nullable=False, description="是否自动滑点")
    custom_slippage_bps: int | None = Field(nullable=True, description="自定义滑点")
    active: bool = Field(nullable=False, description="是否激活")
