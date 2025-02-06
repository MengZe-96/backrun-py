import asyncio
import time
from typing import Any, Callable, Coroutine, Generic, Protocol, TypeVar

import aioredis
from loguru import logger
from typing_extensions import Self


class DataProtocol(Protocol):
    def to_json(self) -> str: ...

    @classmethod
    def from_json(cls, json_str: str) -> "Self": ...


T = TypeVar("T", bound=DataProtocol)
MAX_PROCESS_TIME = 15


class Producer(Generic[T]):
    def __init__(self, redis_client: aioredis.Redis, channel: str) -> None:
        self.redis = redis_client
        self.channel = channel

    async def produce(self, data: T) -> None:
        """Produces a swap event to Redis Stream.

        Args:
            swap_event: Swap event data as string
        """
        await self.redis.xadd(
            name=self.channel,
            fields={"data": data.to_json(), "timestamp": int(time.time())},
            maxlen=10000,  # Keep last 10k events
        )


class Consumer(Generic[T]):

    def __init__(
        self,
        channel: str,
        data_class: type[T],
        redis_client: aioredis.Redis,
        consumer_group: str,
        consumer_name: str,
        batch_size: int = 10,
        poll_timeout_ms: int = 5000,
        max_retries: int = 3,
        dead_letter_channel: str | None = None,
    ) -> None:
        """Initialize the transaction event consumer.

        Args:
            redis_client: Redis client instance
            consumer_group: Name of the consumer group
            consumer_name: Unique name for this consumer instance
            batch_size: Number of events to process in one batch
            poll_timeout_ms: Timeout in milliseconds for blocking read
            max_retries: Maximum number of retries for failed messages
            dead_letter_channel: Channel name for dead letter queue
        """
        self.channel = channel
        self.data_class = data_class
        self.redis = redis_client
        self.consumer_group = consumer_group
        self.consumer_name = consumer_name
        self.batch_size = batch_size
        self.poll_timeout_ms = poll_timeout_ms
        self.max_retries = max_retries
        self.dead_letter_channel = dead_letter_channel or f"{channel}:dead"
        self.is_running = False
        self.callback: Callable[[T], Coroutine[Any, Any, None]] | None = None

    async def setup(self) -> None:
        """Setup the consumer group if it doesn't exist."""
        try:
            # Create consumer group if not exists
            # Use $ as start ID to only process new messages
            await self.redis.xgroup_create(
                name=self.channel,
                groupname=self.consumer_group,
                mkstream=True,
                id="$",
            )
        except aioredis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise
            logger.info(f"Consumer group {self.consumer_group} already exists")

            # 检查是否需要重置消费者组位置
            stream_info = await self.redis.xinfo_stream(self.channel)
            if stream_info["length"] > 0:  # 如果队列中有消息
                group_info = await self.redis.xinfo_groups(self.channel)
                for group in group_info:
                    if group["name"] == self.consumer_group:
                        if group["pending"] == 0:  # 如果没有待处理的消息
                            try:
                                # 删除旧的消费者组
                                await self.redis.xgroup_destroy(
                                    self.channel, self.consumer_group
                                )
                                # 创建新的消费者组，从头开始消费
                                await self.redis.xgroup_create(
                                    name=self.channel,
                                    groupname=self.consumer_group,
                                    mkstream=True,
                                    id="0",  # 从头开始
                                )
                                logger.info(
                                    f"Reset consumer group {self.consumer_group} to start from beginning"
                                )
                            except Exception as e:
                                logger.error(f"Failed to reset consumer group: {e}")
                        break

    def register_callback(
        self, callback: Callable[[T], Coroutine[Any, Any, None]]
    ) -> None:
        """Register a callback function to process events.

        Args:
            callback: Function that takes a dictionary of event data and processes it
        """
        self.callback = callback

    async def process_pending(self) -> None:
        """Process any pending messages for this consumer."""
        logger.info(f"Processing pending messages for {self.consumer_name}")
        try:
            # 首先检查流中的所有消息
            stream_info = await self.redis.xinfo_stream(self.channel)
            logger.info(
                f"Stream info - length: {stream_info['length']}, groups: {stream_info['groups']}, last_id: {stream_info['last-generated-id']}"
            )

            # 检查消费者组信息
            group_info = await self.redis.xinfo_groups(self.channel)
            for group in group_info:
                logger.info(
                    f"Group {group['name']} - pending: {group['pending']}, consumers: {group['consumers']}, last_delivered_id: {group['last-delivered-id']}"
                )

            # 检查消费者信息
            consumers_info = await self.redis.xinfo_consumers(
                self.channel, self.consumer_group
            )
            for consumer in consumers_info:
                logger.info(
                    f"Consumer {consumer['name']} - pending: {consumer['pending']}, idle: {consumer['idle']}"
                )

            # 读取待处理的消息
            pending = await self.redis.xreadgroup(
                groupname=self.consumer_group,
                consumername=self.consumer_name,
                streams={self.channel: "0"},  # 0 means all pending messages
                count=self.batch_size,
            )

            logger.info(
                f"Found pending messages: {pending is not None and len(pending) > 0}"
            )
            if pending:
                for stream_name, messages in pending:
                    logger.info(
                        f"Processing {len(messages)} messages from stream {stream_name}"
                    )
                    for message_id, fields in messages:
                        logger.info(f"Processing pending message {message_id}")
                        logger.debug(f"Message fields: {fields}")
                        try:
                            await self._process_message(message_id, fields)
                        except Exception as e:
                            logger.error(
                                f"Error processing pending message {message_id}: {e}"
                            )
            else:
                # 如果没有待处理的消息，检查是否有新消息
                new_messages = await self.redis.xread(
                    streams={self.channel: "0-0"}, count=1  # 从头开始读取所有消息
                )
                if new_messages:
                    logger.info("Found unassigned messages in the stream")
                    for stream_name, messages in new_messages:
                        logger.info(
                            f"Stream {stream_name} has {len(messages)} unassigned messages"
                        )
                else:
                    logger.info("No messages found in the stream")

        except Exception as e:
            logger.error(f"Error processing pending messages: {e}")

    async def _process_message(self, message_id: str, fields: dict) -> None:
        """Process a single message and acknowledge it.

        Args:
            message_id: ID of the message in Redis Stream
            fields: Message fields containing the event data
        """
        logger.debug(f"Processing message {message_id}: {fields}")
        retry_count = int(fields.get("retry_count", 0))
        try:
            timestamp = float(fields.get("timestamp", 0))
            if time.time() - timestamp > MAX_PROCESS_TIME:
                logger.warning(
                    f"Message {message_id} is too old, moving to dead letter queue. Timestamp: {timestamp}"
                )
                await self._move_to_dead_letter(message_id, fields, "message_timeout")
                return

            if self.callback is not None:
                data = self.data_class.from_json(fields["data"])
                await self.callback(data)

            # Acknowledge the message on successful processing
            await self.redis.xack(self.channel, self.consumer_group, message_id)

        except Exception as e:
            logger.exception(f"Error processing message {message_id}: {e}")

            if retry_count >= self.max_retries:
                logger.error(
                    f"Message {message_id} exceeded max retries, moving to dead letter queue"
                )
                await self._move_to_dead_letter(message_id, fields, str(e))
                return

            # Update retry count and add back to stream
            fields["retry_count"] = str(retry_count + 1)
            fields["last_error"] = str(e)
            fields["last_retry_time"] = str(time.time())

            # Add back to stream for retry
            await self.redis.xadd(self.channel, fields)
            # Acknowledge the original message
            await self.redis.xack(self.channel, self.consumer_group, message_id)

    async def _move_to_dead_letter(
        self, message_id: str, fields: dict, error: str
    ) -> None:
        """Move a message to the dead letter queue.

        Args:
            message_id: Original message ID
            fields: Message fields
            error: Error message
        """
        fields["original_id"] = message_id
        fields["error"] = error
        fields["moved_to_dlq_at"] = str(time.time())

        try:
            # Add to dead letter queue
            await self.redis.xadd(self.dead_letter_channel, fields)
            # Acknowledge the original message
            await self.redis.xack(self.channel, self.consumer_group, message_id)
            # Delete the message from original stream
            await self.redis.xdel(self.channel, message_id)
            logger.info(
                f"Message {message_id} moved to dead letter queue and deleted from original stream"
            )
        except Exception as e:
            logger.error(f"Error moving message {message_id} to dead letter queue: {e}")
            raise

    async def start(self) -> None:
        """Start consuming messages from the stream."""
        if not self.callback:
            raise ValueError("No callback registered. Call register_callback first.")

        await self.setup()
        self.is_running = True

        # First process any pending messages
        await self.process_pending()

        # Then start processing new messages
        while self.is_running:
            try:
                # Read new messages
                messages = await self.redis.xreadgroup(
                    groupname=self.consumer_group,
                    consumername=self.consumer_name,
                    streams={self.channel: ">"},  # > means new messages only
                    count=self.batch_size,
                    block=self.poll_timeout_ms,
                )

                if not messages:
                    continue

                logger.info(
                    f"Processing {len(messages)} messages from stream {messages[0][0]}"
                )
                for stream, stream_messages in messages:
                    for message_id, fields in stream_messages:
                        await self._process_message(message_id, fields)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error reading from stream: {e}")
                await asyncio.sleep(1)  # Avoid tight loop on errors

    def stop(self) -> None:
        """Stop consuming messages."""
        self.is_running = False


class ConsumerProducerBuilder(Generic[T]):
    def __init__(
        self,
        channel: str,
        data_class: type[T],
        redis_client: aioredis.Redis,
    ) -> None:
        self.redis = redis_client
        self.channel = channel
        self.data_class = data_class

    def build_consumer_class(
        self,
        consumer_group: str,
        consumer_name: str,
        batch_size: int = 10,
        poll_timeout_ms: int = 5000,
        max_retries: int = 3,
        dead_letter_channel: str | None = None,
    ) -> Consumer[T]:
        return Consumer(
            channel=self.channel,
            data_class=self.data_class,
            redis_client=self.redis,
            consumer_group=consumer_group,
            consumer_name=consumer_name,
            batch_size=batch_size,
            poll_timeout_ms=poll_timeout_ms,
            max_retries=max_retries,
            dead_letter_channel=dead_letter_channel,
        )

    # def build_producer(self) -> Producer[T]:
    #     return Producer(redis_client=self.redis, channel=self.channel)
