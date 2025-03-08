from dataclasses import dataclass


@dataclass
class CopyTrade:
    owner: str
    chat_id: int
    pk: int | None = None  # primary key
    target_wallet: str | None = None
    target_alias: str | None = None
    # is_fixed_buy: bool = True
    # fixed_buy_amount: float = 0.05
    # stop_loss: bool = False
    # auto_follow: bool = True
    # no_sell: bool = False
    priority: int = int(0.0001 * 10 ** 9)
    anti_sandwich: bool = False
    auto_slippage: bool = True
    custom_slippage: float = 0.1  # 0-100%
    active: bool = True
    # 新增参数, 当有一笔新的快速交易出现时，会计算与fast_trade_start_time的时间间隔，如果超过fast_trade_duration则重置fast_trade_start_time
    anti_fast_trade: bool = True # 防割模式
    auto_buy: bool = True
    auto_sell: bool =  True
    auto_buy_ratio: float = 0.1 # 跟单钱包的仓位缩放比例
    min_buy_sol: int = int(0.1 * 10 ** 9) # 单笔最小购买金额，以sol计价
    max_buy_sol: int = int(0.5 * 10 ** 9) # 单笔最大购买金额，以sol计价
    max_buy_time: int = 3 # 单聪明钱单meme最大购买次数
    min_sell_ratio: float = 0.02 # 单笔最小meme卖出比例
    filter_min_buy: int = int(0.1 * 10 ** 9) # 过滤小于该金额的买入
    fast_trade_threshold: int = 10 # 快速交易时间间隔senconds,小于该间隔的都视作快速交易
    fast_trade_duration: int = 3600 # 快速交易累计时间，在此时间中，快速交易次数超过fast_trade_time_threshold则暂停跟单
    fast_trade_sleep_threshold: int = 5 # 快速交易次数阈值，大于等于该次数则暂停跟单
    fast_trade_sleep_time: int = 3600 # 休眠时长
    max_position: int = 2 * 10 ** 9# 最大仓位金额，以sol计价
    # 新增全局变量数据
    fast_trade_start_time: int= 0 # 快速交易开始时间
    fast_trade_time: int = 0 # fast_trade_start_time -> fast_trade_start_time+fast_trade_duration, 内快速交易的次数
    current_position: int = 0 * 10 ** 9 # 当前持仓所用sol数量
    failed_time: int = 0 # 全局统计失败次数
    filtered_time: int = 0 # 全局统计过滤次数
    sol_sold: int = 0 # 全局统计支出sol数量
    sol_earned: int = 0 # 全局统计收入sol数量
    token_number: int = 0 # 全局统计交易币数

@dataclass
class CopyTradeSummary:
    pk: int
    target_wallet: str
    target_alias: str | None
    active: bool
