from typing import List, Sequence

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from common.models.tg_bot.copytrade import CopyTrade as CopyTradeModel
from db.session import NEW_ASYNC_SESSION, provide_session


class CopyTradeService:
    @classmethod
    @provide_session
    async def get_by_target_wallet(
        cls, target_wallet: str, *, session: AsyncSession = NEW_ASYNC_SESSION
    ) -> List[CopyTradeModel]:
        """ "获取指定目标钱包的活跃跟单"""
        stmt = select(CopyTradeModel).where(
            CopyTradeModel.target_wallet == target_wallet and CopyTradeModel.active == True
        )
        results = await session.execute(stmt)
        return [row.model_copy() for row in results.scalars().all()]

    @classmethod
    @provide_session
    async def get_active_wallet_addresses(
        cls, *, session: AsyncSession = NEW_ASYNC_SESSION
    ) -> Sequence[str]:
        """获取所有已激活的目标钱包地址

        Returns:
            Sequence[str]: 已激活的目标钱包地址列表，去重后的结果
        """
        stmt = (
            select(CopyTradeModel.target_wallet).where(CopyTradeModel.active == True).distinct()
        )
        result = await session.execute(stmt)
        return result.scalars().all()
    
    @classmethod
    @provide_session
    async def get_target_setting(
        cls, target_wallet, *, session: AsyncSession = NEW_ASYNC_SESSION
    ) -> CopyTradeModel:
        """获取target别名、最大仓位、最大加仓次数

        Returns:
            dict
        """
        stmt = (
            select(CopyTradeModel).where(CopyTradeModel.target_wallet == target_wallet).distinct()
        )
        result = await session.execute(stmt)
        target_setting = result.scalar_one_or_none()
        assert target_setting is not None, f"CopyTradeModel of target wallet {target_wallet} is not found."
        
        return target_setting.copy()
    
    @classmethod
    @provide_session
    async def add_failed_time(
        cls, target_wallet: str, *, session: AsyncSession = NEW_ASYNC_SESSION
    ) -> None:
        """Update an existing copytrade in the database"""
        # 验证target_wallet是否是已激活的跟单地址

        stmt = select(CopyTradeModel).where(CopyTradeModel.target_wallet == target_wallet).limit(1)
        result = await session.execute(stmt)
        obj = result.scalar_one_or_none()
        if obj is None:
            raise ValueError(f"Copytrade with target wallet {target_wallet} not found")

        obj.failed_time += 1
        session.add(obj)

        assert obj.id is not None, "obj.id is None"
        await session.commit()

    @classmethod
    @provide_session
    async def add_filtered_time(
        cls, target_wallet: str, *, session: AsyncSession = NEW_ASYNC_SESSION
    ) -> None:
        """Update an existing copytrade in the database"""
        # 验证target_wallet是否是已激活的跟单地址

        stmt = select(CopyTradeModel).where(CopyTradeModel.target_wallet == target_wallet).limit(1)
        result = await session.execute(stmt)
        obj = result.scalar_one_or_none()
        if obj is None:
            raise ValueError(f"Copytrade with target wallet {target_wallet} not found")

        obj.filtered_time += 1
        session.add(obj)

        assert obj.id is not None, "obj.id is None"
        await session.commit()

