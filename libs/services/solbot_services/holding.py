from solbot_common.config import settings
from solbot_common.types.holding import HoldingToken, TokenAccountBalance, HoldingSummary, Holding
from solbot_common.utils.shyft import ShyftAPI
from solbot_common.utils.utils import format_number

from typing import List, Optional, Literal
from solbot_common.types.swap import SwapResult, SwapEvent
from solbot_common.types.enums import SwapDirection
from solbot_common.models.tg_bot.holding import Holding as HoldingModel

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from solbot_db.session import NEW_ASYNC_SESSION, provide_session
from solbot_common.log import logger
from solbot_cache.token_info import TokenInfoCache
from solbot_services.copytrade import CopyTradeService


# PERF: 暂时每次获取都调用 API，后续可以优化
class HoldingService:
    def __init__(self) -> None:
        self.shyft = ShyftAPI(settings.api.shyft_api_key)

    async def get_token_account_balance(self, mint: str, wallet: str) -> TokenAccountBalance:
        """获取代币账户余额

        Args:
            token_mint (str): 代币地址
            owner (str): 持有者地址

        Returns:
            TokenAccountBalance: 代币账户余额
        """
        balance, decimals = await self.shyft.get_token_balance(mint, wallet)
        return TokenAccountBalance(balance=balance, decimals=decimals)

    async def get_tokens(
        self,
        wallet: str,
        hidden_small_amount: bool = False,
    ) -> list[HoldingToken]:
        """获取持有的 Token 列表

        Args:
            hidden_small_amount (bool, optional): 是否隐藏小额 Token. Defaults to False.

        """
        # PREF: 使用Helius获取token 2022 及 spl token
        all_tokens = await self.shyft.get_all_tokens(wallet)
        if hidden_small_amount:
            all_tokens = [token for token in all_tokens if token["balance"] > 0]

        return [
            HoldingToken(
                mint=token["address"],
                balance=token["balance"],
                balance_str=format_number(token["balance"]),
                symbol=token["info"]["symbol"],
                # usd_value=token["info"]["current_supply"] * token["info"]["price"],
                # price=token["info"]["price"],
            )
            for token in all_tokens
        ]

    @classmethod
    async def check_swap_permission(cls, swap_event: SwapEvent) -> bool:
        # user或者卖出均放行 
        if swap_event.by == "user" or swap_event.swap_direction == SwapDirection.Sell:
            return True

        holding = await cls.get_positions(target_wallets=[swap_event.tx_event.who], mint=swap_event.tx_event.mint, mode = 3)
        # 获取数据库setting中的target别名、最大仓位、最大加仓次数
        copytrade_setting = await CopyTradeService.get_target_setting(swap_event.tx_event.who)
        # 交易许可验证
        if holding is None: # 新token需要验证设置部分
            if(copytrade_setting.current_position < copytrade_setting.max_position and
               (copytrade_setting.sol_sold - copytrade_setting.sol_earned) < copytrade_setting.max_position and
                copytrade_setting.fast_trade_time < copytrade_setting.fast_trade_sleep_threshold and
                copytrade_setting.filter_min_buy <= swap_event.tx_event.from_amount):
                return True
            else:
                # PREF: 过滤次数 + 1, 反馈原因
                logger.info(f"current_position < max_position: {copytrade_setting.current_position < copytrade_setting.max_position}, "
                            f"copytrade_setting.sol_sold - copytrade_setting.sol_earned >= {copytrade_setting.max_position}, "
                            f"fast_trade_time < fast_trade_sleep_threshold: {copytrade_setting.fast_trade_time < copytrade_setting.fast_trade_sleep_threshold}, "
                            f"filter_min_buy <= tx_event.from_amount: {copytrade_setting.filter_min_buy <= swap_event.tx_event.from_amount}."
                )
        else: # 旧有token需要验证仓位和设置
            if (holding.buy_time < holding.max_buy_time and
                copytrade_setting.current_position < copytrade_setting.max_position and
                (copytrade_setting.sol_sold - copytrade_setting.sol_earned) < copytrade_setting.max_position and
                copytrade_setting.fast_trade_time < copytrade_setting.fast_trade_sleep_threshold and
                copytrade_setting.filter_min_buy <= swap_event.tx_event.from_amount):
                return True
            else:
                # 过滤次数 + 1, 反馈原因
                logger.info(
                    f"holding.buy_time < holding.max_buy_time: {holding.buy_time < holding.max_buy_time}, "
                    f"current_position < max_position: {copytrade_setting.current_position < copytrade_setting.max_position}, "
                    f"copytrade_setting.sol_sold - copytrade_setting.sol_earned >= {copytrade_setting.max_position}, "
                    f"fast_trade_time < fast_trade_sleep_threshold: {copytrade_setting.fast_trade_time < copytrade_setting.fast_trade_sleep_threshold}, "
                    f"filter_min_buy <= tx_event.from_amount: {copytrade_setting.filter_min_buy <= swap_event.tx_event.from_amount}."
                )
        await CopyTradeService.add_filtered_time(swap_event.tx_event.who)
        return False

    @classmethod
    @provide_session
    async def update_holding_tokens(
        cls, swap_result: SwapResult, *, session: AsyncSession = NEW_ASYNC_SESSION
    ) -> None:
        # holding is None:
        # 1. 跟买建仓 -> copytrade buy
        # -. 跟买减仓 -> copytrade sell 跳过
        # -. 自己建仓 -> user buy 跳过
        # -. 自己减/清仓 -> user sell 跳过
        # holding is not None:
        # 2. 跟买加仓 -> copytrade buy
        # 3. 跟卖减仓 -> copytrade sell
        # -. 自己加仓 -> user buy 跳过
        # -. 自己减/清仓 -> user sell *按比例减少每个target的持仓
        # *PREF:
        # 指定清理某个holding的仓位，通过伪造清仓信息实现。

        if swap_result.by == "copytrade":
            tx = swap_result.swap_event.tx_event
            swap = swap_result.swap_event
            record = swap_result.swap_record

            # 查询现有记录
            stmt = select(HoldingModel).where(
                (HoldingModel.target_wallet == tx.who) &
                (HoldingModel.mint == tx.mint)
            ).limit(1)

            result = await session.execute(stmt)
            holding = result.scalar_one_or_none()

            # 获取数据库setting中的target别名、最大仓位、最大加仓次数等
            copytrade_setting = await CopyTradeService.get_target_setting(tx.who)

            if holding is None and swap.swap_direction == SwapDirection.Buy:
            # 1. 跟买建仓 -> copytrade buy
                # 获取数据库TokenInfo
                token_info_cache = TokenInfoCache()
                token_info = await token_info_cache.get(mint=tx.mint)
                # 增加holding，并更新copytrade全局状态
                await CopyTradeService.update_target_state(
                    state_delta={
                        'target_wallet': tx.who, 
                        'current_position': record.input_amount,
                        'sol_sold': record.input_amount,
                        'token_number': 1
                    }
                )
                holding = Holding(
                    cp_pk = copytrade_setting.id,
                    target_alias= copytrade_setting.target_alias,
                    target_wallet=tx.who,
                    mint=tx.mint,
                    symbol= token_info.symbol,
                    decimals=record.output_token_decimals,
                    my_amount=record.output_amount,
                    target_amount=tx.to_amount,
                    current_position = record.input_amount,
                    max_position= copytrade_setting.max_position,
                    buy_time=1,
                    max_buy_time= copytrade_setting.max_buy_time,
                    sol_sold=record.input_amount,
                    sol_earned=0,
                    latest_trade_timestamp=tx.timestamp,
                )

                await cls._add(holding)
            elif holding is not None:
                data = {}
                data['target_wallet'] = tx.who
                data['mint'] = tx.mint
                data['latest_trade_timestamp'] = tx.timestamp
                # 更新copytrade全局状态
                state_delta = {'target_wallet': tx.who}
                # 3. 跟卖减仓 -> copytrade sell
                if tx.tx_direction == SwapDirection.Sell:
                    data['target_amount'] = holding.target_amount - tx.from_amount
                    data['my_amount'] = holding.my_amount - record.input_amount
                    data['sol_earned'] = holding.sol_earned + record.output_amount
                    data['current_position'] = holding.current_position * (1 - record.input_amount/holding.my_amount)
                    # PREP: 修复精度问题
                    state_delta = {
                        'target_wallet': tx.who, 
                        'current_position': - holding.current_position * record.input_amount/holding.my_amount,
                        'sol_earned': record.output_amount,
                    }

                # 2. 跟买加仓 -> copytrade buy
                else:
                    data['my_amount'] = holding.my_amount + record.output_amount
                    data['target_amount'] = holding.target_amount + tx.to_amount
                    data['buy_time'] = holding.buy_time + 1
                    data['sol_sold'] = holding.sol_sold + record.input_amount
                    data['current_position'] = holding.current_position + record.input_amount

                    state_delta = {
                        'target_wallet': tx.who, 
                        'current_position': record.input_amount,
                        'sol_sold': record.input_amount,
                    }

                # 判定快速交易，更新快速交易的状态
                if tx.timestamp - holding.latest_trade_timestamp < copytrade_setting.fast_trade_threshold:
                    # 是否需要更新fast_trade_start_time
                    if tx.timestamp - copytrade_setting.fast_trade_start_time > copytrade_setting.fast_trade_duration:
                        state_delta['fast_trade_start_time'] = tx.timestamp - copytrade_setting.fast_trade_start_time # delta
                        state_delta['fast_trade_time'] = -(copytrade_setting.fast_trade_time - 1)
                    else:
                        state_delta['fast_trade_time'] = 1

                await CopyTradeService.update_target_state(state_delta)
                await cls._update(data)
            else:
                # -. 跟买减仓 -> copytrade sell 跳过
                pass
        else:
            # 4.自己减/清仓 -> user sell *按比例减少每个target的持仓
            # if swap.swap_direction == SwapDirection.Sell:
            #     swap = swap_result.swap_event
            #     record = swap_result.swap_record
            #     holdings = await cls.get_positions(mint=swap.input_mint, mode = 4)
            #     total_my_amount = sum(holding.my_amount for holding in holdings)
            #     state_delta = {
            #         'target_wallet': holding.target_wallet,

            #     }

            #     for holding in holdings:
            #         data = {}
            #         data['target_wallet'] = holding.target_wallet
            #         data['mint'] = holding.mint
            #         data['my_amount'] = holding.my_amount - holding.my_amount/total_my_amount * record.input_amount
            #         data['current_position'] = holding.current_position * (1 - record.input_amount/holding.my_amount)
            #         await cls._update(data)
            # else:
                # -. 自己建仓 -> user buy 跳过
                pass


    @classmethod
    @provide_session
    async def _add(
        cls, holding: Holding, *, session: AsyncSession = NEW_ASYNC_SESSION
    ) -> None:
        """Add a new holding to the database"""

        model = HoldingModel(
            cp_pk = holding.cp_pk,
            target_alias=holding.target_alias,
            target_wallet=holding.target_wallet,
            mint=holding.mint,
            symbol=holding.symbol,
            decimals=holding.decimals,
            my_amount=holding.my_amount,
            target_amount=holding.target_amount,
            current_position = holding.current_position,
            max_position=holding.max_position,
            buy_time=holding.buy_time,
            max_buy_time=holding.max_buy_time,
            sol_sold=holding.sol_sold,
            sol_earned=holding.sol_earned,
            latest_trade_timestamp=holding.latest_trade_timestamp,
        )

        session.add(model)
        await session.flush()

        assert model.id is not None, "model.id is None"

    @classmethod
    @provide_session
    async def _update(
        cls,
        holding: dict,
        *,
        session: AsyncSession = NEW_ASYNC_SESSION
    ) -> None:
        """Update specific fields of an existing holding in the database based on target_wallet and mint
        
        Args:
            holding: Dictionary containing field names as keys and their values
            session: SQLAlchemy async session
            
        Raises:
            ValueError: If target_wallet or mint not in holding dict, or if record not found
        """
        # 确保 target_wallet 和 mint 在字典中存在
        if 'target_wallet' not in holding or 'mint' not in holding:
            raise ValueError("holding dict must contain 'target_wallet' and 'mint' keys")

        # 查询现有记录
        stmt = select(HoldingModel).where(
            (HoldingModel.target_wallet == holding['target_wallet']) &
            (HoldingModel.mint == holding['mint'])
        ).limit(1)

        result = await session.execute(stmt)
        obj = result.scalar_one_or_none()

        if obj is None:
            raise ValueError(
                f"Holding with target_wallet {holding['target_wallet']} "
                f"and mint {holding['mint']} not found"
            )

        # 只更新 holding dict 中提供的字段（排除 target_wallet 和 mint）
        for key, value in holding.items():
            if key not in ['target_wallet', 'mint']:  # 不允许修改定位用的字段
                if hasattr(obj, key):
                    setattr(obj, key, value)
                else:
                    raise ValueError(f"Invalid field name in holding dict: {key}")

        session.add(obj)
        assert obj.id is not None, "obj.id should not be None after update"
        await session.commit()

    # 1. 获取单个target的所有mint仓位，用于在跟单战绩中第二层详情界面显示。token名称、my amount、target token amount、买入次数/最大次数、支出sol/收入sol、失败次数、过滤次数
    # 2. 获取所有target的所有mint仓位，用于在跟单战绩中第一层界面显示。target名称、支出sol/最大支出sol、仓位价值以sol计价、token数量、失败总次数、过滤总次数
    # 3. 获取单个target的单个mint仓位，用于计算跟单卖出数量。target position 和 my position
    # 4. 获取单个mint的所有target仓位，...
    @classmethod
    @provide_session
    async def get_positions(
        cls,
        target_wallets: Optional[List[str]] = None,
        mint: Optional[str] = None,
        mode: Literal[1, 2, 3, 4] = 1, # 指定上述功能
        *,
        session: AsyncSession = NEW_ASYNC_SESSION
    ) -> List[Holding] | List[HoldingSummary] | Holding | None:
        """灵活查询仓位信息
        
        Args:
            target_wallets: 可选的目标钱包列表,None表示查询所有
            mint: 可选的特定mint,None表示查询所有
            session: SQLAlchemy async session
            
        Returns:
            1. List[Holding]
            2. List[HoldingSummary]
            3. Holding
            4. List[Holding]
            None # 新币将出现none
        """
        if mode == 1:
            assert target_wallets is not None and len(target_wallets) == 1, f"[Get Position Mode 1] Target wallet must be single, but: {target_wallets}."
            assert mint is None, f"[Get Position Mode 1] Mint must be None, but: {mint}."
            stmt = select(HoldingModel).where(
                (HoldingModel.target_wallet.in_(target_wallets)) &
                (HoldingModel.target_amount > 0)
            )
            result = await session.execute(stmt)
            holdings = result.scalars().all()
            return [
                Holding(
                    cp_pk = holding.cp_pk,
                    target_alias=holding.target_alias,
                    target_wallet=holding.target_wallet,
                    mint=holding.mint,
                    symbol=holding.symbol,
                    decimals=holding.decimals,
                    my_amount=holding.my_amount,
                    target_amount=holding.target_amount,
                    current_position=holding.current_position,
                    max_position=holding.max_position,
                    buy_time=holding.buy_time,
                    max_buy_time=holding.max_buy_time,
                    sol_sold=holding.sol_sold,
                    sol_earned=holding.sol_earned,
                    latest_trade_timestamp=holding.latest_trade_timestamp,
                ) for holding in holdings
            ]
        elif mode == 2:
            assert target_wallets is None, f"[Get Position Mode 2] Target wallet must be None, but: {target_wallets}."
            assert mint is None, f"[Get Position Mode 2] Mint must be None, but: {mint}."
            stmt = select(HoldingModel).where(
                HoldingModel.target_amount > 0
            )
            result = await session.execute(stmt)
            holdings = result.scalars().all()

            summaries = {}
            for holding in holdings:
                if holding.target_wallet in summaries:
                    summaries.ui_sol_sold += holding.ui_sol_sold
                    summaries.ui_sol_earned += holding.ui_sol_earned
                    summaries.ui_current_position += holding.ui_current_position
                    summaries.token_number += 1
                else:
                    target_setting = await CopyTradeService.get_target_setting(target_wallet=holding.target_wallet)
                    summaries[holding.target_wallet] = HoldingSummary(
                        target_alias = holding.target_alias,
                        target_wallet = holding.target_wallet,
                        ui_sol_sold = holding.ui_sol_sold,
                        ui_sol_earned = holding.ui_sol_earned,
                        ui_current_position = holding.ui_current_position,
                        ui_max_position = holding.ui_max_position,
                        token_number = 1,
                        failed_time = target_setting.failed_time,
                        filtered_time = target_setting.filtered_time,
                    )
            return list(summaries.values())

        elif mode == 3:
            assert target_wallets is not None and len(target_wallets) == 1, f"[Get Position Mode 3] Target wallet must be single, but: {target_wallets}."
            assert mint is not None, f"[Get Position Mode 3] Mint must be specified, but: {mint}."
            stmt = select(HoldingModel).where(
                (HoldingModel.target_wallet.in_(target_wallets)) &
                (HoldingModel.mint == mint)
            )
            result = await session.execute(stmt)
            holding = result.scalar_one_or_none()
            if holding is None:
                return None
            return Holding(
                cp_pk = holding.cp_pk,
                target_alias=holding.target_alias,
                target_wallet=holding.target_wallet,
                mint=holding.mint,
                symbol=holding.symbol,
                decimals=holding.decimals,
                my_amount=holding.my_amount,
                target_amount=holding.target_amount,
                current_position=holding.current_position,
                max_position=holding.max_position,
                buy_time=holding.buy_time,
                max_buy_time=holding.max_buy_time,
                sol_sold=holding.sol_sold,
                sol_earned=holding.sol_earned,
                latest_trade_timestamp=holding.latest_trade_timestamp,
            )
        else:
            assert target_wallets is None, f"[Get Position Mode 4] Target wallet must be None, but: {target_wallets}."
            assert mint is not None, f"[Get Position Mode 4] Mint must be specified, but: {mint}."
            stmt = select(HoldingModel).where(
                HoldingModel.mint == mint
            )
            result = await session.execute(stmt)
            holdings = result.scalars().all()
            return [
                Holding(
                    cp_pk = holding.cp_pk,
                    target_alias=holding.target_alias,
                    target_wallet=holding.target_wallet,
                    mint=holding.mint,
                    symbol=holding.symbol,
                    decimals=holding.decimals,
                    my_amount=holding.my_amount,
                    target_amount=holding.target_amount,
                    current_position=holding.current_position,
                    max_position=holding.max_position,
                    buy_time=holding.buy_time,
                    max_buy_time=holding.max_buy_time,
                    sol_sold=holding.sol_sold,
                    sol_earned=holding.sol_earned,
                    latest_trade_timestamp=holding.latest_trade_timestamp,
                ) for holding in holdings
            ]