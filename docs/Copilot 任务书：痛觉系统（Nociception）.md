下面是一份可以直接丢给 Copilot 的 **“痛觉系统（Nociception）v0 落地指导”**，完全贴合你现在的代码形态：`ObservationType.ALERT + AlertPayload(data=...)`、system session handler、metrics、GC、fanout 等。目标是：**错误来源无限多，但疼痛处理点只有一个（system session）**，并且能做聚合与最小反射。

---

# ✅ Copilot 指导：痛觉系统（Nociception）v0（基于现有 ALERT Observation）

## 目标（不要新造大系统）

在不改 `Observation` 顶层结构的前提下，把“错误=ALERT”升级为：

1. **统一疼痛规范**（ALERT payload.data 字段标准化）
2. **system session 聚合统计**（按来源/严重度/时间窗口）
3. **最小保护反射**（adapter cooldown、fanout 抑制、drop overload 自痛觉）

> 关键原则：**所有疼痛最终都汇入 system session**，system 负责“统计 + 反射”。

---

# 默认参数（直接用）

* `PAIN_WINDOW_SECONDS = 60`
* `PAIN_BURST_THRESHOLD = 5`（同一来源 60s 内 >= 5 次 → 触发反射）
* `ADAPTER_COOLDOWN_SECONDS = 300`（5分钟）
* `DROP_WINDOW_SECONDS = 30`
* `DROP_BURST_THRESHOLD = 50`
* `FANOUT_SUPPRESS_SECONDS = 60`

---

# 需要新增/修改的文件

## 新增 1：`src/nociception.py`

实现三件事：

### 1) 定义一个轻量规范：Pain 字段约定（不用改 schema）

你项目已有 `AlertPayload(data: dict[str, Any])`，所以这里给出约定字段名即可。

**ALERT payload.data 规范（v0）**：

* `source_kind`: `"core" | "router" | "adapter" | "tool" | "skill" | "external" | "system"`
* `source_id`: 例如 `"timer"` / `"text_input"` / `"skill:qweather"`
* `where`: 可选 `"module:function"`
* `exception_type`: 可选
* `trace_id`: 可选（uuid/短串）
* `tags`: 可选 list[str]
* `cooldown_seconds`: 可选（当 system 触发禁用时写回）
* `drop_delta`: 可选（drop overload 时）

> severity 继续用你已有的 `AlertPayload.severity`（low/medium/high/critical），不用另造一套。

### 2) 提供 `make_pain_alert(...) -> Observation`

让所有模块统一调用一个函数来创建“标准化 ALERT”。

伪接口（按你 Observation/Actor/Payload 实际类型写）：

* 输入：`source_kind, source_id, severity, message, session_key(可选), data_extra(可选), where(可选), exc(可选)`
* 输出：一个 `Observation(obs_type=ALERT, session_key=<system>, payload=AlertPayload(...))`

注意：

* `session_key` 默认走 system（因为 pain 要汇聚到中枢）
* 如果是“某 session 的疼痛”，可以把 affected session 塞进 `data_extra["affected_session"]`

### 3) 提供 `extract_pain_key(obs) -> str`

从 ALERT 里抽取聚合 key：

* `source_kind` + `source_id` → `f"{kind}:{id}"`
* 缺失则 fallback：`unknown:unknown`

---

## 修改 1：`src/core.py`（system session 成为痛觉中枢）

### A) 增加一组 nociception 状态与 metrics（建议放到 metrics 里）

最小需要：

* `pain_total: int`
* `pain_by_source: dict[str, int]`  # key="adapter:timer"
* `pain_by_severity: dict[str, int]`  # "low/medium/high/critical"
* `pain_by_session: dict[str, int]`（如果 payload.data 有 affected_session）
* `pain_timestamps_by_source: dict[str, deque[float]]`（滑窗）

保护策略状态：

* `adapters_disabled_until: dict[str, float]`  # adapter_name -> until_ts
* `fanout_disabled_until: float`
* `drops_last: int`
* `drops_overload_total: int`
* `fanout_skipped_total: int`

> 你已有 metrics 类就扩展；没有就先塞 Core 字段，v0 允许。

### B) 在 system handler 加明确分支：ALERT/TICK/SCHEDULE

在你当前 `_handle_system_observation()` 里做分发：

* ALERT → `_on_system_pain(obs)`
* SCHEDULE/TICK → `_on_system_tick(obs)`（你现在 tick 是 SCHEDULE，按你实际类型判）
* 其他 → 可先 log

### C) 实现 `_on_system_pain(obs)`

做三件事（顺序固定）：

1. **解析 source_key**

   * 用 `nociception.extract_pain_key(obs)`
2. **更新聚合 metrics**

   * pain_total++
   * pain_by_source[source_key]++
   * pain_by_severity[severity]++
   * 如果 `affected_session` 存在：pain_by_session[affected_session]++
3. **滑窗频率判断 + 保护反射**

   * 在 `pain_timestamps_by_source[source_key]` 追加 now
   * 清理 `< now - 60`
   * 若长度 >= 5：

     * 如果 source_kind == "adapter"：

       * 将 `adapters_disabled_until[source_id] = now + 300`
       * 记录一次 system pain（可选）：`source_kind="system", source_id="adapter_cooldown"`，message 写明哪个 adapter 被 cooldown
     * 可选：如果频繁 pain，同时设置 `fanout_disabled_until = now + 60`（保命模式）

### D) 实现 `_on_system_tick(obs)`：drop overload + fanout suppression

每次 tick 做：

1. drop 采样

   * `drops_now = router.dropped_total`（或 bus/router/inbox 合计）
   * `delta = drops_now - drops_last`
   * `drops_last = drops_now`
2. 若 delta >= DROP_BURST_THRESHOLD（50）：

   * `drops_overload_total += 1`
   * `fanout_disabled_until = now + 60`
   * 通过 `make_pain_alert` 生成一条 system pain（severity="high" 或 "critical"）并发布到 system
3. fan-out 固化规则

   * 如果 `enable_system_fanout` 为 False：return
   * 如果 `now < fanout_disabled_until`：`fanout_skipped_total += 1`，return
   * 否则 fan-out：

     * 遍历 `router.list_active_sessions()`
     * 排除 system 自己（避免自循环）
     * 可选：只给 idle<=600s 的 session（用 `SessionState.idle_seconds()`）
     * publish 一个轻量 tick（payload 小、不要 traceback）

---

## 修改 2：Adapters/Tools/Skills 的上报方式（v0 最小改一个示例即可）

你已经在 `BaseAdapter._report_error()` 里能发 ALERT，v0 要做的是：

* 让 `_report_error()` 生成的 `AlertPayload.data` 遵循 pain 字段规范：

  * `source_kind="adapter"`
  * `source_id=self.name`（或你的 adapter id）
  * `exception_type=type(e).__name__`
  * `where="AdapterClass.method"`
  * `tags=["exception"]`

这样 system 端的聚合就稳定了。

> v0 只改 adapter 的报错路径就够了，tool/skill 之后接入同一规范。

---

# 保护策略 v0：adapter cooldown 的“实际生效”怎么做（两档选择）

## 选择 A（推荐、侵入小）：Core 提供 publish 入口

* Core 新增 `publish(obs)`：先检查 `adapters_disabled_until`
* 如果 obs 来自被 cooldown 的 adapter：丢弃 +（可选）生成 system pain（throttled）
* adapters 不再直接 `bus.publish_nowait`，改调用 `core.publish`

## 选择 B（更少改动）：只记录 cooldown，不真正阻断

* v0 仍可接受，但这叫“记录”，不是“保护”
* 建议至少让 TimerTickAdapter 走 A（它最容易造成洪水）

---

# 测试（新增 3 个 pytest，锁死 Phase 2.2）

新建 `tests/test_nociception_v0.py`：

### Test 1：pain 聚合

* 往 system 投递 3 条 ALERT（source_kind=adapter, source_id=a1）
* 断言 `pain_total==3`，`pain_by_source["adapter:a1"]==3`

### Test 2：burst 触发 cooldown

* 在短时间投递 5 条同源 pain
* 断言 `adapters_disabled_until["a1"] > now`

### Test 3：drop overload 触发 system pain + fanout suppression

* 让 `router.dropped_total` 在一次 tick 中增加 >= 50（测试可注入或 mock）
* 触发 system tick
* 断言：

  * `drops_overload_total` 增加
  * `fanout_disabled_until > now`
  * system 生成了 `source_id="drop_overload"` 的 pain（可通过 metrics 或 recent buffer 验证）

---

# 验收标准（Done）

1. 新增 `nociception.py`，并有统一生成/解析 pain 的函数
2. system handler 明确分支 ALERT/TICK/SCHEDULE
3. metrics：pain_total/by_source/by_severity 可用
4. adapter burst 能进入 cooldown（至少记录，最好能阻断）
5. drop overload 会抑制 fanout 并生成 system pain
6. pytest 全绿

---

如果你希望 Copilot“写一次就对”，你把 `observation.py` 里 `AlertPayload`、`Observation`、`Actor`、`ObservationType` 的构造方式（尤其是你现在 Alert 里怎么带 `source_name`）告诉我一句，我可以把上面任务书里的 `make_pain_alert` 和测试构造方式改成**完全贴你现有 schema 的具体代码级签名**。
