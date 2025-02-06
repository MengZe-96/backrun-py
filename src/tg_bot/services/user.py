from solders.keypair import Keypair  # type: ignore
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import and_, delete, select
from typing_extensions import Self

from common.models.tg_bot.user import User as UserModel
from db.session import NEW_ASYNC_SESSION, provide_session


class UserService:
    _instance = None

    def __new__(cls) -> Self:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @provide_session
    async def register(
        self,
        chat_id: int,
        keypair: Keypair,
        is_default: bool = True,
        *,
        session: AsyncSession = NEW_ASYNC_SESSION,
    ) -> None:
        user = UserModel(
            chat_id=chat_id,
            pubkey=keypair.pubkey().__str__(),
            private_key=bytes(keypair),
            is_default=is_default,
        )
        session.add(user)

    @provide_session
    async def set_default(
        self,
        chat_id: int,
        pubkey: str,
        is_default: bool = True,
        *,
        session: AsyncSession = NEW_ASYNC_SESSION,
    ) -> None:
        statement = select(UserModel).where(
            UserModel.chat_id == chat_id, UserModel.pubkey == pubkey
        )
        user = (await session.execute(statement)).scalar_one_or_none()
        if not user:
            raise ValueError(f"User with chat_id {chat_id} not found")
        user.is_default = is_default
        session.add(user)

    @provide_session
    async def set_active(
        self,
        chat_id: int,
        pubkey: str,
        is_active: bool = True,
        *,
        session: AsyncSession = NEW_ASYNC_SESSION,
    ) -> None:
        statement = select(UserModel).where(
            UserModel.chat_id == chat_id, UserModel.pubkey == pubkey
        )
        user = (await session.execute(statement)).scalar_one_or_none()
        if not user:
            raise ValueError(f"User with chat_id {chat_id} not found")
        user.is_active = is_active
        session.add(user)

    @provide_session
    async def is_registered(
        self, chat_id: int, *, session: AsyncSession = NEW_ASYNC_SESSION
    ) -> bool:
        statement = select(UserModel).where(UserModel.chat_id == chat_id).limit(1)
        user = (await session.execute(statement)).scalar_one_or_none()
        return bool(user)

    @provide_session
    async def delete_wallet(
        self, chat_id: int, pubkey: str, *, session: AsyncSession = NEW_ASYNC_SESSION
    ):
        statement = delete(UserModel).where(
            and_(UserModel.chat_id == chat_id, UserModel.pubkey == pubkey)
        )
        await session.execute(statement)

    @provide_session
    async def get_keypair(
        self,
        chat_id: int,
        is_default: bool = True,
        is_active: bool = True,
        *,
        session: AsyncSession = NEW_ASYNC_SESSION,
    ) -> Keypair:
        statement = select(UserModel).where(
            UserModel.chat_id == chat_id,
            UserModel.is_default == is_default,
            UserModel.is_active == is_active,
        )
        user = (await session.execute(statement)).scalar_one_or_none()
        if not user:
            raise ValueError(f"User with chat_id {chat_id} not found")
        if not user.private_key:
            raise ValueError(f"User with chat_id {chat_id} has no private key")
        return Keypair.from_bytes(user.private_key)

    @provide_session
    async def get_pubkey(
        self,
        chat_id: int,
        is_default: bool = True,
        is_active: bool = True,
        *,
        session: AsyncSession = NEW_ASYNC_SESSION,
    ) -> str:
        keypair = await self.get_keypair(
            chat_id, is_default, is_active, session=session
        )
        return str(keypair.pubkey())

    @provide_session
    async def get_chat_id_by_pubkey(
        self, pubkey: str, *, session: AsyncSession = NEW_ASYNC_SESSION
    ) -> list[int]:
        """根据钱包地址获取 chat_id

        Args:
            pubkey(str): 钱包地址

        Returns:
            list[int] 该钱包所属的 user id
        """
        statement = select(UserModel).where(UserModel.pubkey == pubkey)
        users = (await session.execute(statement)).scalars().all()
        return [user.chat_id for user in users]
