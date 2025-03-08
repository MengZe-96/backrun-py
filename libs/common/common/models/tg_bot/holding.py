from sqlalchemy import BIGINT, UniqueConstraint
from sqlmodel import Field

from common.models.base import Base


class Holding(Base, table=True):
    __tablename__ = "bot_holdings"  # type: ignore
    target_alias: str = Field(nullable=True, description="钱包别名")
    target_wallet: str = Field(nullable=False, index=True, description="跟单钱包")
    mint: str = Field(nullable=False, index=True, description="代币地址")
    symbol: str = Field(nullable=False, description="代币符号")
    decimals: int = Field(nullable=False, description="代币精度")
    cp_pk: int = Field(nullable=False, description="copytrade同步主键")
    my_amount: int = Field(nullable=False, sa_type=BIGINT, description="我的余额")
    target_amount: int = Field(nullable=False, sa_type=BIGINT, description="跟单钱包余额")
    current_position: int = Field(nullable=False, sa_type=BIGINT, description="当前仓位")
    max_position: int = Field(nullable=False, sa_type=BIGINT, description="最大仓位")
    buy_time: int = Field(nullable=False, description="购买次数")
    max_buy_time: int = Field(nullable=False, description="最大购买次数")
    sol_sold: int = Field(nullable=False, sa_type=BIGINT, description="支出的SOL")
    sol_earned: int = Field(nullable=False, sa_type=BIGINT, description="收入的SOL")
    # 快速交易识别时间戳
    latest_trade_timestamp: int = Field(nullable=False, description="该mint最新交易时间")
    
    # 定义表级别的唯一约束
    __table_args__ = (
        UniqueConstraint( "mint", "target_wallet", name="unique_mint_target_wallet"),
    )

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