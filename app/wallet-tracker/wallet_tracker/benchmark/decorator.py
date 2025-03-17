import time
from contextlib import asynccontextmanager

from solbot_common.log import logger

from wallet_tracker.benchmark.service import benchmark_service


async def _mark_start_fetch(tx_hash: str):
    data = {"tx_hash": tx_hash, "step": "tx_start_fetch", "timestamp": time.time()}
    await benchmark_service.add(data)
    return data


async def _mark_end_fetch(tx_hash: str):
    data = {"tx_hash": tx_hash, "step": "tx_end_fetch", "timestamp": time.time()}
    await benchmark_service.add(data)
    return data


async def _mark_start_parse(tx_hash: str):
    data = {"tx_hash": tx_hash, "step": "tx_start_parse", "timestamp": time.time()}
    await benchmark_service.add(data)
    return data


async def _mark_end_parse(tx_hash: str):
    data = {"tx_hash": tx_hash, "step": "tx_end_parse", "timestamp": time.time()}
    await benchmark_service.add(data)
    return data


async def init(tx_hash: str):
    await benchmark_service.add(
        {"tx_hash": tx_hash, "step": "tx_detected", "timestamp": time.time()}
    )


async def record_block_time(tx_hash: str, block_time: int):
    await benchmark_service.add({"tx_hash": tx_hash, "step": "block_time", "timestamp": block_time})


async def show_timeline(tx_hash: str):
    timeline = await benchmark_service.get_timeline(tx_hash)

    def _calc_elapsed(start: str, end: str) -> float | None:
        start_time = timeline.get(start)
        end_time = timeline.get(end)
        if start_time is not None and end_time is not None:
            return float(end_time) - float(start_time)
        else:
            return None

    # 区间产生时间点 到 发现该交易的时间点，耗时：
    detect_elapsed = _calc_elapsed("block_time", "tx_detected")

    # 开始抓取该交易时间点 到 结束抓取该交易的时间点，耗时
    fetch_tx_detail_elapsed = _calc_elapsed("tx_start_fetch", "tx_end_fetch")

    # 解析耗时
    parse_elapsed = _calc_elapsed("tx_start_parse", "tx_end_parse")

    # 总耗时
    total_elapsed = _calc_elapsed("block_time", "tx_end_parse")

    logger.info(
        f"\n Transaction: {tx_hash}"
        f"\n 发现交易耗时: {detect_elapsed}"
        f"\n 获取交易详情耗时: {fetch_tx_detail_elapsed}"
        f"\n 解析交易耗时: {parse_elapsed}"
        f"\n 总耗时: {total_elapsed}"
    )


@asynccontextmanager
async def with_fetch_tx(tx_hash: str):
    data = await _mark_start_fetch(tx_hash)
    start_time = data["timestamp"]
    logger.info(f"Fetching transaction: {tx_hash}, start_time: {start_time}")
    try:
        yield
    finally:
        data = await _mark_end_fetch(tx_hash)
        end_time = data["timestamp"]
        logger.info(
            f"Fetching transaction: {tx_hash}, end_time: {end_time}, elapsed: {end_time - start_time}"
        )


@asynccontextmanager
async def with_parse_tx(tx_hash: str):
    data = await _mark_start_parse(tx_hash)
    start_time = data["timestamp"]
    # logger.info(f"Parsing transaction: {tx_hash}, start_time: {start_time}")
    try:
        yield
    finally:
        data = await _mark_end_parse(tx_hash)
        end_time = data["timestamp"]
        logger.info(
            f"Parsing transaction: {tx_hash}, end_time: {end_time}, elapsed: {end_time - start_time}"
        )
