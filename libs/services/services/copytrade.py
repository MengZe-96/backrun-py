from typing import List, Sequence

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from common.models.tg_bot.copytrade import CopyTrade as CopyTradeModel
from common.types.copytrade import CopyTrade
from db.session import NEW_ASYNC_SESSION, provide_session


class CopyTradeService:
    @classmethod
    @provide_session
    async def get_target_wallet_by_pk(
        cls, pk: int, *, session: AsyncSession = NEW_ASYNC_SESSION
    ) -> str:
        """获取指定pk的target_wallet"""
        stmt = select(CopyTradeModel).where(CopyTradeModel.id == pk)
        result = await session.execute(stmt)
        obj = result.scalar_one_or_none()
        if obj is None:
            raise ValueError(f"Copytrade with pk {pk} not found")
        return obj.target_wallet

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
    async def get_copytrade_states(
        cls, *, session: AsyncSession = NEW_ASYNC_SESSION
    ) -> List[CopyTradeModel]:
        """获取全部的 CopyTradeModel 对象

        Returns:
            List[CopyTradeModel]: 包含所有 CopyTradeModel 对象的列表
        """
        stmt = select(CopyTradeModel).distinct()
        result = await session.execute(stmt)
        copytrades = result.scalars().all()
        copytrades = [copytrade.copy() for copytrade in copytrades]
        return copytrades
    
    @classmethod
    async def add_failed_time(cls, target_wallet: str) -> None:
        """Update an existing copytrade in the database"""

        state_delta = {
            'target_wallet': target_wallet,
            'failed_time': 1
        }
        await cls.update_target_state(state_delta)

    @classmethod
    async def add_filtered_time(cls, target_wallet: str) -> None:
        """Update an existing copytrade in the database"""

        state_delta = {
            'target_wallet': target_wallet,
            'filtered_time': 1
        }
        await cls.update_target_state(state_delta)

    @classmethod
    @provide_session
    async def update_target_state(
        cls,
        state_delta: dict,
        *,
        session: AsyncSession = NEW_ASYNC_SESSION
    ) -> None:
        """Update specific fields of an existing holding in the database based on target_wallet and mint
        
        Args:
            state_delta: Dictionary containing field names as keys and their values
            session: SQLAlchemy async session
            
        Raises:
            ValueError: If target_wallet or mint not in holding dict, or if record not found
        """
        # 确保 target_wallet 和 mint 在字典中存在
        if 'target_wallet' not in state_delta:
            raise ValueError("state_delta dict must contain 'target_wallet' keys")
        
        # 查询现有记录
        stmt = select(CopyTradeModel).where(
            (CopyTradeModel.target_wallet == state_delta['target_wallet'])
        ).limit(1)
        
        result = await session.execute(stmt)
        obj = result.scalar_one_or_none()
        
        if obj is None:
            raise ValueError(f"Copytrade with target_wallet {state_delta['target_wallet']} not found.")
        
        # 只更新 copytrade中的统计字段（target_wallet等设置字段不在此更新）
        for key, value in state_delta.items():
            if key in ['target_wallet', 'owner', 'chat_id', 'pk', 'id']:
                continue
            if hasattr(obj, key):
                current_value = getattr(obj, key)
                setattr(obj, key, current_value + value)
            else:
                raise ValueError(f"Invalid field name in state_delta dict: {key}")
        
        session.add(obj)
        assert obj.id is not None, "obj.id should not be None after update"
        await session.commit()

