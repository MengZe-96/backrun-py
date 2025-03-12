from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed
# from solana.rpc.types import TokenAccountOpts
# from solbot_common.constants import TOKEN_PROGRAM_ID
from solbot_common.layouts.mint_account import MintAccount
from solbot_common.layouts.token_account import TokenAccount
from solders.pubkey import Pubkey  # type: ignore


async def get_wallet_tokens(address: Pubkey, client: AsyncClient) -> list[TokenAccount]:
    response = await client.get_token_accounts_by_owner(
        address,
        # opts=TokenAccountOpts(
        #     program_id=TOKEN_PROGRAM_ID,
        # ),
        commitment=Confirmed,
    )
    accounts = response.value
    token_accounts = []
    for account in accounts:
        data = account.account.data
        token_account = TokenAccount.from_buffer(data)
        token_accounts.append(token_account)

    return token_accounts


async def get_mint_account(mint: Pubkey, client: AsyncClient) -> MintAccount | None:
    response = await client.get_account_info(mint)
    account = response.value
    if account is None:
        return None
    mint_account = MintAccount.from_buffer(account.data)
    return mint_account
