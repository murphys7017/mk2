# Copilot 执行命令书：Gate / Planner 去重重构（v0）

> 这份文档包含**具体代码改动点**和**YAML 配置示例**，可直接指导代码生成。

---

## 总目标

1. **Gate → 系统层决策**：安全、过载、预算、模型层级、响应策略
2. **Planner → 任务层计划**：意图识别、证据来源选择、工具计划
3. **No Silent Black Hole**：用户 MESSAGE 默认 DELIVER（除非明确 DROP）
4. **预算驱动**：Planner 在 Gate 预算约束内做决策

---

## PART 1: 新增 GateHint 数据结构

### 文件位置
`src/gate/types.py` - 在现有的 `GateDecision` 之后新增

### 代码实现

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Literal


# ========== 新增结构：GateHint（Gate 输出的预算/风险信号）==========

@dataclass
class BudgetSpec:
    """执行预算规格"""
    budget_level: Literal["tiny", "normal", "deep"] = "normal"
    
    # 计算资源
    time_ms: int = 1500
    max_tokens: int = 512
    max_parallel: int = 2
    
    # 能力约束
    evidence_allowed: bool = True
    max_tool_calls: int = 1
    can_search_kb: bool = True
    can_call_tools: bool = True
    
    # 扩展字段（用于未来增强）
    auto_clarify: bool = False  # 是否允许主动澄清
    fallback_mode: bool = False  # 回源失败时的降级模式


@dataclass
class GateHint:
    """Gate 向 Agent/Planner 输出的预算与风险提示"""
    
    # 平台层决策
    model_tier: Literal["low", "high"] = "low"
    response_policy: Literal["respond_now", "clarify", "ack"] = "respond_now"
    
    # 预算
    budget: BudgetSpec = field(default_factory=BudgetSpec)
    
    # 可观测
    reason_tags: List[str] = field(default_factory=list)
    # 可能值：
    # - "score_high" / "score_medium" / "score_low"
    # - "override_deliver" / "override_drop" / "emergency_mode"
    # - "system_overload" / "drop_burst"
    # - "user_dialogue_safe_valve"（新增：UX 安全阀）
    
    # 元数据
    debug: Dict[str, Any] = field(default_factory=dict)


# ========== 修改现有 GateDecision：增加 hint 字段 ==========

@dataclass
class GateDecision:
    # ... 现有字段保持不变 ...
    action: GateAction
    scene: Scene
    session_key: str
    target_worker: Optional[str] = None
    score: float = 0.0
    reasons: List[str] = field(default_factory=list)
    tags: Dict[str, str] = field(default_factory=dict)
    fingerprint: Optional[str] = None
    
    # 新增：Gate 预算与风险信号
    hint: GateHint = field(default_factory=GateHint)
```

---

## PART 2: Gate 规则调整：User Dialogue UX 安全阀

### 文件位置
`src/gate/pipeline/policy.py` - PolicyMapper 类的 apply 方法

### 修改逻辑

在 **"标准策略（score-based policy）"前** 插入新规则：

```python
class PolicyMapper:
    def apply(self, obs, ctx: GateContext, wip: GateWip) -> None:
        try:
            scene = wip.scene or Scene.UNKNOWN
            policy = ctx.config.scene_policy(scene)
            overrides = ctx.config.overrides

            # ========== NEW: User Dialogue UX Safety Valve ==========
            # 防止用户对话消息被沉默 SINK
            if (
                scene == Scene.DIALOGUE
                and obs.obs_type == ObservationType.MESSAGE
                and obs.actor
                and obs.actor.actor_type == "user"
                and wip.action_hint != GateAction.DROP  # 除非被硬 DROP
            ):
                # 强制用户对话消息 DELIVER
                wip.action_hint = GateAction.DELIVER
                wip.reasons.append("user_dialogue_safe_valve")
                
                # 初始化 GateHint
                wip.gate_hint = GateHint(
                    model_tier=policy.default_model_tier or "low",
                    response_policy=policy.default_response_policy or "respond_now",
                    budget=self._select_budget(wip.score, scene),
                    reason_tags=["user_dialogue_safe_valve"],
                )
                return
            
            # ========== 原有优先级逻辑 ==========
            # 1. emergency_mode
            if overrides.emergency_mode:
                wip.action_hint = GateAction.SINK
                wip.model_tier = "low"
                wip.response_policy = policy.default_response_policy
                wip.reasons.append("override=emergency")
                # ... 初始化 gate_hint ...
                return
            
            # 2-6. ... 其他 override 规则保持不变 ...
            
            # 7. 标准策略
            if not deliver_override:
                if wip.action_hint is None:
                    if wip.score >= policy.deliver_threshold:
                        wip.action_hint = GateAction.DELIVER
                    elif wip.score >= policy.sink_threshold:
                        wip.action_hint = GateAction.SINK
                    else:
                        wip.action_hint = policy.default_action
                
                wip.model_tier = policy.default_model_tier
                wip.response_policy = policy.default_response_policy
            
            # 8. force_low_model
            if overrides.force_low_model and wip.action_hint == GateAction.DELIVER:
                wip.model_tier = "low"
                wip.reasons.append("override=force_low_model")
            
            # ========== NEW: 初始化 GateHint（所有路径都需要） ==========
            if not hasattr(wip, 'gate_hint') or wip.gate_hint is None:
                wip.gate_hint = GateHint(
                    model_tier=wip.model_tier or "low",
                    response_policy=wip.response_policy or "respond_now",
                    budget=self._select_budget(wip.score, scene),
                    reason_tags=wip.reasons,
                )
        
        except Exception as e:
            wip.reasons.append(f"policy_error:{e}")
    
    
    # ========== NEW: 预算分档函数 ==========
    def _select_budget(self, score: float, scene: Scene) -> BudgetSpec:
        """根据 score 和 scene 选择预算分档"""
        
        # 基础阈值（来自配置或常数）
        high_threshold = 0.75
        medium_threshold = 0.50
        
        # SCENE 特定调整
        if scene == Scene.ALERT:
            # 告警总是 deep
            return BudgetSpec(
                budget_level="deep",
                time_ms=3000,
                max_tokens=1024,
                max_parallel=4,
                evidence_allowed=True,
                max_tool_calls=3,
                can_search_kb=True,
                can_call_tools=True,
            )
        elif scene == Scene.TOOL_CALL:
            # 工具调用 normal
            return BudgetSpec(
                budget_level="normal",
                time_ms=1500,
                max_tokens=512,
                max_parallel=2,
                evidence_allowed=True,
                max_tool_calls=1,
            )
        elif scene == Scene.TOOL_RESULT:
            # 工具结果 tiny（只做 ack）
            return BudgetSpec(
                budget_level="tiny",
                time_ms=300,
                max_tokens=256,
                max_parallel=1,
                evidence_allowed=False,
                max_tool_calls=0,
                can_search_kb=False,
                can_call_tools=False,
            )
        elif scene == Scene.GROUP:
            # 群聊根据 score
            if score >= high_threshold:
                return BudgetSpec(
                    budget_level="deep",
                    time_ms=2500,
                    max_tokens=1024,
                    max_parallel=3,
                    evidence_allowed=True,
                    max_tool_calls=2,
                )
            elif score >= medium_threshold:
                return BudgetSpec(
                    budget_level="normal",
                    time_ms=1000,
                    max_tokens=512,
                    max_parallel=1,
                    evidence_allowed=True,
                    max_tool_calls=0,
                )
            else:
                return BudgetSpec(
                    budget_level="tiny",
                    time_ms=500,
                    max_tokens=256,
                    max_parallel=1,
                    evidence_allowed=False,
                    max_tool_calls=0,
                )
        else:
            # DIALOGUE 和其他 scene
            if score >= high_threshold:
                return BudgetSpec(
                    budget_level="deep",
                    time_ms=3000,
                    max_tokens=1024,
                    max_parallel=4,
                    evidence_allowed=True,
                    max_tool_calls=3,
                )
            elif score >= medium_threshold:
                return BudgetSpec(
                    budget_level="normal",
                    time_ms=1500,
                    max_tokens=512,
                    max_parallel=2,
                    evidence_allowed=True,
                    max_tool_calls=1,
                )
            else:
                return BudgetSpec(
                    budget_level="tiny",
                    time_ms=800,
                    max_tokens=256,
                    max_parallel=1,
                    evidence_allowed=False,
                    max_tool_calls=0,
                    auto_clarify=True,  # 低分时主动澄清
                )
```

---

## PART 3: Finalize Stage 修改：传递 hint 到 GateDecision

### 文件位置
`src/gate/pipeline/finalize.py` - FinalizeStage 类

### 修改代码

```python
class FinalizeStage:
    def apply(self, obs, ctx: GateContext, wip: GateWip) -> None:
        try:
            scene = wip.scene or Scene.UNKNOWN
            action = wip.action_hint or GateAction.SINK
            
            # 确保 wip 有 gate_hint（防御性编程）
            gate_hint = wip.gate_hint if hasattr(wip, 'gate_hint') else GateHint()

            decision = GateDecision(
                action=action,
                scene=scene,
                session_key=obs.session_key or "",
                target_worker=ctx.system_session_key if scene == Scene.SYSTEM else None,
                model_tier=gate_hint.model_tier,  # 从 hint 读取
                response_policy=gate_hint.response_policy,  # 从 hint 读取
                tool_policy=wip.tool_policy,
                score=wip.score,
                reasons=wip.reasons[: ctx.config.get_policy(scene).max_reasons],
                tags=wip.tags,
                fingerprint=wip.fingerprint,
                hint=gate_hint,  # ← 新增：传递 GateHint
            )

            outcome = GateOutcome(decision=decision, emit=wip.emit, ingest=wip.ingest)
            wip.features["outcome"] = outcome

            if ctx.metrics:
                ctx.metrics.processed_total += 1
                ctx.metrics.inc_scene(scene.value)
                ctx.metrics.inc_action(action.value)
                if action == GateAction.DROP:
                    ctx.metrics.dropped_total += 1
                elif action == GateAction.SINK:
                    ctx.metrics.sunk_total += 1
                elif action == GateAction.DELIVER:
                    ctx.metrics.delivered_total += 1
        except Exception as e:
            wip.reasons.append(f"finalize_error:{e}")
```

---

## PART 4: GateWip 增加 gate_hint 字段

### 文件位置
`src/gate/types.py` - GateWip 类

### 修改代码

```python
@dataclass
class GateWip:
    scene: Optional[Scene] = None
    features: Dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    reasons: List[str] = field(default_factory=list)
    tags: Dict[str, str] = field(default_factory=dict)
    fingerprint: Optional[str] = None

    action_hint: Optional[GateAction] = None
    model_tier: Optional[str] = None
    response_policy: Optional[str] = None
    tool_policy: Optional[Dict[str, Any]] = None

    emit: List[Observation] = field(default_factory=list)
    ingest: List[Observation] = field(default_factory=list)
    
    # 新增：Gate 提示信息
    gate_hint: Optional[GateHint] = None
```

---

## PART 5: Core 透传 GateHint 给 Agent

### 文件位置
`src/agent/types.py` - AgentRequest 类

### 修改代码

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from ..schemas.observation import Observation
from ..gate.types import GateDecision, GateHint  # 新增导入
from ..session_state import SessionState


@dataclass
class AgentRequest:
    """Agent 处理请求"""
    obs: Observation
    gate_decision: GateDecision
    session_state: SessionState
    now: datetime
    
    # 新增：从 GateDecision.hint 填充
    gate_hint: GateHint = None  # type: ignore
    
    def __post_init__(self):
        if self.gate_hint is None and self.gate_decision:
            self.gate_hint = self.gate_decision.hint
```

### 调用位置修改
`src/core.py` - _handle_user_observation 方法：

```python
async def _handle_user_observation(
    self, session_key: str, obs: Observation, state: SessionState, decision=None
) -> None:
    # ... 防止死循环逻辑保持不变 ...
    
    if (
        decision
        and decision.action == GateAction.DELIVER
        and obs.obs_type == ObservationType.MESSAGE
    ):
        try:
            logger.debug(f"[{session_key}] Calling Agent for DELIVER decision")
            
            # 构造 AgentRequest，自动从 decision.hint 获取
            agent_req = AgentRequest(
                obs=obs,
                gate_decision=decision,
                session_state=state,
                now=datetime.now(timezone.utc),
                # gate_hint 会在 __post_init__ 中自动填充
            )
            
            # 调用 agent
            agent_outcome = await self.agent_orchestrator.handle(agent_req)
            
            # ... 后续 emit 和日志保持不变 ...
        except Exception as e:
            logger.error(f"[{session_key}] Agent exception: {e}", exc_info=True)
```

---

## PART 6: Planner 访问 gate_hint（约束检查）

### 文件位置
`src/agent/planner.py` - Planner.handle 或 RulePlanner.plan 方法

### 修改代码

```python
from ..gate.types import GateHint

class RulePlanner:
    async def plan(
        self,
        obs: Observation,
        session_state: SessionState,
        gate_hint: Optional[GateHint] = None,
    ) -> InfoPlan:
        """生成信息计划，遵守 Gate 的预算约束"""
        
        goal = self._infer_goal(obs)
        
        # 根据分数和预算决定取证策略
        budget = gate_hint.budget if gate_hint else None
        
        sources = []
        
        # ✓ 必须遵守：evidence_allowed
        if budget and not budget.evidence_allowed:
            # 不允许取证，只能用 memory / direct
            sources = ["memory"]
        else:
            # 允许取证
            if goal == "factual_question":
                if budget and budget.can_search_kb:
                    sources.append("kb")
                sources.append("memory")
            elif goal == "tool_required":
                if budget and budget.can_call_tools:
                    sources.append("tool_registry")
                sources.append("memory")
            else:
                sources = ["memory"]
        
        # ✓ 必须遵守：max_tool_calls
        tool_calls = []
        if budget and budget.max_tool_calls > 0:
            # 可以规划工具调用（不要超过 max_tool_calls）
            if goal == "tool_required":
                tool_calls = self._plan_tools(obs, limit=budget.max_tool_calls)
        # else: tool_calls 为空
        
        return InfoPlan(
            sources=sources,
            budget={
                "time_ms": budget.time_ms if budget else 1500,
                "max_tokens": budget.max_tokens if budget else 512,
                "evidence_allowed": budget.evidence_allowed if budget else True,
                "max_tool_calls": len(tool_calls),
            },
            tool_calls=tool_calls,
        )
```

### AgentOrchestrator 传递 hint 给 Planner

修改 `src/agent/orchestrator.py`：

```python
async def handle(self, req: AgentRequest) -> AgentOutcome:
    # ... 现有逻辑 ...
    
    # Step 1: Plan
    info_plan = await self.planner.plan(
        obs=req.obs,
        session_state=req.session_state,
        gate_hint=req.gate_hint,  # ← 新增：传递 gate_hint
    )
    
    # ... 后续步骤保持不变 ...
```

---

## PART 7: 可观测性增强

### 日志改进位置
`src/core.py` - _session_loop 方法中的日志输出

```python
# [GATE:OUT] 新增字段
decision_info = {
    "action": outcome.decision.action.value,
    "scene": outcome.decision.scene.value,
    "score": outcome.decision.score,
    "model_tier": outcome.decision.hint.model_tier,
    "response_policy": outcome.decision.hint.response_policy,
    "budget": {
        "level": outcome.decision.hint.budget.budget_level,
        "time_ms": outcome.decision.hint.budget.time_ms,
        "max_tokens": outcome.decision.hint.budget.max_tokens,
        "evidence_allowed": outcome.decision.hint.budget.evidence_allowed,
        "max_tool_calls": outcome.decision.hint.budget.max_tool_calls,
    },
    "reason_tags": outcome.decision.hint.reason_tags,
    "emit_count": len(outcome.emit),
    "ingest_count": len(outcome.ingest),
}
print(f"[GATE:OUT] {json.dumps(decision_info, ensure_ascii=False)}")
```

---

## PART 8: Gate 配置 YAML 补充

### 文件位置
`config/gate.yaml` - 新增 score-to-budget 映射表

```yaml
version: 1

# 新增：预算阈值配置
budget_thresholds:
  high_score: 0.75      # ≥ 此分数 → deep budget
  medium_score: 0.50    # ≥ 此分数 → normal budget
  # < 0.50 → tiny budget

# 预算细节（可选，若代码写死可不加）
budget_profiles:
  tiny:
    time_ms: 500
    max_tokens: 256
    max_parallel: 1
    evidence_allowed: false
    max_tool_calls: 0
  
  normal:
    time_ms: 1500
    max_tokens: 512
    max_parallel: 2
    evidence_allowed: true
    max_tool_calls: 1
  
  deep:
    time_ms: 3000
    max_tokens: 1024
    max_parallel: 4
    evidence_allowed: true
    max_tool_calls: 3

# ... 现有的 scene_policies / rules / overrides 保持不变 ...
```

---

## PART 9: 测试用例

### 测试 1：User Dialogue 不被沉默 SINK

**文件**：`tests/test_gate_user_dialogue_safe_valve.py` (新建)

```python
import pytest
from src.gate import DefaultGate, GateContext
from src.gate.types import Scene, GateAction
from src.schemas.observation import Observation, ObservationType, Actor, MessagePayload, SourceKind
from datetime import datetime, timezone


@pytest.mark.asyncio
async def test_user_dialogue_never_silent_sink():
    """用户 DIALOGUE 消息不会被沉默 SINK（除非 DROP）"""
    gate = DefaultGate()
    
    # 低分消息（通常会被 SINK）
    obs = Observation(
        obs_type=ObservationType.MESSAGE,
        source_name="test",
        source_kind=SourceKind.EXTERNAL,
        session_key="test_session",
        actor=Actor(actor_id="user1", actor_type="user"),
        payload=MessagePayload(text="hi"),  # 短消息，低分
    )
    
    ctx = GateContext(
        now=datetime.now(timezone.utc),
        config=gate.config,
        system_session_key="system",
        metrics=gate.metrics,
    )
    
    outcome = gate.handle(obs, ctx)
    
    # 断言：即使分数低，user DIALOGUE 也应该 DELIVER
    assert outcome.decision.action == GateAction.DELIVER, \
        f"User dialogue should be DELIVER, got {outcome.decision.action}"
    
    # 断言：reason_tags 中包含 "user_dialogue_safe_valve"
    assert "user_dialogue_safe_valve" in outcome.decision.hint.reason_tags


@pytest.mark.asyncio
async def test_user_dialogue_respects_hard_drop():
    """但用户 DIALOGUE 仍然会尊重硬 DROP（系统过载等）"""
    gate = DefaultGate()
    
    obs = Observation(
        obs_type=ObservationType.MESSAGE,
        source_name="test",
        source_kind=SourceKind.EXTERNAL,
        session_key="test_session",
        actor=Actor(actor_id="user1", actor_type="user"),
        payload=MessagePayload(text=""),  # 空消息 → hard DROP
    )
    
    ctx = GateContext(
        now=datetime.now(timezone.utc),
        config=gate.config,
        system_session_key="system",
        metrics=gate.metrics,
        system_health={"overload": False},  # 不过载
    )
    
    outcome = gate.handle(obs, ctx)
    
    # 空消息被硬 DROP
    assert outcome.decision.action == GateAction.DROP
```

### 测试 2：Planner 遵守预算约束

**文件**：`tests/test_planner_budget_constraint.py` (新建)

```python
import pytest
from src.agent.planner import RulePlanner
from src.gate.types import GateHint, BudgetSpec
from src.schemas.observation import Observation, ObservationType, MessagePayload, Actor, SourceKind
from src.session_state import SessionState


@pytest.mark.asyncio
async def test_planner_respects_no_evidence():
    """evidence_allowed=false 时，Planner 不选择 kb/tool 源"""
    planner = RulePlanner()
    
    obs = Observation(
        obs_type=ObservationType.MESSAGE,
        source_name="test",
        source_kind=SourceKind.EXTERNAL,
        session_key="test",
        actor=Actor(actor_id="user1", actor_type="user"),
        payload=MessagePayload(text="2025年的 GDP 是多少?"),  # 事实问题
    )
    
    state = SessionState(session_key="test")
    
    # 预算：不允许取证
    gate_hint = GateHint(
        budget=BudgetSpec(
            evidence_allowed=False,
            max_tool_calls=0,
            can_search_kb=False,
        )
    )
    
    plan = await planner.plan(obs, state, gate_hint)
    
    # 断言：即使是事实问题也不调用 kb
    assert "kb" not in plan.sources
    assert len(plan.budget.get("tool_calls", [])) == 0


@pytest.mark.asyncio
async def test_planner_respects_tool_limit():
    """max_tool_calls=0 时不规划工具调用"""
    planner = RulePlanner()
    
    obs = Observation(
        obs_type=ObservationType.MESSAGE,
        source_name="test",
        source_kind=SourceKind.EXTERNAL,
        session_key="test",
        actor=Actor(actor_id="user1", actor_type="user"),
        payload=MessagePayload(text="给我查一下天气"),  # 需要工具
    )
    
    state = SessionState(session_key="test")
    
    # 预算：不允许工具调用
    gate_hint = GateHint(
        budget=BudgetSpec(
            max_tool_calls=0,
            can_call_tools=False,
        )
    )
    
    plan = await planner.plan(obs, state, gate_hint)
    
    # 断言：即使需要工具也不调用
    assert plan.budget["max_tool_calls"] == 0
```

### 测试 3：E2E 验证（现有测试改进）

修改 `tests/test_core_agent_e2e_live.py`：

```python
# 删除原来 gate.yaml 的自定义配置，改为默认配置
# 因为现在 user MESSAGE 默认就会 DELIVER

@pytest.mark.integration
@pytest.mark.skipif(SKIP_INTEGRATION, reason="...")
@pytest.mark.asyncio
async def test_core_agent_e2e_user_to_response():
    """
    E2E 测试：用户输入 → Gate 强制 DELIVER（UX 安全阀）→ Agent(LLM) → 回流
    
    改进：不需要 deliver_sessions 白名单，用户消息自动 DELIVER
    """
    core = Core(
        bus_maxsize=100,
        inbox_maxsize=50,
        system_session_key="system",
        message_routing="user",
        enable_system_fanout=False,
    )
    
    # 使用默认 gate.yaml（不需要特殊配置）
    # Gate 的 UX 安全阀会确保 user MESSAGE 被 DELIVER
    
    # ... 后续测试逻辑保持不变 ...
```

---

## PART 10: 验收检查清单

### 代码变更完成度

- [ ] `src/gate/types.py`：新增 GateHint / BudgetSpec；修改 GateDecision / GateWip
- [ ] `src/gate/pipeline/policy.py`：新增用户对话安全阀 + _select_budget() 方法
- [ ] `src/gate/pipeline/finalize.py`：传递 hint 到 GateDecision
- [ ] `src/agent/types.py`：AgentRequest 增加 gate_hint，__post_init__ 自动填充
- [ ] `src/core.py`：_handle_user_observation 透传 decision.hint
- [ ] `src/agent/planner.py`：plan() 方法接收 gate_hint 参数，做约束检查
- [ ] `src/agent/orchestrator.py`：handle() 调用 planner 时传递 gate_hint
- [ ] `config/gate.yaml`：新增 budget_thresholds 和 budget_profiles
- [ ] `src/core.py`：增强 [GATE:OUT] 日志输出 hint 信息

### 测试完成度

- [ ] `tests/test_gate_user_dialogue_safe_valve.py`（新建）
- [ ] `tests/test_planner_budget_constraint.py`（新建）
- [ ] `tests/test_core_agent_e2e_live.py`（改进 - 删除过度配置）
- [ ] 运行 `pytest -q` 确保无回归

### 功能验收

- [ ] 用户 MESSAGE 默认被 DELIVER（不再沉默 SINK）❌ → ✅
- [ ] Gate 与 Planner 职责分离（预算分档不重叠）❌ → ✅
- [ ] Planner 在预算约束内做决策（evidence_allowed/max_tool_calls）❌ → ✅
- [ ] [GATE:OUT] 日志包含预算信息，可解释决策❌ → ✅
- [ ] Hard bypass 保护能力不受影响（emergency_mode/overload 仍有效）✅ → ✅

---

## 快速操作指南

1. **按依赖顺序实现**：
   ```
   types.py (GateHint) 
   → policy.py (安全阀 + _select_budget) 
   → finalize.py (传递 hint) 
   → agent/types.py (AgentRequest) 
   → core.py (透传) 
   → planner.py (约束检查) 
   → orchestrator.py (传递给 planner)
   → 日志增强 + gate.yaml 补充
   ```

2. **验证每个变更**：
   ```bash
   # 为每个文件的改动运行相关测试
   uv run pytest tests/test_gate_* -v
   uv run pytest tests/test_agent_* -v
   uv run pytest tests/test_core_* -v
   ```

3. **最后运行完整测试**：
   ```bash
   uv run pytest -q  # 确保 38+ 通过，无回归
   ```

---

**准备好了吗？** 这份文档包含了所有代码框架和配置细节，可以直接给 Copilot，它应该能一次性生成大部分代码（除了 Planner 的 _infer_goal / _plan_tools 等业务逻辑可能需要你补充）。
