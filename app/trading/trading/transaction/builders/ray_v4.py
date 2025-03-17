import base64
import os

from loguru import logger
from solana.rpc.commitment import Processed
from solana.rpc.types import TokenAccountOpts
from solbot_cache import get_min_balance_rent
from solbot_cache.rayidum import get_preferred_pool
from solbot_common.constants import ACCOUNT_LAYOUT_LEN, SOL_DECIMAL, TOKEN_PROGRAM_ID, WSOL
from solbot_common.utils.pool import (
    AmmV4PoolKeys,
    get_amm_v4_reserves,
    make_amm_v4_swap_instruction,
)
from solbot_common.utils.utils import get_associated_token_address, get_token_balance
from solders.instruction import Instruction  # type: ignore[reportMissingModuleSource]
from solders.keypair import Keypair  # type: ignore[reportMissingModuleSource]
from solders.pubkey import Pubkey  # type: ignore[reportMissingModuleSource]
from solders.system_program import (  # type: ignore[reportMissingModuleSource]
    CreateAccountWithSeedParams,
    create_account_with_seed,
)
from solders.transaction import VersionedTransaction  # type: ignore
from spl.token.instructions import (
    CloseAccountParams,  # type: ignore
    InitializeAccountParams,
    close_account,
    create_associated_token_account,
    initialize_account,
)

from trading.tx import build_transaction

from .base import TransactionBuilder

from solbot_common.types.enums import SwapDirection, SwapInType


class RaydiumV4TransactionBuilder(TransactionBuilder):
    async def build_buy_instructions(
        self,
        payer_keypair: Keypair,
        token_address: str,
        sol_in: float,
        slippage_bps: int,
        target_price: float | None = None,
    ) -> list[Instruction]:
        """构建购买代币的指令列表

        Args:
            payer_keypair: 支付者的密钥对
            token_address: 代币地址
            sol_in: 输入的SOL数量
            slippage_bps: 滑点，以基点(bps)为单位，1bps = 0.01%

        Returns:
            list[Instruction]: 指令列表
        """
        logger.info(f"构建购买交易: {token_address}, SOL输入: {sol_in}, 滑点: {slippage_bps}bps")

        # 获取池子信息
        pool_data = await get_preferred_pool(token_address)
        if pool_data is None:
            raise ValueError(f"未找到代币 {token_address} 的交易池")

        # 构建池子密钥
        pool_keys = await AmmV4PoolKeys.from_pool_data(
            pool_id=pool_data["pool_id"],
            amm_data=pool_data["amm_data"],
            market_data=pool_data["market_data"],
        )

        # 确定代币铸币厂
        token_mint = pool_keys.base_mint if pool_keys.base_mint != WSOL else pool_keys.quote_mint

        # 计算交易金额
        amount_in = int(sol_in * 10 ** SOL_DECIMAL)

        # 获取池子储备量
        base_reserve, quote_reserve, token_decimal = await get_amm_v4_reserves(pool_keys)

        # 计算预期输出量
        # 这里使用简化的计算方法，实际应用中可能需要更复杂的计算
        constant_product = base_reserve * quote_reserve
        effective_sol_in = sol_in * (1 - (0.25 / 100))  # 考虑0.25%的交易费用
        new_quote_reserve = quote_reserve + effective_sol_in
        new_base_reserve = constant_product / new_quote_reserve
        amount_out = base_reserve - new_base_reserve

        # 应用跟单滑点
        if target_price is None:
            slippage_adjustment = 1 - (slippage_bps / 10000)  # 转换bps为百分比
            minimum_amount_out = int(amount_out * slippage_adjustment * (10**token_decimal))
        else:
            minimum_amount_out = int(target_price * (1 - slippage_bps / 10000) * sol_in * (10**token_decimal))

        # PREF: 如果minimum_amount_out小于amount_out，说明已达滑点上限，直接返回
        # logger.info(f"输入金额: {amount_in}, 最小输出金额: {minimum_amount_out}")
        if amount_out*(10**token_decimal) < minimum_amount_out:
            raise ValueError(f"已达滑点上限，最小输出金额: {minimum_amount_out}, 实际输出金额: {amount_out*(10**token_decimal)}")

        # 检查代币账户是否存在
        token_account = None
        token_accounts = await self.rpc_client.get_token_accounts_by_owner(
            payer_keypair.pubkey(), TokenAccountOpts(mint=token_mint), Processed
        )

        create_token_account_ix = None
        if token_accounts.value:
            token_account = token_accounts.value[0].pubkey
            logger.info(f"找到现有代币账户: {token_account}")
        else:
            token_account = get_associated_token_address(payer_keypair.pubkey(), token_mint)
            create_token_account_ix = create_associated_token_account(
                payer_keypair.pubkey(), payer_keypair.pubkey(), token_mint
            )
            logger.info(f"创建新的关联代币账户: {token_account}")

        # 创建临时WSOL账户
        seed = base64.urlsafe_b64encode(os.urandom(24)).decode("utf-8")
        wsol_token_account = Pubkey.create_with_seed(payer_keypair.pubkey(), seed, TOKEN_PROGRAM_ID)

        # 获取租金豁免所需的最小余额
        balance_needed = await get_min_balance_rent()

        # 创建WSOL账户指令
        create_wsol_account_ix = create_account_with_seed(
            CreateAccountWithSeedParams(
                from_pubkey=payer_keypair.pubkey(),
                to_pubkey=wsol_token_account,
                base=payer_keypair.pubkey(),
                seed=seed,
                lamports=balance_needed + amount_in,
                space=ACCOUNT_LAYOUT_LEN,
                owner=TOKEN_PROGRAM_ID,
            )
        )

        # 初始化WSOL账户指令
        init_wsol_account_ix = initialize_account(
            InitializeAccountParams(
                program_id=TOKEN_PROGRAM_ID,
                account=wsol_token_account,
                mint=WSOL,
                owner=payer_keypair.pubkey(),
            )
        )

        # 创建交换指令
        swap_ix = make_amm_v4_swap_instruction(
            amount_in=amount_in,
            minimum_amount_out=minimum_amount_out,
            token_account_in=wsol_token_account,
            token_account_out=token_account,
            accounts=pool_keys,
            owner=payer_keypair.pubkey(),
        )

        # 关闭WSOL账户指令
        close_wsol_account_ix = close_account(
            CloseAccountParams(
                program_id=TOKEN_PROGRAM_ID,
                account=wsol_token_account,
                dest=payer_keypair.pubkey(),
                owner=payer_keypair.pubkey(),
            )
        )

        # 组装指令列表
        instructions = [
            create_wsol_account_ix,
            init_wsol_account_ix,
        ]

        if create_token_account_ix:
            instructions.append(create_token_account_ix)

        instructions.append(swap_ix)
        instructions.append(close_wsol_account_ix)

        return instructions

    async def build_sell_instructions(
        self,
        payer_keypair: Keypair,
        token_address: str,
        ui_amount: float,
        in_type: SwapInType,
        slippage_bps: int,
    ) -> list[Instruction]:
        """构建卖出代币的指令列表

        Args:
            payer_keypair: 支付者的密钥对
            token_address: 代币地址
            ui_amount: 输入的数量（百分比或具体数量）
            in_type: 输入类型（百分比或具体数量）
            slippage_bps: 滑点，以基点(bps)为单位，1bps = 0.01%

        Returns:
            list[Instruction]: 指令列表
        """
        if in_type == SwapInType.Pct:
            if not (0 < ui_amount <= 100):
                raise ValueError("百分比必须在1到100之间")
        elif in_type == SwapInType.Qty:
            if ui_amount <= 0:
                raise ValueError("数量必须大于0")
        else:
            raise ValueError("in_type must be pct or qty")

        logger.info(
            f"构建卖出交易: {token_address}, 输入: {ui_amount}{in_type.value}, 滑点: {slippage_bps}bps"
        )

        # 获取池子信息
        pool_data = await get_preferred_pool(token_address)
        if pool_data is None:
            raise ValueError(f"未找到代币 {token_address} 的交易池")

        # 构建池子密钥
        pool_keys = await AmmV4PoolKeys.from_pool_data(
            pool_id=pool_data["pool_id"],
            amm_data=pool_data["amm_data"],
            market_data=pool_data["market_data"],
        )

        # 确定代币铸币厂
        token_mint = pool_keys.base_mint if pool_keys.base_mint != WSOL else pool_keys.quote_mint

        # 获取代币账户
        token_account = get_associated_token_address(payer_keypair.pubkey(), token_mint)

        # 计算要卖出的数量
        if in_type == SwapInType.Pct:
            # 获取代币余额
            token_balance = await get_token_balance(token_account, self.rpc_client)
            if token_balance is None or token_balance == 0:
                raise ValueError(f"没有可用的代币余额: {token_mint}")
            sell_amount = token_balance * (ui_amount / 100)
            logger.info(f"代币余额: {token_balance}, 卖出数量: {sell_amount} ({ui_amount}%)")
        else:
            sell_amount = ui_amount
            logger.info(f"卖出数量: {sell_amount}")

        # 获取池子储备量
        base_reserve, quote_reserve, token_decimal = await get_amm_v4_reserves(pool_keys)

        # 计算预期输出量
        # 这里使用简化的计算方法，实际应用中可能需要更复杂的计算
        constant_product = base_reserve * quote_reserve
        effective_token_in = sell_amount * (1 - (0.25 / 100))  # 考虑0.25%的交易费用
        new_base_reserve = base_reserve + effective_token_in
        new_quote_reserve = constant_product / new_base_reserve
        amount_out = quote_reserve - new_quote_reserve

        # 应用滑点
        slippage_adjustment = 1 - (slippage_bps / 10000)  # 转换bps为百分比
        minimum_amount_out = int(amount_out * slippage_adjustment * 10 ** SOL_DECIMAL)

        # 计算输入金额
        amount_in = int(sell_amount * (10**token_decimal))

        logger.info(f"输入金额: {amount_in}, 最小输出金额: {minimum_amount_out}")

        # 创建临时WSOL账户
        seed = base64.urlsafe_b64encode(os.urandom(24)).decode("utf-8")
        wsol_token_account = Pubkey.create_with_seed(payer_keypair.pubkey(), seed, TOKEN_PROGRAM_ID)

        # 获取租金豁免所需的最小余额
        balance_needed = await get_min_balance_rent()

        # 创建WSOL账户指令
        create_wsol_account_ix = create_account_with_seed(
            CreateAccountWithSeedParams(
                from_pubkey=payer_keypair.pubkey(),
                to_pubkey=wsol_token_account,
                base=payer_keypair.pubkey(),
                seed=seed,
                lamports=balance_needed,
                space=ACCOUNT_LAYOUT_LEN,
                owner=TOKEN_PROGRAM_ID,
            )
        )

        # 初始化WSOL账户指令
        init_wsol_account_ix = initialize_account(
            InitializeAccountParams(
                program_id=TOKEN_PROGRAM_ID,
                account=wsol_token_account,
                mint=WSOL,
                owner=payer_keypair.pubkey(),
            )
        )

        # 创建交换指令
        swap_ix = make_amm_v4_swap_instruction(
            amount_in=amount_in,
            minimum_amount_out=minimum_amount_out,
            token_account_in=token_account,
            token_account_out=wsol_token_account,
            accounts=pool_keys,
            owner=payer_keypair.pubkey(),
        )

        # 关闭WSOL账户指令
        close_wsol_account_ix = close_account(
            CloseAccountParams(
                program_id=TOKEN_PROGRAM_ID,
                account=wsol_token_account,
                dest=payer_keypair.pubkey(),
                owner=payer_keypair.pubkey(),
            )
        )

        # 组装指令列表
        instructions = [
            create_wsol_account_ix,
            init_wsol_account_ix,
            swap_ix,
            close_wsol_account_ix,
        ]

        # 如果卖出100%，则关闭代币账户
        # if token_balance == ui_amount:
        #     close_token_account_ix = close_account(
        #         CloseAccountParams(
        #             program_id=TOKEN_PROGRAM_ID,
        #             account=token_account,
        #             dest=payer_keypair.pubkey(),
        #             owner=payer_keypair.pubkey(),
        #         )
        #     )
        #     instructions.append(close_token_account_ix)

        return instructions

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
        if swap_direction not in [SwapDirection.Buy, SwapDirection.Sell]:
            raise ValueError("swap_direction must be buy or sell")

        if swap_direction == SwapDirection.Buy:
            instructions = await self.build_buy_instructions(
                payer_keypair=keypair,
                token_address=token_address,
                sol_in=ui_amount,
                slippage_bps=slippage_bps,
                target_price=target_price,
            )
        elif swap_direction == SwapDirection.Sell:
            if in_type is None:
                raise ValueError("in_type must be pct or qty")

            instructions = await self.build_sell_instructions(
                payer_keypair=keypair,
                token_address=token_address,
                ui_amount=ui_amount,
                slippage_bps=slippage_bps,
                in_type=in_type,
            )

        return await build_transaction(
            keypair=keypair,
            instructions=instructions,
            use_jito=use_jito,
            priority_fee=priority_fee,
        )
