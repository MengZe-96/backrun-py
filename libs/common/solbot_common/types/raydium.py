import struct
from dataclasses import dataclass
from enum import Enum

from solders.pubkey import Pubkey  # type: ignore
from typing_extensions import Self

from solbot_common.constants import OPEN_BOOK_PROGRAM, RAY_AUTHORITY_V4, WSOL
from solbot_common.layouts.amm_v4 import LIQUIDITY_STATE_LAYOUT_V4, MARKET_STATE_LAYOUT_V3
from solbot_cache.token_info import TokenInfoCache


def bytes_of(value):
    if not (0 <= value < 2**64):
        raise ValueError("Value must be in the range of a u64 (0 to 2^64 - 1).")
    return struct.pack("<Q", value)


@dataclass
class AmmV4PoolKeys:
    amm_id: Pubkey
    base_mint: Pubkey
    quote_mint: Pubkey
    base_decimals: int
    quote_decimals: int
    open_orders: Pubkey
    target_orders: Pubkey
    base_vault: Pubkey
    quote_vault: Pubkey
    market_id: Pubkey
    market_authority: Pubkey
    market_base_vault: Pubkey
    market_quote_vault: Pubkey
    bids: Pubkey
    asks: Pubkey
    event_queue: Pubkey
    ray_authority_v4: Pubkey
    open_book_program: Pubkey
    token_program_id: Pubkey
    
    @classmethod
    async def from_pool_data(cls, pool_id: str | Pubkey, amm_data: bytes, market_data: bytes) -> Self:
        if isinstance(pool_id, str):
            amm_id = Pubkey.from_string(pool_id)
        else:
            amm_id = pool_id
        try:
            amm_data_decoded = LIQUIDITY_STATE_LAYOUT_V4.parse(amm_data)
            market_decoded = MARKET_STATE_LAYOUT_V3.parse(market_data)
            marketId = Pubkey.from_bytes(amm_data_decoded.serumMarket)
            vault_signer_nonce = market_decoded.vault_signer_nonce
        except Exception as e:
            raise ValueError("Error parsing pool data") from e

        ray_authority_v4 = RAY_AUTHORITY_V4
        open_book_program = OPEN_BOOK_PROGRAM
        # token_program_id = TOKEN_PROGRAM_ID
        # 区分spl token与token 2022的program id
        base_mint = Pubkey.from_bytes(market_decoded.base_mint)
        quote_mint = Pubkey.from_bytes(market_decoded.quote_mint)
        mint = quote_mint if base_mint == WSOL else base_mint
        # PREF: 尽量不实例化
        token_info_cache = TokenInfoCache()
        token_info = await token_info_cache.get(mint) # bytes to string
        pool_keys = cls(
            amm_id=amm_id,
            base_mint=base_mint,
            quote_mint=quote_mint,
            base_decimals=amm_data_decoded.coinDecimals,
            quote_decimals=amm_data_decoded.pcDecimals,
            open_orders=Pubkey.from_bytes(amm_data_decoded.ammOpenOrders),
            target_orders=Pubkey.from_bytes(amm_data_decoded.ammTargetOrders),
            base_vault=Pubkey.from_bytes(amm_data_decoded.poolCoinTokenAccount),
            quote_vault=Pubkey.from_bytes(amm_data_decoded.poolPcTokenAccount),
            market_id=marketId,
            market_authority=Pubkey.create_program_address(
                seeds=[bytes(marketId), bytes_of(vault_signer_nonce)],
                program_id=open_book_program,
            ),
            market_base_vault=Pubkey.from_bytes(market_decoded.base_vault),
            market_quote_vault=Pubkey.from_bytes(market_decoded.quote_vault),
            bids=Pubkey.from_bytes(market_decoded.bids),
            asks=Pubkey.from_bytes(market_decoded.asks),
            event_queue=Pubkey.from_bytes(market_decoded.event_queue),
            ray_authority_v4=ray_authority_v4,
            open_book_program=open_book_program,
            token_program_id=Pubkey.from_string(token_info.token_program)
        )

        return pool_keys


@dataclass
class CpmmPoolKeys:
    pool_state: Pubkey
    raydium_vault_auth_2: Pubkey
    amm_config: Pubkey
    pool_creator: Pubkey
    token_0_vault: Pubkey
    token_1_vault: Pubkey
    lp_mint: Pubkey
    token_0_mint: Pubkey
    token_1_mint: Pubkey
    token_0_program: Pubkey
    token_1_program: Pubkey
    observation_key: Pubkey
    auth_bump: int
    status: int
    lp_mint_decimals: int
    mint_0_decimals: int
    mint_1_decimals: int
    lp_supply: int
    protocol_fees_token_0: int
    protocol_fees_token_1: int
    fund_fees_token_0: int
    fund_fees_token_1: int
    open_time: int


@dataclass
class ClmmPoolKeys:
    pool_state: Pubkey
    amm_config: Pubkey
    owner: Pubkey
    token_mint_0: Pubkey
    token_mint_1: Pubkey
    token_vault_0: Pubkey
    token_vault_1: Pubkey
    observation_key: Pubkey
    current_tick_array: Pubkey
    prev_tick_array: Pubkey
    additional_tick_array: Pubkey
    bitmap_extension: Pubkey
    mint_decimals_0: int
    mint_decimals_1: int
    tick_spacing: int
    liquidity: int
    sqrt_price_x64: int
    tick_current: int
    observation_index: int
    observation_update_duration: int
    fee_growth_global_0_x64: int
    fee_growth_global_1_x64: int
    protocol_fees_token_0: int
    protocol_fees_token_1: int
    swap_in_amount_token_0: int
    swap_out_amount_token_1: int
    swap_in_amount_token_1: int
    swap_out_amount_token_0: int
    status: int
    total_fees_token_0: int
    total_fees_claimed_token_0: int
    total_fees_token_1: int
    total_fees_claimed_token_1: int
    fund_fees_token_0: int
    fund_fees_token_1: int


class DIRECTION(Enum):
    BUY = 0
    SELL = 1
