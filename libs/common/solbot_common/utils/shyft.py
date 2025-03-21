from typing import TypedDict
from solbot_common.config import settings
from solbot_common.log import logger
import httpx, asyncio


# "name": "BOOK OF MEME",
# "symbol": "BOME",
# "metadata_uri": "https://bafkreifi2rtjfhynuvm423e2655frhjeby3k6hiu64way4wlnehkffscfy.ipfs.nftstorage.link",
# "description": "https://eqvghohdoxismy2goa55mzpfknwetosy34xoqj3nawodbd3rueha.arweave.net/JCpjuON10SZjRnA71mXlU2xJuljfLugnbQWcMI9xoQ4",
# "image": "https://bafkreihztk5poge7f2lz6logfjmhc7h7u6shvgacoktnuezks5oblmieue.ipfs.nftstorage.link",
# "decimals": 6,
# "address": "ukHH6c7mMyiWCf1b9pnWe25TSpkDDt3H5pQZgZ74J82",
# "mint_authority": "",
# "freeze_authority": "",
# "current_supply": 68953239706.69019,
# "extensions": []
class TokenInfoDict(TypedDict):
    name: str
    symbol: str
    metadata_uri: str
    description: str
    image: str
    decimals: int
    address: str
    mint_authority: str
    freeze_authority: str
    current_supply: float
    extensions: list


class TokenInfoSummary(TypedDict):
    decimals: int
    name: str
    symbol: str
    image: str


class WalletToken(TypedDict):
    address: str
    balance: float
    associated_account: str
    info: TokenInfoSummary


class ShyftAPI:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, api_key: str = settings.api.shyft_api_key):
        self.api_key = api_key
        self.client = httpx.AsyncClient(
            base_url="https://api.shyft.to",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "x-api-key": api_key,
            },
        )

    async def get_balance(self, wallet: str) -> float:
        """Get the balance of a wallet."""
        response = await self.client.get(
            "/sol/v1/wallet/balance",
            params={
                "network": "mainnet-beta",
                "wallet": wallet,
            },
        )
        response.raise_for_status()
        js = response.json()
        if js["success"] is True:
            return js["result"]["balance"]
        raise ValueError(js["message"])

    async def get_token_balance(self, mint: str, wallet: str) -> tuple[float, int]:
        """获取代币账户余额

        Response:
            {
            "success": true,
            "message": "Token balance fetched successfully",
            "result": {
                "address": "GFUgXbMeDnLkhZaJS3nYFqunqkFNMRo9ukhyajeXpump",
                "balance": 47.702044,
                "associated_account": "4Y1ypoSop5JezbosNUqMqNvWoiBzhL5d1LFC2NCtE6Fq",
                "info": {
                "name": "Evan",
                "symbol": "EVAN",
                "image": "",
                "metadata_uri": "",
                "decimals": 6
                },
                "isFrozen": false
            }
            }

        Args:
            token_mint (str): 代币地址
            owner (str): 持有者地址

        Returns:
            (float, int): 代币账户余额，代币精度
        """
        response = await self.client.get(
            "/sol/v1/wallet/token_balance",
            params={
                "network": "mainnet-beta",
                "token": mint,
                "wallet": wallet,
            },
        )
        response.raise_for_status()
        js = response.json()
        if js["success"] is True:
            return js["result"]["balance"], js["result"]["info"]["decimals"]
        raise ValueError(js["message"])

    async def get_all_tokens(self, wallet: str) -> list[WalletToken]:
        """获取所有token

        {
          "address": "2FMB8JDMJUvqHw9HqoqSvXDAYQtiktt1R13p7dZwy16y",
          "balance": 0,
          "associated_account": "Gfs74SjqTGgNPzbgDyWvWYgy2i8TxDZEyRNGWdvUiHTQ",
          "info": {
            "decimals": 6,
            "name": "Cats with Thumbs",
            "symbol": "TCats",
            "image": "https://cf-ipfs.com/ipfs/QmS2VPtVGF1kVE54rsHMKgPSzgSqgzUaDLzGNZDdgR1tgR",
            "metadata_uri": ""
          }
        }

        Args:
            wallet (str): 钱包地址

        Raises:
            ValueError: 如果请求失败

        Returns:
            list[WalletToken]:  该钱包下的所有token
        """
        response = await self.client.get(
            "/sol/v1/wallet/all_tokens",
            params={
                "wallet": wallet,
                "network": "mainnet-beta",
            },
        )
        response.raise_for_status()
        js = response.json()
        if js["success"] is True:
            return js["result"]
        raise ValueError(js["message"])

    async def get_token_info(self, token_address: str) -> TokenInfoDict:
        response = await self.client.get(
            "/sol/v1/token/get_info",
            params={
                "network": "mainnet-beta",
                "token_address": token_address,
            },
        )
        response.raise_for_status()
        js = response.json()
        if js["success"] is True:
            return js["result"]
        raise ValueError(js["message"])

    async def is_transaction_swap(self, tx_hash: str) -> bool:
        response = await self.client.get(
            "/sol/v1/transaction/parsed",
            params={
                "network": "mainnet-beta",
                "txn_signature": tx_hash,
                "commitment": "confirmed",
            },
        )

        response.raise_for_status()
        js = response.json()
        if js["success"] is True and js["result"]["type"] == "SWAP":
            return True
        else:
            return False

    async def get_parsed_transaction(self, tx_hash: str) -> dict:
        """获取交易详情"""
        n = 5
        for i in range(n):
            try:
                response = await self.client.get(
                    "/sol/v1/transaction/parsed",
                    params={
                        "network": "mainnet-beta",
                        "txn_signature": tx_hash,
                    },
                )
                response.raise_for_status()
                js = response.json()
                if js["success"] is True:
                    return js["result"]
                else:
                    return None
            except Exception as _:
                logger.info(f"Retry {i}/{n} get parsed transaction via Shyft.")
                await asyncio.sleep(0.1)
        return None

            
