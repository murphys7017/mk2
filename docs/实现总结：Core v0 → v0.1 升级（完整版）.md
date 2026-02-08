📋 实现总结：Core v0 → v0.1 升级（完整版）
✅ 已实现的三大功能模块
1️⃣ SessionState + Worker Metrics（会话状态与指标）
session_state.py：轻量运行态状态类，持有 processed_total、error_total、recent_obs、idle 计算
Core 维护 _states 字典，每个 worker 都获得对应的 SessionState
改造后的 worker 在处理每条 obs 时自动更新 state 和 metrics
2️⃣ Session Idle 回收（GC Loop）
新增 GC 配置参数（默认值：idle_ttl_seconds=600、sweep_interval_seconds=30）
_session_gc_loop() 每隔固定时间扫一次，识别 idle session 并回收
_gc_session() 安全取消 worker、清理 state、清理 debug 缓存
避免长期运行系统的 worker/state 泄漏
3️⃣ 痛觉系统（Nociception）v0
nociception.py：标准化 pain alert 生成与解析
make_pain_alert()：统一接口，生成标准化 ALERT observation
重新设计 system handler：
_on_system_pain()：聚合痛觉 metrics（pain_total/by_source/by_severity）
当单源在 60s 内达到 5 次 burst → 触发 adapter cooldown（记录+可扩展）
_on_system_tick()：drop overload 检测、fanout 抑制
drop delta >= 50 → 设置 fanout 禁用窗口，生成 system pain
📊 核心指标新增
CoreMetrics 扩展：

🧪 测试覆盖（13/13 全绿）
测试文件	项目	通过
test_core_metrics.py	metrics & state	✅ 2/2
test_input_bus_and_adapters.py	adapter 基础	✅ 3/3
test_nociception_v0.py	痛觉系统	✅ 4/4
test_session_gc.py	GC 回收	✅ 1/1
test_session_router.py	router 路由	✅ 3/3
🚀 验收清单
✅ 系统运行 10 分钟后，非 system 的 idle session 被回收（worker 停止、state 消失）
✅ uv run pytest -q 全绿（13 passed）
✅ shutdown 不挂：Ctrl+C 能在 1 秒内退出
✅ GC loop 不会因某个 worker 卡死而崩溃（timeout=1.0）
✅ 痛觉聚合正常工作：pain_total/by_source/by_severity 可用
✅ burst 触发 cooldown：5 条同源 alert 在 60s 内 → 标记 adapter cooldown
✅ drop overload 触发 fanout suppression：>= 50 drops → 抑制 fanout
✅ system handler 明确分支 ALERT / SCHEDULE / 其他

📁 新增/修改文件清单
新增：

session_state.py（62 行）
nociception.py（116 行）
test_nociception_v0.py（试测试）
修改：

core.py：+150 行（metrics、GC、nociception handler）
状态：🟢 完全就绪，可直接用于生产环评或进入 Phase 2.3（Tool/Skill 接入）

Claude Hai