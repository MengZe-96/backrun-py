from typing import List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from common.cp.monitor_events import MonitorEventProducer
from common.models.tg_bot.copytrade import CopyTrade as CopyTradeModel
from db.redis import RedisClient
from db.session import NEW_ASYNC_SESSION, provide_session
from tg_bot.models.copytrade import CopyTrade, CopyTradeSummary


def from_db_model(obj: CopyTradeModel) -> CopyTrade:
    copytrade = CopyTrade(
        pk=obj.id,
        owner=obj.owner,
        chat_id=obj.chat_id,
        target_wallet=obj.target_wallet,
        wallet_alias=obj.wallet_alias,
        is_fixed_buy=obj.is_fixed_buy,
        auto_follow=obj.auto_follow,
        stop_loss=obj.stop_loss,
        no_sell=obj.no_sell,
        priority=obj.priority,
        anti_sandwich=obj.anti_sandwich,
        auto_slippage=obj.auto_slippage,
        active=obj.active,
    )

    if obj.fixed_buy_amount is not None:
        copytrade.fixed_buy_amount = round(obj.fixed_buy_amount, 4)

    if obj.custom_slippage_bps is not None:
        copytrade.custom_slippage = round(obj.custom_slippage_bps, 4)
    return copytrade


class CopyTradeService:
    def __init__(self):
        redis = RedisClient.get_instance()
        self.monitor_event_producer = MonitorEventProducer(redis)

    @provide_session
    async def add(
        self, copytrade: CopyTrade, *, session: AsyncSession = NEW_ASYNC_SESSION
    ) -> None:
        """Add a new copytrade to the database"""
        if copytrade.target_wallet is None:
            raise ValueError("target_wallet is required")

        model = CopyTradeModel(
            owner=copytrade.owner,
            chat_id=copytrade.chat_id,
            target_wallet=copytrade.target_wallet,
            wallet_alias=copytrade.wallet_alias,
            is_fixed_buy=copytrade.is_fixed_buy,
            fixed_buy_amount=copytrade.fixed_buy_amount,
            auto_follow=copytrade.auto_follow,
            stop_loss=copytrade.stop_loss,
            no_sell=copytrade.no_sell,
            priority=copytrade.priority,
            anti_sandwich=copytrade.anti_sandwich,
            auto_slippage=copytrade.auto_slippage,
            custom_slippage_bps=int(copytrade.custom_slippage * 100),
            active=True,
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
        obj.wallet_alias = copytrade.wallet_alias
        obj.is_fixed_buy = copytrade.is_fixed_buy
        obj.fixed_buy_amount = copytrade.fixed_buy_amount
        obj.auto_follow = copytrade.auto_follow
        obj.stop_loss = copytrade.stop_loss
        obj.no_sell = copytrade.no_sell
        obj.priority = copytrade.priority
        obj.anti_sandwich = copytrade.anti_sandwich
        obj.auto_slippage = copytrade.auto_slippage
        obj.custom_slippage_bps = int(copytrade.custom_slippage * 100)
        obj.active = copytrade.active
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
    async def list(
        self, *, session: AsyncSession = NEW_ASYNC_SESSION
    ) -> list[CopyTradeSummary]:
        """Get all copytrades from the database"""
        stmt = select(
            CopyTradeModel.id,
            CopyTradeModel.target_wallet,
            CopyTradeModel.wallet_alias,
            CopyTradeModel.active,
        )
        result = await session.execute(stmt)
        return [
            CopyTradeSummary(
                pk=row[0],  # type: ignore
                target_wallet=row[1],
                wallet_alias=row[2],
                active=row[3],
            )
            for row in result.all()
        ]

    @provide_session
    async def get_by_id(
        self, pk: int, *, session: AsyncSession = NEW_ASYNC_SESSION
    ) -> CopyTrade:
        """Get a copytrade by pk from the database"""
        stmt = select(CopyTradeModel).where(CopyTradeModel.id == pk).limit(1)
        result = await session.execute(stmt)
        obj = result.scalar_one_or_none()
        if obj is None:
            raise ValueError(f"Copytrade with pk {pk} not found")
        return from_db_model(obj)

    @provide_session
    async def get_wallet_alias(
        self,
        target_wallet: str,
        chat_id: int,
        *,
        session: AsyncSession = NEW_ASYNC_SESSION,
    ) -> str | None:
        """ "Get the wallet alias of a target wallet


        Args:
            target_wallet (str): The target wallet
            chat_id (int): The chat ID

        Returns:
            str: The wallet alias
        """
        stmt = select(CopyTradeModel).where(
            CopyTradeModel.target_wallet == target_wallet,
            CopyTradeModel.chat_id == chat_id,
        )
        result = await session.execute(stmt)
        obj = result.scalar_one_or_none()
        if obj is None:
            return None
        return obj.wallet_alias

    @provide_session
    async def list_by_owner(
        self, chat_id: int, *, session: AsyncSession = NEW_ASYNC_SESSION
    ) -> List[CopyTradeSummary]:
        stmt = select(
            CopyTradeModel.id,
            CopyTradeModel.target_wallet,
            CopyTradeModel.wallet_alias,
            CopyTradeModel.active,
        ).where(CopyTradeModel.chat_id == chat_id)

        results = await session.execute(stmt)
        return [
            CopyTradeSummary(
                pk=row[0],  # type: ignore
                target_wallet=row[1],
                wallet_alias=row[2],
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
