import asyncio
import logging
import signal
import sys

from src.core import Core
from src.adapters.text_input_adapter import TextInputAdapter
from src.adapters.timer_tick_adapter import TimerTickAdapter


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger(__name__)


async def main():
    """
    Core v0 演示入口：
    - 启动 Core 与 adapters
    - 支持 Ctrl+C 优雅退出
    """
    # 创建 Core
    core = Core(
        bus_maxsize=1000,
        inbox_maxsize=256,
        system_session_key="system",
        message_routing="user",
        enable_system_fanout=False,  # v0 暂不开启扇出（可改为 True 测试）
        # idle_ttl_seconds = 3,  # session 空闲多久后被标记为 idle（仅影响 metrics 和状态，不会自动删除 session）
        # gc_sweep_interval_seconds = 1,  # session GC 扫描间隔（仅影响 metrics 和状态，不会自动删除 session）
        # enable_session_gc = True,  # 是否启用 session GC（仅影响 metrics 和状态，不会自动删除 session）
    )

    # 添加 adapters
    text_adapter = TextInputAdapter(name="text_input", default_session_key="dm:local")
    timer_adapter = TimerTickAdapter(
        name="timer",
        schedule_id="heartbeat",
        session_key="system",
    )

    core.add_adapter(text_adapter)
    core.add_adapter(timer_adapter)

    # 演示：启动后自动投递几条消息
    async def demo_input():
        """演示：模拟一些输入"""
        await asyncio.sleep(0.5)  # 等待 Core 启动

        # 投递几条用户消息
        text_adapter.ingest_text("Hello!", actor_id="alice", session_key="dm:alice")
        text_adapter.ingest_text("Hi there", actor_id="bob", session_key="dm:bob")
        text_adapter.ingest_text("How are you?", actor_id="alice", session_key="dm:alice")

        # 触发 timer tick（会进入 system session）
        for i in range(3):
            await asyncio.sleep(1.0)
            timer_adapter.trigger(reason=f"demo_tick_{i}")

    demo_task = asyncio.create_task(demo_input())

    # 运行 Core
    try:
        logger.info("Starting Core v0...")
        await core.run_forever()
    except KeyboardInterrupt:
        logger.info("Received KeyboardInterrupt")
    finally:
        demo_task.cancel()
        await asyncio.gather(demo_task, return_exceptions=True)
        logger.info("Main exit")


if __name__ == "__main__":
    # Windows 下支持 Ctrl+C
    if sys.platform == "win32":
        # ProactorEventLoop 在 Windows 上更好地处理信号
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
