"""
E2E CLI Demo - 真实系统端到端演示脚本

启动完整的 Core（InputBus/Router/Workers/Gate/ConfigProvider/SystemReflex）
通过 CLI 注入 Observation，观察系统处理链路

使用方式:
    uv run python tools/demo_e2e.py
"""

import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

# 将 src 目录加入 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 导入系统核心模块
from src.core import Core
from src.adapters.cli_adapter import CliInputAdapter
from src.gate.config import GateConfig
from src.gate.types import GateAction, GateContext
from src.schemas.observation import Observation


# 日志配置
logging.basicConfig(
    level=logging.WARNING,  # 降低系统日志噪音
    format="%(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class DemoObserver:
    """
    Demo 观测器 - 简化版
    主要通过 CliInputAdapter 打印关键节点日志
    """

    def __init__(self, enable_gate_trace: bool = False):
        self.enable_gate_trace = enable_gate_trace

    def log_section(self, title: str):
        """打印分隔符"""
        print(f"\n{'─' * 70}")
        print(f"  {title}")
        print(f"{'─' * 70}\n")


async def setup_core_with_cli(
    enable_gate_trace: bool = False,
    observer: Optional[DemoObserver] = None,
) -> Core:
    """
    设置带 CLI 适配器的 Core 实例

    参数：
    - enable_gate_trace: 是否启用 Gate trace hook
    - observer: DemoObserver 实例（用于日志）

    返回 Core 实例（已初始化但未启动）
    """
    if observer is None:
        observer = DemoObserver(enable_gate_trace=enable_gate_trace)

    # 创建 Core 实例
    core = Core()

    # 添加 CLI 适配器
    cli_adapter = CliInputAdapter(name="cli_input", source_kind="external")
    core.adapters.append(cli_adapter)

    print("[INIT] Core 实例化完成")
    print(f"[INIT] 启用 Gate Trace: {enable_gate_trace}")
    print(f"[INIT] Adapters: {[a.name for a in core.adapters]}")

    return core


async def run_demo_with_logging(
    core: Core,
    observer: DemoObserver,
    enable_gate_trace: bool = False,
    stop_event: Optional[asyncio.Event] = None,
) -> None:
    """
    运行 Demo - 启动 Core.run_forever() 任务并等待 stop_event

    参数：
    - core: Core 实例
    - observer: DemoObserver
    - enable_gate_trace: 是否启用 Gate trace
    - stop_event: 用于优雅关闭的 asyncio.Event

    流程：
    1. 启动 core.run_forever() 作为后台任务
    2. 等待 stop_event 被设置（由 /quit 触发）
    3. 取消 core 任务并等待完成
    4. 清理所有 tasks
    """
    if stop_event is None:
        stop_event = asyncio.Event()

    observer.log_section("🚀 启动 Core - 等待 CLI 输入")

    # 启动 core.run_forever() 作为后台任务
    core_task = asyncio.create_task(core.run_forever(), name="core_run")

    try:
        # 等待 stop_event（由 /quit 触发）
        await stop_event.wait()
        print("\n\n[DEMO] 收到停止信号，开始优雅关闭...")

    except KeyboardInterrupt:
        print("\n\n[DEMO] KeyboardInterrupt - 正在关闭...")
    except asyncio.CancelledError:
        print("\n\n[DEMO] CancelledError - 正在关闭...")

    finally:
        # 取消 core_task
        if not core_task.done():
            core_task.cancel()

        # 等待 core_task 完成（忽略 CancelledError）
        try:
            await core_task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Core task error: {e}")

        # 显式调用 shutdown（确保清理完成）
        try:
            await core.shutdown()
        except Exception as e:
            logger.warning(f"Error during shutdown: {e}")

        print("[DEMO] 核心系统已关闭")


async def main():
    """主入口"""
    print("\n")
    print("╔" + "=" * 68 + "╗")
    print("║" + " " * 68 + "║")
    print("║" + "  🎬 E2E Demo - 真实系统端到端演示".center(68) + "║")
    print("║" + " " * 68 + "║")
    print("╚" + "=" * 68 + "╝")
    print()

    # 创建 stop_event（用于优雅关闭）
    stop_event = asyncio.Event()

    # 创建 observer
    observer = DemoObserver(enable_gate_trace=False)

    # 设置 Core（传入 stop_event）
    core = await setup_core_with_cli(enable_gate_trace=False, observer=observer)

    # 将 stop_event 保存到 cli_adapter，以便 /quit 能触发它
    for adapter in core.adapters:
        if hasattr(adapter, 'set_stop_event'):
            adapter.set_stop_event(stop_event)

    # 运行 Demo（传入 stop_event）
    await run_demo_with_logging(core, observer, enable_gate_trace=False, stop_event=stop_event)


if __name__ == "__main__":
    asyncio.run(main())
