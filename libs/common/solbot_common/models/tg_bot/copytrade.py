from sqlalchemy import BIGINT
from sqlmodel import Field

from solbot_common.models.base import Base


class CopyTrade(Base, table=True):
    __tablename__ = "bot_copytrade"  # type: ignore
    owner: str = Field(nullable=False, index=True, description="所属钱包")
    chat_id: int = Field(nullable=False, index=True, sa_type=BIGINT, description="用户 ID")
    target_wallet: str = Field(nullable=False, index=True)
    target_alias: str = Field(nullable=False)
    # delete some fields
    priority: int = Field(nullable=False, description="优先费用(单位 SOL)")
    anti_sandwich: bool = Field(nullable=False, description="是否开启防夹")
    auto_slippage: bool = Field(nullable=False, description="是否自动滑点")
    custom_slippage: float | None = Field(nullable=True, description="自定义滑点")
    active: bool = Field(nullable=False, description="是否激活")
    # 新增参数, 当有一笔新的快速交易出现时，会计算与fast_trade_start_time的时间间隔，如果超过fast_trade_duration则重置fast_trade_start_time
    anti_fast_trade: bool = Field(nullable=False, description="防割模式")
    auto_buy: bool = Field(nullable=False, description="自动跟买")
    auto_sell: bool = Field(nullable=False, description="自动跟卖")
    auto_buy_ratio: float = Field(nullable=False, description="跟单钱包的仓位缩放比例")
    min_buy_sol: int = Field(nullable=False, description="单笔最小购买金额，以sol计价")
    max_buy_sol: int = Field(nullable=False, description="单笔最大购买金额，以sol计价")
    min_sell_ratio: float = Field(nullable=False, description="单笔最小meme卖出比例")
    filter_min_buy: int = Field(nullable=False, description="过滤小于该金额的买入")
    max_position: int = Field(nullable=False, description="最大仓位金额，以sol计价")
    max_buy_time: int = Field(nullable=False, description="单聪明钱单meme最大购买次数")
    fast_trade_threshold: int = Field(nullable=False, description="快速交易时间间隔senconds,小于该间隔的都视作快速交易")
    fast_trade_duration: int = Field(nullable=False, description="快速交易累计时间，在此时间中，快速交易次数超过fast_trade_time_threshold则暂停跟单")
    fast_trade_sleep_threshold: int = Field(nullable=False, description="快速交易次数阈值，超过该次数则暂停跟单")
    fast_trade_sleep_time: int = Field(nullable=False, description="睡眠时长")
    # 新增全局统计数据
    fast_trade_time: int = Field(nullable=False, description="快速交易累计次数") # fast_trade_start_time -> fast_trade_start_time+fast_trade_duration, 内快速交易的次数
    current_position: int = Field(nullable=False, description="当前持仓所用sol数量")
    fast_trade_start_time: int= Field(nullable=False, description="快速交易开始时间")
    failed_time: int = Field(nullable=False, description="累计失败次数")
    filtered_time: int = Field(nullable=False, description="累计过滤次数")
    sol_sold: int = Field(nullable=False, description="累计支出sol数量")
    sol_earned: int = Field(nullable=False, description="累计收入sol数量")
    token_number: int = Field(nullable=False, description="累计交易币数")

