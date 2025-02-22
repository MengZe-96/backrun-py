from abc import ABC, abstractmethod
from typing import Optional

from solana.rpc.async_api import AsyncClient
from solders.keypair import Keypair  # type: ignore
from solders.transaction import VersionedTransaction  # type: ignore
from common.types.enums import SwapDirection, SwapInType


class TransactionBuilder(ABC):
    """交易构建器的抽象基类"""

    def __init__(self, rpc_client: AsyncClient):
        self.rpc_client = rpc_client

    @abstractmethod
    async def build_swap_transaction(
        self,
        keypair: Keypair,
        token_address: str,
        ui_amount: float,
        swap_direction: SwapDirection,
        slippage_bps: int,
        in_type: SwapInType | None = None,
        use_jito: bool = False,
        priority_fee: Optional[float] = None,
    ) -> VersionedTransaction:
        """构建交易

        Args:
            keypair (Keypair): 钱包密钥对
            token_address (str): 代币地址
            ui_amount (float): 交易数量
            swap_direction (SwapDirection): 交易方向
            slippage_bps (int): 滑点，以 bps 为单位
            in_type (SwapInType | None, optional): 输入类型. Defaults to None.
            use_jito (bool, optional): 是否使用 Jito. Defaults to False.
            priority_fee (Optional[float], optional): 优先费用. Defaults to None.

        Returns:
            VersionedTransaction: 构建好的交易
        """
        pass
