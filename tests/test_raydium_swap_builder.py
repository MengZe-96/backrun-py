# import pytest
# from common.log import logger
# from solana_trade_bot.trading.raydium.swap_builder import RaydiumSwapBuilder
# from common.constants import SOL_DECIMAL


# @pytest.fixture
# def swap_builder() -> RaydiumSwapBuilder:
#     return RaydiumSwapBuilder()


# def test_fetch_swap_response(swap_builder: RaydiumSwapBuilder):
#     """测试获取 swap response"""
#     # BONK/SOL pair
#     mint = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
#     sol_in = 0.1
#     slippage = 100  # 1%

#     swap_resp = swap_builder._fetch_swap_response(sol_in, slippage, mint)
#     assert swap_resp is not None
#     assert swap_resp.data["inputAmount"] == str(int(sol_in * 10 ** SOL_DECIMAL))


# def test_build_buy_transaction(swap_builder):
#     """测试构建买入交易"""
#     # BONK/SOL pair
#     mint = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
#     sol_in = 0.1
#     slippage = 100  # 1%

#     transaction = swap_builder.build_buy_transaction(sol_in, slippage, mint)
#     assert transaction is not None
#     assert isinstance(transaction, str)
#     assert len(transaction) > 0


# def test_compute_unit_price_setting(swap_builder):
#     """测试计算单元价格设置"""
#     # 测试默认值
#     assert swap_builder.DEFAULT_COMPUTE_UNIT_PRICE == 1_000

#     # 测试设置新值
#     new_price = 5_000
#     swap_builder.set_compute_unit_price(new_price)
#     assert swap_builder.DEFAULT_COMPUTE_UNIT_PRICE == new_price

#     # 测试交易构建是否使用新的计算单元价格
#     mint = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
#     sol_in = 0.1
#     slippage = 100

#     transaction = swap_builder.build_buy_transaction(sol_in, slippage, mint)
#     assert transaction is not None


# def test_different_slippage_values(swap_builder):
#     """测试不同滑点值的情况"""
#     mint = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
#     sol_in = 0.1
#     slippage_values = [50, 100, 200]  # 0.5%, 1%, 2%

#     for slippage in slippage_values:
#         transaction = swap_builder.build_buy_transaction(sol_in, slippage, mint)
#         assert transaction is not None
#         logger.info(f"Successfully built transaction with {slippage/100}% slippage")


# def test_different_sol_amounts(swap_builder):
#     """测试不同 SOL 数量的情况"""
#     mint = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
#     sol_amounts = [0.05, 0.1, 0.2]
#     slippage = 100

#     for sol_in in sol_amounts:
#         transaction = swap_builder.build_buy_transaction(sol_in, slippage, mint)
#         assert transaction is not None
#         logger.info(f"Successfully built transaction with {sol_in} SOL")
