import httpx
from solana.rpc.async_api import AsyncClient
from solders.keypair import Keypair  # type: ignore
from solders.transaction import VersionedTransaction  # type: ignore

from cache.token_info import TokenInfoCache
from common.config import settings
from common.constants import SOL_DECIMAL, WSOL
from trading.exceptions import NoRouteFound
from trading.swap import SwapDirection, SwapInType
from trading.tx import sign_transaction_from_raw

from .base import TransactionBuilder


class GMGNTransactionBuilder(TransactionBuilder):
    """GMGN 交易构建器"""

    def __init__(self, rpc_client: AsyncClient) -> None:
        self.client = httpx.AsyncClient(base_url="https://gmgn.ai")
        self.api_path = "/defi/router/v1/sol/tx/get_swap_route"
        self.rpc_client = rpc_client
        self.token_info_cache = TokenInfoCache()

    async def build_swap_transaction(
        self,
        keypair: Keypair,
        token_address: str,
        ui_amount: float,
        swap_direction: SwapDirection,
        slippage_bps: int,
        in_type: SwapInType | None = None,
        use_jito: bool = False,
        priority_fee: float | None = None,
    ) -> VersionedTransaction:
        """Build swap transaction with GMGN API.

        Args:
            token_address (str): token address
            amount_in (float): amount in
            swap_direction (SwapDirection): swap direction
            slippage (int): slippage, percentage
            in_type (SwapInType | None, optional): in type. Defaults to None.
            use_jto (bool, optional): use jto. Defaults to False.
            priority_fee (float | None, optional): priority fee. Defaults to None.

        Returns:
            VersionedTransaction: The built transaction ready to be signed and sent
        """
        if swap_direction == SwapDirection.Sell and in_type is None:
            raise ValueError("in_type must be specified when selling")

        if swap_direction == SwapDirection.Buy:
            token_in = str(WSOL)
            token_out = token_address
            swap_mode = "ExactIn"
            amount = str(int(ui_amount * 10 ** SOL_DECIMAL))
        elif swap_direction == SwapDirection.Sell:
            token_info = await self.token_info_cache.get(token_address)
            if token_info is None:
                raise ValueError("Token info not found")
            decimals = token_info.decimals
            token_in = token_address
            token_out = str(WSOL)
            swap_mode = "ExactIn"
            amount = str(int(ui_amount * 10**decimals))
        else:
            raise ValueError("swap_direction must be buy or sell")

        if priority_fee is None:
            fee = settings.trading.unit_limit * settings.trading.unit_price / 10**15
        else:
            fee = priority_fee

        slippage = slippage_bps / 100
        params = {
            "token_in_address": token_in,
            "token_out_address": token_out,
            "in_amount": amount,
            "from_address": keypair.pubkey().__str__(),
            "slippage": slippage,
            "swap_mode": swap_mode,
            "fee": fee,
        }

        # TODO: 获取报价解耦
        resp = await self.client.get(self.api_path, params=params)
        resp.raise_for_status()

        js = resp.json()
        if js["code"] != 0:
            msg = js["msg"]
            if "no route" in msg:
                raise NoRouteFound(msg)
            raise Exception("Error: {}, Argument: {}".format(js["msg"], params))

        data = js["data"]
        raw_tx = data["raw_tx"]
        swap_tx = raw_tx["swapTransaction"]

        signed_tx = await sign_transaction_from_raw(swap_tx, keypair)
        return signed_tx
