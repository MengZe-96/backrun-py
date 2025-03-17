import httpx

from solbot_common.config import settings


class HeliusAPI:
    def __init__(self):
        self.client = httpx.AsyncClient(
            base_url=settings.api.helius_api_base_url,
            params={
                "api-key": settings.api.helius_api_key,
                "commitment": "confirmed",
            },
        )
        self.rpc = httpx.AsyncClient(
            base_url='https://mainnet.helius-rpc.com',
            params={
                "api-key": settings.api.helius_api_key,
                # "commitment": "confirmed",
            })

    async def get_parsed_transaction(self, tx_hash: str) -> dict:
        """获取交易详情"""
        response = await self.client.post(
            "/transactions",
            json={
                "transactions": [tx_hash],
            },
        )
        response.raise_for_status()
        return response.json()
    
    async def get_token_info(self, mint: str) -> dict:
        """获取代币信息"""
        payload = {
            "jsonrpc": "2.0",
            "id": "zoopunkey",
            "method": "getAsset",
            "params": {"id": mint}
        }
        response = await self.rpc.post(url="",json=payload)
        response.raise_for_status()
        data = response.json()['result']
        return {
            'address': mint,
            'name': data['content']['metadata']['name'] if data['content']['metadata'] else None,
            'symbol': data['content']['metadata']['symbol'] if data['content']['metadata'] else None,
            'decimals': data['token_info']['decimals'],
            'token_program': data['token_info']['token_program']
        }
