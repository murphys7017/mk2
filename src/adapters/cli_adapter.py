"""
CLI Input Adapter - 交互式命令行适配器
支持通过 CLI 注入 Observation 到系统进行 E2E 测试
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from typing import Optional

from .interface.base import BaseAdapter
from ..input_bus import AsyncInputBus
from ..schemas.observation import (
    Observation,
    ObservationType,
    SourceKind,
    Actor,
    EvidenceRef,
    MessagePayload,
    AlertPayload,
    ControlPayload,
)


class CliInputAdapter(BaseAdapter):
    """
    CLI 输入适配器 - 支持交互式命令行注入 Observation

    支持命令：
    - <text>: 发送用户文本到当前 session
    - /session <key>: 切换当前 session_key
    - /tick: 注入 system tick
    - /alert <kind>: 注入 ALERT(kind) 到 system session
    - /suggest force_low_model=0|1 ttl=<sec>: 注入 CONTROL(tuning_suggestion)
    - /trace on|off: 开关 gate stage trace（如果 demo 支持）
    - /quit: 退出
    """

    def __init__(
        self,
        *,
        name: str = "cli_adapter",
        source_kind: SourceKind = SourceKind.EXTERNAL,
    ) -> None:
        super().__init__(name=name, source_kind=source_kind)
        self.current_session_key: str = "demo"
        self.trace_enabled: bool = False
        self._cli_task: Optional[asyncio.Task] = None
        self._stop_event: Optional[asyncio.Event] = None

    def set_stop_event(self, stop_event: asyncio.Event) -> None:
        """设置 stop_event（由 demo 主协程调用）"""
        self._stop_event = stop_event

    def _on_start(self) -> None:
        """启动 CLI 交互循环作为后台任务"""
        print("\n" + "=" * 60)
        print("🎬 E2E Demo CLI 已启动 (CLI Input Adapter)")
        print("=" * 60)
        print("支持的命令:")
        print("  <text>                              - 发送文本到当前 session")
        print("  /session <key>                      - 切换 session_key")
        print("  /tick                               - 注入 system tick")
        print("  /alert <kind>                       - 注入 ALERT (e.g., drop_burst)")
        print("  /suggest force_low_model=0|1 ttl=<sec> - 注入 tuning_suggestion")
        print("  /trace on|off                       - 开关 gate trace")
        print("  /quit                               - 退出")
        print("=" * 60 + "\n")

        # 创建后台 CLI 任务
        if self._cli_task is None or self._cli_task.done():
            self._cli_task = asyncio.create_task(self._cli_loop())

    def _on_stop(self) -> None:
        """停止 CLI 循环"""
        if self._cli_task and not self._cli_task.done():
            self._cli_task.cancel()

    async def _cli_loop(self) -> None:
        """交互式 CLI 循环（在后台运行）"""
        loop = asyncio.get_event_loop()

        while self._running:
            try:
                # 在线程池中运行阻塞的 input()
                user_input = await loop.run_in_executor(
                    None,
                    lambda: input(f"[session: {self.current_session_key}] > "),
                )

                if not user_input.strip():
                    continue

                await self._process_command(user_input)

            except EOFError:
                # Ctrl+D
                print("\n[CLI] EOF received, exiting...")
                break
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[CLI:ERROR] {e}")

    async def _process_command(self, user_input: str) -> None:
        """处理用户输入命令"""
        user_input = user_input.strip()

        if user_input.startswith("/quit"):
            print("[CLI] /quit detected, shutting down...")
            # 触发 stop_event（不用 sys.exit）
            if self._stop_event:
                self._stop_event.set()
            # 可选：注入一个 CONTROL observation 用于优雅关闭
            await self._inject_observation(
                obs_type=ObservationType.CONTROL,
                session_key="system",
                payload=ControlPayload(
                    kind="demo_stop",
                    data={"reason": "user_quit"},
                ),
            )
            # 给系统一点时间处理
            await asyncio.sleep(0.5)
            return

        elif user_input.startswith("/session "):
            new_session = user_input[9:].strip()
            if new_session:
                self.current_session_key = new_session
                print(f"[CLI] Switched to session: {self.current_session_key}")
            else:
                print("[CLI] Usage: /session <key>")

        elif user_input == "/tick":
            await self._inject_observation(
                obs_type=ObservationType.SCHEDULE,
                session_key="system",
                payload=None,
            )
            print("[CLI] Injected SCHEDULE (system tick) to system session")

        elif user_input.startswith("/alert "):
            alert_kind = user_input[7:].strip()
            if alert_kind:
                await self._inject_observation(
                    obs_type=ObservationType.ALERT,
                    session_key="system",
                    payload=AlertPayload(
                        alert_type=alert_kind,
                        severity="high",
                        message=f"User-injected alert: {alert_kind}",
                        data={"kind": alert_kind},
                    ),
                )
                print(f"[CLI] Injected ALERT: {alert_kind}")
            else:
                print("[CLI] Usage: /alert <kind>")

        elif user_input.startswith("/suggest "):
            suggestion = user_input[9:].strip()
            try:
                data = self._parse_suggest_params(suggestion)
                await self._inject_observation(
                    obs_type=ObservationType.CONTROL,
                    session_key="system",
                    payload=ControlPayload(
                        kind="tuning_suggestion",
                        data=data,
                    ),
                )
                print(f"[CLI] Injected CONTROL(tuning_suggestion): {data}")
            except ValueError as e:
                print(f"[CLI:ERROR] {e}")

        elif user_input.startswith("/trace "):
            trace_cmd = user_input[7:].strip()
            if trace_cmd == "on":
                self.trace_enabled = True
                print("[CLI] Gate trace enabled")
            elif trace_cmd == "off":
                self.trace_enabled = False
                print("[CLI] Gate trace disabled")
            else:
                print("[CLI] Usage: /trace on|off")

        else:
            # 普通文本 -> 发送到当前 session
            await self._inject_observation(
                obs_type=ObservationType.MESSAGE,
                session_key=self.current_session_key,
                payload=MessagePayload(
                    text=user_input,
                ),
            )
            print(f"[CLI] Sent message to session '{self.current_session_key}'")

    def _parse_suggest_params(self, params_str: str) -> dict:
        """
        解析 /suggest 的参数
        例如: "force_low_model=1 ttl=5"
        """
        result = {}
        parts = params_str.split()

        for part in parts:
            if "=" in part:
                key, value = part.split("=", 1)
                key = key.strip()
                value = value.strip()

                if key == "force_low_model":
                    result["force_low_model"] = value in ("1", "true", "True")
                elif key == "ttl":
                    try:
                        result["ttl"] = int(value)
                    except ValueError:
                        raise ValueError(f"Invalid ttl value: {value}")
                else:
                    raise ValueError(f"Unknown parameter: {key}")

        return result

    async def _inject_observation(
        self,
        obs_type: ObservationType,
        session_key: str,
        payload,
    ) -> None:
        """
        构造并投递 Observation 到总线
        
        确保包含完整字段：
        - obs_type: 观察类型
        - session_key: 会话标识
        - actor: 触发者信息
        - payload: 载荷数据
        - evidence: 证据引用（用于审计）
        """
        if not self._running or self._bus is None:
            return

        try:
            now = datetime.now(timezone.utc)
            
            # 生成唯一的 raw_event_id
            raw_event_id = f"cli:{self.current_session_key}:{int(now.timestamp() * 1000)}"
            
            obs = Observation(
                obs_type=obs_type,
                source_name=self.name,
                source_kind=self.source_kind,
                timestamp=now,
                received_at=now,
                session_key=session_key,
                actor=Actor(
                    actor_id="cli",
                    actor_type="user",
                    display_name="CLI User",
                ),
                payload=payload,
                evidence=EvidenceRef(
                    raw_event_id=raw_event_id,
                    raw_event_uri=f"cli://local/{session_key}",
                    extra={"source": "cli_adapter"},
                ),
                metadata={
                    "adapter": self.name,
                    "interaction_type": "manual",
                },
            )

            obs.validate()
            
            # 打印 [ADAPTER] 日志
            obs_data = {
                "obs_id": obs.obs_id if hasattr(obs, 'obs_id') else "unknown",
                "obs_type": obs.obs_type.value if hasattr(obs.obs_type, 'value') else str(obs.obs_type),
                "session_key": obs.session_key,
                "actor_id": obs.actor.actor_id if obs.actor else None,
                "timestamp": obs.timestamp.isoformat() if obs.timestamp else None,
            }
            import json
            print(f"[ADAPTER]\n{json.dumps(obs_data, ensure_ascii=False, indent=2)}")
            
            result = self._bus.publish_nowait(obs)

            if result.ok:
                # 查询实际的队列长度
                queue_size = None
                if hasattr(self._bus, '_queue') and hasattr(self._bus._queue, 'qsize'):
                    queue_size = self._bus._queue.qsize()
                elif hasattr(self._bus, 'qsize'):
                    queue_size = self._bus.qsize()
                
                # 打印 [BUS] 日志
                bus_data = {
                    "status": "published",
                }
                if queue_size is not None:
                    bus_data["queue_size"] = queue_size
                
                print(f"[BUS]\n{json.dumps(bus_data, ensure_ascii=False, indent=2)}")
            else:
                print(f"[CLI:WARN] Failed to publish obs: {result.reason}")

        except Exception as e:
            import traceback
            print(f"[CLI:ERROR] {type(e).__name__}: {e}")
            traceback.print_exc()
