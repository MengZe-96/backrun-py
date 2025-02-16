import os
from typing import Tuple
from datetime import timedelta

from solders.hash import Hash  # type: ignore

from common.utils import get_async_client
import aioredis
from cache.auto.base import BaseAutoUpdateCache
from common.log import logger
import orjson as json

from db.redis import RedisClient


class BlockhashCache(BaseAutoUpdateCache):
    key = "blockhash"

    def __init__(self, redis: aioredis.Redis):
        self.client = get_async_client()
        self.redis = redis
        super().__init__(redis)

    @classmethod
    async def _get_latest_blockhash(cls) -> tuple[Hash, int]:
        resp = await get_async_client().get_latest_blockhash()
        return resp.value.blockhash, resp.value.last_valid_block_height

    async def _gen_new_value(self) -> str:
        _hash, _last_valid_block_height = await self._get_latest_blockhash()
        return json.dumps(
            {
                "blockhash": str(_hash),
                "last_valid_block_height": str(_last_valid_block_height),
            }
        ).decode("utf-8")

    @classmethod
    async def get(cls, redis: aioredis.Redis | None = None) -> Tuple[Hash, int]:
        """
        Get current blockhash and last valid block height
        Uses cached value if available
        """
        if os.getenv("PYTEST_CURRENT_TEST"):
            return await cls._get_latest_blockhash()

        redis = redis or RedisClient.get_instance()
        raw_cached_value = await redis.get(cls.key)
        if raw_cached_value is None:
            logger.warning("Blockhash cache not found, updating...")
            blockhash_cache = cls(redis)
            raw_cached_value = await blockhash_cache._gen_new_value()
            await redis.set(cls.key, raw_cached_value, ex=timedelta(seconds=30))
        cached_value = json.loads(raw_cached_value)
        return Hash.from_string(cached_value["blockhash"]), int(
            cached_value["last_valid_block_height"]
        )
