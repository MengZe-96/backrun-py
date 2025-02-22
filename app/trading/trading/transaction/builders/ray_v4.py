import base64
import os

from loguru import logger
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Processed
from solana.rpc.types import TokenAccountOpts, TxOpts
from solders.instruction import Instruction  # type: ignore[reportMissingModuleSource]
from solders.keypair import Keypair  # type: ignore[reportMissingModuleSource]
from solders.pubkey import Pubkey  # type: ignore[reportMissingModuleSource]
from solders.rpc.responses import RpcSimulateTransactionResult  # type: ignore
from solders.signature import Signature  # type: ignore[reportMissingModuleSource]
from solders.system_program import (  # type: ignore[reportMissingModuleSource]
    CreateAccountWithSeedParams,
    create_account_with_seed,
)
from solders.transaction import VersionedTransaction  # type: ignore
from spl.token.instructions import (
    CloseAccountParams,
    InitializeAccountParams,
    close_account,
    create_associated_token_account,
    get_associated_token_address,
    initialize_account,
)

from cache import MinBalanceRentCache
from cache.auto.raydium_pool import get_preferred_pool
from common.config import settings
from common.constants import ACCOUNT_LAYOUT_LEN, SOL_DECIMAL, TOKEN_PROGRAM_ID, WSOL
from common.utils.pool import (
    AmmV4PoolKeys,
    get_amm_v4_reserves,
    make_amm_v4_swap_instruction,
)
from common.utils.utils import get_token_balance
from common.types.swap import SwapDirection, SwapInType
from trading.tx import build_transaction

from .base import TransactionBuilder


class RaydiumV4TransactionBuilder(TransactionBuilder):
    async def build_buy_instructions(
        self,
        payer_keypair: Keypair,
        token_address: str,
        sol_in: float,
        slippage_bps: int,
    ) -> list[Instruction]:
        raise NotImplementedError()

    async def build_sell_instructions(
        self,
        payer_keypair: Keypair,
        token_address: str,
        ui_amount: float,
        in_type: SwapInType,
        slippage_bps: int,
    ) -> list[Instruction]:
        raise NotImplementedError()

    async def build_swap_transaction(
        self,
        keypair: Keypair,
        token_address: str,
        ui_amount: float,
        swap_direction: SwapDirection,
        slippage_bps: int,
        in_type: SwapInType | None = None,
        use_jito: bool = False,
    ) -> VersionedTransaction:
        if swap_direction not in [SwapDirection.Buy, SwapDirection.Sell]:
            raise ValueError("swap_direction must be buy or sell")

        if swap_direction == SwapDirection.Buy:
            instructions = await self.build_buy_instructions(
                payer_keypair=keypair,
                token_address=token_address,
                sol_in=ui_amount,
                slippage_bps=slippage_bps,
            )
        elif swap_direction == SwapDirection.Sell:
            if in_type == SwapInType.Pct:
                instructions = await self.build_sell_instructions(
                    payer_keypair=keypair,
                    token_address=token_address,
                    ui_amount=ui_amount,
                    slippage_bps=slippage_bps,
                    in_type=in_type,
                )
            elif in_type == SwapInType.Qty:
                raise NotImplementedError("Qty in_type is not implemented yet")
            else:
                raise ValueError("in_type must be pct or qty")

        return await build_transaction(
            keypair=keypair,
            instructions=instructions,
            use_jito=use_jito,
        )
