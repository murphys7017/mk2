import asyncio
import sys
from loguru import logger

from src.core import Core
from src.adapters.text_input_adapter import TextInputAdapter
from src.adapters.timer_tick_adapter import TimerTickAdapter


async def main():
    """
    Core v0 演示入口：
    - 启动 Core 与 adapters
    - 支持 Ctrl+C 优雅退出
    """
    logger.info("Main starting")

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
    text_adapter = TextInputAdapter()
    core.add_adapter(text_adapter)

    # 演示：启动后自动投递几条消息
    async def demo_input():
        """演示：模拟一些输入"""
        await asyncio.sleep(0.5)  # 等待 Core 启动
        actor_id = "demo_user"
        session_key = "dm:demo_user"
        while True:
            text = input(">:")
        

            # 投递几条用户消息
            text_adapter.ingest_text(text, actor_id=actor_id, session_key=session_key)


    demo_task = asyncio.create_task(demo_input())
    logger.info("Demo input task created")

    # 运行 Core
    try:
        logger.info("Core run loop starting")
        await core.run_forever()
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received in main()")
        pass
    finally:
        logger.info("Main shutting down")
        demo_task.cancel()
        await asyncio.gather(demo_task, return_exceptions=True)
        logger.info("Main stopped")


if __name__ == "__main__":
    # Configure loguru to output to stdout for better Windows compatibility
    logger.remove()  # Remove default stderr handler
    logger.add(sys.stdout, colorize=True, level="DEBUG")
    
    logger.info("Application starting")

    # Windows 下支持 Ctrl+C
    if sys.platform == "win32":
        # ProactorEventLoop 在 Windows 上更好地处理信号
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
