from solana.rpc.async_api import AsyncClient
from solbot_cache.token_info import TokenInfoCache
from solbot_common.constants import SOL_DECIMAL, WSOL
from solbot_common.utils.jupiter import JupiterAPI
from solbot_common.utils.shyft import ShyftAPI
from solders.keypair import Keypair  # type: ignore
from solders.transaction import VersionedTransaction  # type: ignore

from solbot_common.types.enums import SwapDirection, SwapInType
from trading.tx import sign_transaction_from_raw
from .base import TransactionBuilder


class JupiterTransactionBuilder(TransactionBuilder):
    """Jupiter 交易构建器"""

    def __init__(self, rpc_client: AsyncClient) -> None:
        super().__init__(rpc_client=rpc_client)
        self.token_info_cache = TokenInfoCache()
        self.jupiter_client = JupiterAPI() # base_url="https://public.jupiterapi.com"
        self.shyft = ShyftAPI()

    async def build_swap_transaction(
        self,
        keypair: Keypair,
        token_address: str,
        ui_amount: float,
        swap_direction: SwapDirection,
        slippage_bps: int,
        target_price: float | None = None,
        in_type: SwapInType | None = None,
        use_jito: bool = False,
        priority_fee: float | None = None,
    ) -> VersionedTransaction:
        """Build swap transaction with Jupiter API.

        Args:
            token_address (str): token address
            amount_in (float): amount in
            swap_direction (SwapDirection): swap direction
            slippage (int): slippage, percentage
            target_price (float | None, optional): target price. Defaults to None.
            in_type (SwapInType | None, optional): in type. Defaults to None.
            use_jto (bool, optional): use jto. Defaults to False.
            priority_fee (float | None, optional): priority fee. Defaults to None.

        Returns:
            VersionedTransaction: The built transaction ready to be signed and sent
        """
        if swap_direction == "sell" and in_type is None:
            raise ValueError("in_type must be specified when selling")

        if swap_direction == SwapDirection.Buy:
            token_in = str(WSOL)
            token_out = token_address
            amount = int(ui_amount * 10 ** SOL_DECIMAL)
        elif swap_direction == SwapDirection.Sell:
            token_info = await self.token_info_cache.get(token_address)
            if token_info is None:
                raise ValueError("Token info not found")
            decimals = token_info.decimals
            token_in = token_address
            token_out = str(WSOL)
            amount = int(ui_amount * 10**decimals)
        else:
            raise ValueError("swap_direction must be buy or sell")

        if use_jito and priority_fee is None:
            raise ValueError("priority_fee must be specified when using jito")
        
        # 买入设置跟单滑点
        min_amount_out = None
        if target_price is not None and swap_direction == SwapDirection.Buy:
            token_info = await self.shyft.get_token_info(token_address)
            min_amount_out = int(ui_amount * target_price * (1 - slippage_bps / 10000) * 10 ** token_info['decimals'])

        swap_tx_response = await self.jupiter_client.get_swap_transaction(
            input_mint=token_in,
            output_mint=token_out,
            user_publickey=str(keypair.pubkey()),
            amount=amount,
            min_amount_out=min_amount_out if min_amount_out is not None else None,
            slippage_bps=slippage_bps,
            use_jito=use_jito,
            jito_tip_lamports=int(priority_fee * 10 ** SOL_DECIMAL) if priority_fee else None,
        )
        swap_tx = swap_tx_response["swapTransaction"]
        signed_tx = await sign_transaction_from_raw(swap_tx, keypair)
        return signed_tx
