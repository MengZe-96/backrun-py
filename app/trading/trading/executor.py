from solana.rpc.async_api import AsyncClient
from solbot_cache.launch import LaunchCache
from solbot_common.config import settings
from solbot_common.constants import PUMP_FUN_PROGRAM, RAY_V4
from solbot_common.log import logger
from solbot_common.models.tg_bot.user import User
from solbot_common.types.swap import SwapEvent
from solbot_common.types.enums import SwapDirection, SwapInType
from solbot_db.session import NEW_ASYNC_SESSION, provide_session
from solders.keypair import Keypair  # type: ignore
from solders.signature import Signature  # type: ignore
from sqlmodel import select

from trading.transaction import TradingRoute, TradingService

PUMP_FUN_PROGRAM_ID = str(PUMP_FUN_PROGRAM)
RAY_V4_PROGRAM_ID = str(RAY_V4)


class TradingExecutor:
    def __init__(self, client: AsyncClient):
        self._rpc_client = client
        self._launch_cache = LaunchCache()
        self._trading_service = TradingService(self._rpc_client)

    @provide_session
    async def __get_keypair(self, pubkey: str, *, session=NEW_ASYNC_SESSION) -> Keypair:
        stmt = select(User.private_key).where(User.pubkey == pubkey).limit(1)
        private_key = (await session.execute(stmt)).scalar_one_or_none()
        if not private_key:
            raise ValueError("Wallet not found")
        return Keypair.from_bytes(private_key)

    async def exec(self, swap_event: SwapEvent) -> Signature | None:
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

        # 检查是否需要使用 Pump 协议进行交易
        should_use_pump = False
        program_id = swap_event.program_id

        try:
            if program_id == PUMP_FUN_PROGRAM_ID or (
                token_address.endswith("pump") and 
                not await self._launch_cache.is_pump_token_launched(token_address)
            ):
                should_use_pump = True
                logger.info(
                    f"Token {token_address} is not launched on Raydium, using Pump protocol to trade"
                )
            elif program_id == RAY_V4_PROGRAM_ID:
                # 如果 token 在 Raydium 上启动，则使用 Raydium 协议进行交易
                logger.info(
                    f"Token {token_address} is launched on Raydium, using Raydium protocol to trade"
                )
            else:
                logger.info(
                    f"Token {token_address} program id is None, using aggregate protocol to trade"
                )
        except Exception as e:
            logger.exception(f"Failed to check launch status, cause: {e}")

        if should_use_pump:
            logger.info("Program ID is PUMP")
            trade_route = TradingRoute.PUMP
        # NOTE: 测试下来不是很理想，暂时使用备选方案
        elif swap_event.program_id == RAY_V4_PROGRAM_ID:
            logger.info("Program ID is RayV4")
            trade_route = TradingRoute.RAYDIUM_V4
        elif program_id is None:
            logger.warning("Program ID is Unknown, So We use aggregate dex to trade")
            trade_route = TradingRoute.DEX
        else:
            raise ValueError(f"Program ID is not supported, {swap_event.program_id}")

        target_price = None
        if swap_event.by == 'copytrade' and swap_event.swap_direction == SwapDirection.Buy:
            target_price = (swap_event.tx_event.to_amount / 10**swap_event.tx_event.to_decimals)/ (swap_event.tx_event.from_amount / 10**swap_event.tx_event.from_decimals)

        sig = await self._trading_service.use_route(trade_route, settings.trading.use_jito).swap(
            keypair,
            token_address,
            swap_event.ui_amount,
            swap_event.swap_direction,
            slippage_bps,
            target_price,
            swap_in_type,
            use_jito=settings.trading.use_jito,
            priority_fee=swap_event.priority_fee,
        )

        return sig
