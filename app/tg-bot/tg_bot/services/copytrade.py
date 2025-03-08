import builtins

from solbot_common.cp.monitor_events import MonitorEventProducer
from solbot_common.models.tg_bot.copytrade import CopyTrade as CopyTradeModel
from solbot_common.types.copytrade import CopyTrade, CopyTradeSummary
from solbot_db.redis import RedisClient
from solbot_db.session import NEW_ASYNC_SESSION, provide_session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select


def from_db_model(obj: CopyTradeModel) -> CopyTrade:
    copytrade = CopyTrade(
        pk=obj.id,
        owner=obj.owner,
        chat_id=obj.chat_id,
        target_wallet=obj.target_wallet,
        target_alias=obj.target_alias,
        # delete some fields
        priority=obj.priority,
        anti_sandwich=obj.anti_sandwich,
        auto_slippage=obj.auto_slippage,
        custom_slippage = obj.custom_slippage,
        active=obj.active,
        # 新增参数, 当有一笔新的快速交易出现时，会计算与fast_trade_start_time的时间间隔，如果超过fast_trade_duration则重置fast_trade_start_time
        anti_fast_trade = obj.anti_fast_trade,
        auto_buy = obj.auto_buy,
        auto_sell = obj.auto_sell,
        auto_buy_ratio = obj.auto_buy_ratio, # 跟单钱包的仓位缩放比例
        min_buy_sol = obj.min_buy_sol, # 单笔最小购买金额，以sol计价
        max_buy_sol = obj.max_buy_sol, # 单笔最大购买金额，以sol计价
        min_sell_ratio = obj.min_sell_ratio, # 单笔最小meme卖出比例
        filter_min_buy = obj.filter_min_buy, # 过滤小于该金额的买入
        max_position = obj.max_position, # 最大仓位金额，以sol计价
        max_buy_time = obj.max_buy_time, # 单聪明钱单meme最大购买次数
        # 快速交易限制
        fast_trade_threshold = obj.fast_trade_threshold, # 快速交易时间间隔senconds,小于该间隔的都视作快速交易
        fast_trade_duration = obj.fast_trade_duration, # 快速交易累计时间，在此时间中，快速交易次数超过fast_trade_time_threshold则暂停跟单
        fast_trade_sleep_threshold = obj.fast_trade_sleep_threshold, # 快速交易次数阈值，超过该次数则暂停跟单
        fast_trade_sleep_time = obj.fast_trade_sleep_time,
        # 新增统计数据
        fast_trade_time = obj.fast_trade_time, # fast_trade_start_time -> fast_trade_start_time+fast_trade_duration, 内快速交易的次数
        current_position = obj.current_position, # 当前持仓所用sol数量
        fast_trade_start_time = obj.fast_trade_start_time, # 快速交易开始时间
        failed_time = obj.failed_time,
        filtered_time = obj.filtered_time,
        sol_sold = obj.sol_sold,
        sol_earned = obj.sol_earned,
        token_number = obj.token_number,
    )

    return copytrade


class CopyTradeService:
    def __init__(self):
        redis = RedisClient.get_instance()
        self.monitor_event_producer = MonitorEventProducer(redis)

    @provide_session
    async def add(self, copytrade: CopyTrade, *, session: AsyncSession = NEW_ASYNC_SESSION) -> None:
        """Add a new copytrade to the database"""
        if copytrade.target_wallet is None:
            raise ValueError("target_wallet is required")

        model = CopyTradeModel(
            owner=copytrade.owner,
            chat_id=copytrade.chat_id,
            target_wallet=copytrade.target_wallet,
            target_alias=copytrade.target_alias,
            # delete some fields
            priority=copytrade.priority,
            anti_sandwich=copytrade.anti_sandwich,
            auto_slippage=copytrade.auto_slippage,
            custom_slippage=copytrade.custom_slippage,
            active=True,
            # 新增参数, 当有一笔新的快速交易出现时，会计算与fast_trade_start_time的时间间隔，如果超过fast_trade_duration则重置fast_trade_start_time
            anti_fast_trade = copytrade.anti_fast_trade,
            auto_buy = copytrade.auto_buy,
            auto_sell = copytrade.auto_sell,
            auto_buy_ratio = copytrade.auto_buy_ratio, # 跟单钱包的仓位缩放比例
            min_buy_sol = copytrade.min_buy_sol, # 单笔最小购买金额，以sol计价
            max_buy_sol = copytrade.max_buy_sol, # 单笔最大购买金额，以sol计价
            min_sell_ratio = copytrade.min_sell_ratio, # 单笔最小meme卖出比例
            filter_min_buy = copytrade.filter_min_buy, # 过滤小于该金额的买入
            max_position = copytrade.max_position, # 最大仓位金额，以sol计价
            max_buy_time = copytrade.max_buy_time, # 单聪明钱单meme最大购买次数
            fast_trade_threshold = copytrade.fast_trade_threshold, # 快速交易时间间隔senconds,小于该间隔的都视作快速交易
            fast_trade_duration = copytrade.fast_trade_duration, # 快速交易累计时间，在此时间中，快速交易次数超过fast_trade_time_threshold则暂停跟单
            fast_trade_sleep_threshold = copytrade.fast_trade_sleep_threshold, # 快速交易次数阈值，超过该次数则暂停跟单
            fast_trade_sleep_time = copytrade.fast_trade_sleep_time,
            # 新增全局状态数据
            fast_trade_time = copytrade.fast_trade_time, # fast_trade_start_time -> fast_trade_start_time+fast_trade_duration, 内快速交易的次数
            current_position = copytrade.current_position, # 当前持仓所用sol数量
            fast_trade_start_time = copytrade.fast_trade_start_time, # 快速交易开始时间 
            failed_time = copytrade.failed_time,
            filtered_time = copytrade.filtered_time,
            sol_sold = copytrade.sol_sold,
            sol_earned = copytrade.sol_earned,
            token_number = copytrade.token_number,
        )

        session.add(model)
        await session.flush()

        assert model.id is not None, "model.id is None"
        # 写入 redis
        await self.monitor_event_producer.resume_monitor(
            monitor_id=model.id,
            target_wallet=model.target_wallet,
            owner_id=int(model.chat_id),
        )

    @provide_session
    async def update(
        self, copytrade: CopyTrade, *, session: AsyncSession = NEW_ASYNC_SESSION
    ) -> None:
        """Update an existing copytrade in the database"""
        if copytrade.target_wallet is None:
            raise ValueError("target_wallet is required")

        stmt = select(CopyTradeModel).where(CopyTradeModel.id == copytrade.pk).limit(1)
        result = await session.execute(stmt)
        obj = result.scalar_one_or_none()
        if obj is None:
            raise ValueError(f"Copytrade with pk {copytrade.pk} not found")
        obj.target_wallet = copytrade.target_wallet
        obj.target_alias = copytrade.target_alias
        # delete some fields
        obj.priority = copytrade.priority
        obj.anti_sandwich = copytrade.anti_sandwich
        obj.auto_slippage = copytrade.auto_slippage
        obj.custom_slippage = copytrade.custom_slippage
        obj.active = copytrade.active
        # 新增参数, 当有一笔新的快速交易出现时，会计算与fast_trade_start_time的时间间隔，如果超过fast_trade_duration则重置fast_trade_start_time
        obj.anti_fast_trade = copytrade.anti_fast_trade
        obj.auto_buy = copytrade.auto_buy
        obj.auto_sell = copytrade.auto_sell
        obj.auto_buy_ratio = copytrade.auto_buy_ratio # 跟单钱包的仓位缩放比例
        obj.min_buy_sol = copytrade.min_buy_sol # 单笔最小购买金额，以sol计价
        obj.max_buy_sol = copytrade.max_buy_sol # 单笔最大购买金额，以sol计价
        obj.min_sell_ratio = copytrade.min_sell_ratio # 单笔最小meme卖出比例
        obj.filter_min_buy = copytrade.filter_min_buy # 过滤小于该金额的买入
        obj.max_position = copytrade.max_position # 最大仓位金额，以sol计价
        obj.max_buy_time = copytrade.max_buy_time # 单聪明钱单meme最大购买次数
        obj.fast_trade_threshold = copytrade.fast_trade_threshold # 快速交易时间间隔senconds,小于该间隔的都视作快速交易
        obj.fast_trade_duration = copytrade.fast_trade_duration # 快速交易累计时间，在此时间中，快速交易次数超过fast_trade_time_threshold则暂停跟单
        obj.fast_trade_sleep_threshold = copytrade.fast_trade_sleep_threshold # 快速交易次数阈值，超过该次数则暂停跟单
        obj.fast_trade_sleep_time = copytrade.fast_trade_sleep_time
        # 新增全局状态数据
        obj.fast_trade_time = copytrade.fast_trade_time # fast_trade_start_time -> fast_trade_start_time+fast_trade_duration, 内快速交易的次数
        obj.current_position = copytrade.current_position # 当前持仓所用sol数量
        obj.fast_trade_start_time = copytrade.fast_trade_start_time # 快速交易开始时间 
        obj.failed_time = copytrade.failed_time
        obj.filtered_time = copytrade.filtered_time
        obj.sol_sold = copytrade.sol_sold
        obj.sol_earned = copytrade.sol_earned
        obj.token_number = copytrade.token_number
        session.add(obj)

        assert obj.id is not None, "obj.id is None"
        if copytrade.active:
            await self.monitor_event_producer.resume_monitor(
                monitor_id=obj.id,
                target_wallet=obj.target_wallet,
                owner_id=obj.chat_id,
            )
        else:
            await self.monitor_event_producer.pause_monitor(
                monitor_id=obj.id,
                target_wallet=obj.target_wallet,
                owner_id=obj.chat_id,
            )
        await session.commit()

    @provide_session
    async def delete(
        self, copytrade: CopyTrade, *, session: AsyncSession = NEW_ASYNC_SESSION
    ) -> None:
        """Delete a copytrade from the database"""
        if copytrade.pk is None:
            raise ValueError("pk is required")

        stmt = select(CopyTradeModel).where(CopyTradeModel.id == copytrade.pk)
        result = await session.execute(stmt)
        obj = result.scalar_one_or_none()
        if obj is None:
            return
        await session.delete(obj)

        assert obj.id is not None, "obj.id is None"
        await self.monitor_event_producer.pause_monitor(
            monitor_id=obj.id,
            target_wallet=obj.target_wallet,
            owner_id=obj.chat_id,
        )

    @provide_session
    async def list(self, *, session: AsyncSession = NEW_ASYNC_SESSION) -> list[CopyTradeSummary]:
        """Get all copytrades from the database"""
        stmt = select(
            CopyTradeModel.id,
            CopyTradeModel.target_wallet,
            CopyTradeModel.target_alias,
            CopyTradeModel.active,
        )
        result = await session.execute(stmt)
        return [
            CopyTradeSummary(
                pk=row[0],  # type: ignore
                target_wallet=row[1],
                target_alias=row[2],
                active=row[3],
            )
            for row in result.all()
        ]

    @provide_session
    async def get_by_id(self, pk: int, *, session: AsyncSession = NEW_ASYNC_SESSION) -> CopyTrade:
        """Get a copytrade by pk from the database"""
        stmt = select(CopyTradeModel).where(CopyTradeModel.id == pk).limit(1)
        result = await session.execute(stmt)
        obj = result.scalar_one_or_none()
        if obj is None:
            raise ValueError(f"Copytrade with pk {pk} not found")
        return from_db_model(obj)

    @provide_session
    async def get_target_alias(
        self,
        target_wallet: str,
        chat_id: int,
        *,
        session: AsyncSession = NEW_ASYNC_SESSION,
    ) -> str | None:
        """ "Get the target alias of a target wallet


        Args:
            target_wallet (str): The target wallet
            chat_id (int): The chat ID

        Returns:
            str: The target alias
        """
        stmt = select(CopyTradeModel).where(
            CopyTradeModel.target_wallet == target_wallet,
            CopyTradeModel.chat_id == chat_id,
        )
        result = await session.execute(stmt)
        obj = result.scalar_one_or_none()
        if obj is None:
            return None
        return obj.target_alias

    @provide_session
    async def list_by_owner(
        self, chat_id: int, *, session: AsyncSession = NEW_ASYNC_SESSION
    ) -> builtins.list[CopyTradeSummary]:
        stmt = select(
            CopyTradeModel.id,
            CopyTradeModel.target_wallet,
            CopyTradeModel.target_alias,
            CopyTradeModel.active,
        ).where(CopyTradeModel.chat_id == chat_id)

        results = await session.execute(stmt)
        return [
            CopyTradeSummary(
                pk=row[0],  # type: ignore
                target_wallet=row[1],
                target_alias=row[2],
                active=row[3],
            )
            for row in results.all()
        ]

    @provide_session
    async def inactive_all(
        self, chat_id: int, *, session: AsyncSession = NEW_ASYNC_SESSION
    ) -> None:
        stmt = select(CopyTradeModel).where(CopyTradeModel.chat_id == chat_id)
        results = await session.execute(stmt)
        for obj in results.scalars():
            obj.active = False
            session.add(obj)

            assert obj.id is not None, "obj.id is None"
            await self.monitor_event_producer.pause_monitor(
                monitor_id=obj.id,
                target_wallet=obj.target_wallet,
                owner_id=obj.chat_id,
            )
