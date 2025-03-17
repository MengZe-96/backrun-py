import struct
from typing import TypedDict

from solana.rpc import commitment
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Processed
from solana.rpc.types import MemcmpOpts
from solbot_cache.cached import cached
from solbot_cache.token_info import TokenInfoCache
from solders.instruction import AccountMeta, Instruction  # type: ignore
from solders.pubkey import Pubkey  # type: ignore

from solbot_common.constants import (
    DEFAULT_QUOTE_MINT,
    OPEN_BOOK_PROGRAM,
    RAY_AUTHORITY_V4,
    RAY_VAULT_AUTH_2,
    RAYDIUM_AMM_V4,
    RAYDIUM_CLMM,
    RAYDIUM_CPMM,
    TOKEN_PROGRAM_ID,
    TOKEN_2022_PROGRAM_ID,
    WSOL,
)
from solbot_common.layouts.amm_v4 import LIQUIDITY_STATE_LAYOUT_V4, MARKET_STATE_LAYOUT_V3
from solbot_common.layouts.clmm import CLMM_POOL_STATE_LAYOUT
from solbot_common.layouts.cpmm import CPMM_POOL_STATE_LAYOUT
from solbot_common.log import logger
from solbot_common.types.raydium import DIRECTION, AmmV4PoolKeys, ClmmPoolKeys, CpmmPoolKeys
from solbot_common.utils import get_async_client


class AMMData(TypedDict):
    pool_id: Pubkey
    amm_data: bytes
    market_data: bytes


async def fetch_pool_data_from_rpc(pool_id: Pubkey, rpc_client: AsyncClient) -> AMMData | None:
    """从 rpc 获取池子信息"""
    resp = await rpc_client.get_account_info_json_parsed(pool_id, commitment=commitment.Processed)
    if resp.value is None:
        return None
    amm_data = bytes(resp.value.data)
    amm_data_decoded = LIQUIDITY_STATE_LAYOUT_V4.parse(amm_data)
    market_id = Pubkey.from_bytes(amm_data_decoded.serumMarket)

    resp = await rpc_client.get_account_info_json_parsed(market_id, commitment=commitment.Processed)
    if resp.value is None:
        logger.error(f"Failed to fetch market data: {market_id}， pool_id: {pool_id}")
        return None

    market_data = bytes(resp.value.data)

    return {
        "pool_id": pool_id,
        "amm_data": amm_data,
        "market_data": market_data,
    }


@cached(ttl=60)
async def fetch_amm_v4_pool_keys(pool_id: str) -> AmmV4PoolKeys | None:
    def bytes_of(value):
        if not (0 <= value < 2**64):
            raise ValueError("Value must be in the range of a u64 (0 to 2^64 - 1).")
        return struct.pack("<Q", value)

    client = get_async_client()

    amm_id = Pubkey.from_string(pool_id)
    resp = await client.get_account_info_json_parsed(amm_id, commitment=Processed)
    if resp.value is None:
        return None
    amm_data_decoded = LIQUIDITY_STATE_LAYOUT_V4.parse(bytes(resp.value.data))

    marketId = Pubkey.from_bytes(amm_data_decoded.serumMarket)
    resp = await client.get_account_info_json_parsed(marketId, commitment=Processed)
    if resp.value is None:
        return None
    market_decoded = MARKET_STATE_LAYOUT_V3.parse(bytes(resp.value.data))
    vault_signer_nonce = market_decoded.vault_signer_nonce

    ray_authority_v4 = RAY_AUTHORITY_V4
    open_book_program = OPEN_BOOK_PROGRAM
    # token_program_id = TOKEN_PROGRAM_ID
    # 区分spl token与token 2022的program id
    base_mint = Pubkey.from_bytes(market_decoded.base_mint)
    quote_mint = Pubkey.from_bytes(market_decoded.base_mint)
    mint = quote_mint if base_mint == WSOL else base_mint
    # 尽量不实例化
    token_info_cache = TokenInfoCache()
    token_info = await token_info_cache.get(mint) # bytes to string
    pool_keys = AmmV4PoolKeys(
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


async def fetch_cpmm_pool_keys(pool_id: str) -> CpmmPoolKeys | None:
    try:
        client = get_async_client()
        pool_state = Pubkey.from_string(pool_id)
        raydium_vault_auth_2 = RAY_VAULT_AUTH_2
        resp = await client.get_account_info_json_parsed(pool_state, commitment=Processed)
        if resp.value is None:
            return None
        parsed_data = CPMM_POOL_STATE_LAYOUT.parse(bytes(resp.value.data))

        pool_keys = CpmmPoolKeys(
            pool_state=pool_state,
            raydium_vault_auth_2=raydium_vault_auth_2,
            amm_config=Pubkey.from_bytes(parsed_data.amm_config),
            pool_creator=Pubkey.from_bytes(parsed_data.pool_creator),
            token_0_vault=Pubkey.from_bytes(parsed_data.token_0_vault),
            token_1_vault=Pubkey.from_bytes(parsed_data.token_1_vault),
            lp_mint=Pubkey.from_bytes(parsed_data.lp_mint),
            token_0_mint=Pubkey.from_bytes(parsed_data.token_0_mint),
            token_1_mint=Pubkey.from_bytes(parsed_data.token_1_mint),
            token_0_program=Pubkey.from_bytes(parsed_data.token_0_program),
            token_1_program=Pubkey.from_bytes(parsed_data.token_1_program),
            observation_key=Pubkey.from_bytes(parsed_data.observation_key),
            auth_bump=parsed_data.auth_bump,
            status=parsed_data.status,
            lp_mint_decimals=parsed_data.lp_mint_decimals,
            mint_0_decimals=parsed_data.mint_0_decimals,
            mint_1_decimals=parsed_data.mint_1_decimals,
            lp_supply=parsed_data.lp_supply,
            protocol_fees_token_0=parsed_data.protocol_fees_token_0,
            protocol_fees_token_1=parsed_data.protocol_fees_token_1,
            fund_fees_token_0=parsed_data.fund_fees_token_0,
            fund_fees_token_1=parsed_data.fund_fees_token_1,
            open_time=parsed_data.open_time,
        )

        return pool_keys

    except Exception as e:
        print(f"Error fetching pool keys: {e}")
        return None


async def fetch_clmm_pool_keys(pool_id: str, zero_for_one: bool = True) -> ClmmPoolKeys | None:
    def calculate_start_index(
        tick_current: int, tick_spacing: int, tick_array_size: int = 60
    ) -> int:
        return (tick_current // (tick_spacing * tick_array_size)) * (tick_spacing * tick_array_size)

    def get_pda_tick_array_address(pool_id: Pubkey, start_index: int):
        tick_array, _ = Pubkey.find_program_address(
            [b"tick_array", bytes(pool_id), struct.pack(">i", start_index)],
            RAYDIUM_CLMM,
        )
        return tick_array

    def get_pda_tick_array_bitmap_extension(pool_id: Pubkey):
        bitmap_extension, _ = Pubkey.find_program_address(
            [b"pool_tick_array_bitmap_extension", bytes(pool_id)], RAYDIUM_CLMM
        )
        return bitmap_extension

    try:
        client = get_async_client()
        pool_state = Pubkey.from_string(pool_id)
        resp = await client.get_account_info_json_parsed(pool_state, commitment=Processed)
        if resp.value is None:
            return None
        parsed_data = CLMM_POOL_STATE_LAYOUT.parse(bytes(resp.value.data))

        tick_spacing = int(parsed_data.tick_spacing)
        tick_current = int(parsed_data.tick_current)
        array_size = 60

        start_index = calculate_start_index(tick_current, tick_spacing)
        if zero_for_one:
            prev_index = start_index - (tick_spacing * array_size)
            additional_index = prev_index - (tick_spacing * array_size)
        else:
            prev_index = start_index + (tick_spacing * array_size)
            additional_index = prev_index + (tick_spacing * array_size)

        current_tick_array = get_pda_tick_array_address(pool_state, start_index)
        prev_tick_array = get_pda_tick_array_address(pool_state, prev_index)
        additional_tick_array = get_pda_tick_array_address(pool_state, additional_index)
        bitmap_extension = get_pda_tick_array_bitmap_extension(pool_state)

        pool_keys = ClmmPoolKeys(
            pool_state=pool_state,
            amm_config=Pubkey.from_bytes(parsed_data.amm_config),
            owner=Pubkey.from_bytes(parsed_data.owner),
            token_mint_0=Pubkey.from_bytes(parsed_data.token_mint_0),
            token_mint_1=Pubkey.from_bytes(parsed_data.token_mint_1),
            token_vault_0=Pubkey.from_bytes(parsed_data.token_vault_0),
            token_vault_1=Pubkey.from_bytes(parsed_data.token_vault_1),
            observation_key=Pubkey.from_bytes(parsed_data.observation_key),
            current_tick_array=current_tick_array,
            prev_tick_array=prev_tick_array,
            additional_tick_array=additional_tick_array,
            bitmap_extension=bitmap_extension,
            mint_decimals_0=parsed_data.mint_decimals_0,
            mint_decimals_1=parsed_data.mint_decimals_1,
            tick_spacing=parsed_data.tick_spacing,
            liquidity=parsed_data.liquidity,
            sqrt_price_x64=parsed_data.sqrt_price_x64,
            tick_current=parsed_data.tick_current,
            observation_index=parsed_data.observation_index,
            observation_update_duration=parsed_data.observation_update_duration,
            fee_growth_global_0_x64=parsed_data.fee_growth_global_0_x64,
            fee_growth_global_1_x64=parsed_data.fee_growth_global_1_x64,
            protocol_fees_token_0=parsed_data.protocol_fees_token_0,
            protocol_fees_token_1=parsed_data.protocol_fees_token_1,
            swap_in_amount_token_0=parsed_data.swap_in_amount_token_0,
            swap_out_amount_token_1=parsed_data.swap_out_amount_token_1,
            swap_in_amount_token_1=parsed_data.swap_in_amount_token_1,
            swap_out_amount_token_0=parsed_data.swap_out_amount_token_0,
            status=parsed_data.status,
            total_fees_token_0=parsed_data.total_fees_token_0,
            total_fees_claimed_token_0=parsed_data.total_fees_claimed_token_0,
            total_fees_token_1=parsed_data.total_fees_token_1,
            total_fees_claimed_token_1=parsed_data.total_fees_claimed_token_1,
            fund_fees_token_0=parsed_data.fund_fees_token_0,
            fund_fees_token_1=parsed_data.fund_fees_token_1,
        )

        return pool_keys

    except Exception as e:
        print(f"Error fetching pool keys: {e}")
        return None


def make_amm_v4_swap_instruction(
    amount_in: int,
    minimum_amount_out: int,
    token_account_in: Pubkey,
    token_account_out: Pubkey,
    accounts: AmmV4PoolKeys,
    owner: Pubkey,
) -> Instruction:
    # PREF: 区分spl token与token 2022的program id
    keys = [
        AccountMeta(pubkey=accounts.token_program_id, is_signer=False, is_writable=False),
        AccountMeta(pubkey=accounts.amm_id, is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts.ray_authority_v4, is_signer=False, is_writable=False),
        AccountMeta(pubkey=accounts.open_orders, is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts.target_orders, is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts.base_vault, is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts.quote_vault, is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts.open_book_program, is_signer=False, is_writable=False),
        AccountMeta(pubkey=accounts.market_id, is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts.bids, is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts.asks, is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts.event_queue, is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts.market_base_vault, is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts.market_quote_vault, is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts.market_authority, is_signer=False, is_writable=False),
        AccountMeta(pubkey=token_account_in, is_signer=False, is_writable=True),
        AccountMeta(pubkey=token_account_out, is_signer=False, is_writable=True),
        AccountMeta(pubkey=owner, is_signer=True, is_writable=False),
    ]

    data = bytearray()
    discriminator = 9
    data.extend(struct.pack("<B", discriminator))
    data.extend(struct.pack("<Q", amount_in))
    data.extend(struct.pack("<Q", minimum_amount_out))
    swap_instruction = Instruction(RAYDIUM_AMM_V4, bytes(data), keys)

    return swap_instruction


def make_cpmm_swap_instruction(
    amount_in: int,
    minimum_amount_out: int,
    token_account_in: Pubkey,
    token_account_out: Pubkey,
    accounts: CpmmPoolKeys,
    owner: Pubkey,
    action: DIRECTION,
) -> Instruction:
    if action == DIRECTION.BUY:
        input_vault = accounts.token_0_vault
        output_vault = accounts.token_1_vault
        input_token_program = accounts.token_0_program
        output_token_program = accounts.token_1_program
        input_token_mint = accounts.token_0_mint
        output_token_mint = accounts.token_1_mint
    elif action == DIRECTION.SELL:
        input_vault = accounts.token_1_vault
        output_vault = accounts.token_0_vault
        input_token_program = accounts.token_1_program
        output_token_program = accounts.token_0_program
        input_token_mint = accounts.token_1_mint
        output_token_mint = accounts.token_0_mint

    keys = [
        AccountMeta(pubkey=owner, is_signer=True, is_writable=True),
        AccountMeta(pubkey=accounts.raydium_vault_auth_2, is_signer=False, is_writable=False),
        AccountMeta(pubkey=accounts.amm_config, is_signer=False, is_writable=False),
        AccountMeta(pubkey=accounts.pool_state, is_signer=False, is_writable=True),
        AccountMeta(pubkey=token_account_in, is_signer=False, is_writable=True),
        AccountMeta(pubkey=token_account_out, is_signer=False, is_writable=True),
        AccountMeta(pubkey=input_vault, is_signer=False, is_writable=True),
        AccountMeta(pubkey=output_vault, is_signer=False, is_writable=True),
        AccountMeta(pubkey=input_token_program, is_signer=False, is_writable=False),
        AccountMeta(pubkey=output_token_program, is_signer=False, is_writable=False),
        AccountMeta(pubkey=input_token_mint, is_signer=False, is_writable=False),
        AccountMeta(pubkey=output_token_mint, is_signer=False, is_writable=False),
        AccountMeta(pubkey=accounts.observation_key, is_signer=False, is_writable=True),
    ]

    data = bytearray()
    data.extend(bytes.fromhex("8fbe5adac41e33de"))
    data.extend(struct.pack("<Q", amount_in))
    data.extend(struct.pack("<Q", minimum_amount_out))
    swap_instruction = Instruction(RAYDIUM_CPMM, bytes(data), keys)

    return swap_instruction


def make_clmm_swap_instruction(
    amount: int,
    token_account_in: Pubkey,
    token_account_out: Pubkey,
    accounts: ClmmPoolKeys,
    owner: Pubkey,
    action: DIRECTION,
) -> Instruction:
    if action == DIRECTION.BUY:
        input_vault = accounts.token_vault_0
        output_vault = accounts.token_vault_1
    elif action == DIRECTION.SELL:
        input_vault = accounts.token_vault_1
        output_vault = accounts.token_vault_0
    # PREF: 区分spl token与token 2022的program id
    keys = [
        AccountMeta(pubkey=owner, is_signer=True, is_writable=True),
        AccountMeta(pubkey=accounts.amm_config, is_signer=False, is_writable=False),
        AccountMeta(pubkey=accounts.pool_state, is_signer=False, is_writable=True),
        AccountMeta(pubkey=token_account_in, is_signer=False, is_writable=True),
        AccountMeta(pubkey=token_account_out, is_signer=False, is_writable=True),
        AccountMeta(pubkey=input_vault, is_signer=False, is_writable=True),
        AccountMeta(pubkey=output_vault, is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts.observation_key, is_signer=False, is_writable=True),
        AccountMeta(pubkey=TOKEN_PROGRAM_ID, is_signer=False, is_writable=False),
        AccountMeta(pubkey=accounts.current_tick_array, is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts.bitmap_extension, is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts.prev_tick_array, is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts.additional_tick_array, is_signer=False, is_writable=True),
    ]

    data = bytearray()
    data.extend(bytes.fromhex("f8c69e91e17587c8"))
    data.extend(struct.pack("<Q", amount))
    data.extend(struct.pack("<Q", 0))
    data.extend((0).to_bytes(16, byteorder="little"))
    data.extend(struct.pack("<?", True))
    swap_instruction = Instruction(RAYDIUM_CLMM, bytes(data), keys)

    return swap_instruction


async def get_amm_v4_reserves(pool_keys: AmmV4PoolKeys) -> tuple:
    quote_vault = pool_keys.quote_vault
    quote_decimal = pool_keys.quote_decimals
    quote_mint = pool_keys.quote_mint

    base_vault = pool_keys.base_vault
    base_decimal = pool_keys.base_decimals
    base_mint = pool_keys.base_mint

    client = get_async_client()
    balances_response = await client.get_multiple_accounts_json_parsed(
        [quote_vault, base_vault], Processed
    )
    balances = balances_response.value

    balances_response = await client.get_multiple_accounts_json_parsed(
        [quote_vault, base_vault], Processed
    )
    balances = balances_response.value

    try:
        quote_account = balances[0]
        base_account = balances[1]
        quote_account_balance = quote_account.data.parsed["info"]["tokenAmount"][  # type: ignore
            "uiAmount"
        ]
        base_account_balance = base_account.data.parsed["info"]["tokenAmount"][  # type: ignore
            "uiAmount"
        ]
    except Exception as e:
        raise ValueError(f"Error occurred: {e}")

    if quote_account_balance is None or base_account_balance is None:
        raise ValueError("Error: One of the account balances is None.")

    if base_mint == WSOL:
        base_reserve = quote_account_balance
        quote_reserve = base_account_balance
        token_decimal = quote_decimal
    else:
        base_reserve = base_account_balance
        quote_reserve = quote_account_balance
        token_decimal = base_decimal

    return base_reserve, quote_reserve, token_decimal


async def get_cpmm_reserves(pool_keys: CpmmPoolKeys):
    quote_vault = pool_keys.token_0_vault
    quote_decimal = pool_keys.mint_0_decimals
    quote_mint = pool_keys.token_0_mint

    base_vault = pool_keys.token_1_vault
    base_decimal = pool_keys.mint_1_decimals
    base_mint = pool_keys.token_1_mint

    protocol_fees_token_0 = pool_keys.protocol_fees_token_0 / (10**quote_decimal)
    fund_fees_token_0 = pool_keys.fund_fees_token_0 / (10**quote_decimal)
    protocol_fees_token_1 = pool_keys.protocol_fees_token_1 / (10**base_decimal)
    fund_fees_token_1 = pool_keys.fund_fees_token_1 / (10**base_decimal)

    client = get_async_client()

    balances_response = await client.get_multiple_accounts_json_parsed(
        [quote_vault, base_vault], Processed
    )
    balances = balances_response.value

    if balances is None:
        return None, None, None

    try:
        quote_account = balances[0]
        base_account = balances[1]
        quote_account_balance = quote_account.data.parsed["info"]["tokenAmount"][  # type: ignore
            "uiAmount"
        ]
        base_account_balance = base_account.data.parsed["info"]["tokenAmount"][  # type: ignore
            "uiAmount"
        ]
    except Exception as e:
        print(f"Error occurred: {e}")
        return None, None, None

    if quote_account_balance is None or base_account_balance is None:
        print("Error: One of the account balances is None.")
        return None, None, None

    if base_mint == WSOL:
        base_reserve = quote_account_balance - (protocol_fees_token_0 + fund_fees_token_0)
        quote_reserve = base_account_balance - (protocol_fees_token_1 + fund_fees_token_1)
        token_decimal = quote_decimal
    else:
        base_reserve = base_account_balance - (protocol_fees_token_1 + fund_fees_token_1)
        quote_reserve = quote_account_balance - (protocol_fees_token_0 + fund_fees_token_0)
        token_decimal = base_decimal

    print(f"Base Mint: {base_mint} | Quote Mint: {quote_mint}")
    print(
        f"Base Reserve: {base_reserve} | Quote Reserve: {quote_reserve} | Token Decimal: {token_decimal}"
    )
    return base_reserve, quote_reserve, token_decimal


async def get_clmm_reserves(pool_keys: ClmmPoolKeys):
    quote_vault = pool_keys.token_vault_0
    quote_decimal = pool_keys.mint_decimals_0
    quote_mint = pool_keys.token_mint_0

    base_vault = pool_keys.token_vault_1
    base_decimal = pool_keys.mint_decimals_1
    base_mint = pool_keys.token_mint_1

    protocol_fees_token_0 = pool_keys.protocol_fees_token_0 / (10**quote_decimal)
    fund_fees_token_0 = pool_keys.fund_fees_token_0 / (10**quote_decimal)
    protocol_fees_token_1 = pool_keys.protocol_fees_token_1 / (10**base_decimal)
    fund_fees_token_1 = pool_keys.fund_fees_token_1 / (10**base_decimal)

    client = get_async_client()
    balances_response = await client.get_multiple_accounts_json_parsed(
        [quote_vault, base_vault], Processed
    )
    balances = balances_response.value
    if balances is None:
        return None, None, None

    try:
        quote_account = balances[0]
        base_account = balances[1]
        quote_account_balance = quote_account.data.parsed["info"]["tokenAmount"][  # type: ignore
            "uiAmount"
        ]
        base_account_balance = base_account.data.parsed["info"]["tokenAmount"][  # type: ignore
            "uiAmount"
        ]
    except Exception as e:
        print(f"Error occurred: {e}")
        return None, None, None

    if quote_account_balance is None or base_account_balance is None:
        print("Error: One of the account balances is None.")
        return None, None, None

    if base_mint == WSOL:
        base_reserve = quote_account_balance - (protocol_fees_token_0 + fund_fees_token_0)
        quote_reserve = base_account_balance - (protocol_fees_token_1 + fund_fees_token_1)
        token_decimal = quote_decimal
    else:
        base_reserve = base_account_balance - (protocol_fees_token_1 + fund_fees_token_1)
        quote_reserve = quote_account_balance - (protocol_fees_token_0 + fund_fees_token_0)
        token_decimal = base_decimal

    print(f"Base Mint: {base_mint} | Quote Mint: {quote_mint}")
    print(
        f"Base Reserve: {base_reserve} | Quote Reserve: {quote_reserve} | Token Decimal: {token_decimal}"
    )
    return base_reserve, quote_reserve, token_decimal


async def fetch_pair_address_from_rpc(
    program_id: Pubkey,
    token_mint: str,
    quote_offset: int,
    base_offset: int,
    data_length: int,
) -> list:
    client = get_async_client()

    async def fetch_pair(base_mint: str, quote_mint: str) -> list:
        memcmp_filter_base = MemcmpOpts(offset=quote_offset, bytes=quote_mint)
        memcmp_filter_quote = MemcmpOpts(offset=base_offset, bytes=base_mint)
        try:
            print(f"Fetching pair addresses for base_mint: {base_mint}, quote_mint: {quote_mint}")
            response = await client.get_program_accounts(
                program_id,
                commitment=Processed,
                filters=[data_length, memcmp_filter_base, memcmp_filter_quote],
            )
            accounts = response.value
            if accounts:
                print(f"Found {len(accounts)} matching AMM account(s).")
                return [account.pubkey.__str__() for account in accounts]
            else:
                print("No matching AMM accounts found.")
        except Exception as e:
            print(f"Error fetching AMM pair addresses: {e}")
        return []

    pair_addresses = await fetch_pair(token_mint, DEFAULT_QUOTE_MINT)

    if not pair_addresses:
        print("Retrying with reversed base and quote mints...")
        pair_addresses = await fetch_pair(DEFAULT_QUOTE_MINT, token_mint)

    return pair_addresses


async def get_amm_v4_pair_from_rpc(token_mint: str) -> list:
    return await fetch_pair_address_from_rpc(
        program_id=RAYDIUM_AMM_V4,
        token_mint=token_mint,
        quote_offset=400,
        base_offset=432,
        data_length=752,
    )


async def get_cpmm_pair_address_from_rpc(token_mint: str) -> list:
    return await fetch_pair_address_from_rpc(
        program_id=RAYDIUM_CPMM,
        token_mint=token_mint,
        quote_offset=168,
        base_offset=200,
        data_length=637,
    )


async def get_clmm_pair_address_from_rpc(token_mint: str) -> list:
    return await fetch_pair_address_from_rpc(
        program_id=RAYDIUM_CLMM,
        token_mint=token_mint,
        quote_offset=73,
        base_offset=105,
        data_length=1544,
    )
