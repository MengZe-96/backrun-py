from solana.rpc.async_api import AsyncClient
from solders.keypair import Keypair  # type: ignore
from sqlmodel import select

from common.constants import PUMP_FUN_PROGRAM, RAY_V4
from common.log import logger
from common.models.tg_bot.user import User
from common.types.swap import SwapEvent
from db.session import NEW_ASYNC_SESSION, provide_session
from trading.swap import SwapDirection, SwapInType
from common.utils.raydium import RaydiumAPI
from cache.launch import LaunchCache
from .swap_protocols import Gmgn, Pump

PUMP_FUN_PROGRAM_ID = str(PUMP_FUN_PROGRAM)
RAY_V4_PROGRAM_ID = str(RAY_V4)


class TradingExecutor:
    def __init__(self, client: AsyncClient):
        self._client = client
        self._raydium_api = RaydiumAPI()
        self._launch_cache = LaunchCache()

    @provide_session
    async def __get_keypair(self, pubkey: str, *, session=NEW_ASYNC_SESSION) -> Keypair:
        stmt = select(User.private_key).where(User.pubkey == pubkey).limit(1)
        private_key = (await session.execute(stmt)).scalar_one_or_none()
        if not private_key:
            raise ValueError("Wallet not found")
        return Keypair.from_bytes(private_key)

    async def exec(self, swap_event: SwapEvent):
        """执行交易

        Args:
            swap_event (SwapEvent): 交易事件

        Raises:
            ConnectTimeout: If connection to the RPC node times out
            ConnectError: If connection to the RPC node fails
        """
        if swap_event.slippage_bps is not None:
            slippage_bps = swap_event.slippage_bps
        else:
            raise ValueError("slippage_bps must be specified")

        assert isinstance(swap_event.swap_direction, SwapDirection)
        token_address = swap_event.output_mint if swap_event.swap_direction == SwapDirection.Buy else swap_event.input_mint

        sig = None
        keypair = await self.__get_keypair(swap_event.user_pubkey)
        swap_in_type = SwapInType(swap_event.swap_in_type)


        # 暂时跳过是否需要使用 Pump 协议进行交易的检查
        # program_id = swap_event.program_id
        # should_use_pump = False
        # try:
        #     is_pump_token_launched = await self._launch_cache.is_pump_token_launched(
        #         token_address
        #     )
        #     if (
        #         program_id == PUMP_FUN_PROGRAM_ID
        #         or token_address.endswith("pump")
        #         and not is_pump_token_launched
        #     ):
        #         should_use_pump = True
        #         logger.info(
        #             f"Token {token_address} is not launched on Raydium, using Pump protocol to trade"
        #         )
        #     else:
        #         logger.info(
        #             f"Token {token_address} is launched on Raydium, using Raydium protocol to trade"
        #         )
        # except Exception as e:
        #     logger.exception(f"Failed to check launch status, cause: {e}")

        # if should_use_pump:
        #     logger.info("Program ID is PUMP")
        #     sig = await Pump(self._client).swap(
        #         keypair=keypair,
        #         token_address=token_address,
        #         ui_amount=swap_event.ui_amount,
        #         swap_direction=swap_event.swap_direction,
        #         slippage_bps=slippage_bps,
        #         in_type=swap_in_type,
        #         priority_fee=swap_event.priority_fee,
        #     )
        # NOTE: 测试下来不是很理想，暂时使用备选方案
        # elif swap_event.program_id == RAY_V4_PROGRAM_ID:
        #     logger.info("Program ID is RayV4")
        #     sig = await Gmgn(self._client).swap(
        #         keypair=keypair,
        #         token_address=token_address,
        #         ui_amount=swap_event.ui_amount,
        #         swap_direction=swap_event.swap_direction,
        #         slippage_bps=slippage_bps,
        #         in_type=swap_in_type,
        #         priority_fee=swap_event.priority_fee,
        #     )
        # elif program_id is None or program_id == RAY_V4_PROGRAM_ID:
        #     logger.warning("Program ID is Unknown, So We use thrid party to trade")
        #     sig = await Gmgn(self._client).swap(
        #         keypair=keypair,
        #         token_address=token_address,
        #         ui_amount=swap_event.ui_amount,
        #         swap_direction=swap_event.swap_direction,
        #         slippage_bps=slippage_bps,
        #         in_type=swap_in_type,
        #         priority_fee=swap_event.priority_fee,
        #     )
        # else:
        #     raise ValueError(f"Program ID is not supported, {swap_event.program_id}")
        
        sig = await Gmgn(self._client).swap(
                keypair=keypair,
                token_address=token_address,
                ui_amount=swap_event.ui_amount,
                swap_direction=swap_event.swap_direction,
                slippage_bps=slippage_bps,
                in_type=swap_in_type,
                priority_fee=swap_event.priority_fee,
        )

        return sig
