"""跟单交易通知"""

import aioredis

from common.types import SwapEvent

from .base import Consumer, Producer

NOTIFY_COPYTRADE_CHANNEL = "notify:copytrade"
MAX_PROCESS_TIME = 15  # s


class NotifyCopyTradeProducer(Producer[SwapEvent]):
    def __init__(self, redis_client: aioredis.Redis) -> None:
        super().__init__(redis_client=redis_client, channel=NOTIFY_COPYTRADE_CHANNEL)


class NotifyCopyTradeConsumer(Consumer[SwapEvent]):
    def __init__(
        self,
        redis_client: aioredis.Redis,
        consumer_group: str,
        consumer_name: str,
        batch_size: int = 10,
        poll_timeout_ms: int = 5000,
    ) -> None:
        super().__init__(
            channel=NOTIFY_COPYTRADE_CHANNEL,
            data_class=SwapEvent,
            redis_client=redis_client,
            consumer_group=consumer_group,
            consumer_name=consumer_name,
            batch_size=batch_size,
            poll_timeout_ms=poll_timeout_ms,
        )
