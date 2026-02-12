# 🧠 项目概述 —— 一个长期运行的类生命体 Agent 系统

## 这不是一个简单的对话机器人

本项目构建的并不是一个“包装 LLM 的聊天接口”，而是一个：

> **长期运行、多会话并发、自我保护、可调节的 Agent 系统**

系统设计参考类生命体结构：

> 感知 → 反射 → 认知 → 行动 → 反馈 → 自主调节

目标是构建一个：

* 可长期运行
* 支持多 session 并发
* 具备过载保护能力
* 支持运行时降级
* 可自动恢复
* 支持工具扩展
* 支持模型分层
* 可观测、可调节、可回滚

---

# 🏗 系统整体架构

系统被划分为三个结构层级：

---

## 1️⃣ 脑干层（Gate）—— 反射与保护层

该层已经实现完成。

### 职责

* 场景识别（scene inference）
* 打分与分流
* 去重
* 速率控制
* 过载保护
* DROP / SINK / DELIVER 决策
* 运行时 overrides（emergency / 强制 low 模型）

### 特点

* 规则驱动
* 无 LLM 参与
* 快速且可预测
* YAML 配置驱动
* 支持热更新
* 仅负责门控，不负责智能

Gate 是系统的“反射系统”，而不是“思考系统”。

---

## 2️⃣ 认知层（Agent）—— 智能与规划层

该层正在进入主要开发阶段。

### 规划职责

* 意图识别（IntentJudge）
* 任务规划（Planner）
* 记忆管理
* 工具调用决策
* 多模型策略
* 结构化响应生成

Agent 只处理通过 Gate 的输入。

它不再负责：

* 是否响应
* 过载保护
* 降级决策
* 去重

这些全部由脑干层处理。

---

## 3️⃣ 自主神经层（System Reflex）—— 自我调节系统

该层已实现 MVP，并具备闭环能力。

### 已实现闭环

```
Gate 发出 ALERT
→ system session 聚合统计
→ Reflex Controller 判断
→ 修改 overrides
→ Gate 行为改变
→ 广播 CONTROL(system_mode_changed)
```

### 当前能力

* emergency 模式自动触发
* 强制 low 模型
* drop burst 监测
* TTL 限时调节
* Agent 调节建议（白名单 + TTL + 冷却）
* 自动恢复机制

### 设计原则

* 不使用 LLM
* 纯规则反射
* 可观测
* 可恢复
* 无隐藏通道

---

# 🔄 运行时主流程

```
Adapter
→ Observation
→ InputBus
→ SessionRouter
→ SessionWorker
→ Gate（脑干）
→ Agent（认知）
→ Tool（未来扩展）
→ Observation 回流
→ System Reflex（自主神经）
```

所有状态变化都通过 Observation 传播。

系统不存在隐式全局变量修改。

---

# ⚙ 配置系统

Gate 使用 YAML 配置驱动：

* Scene 策略
* 打分权重
* 去重窗口
* Drop 升级规则
* 运行时 overrides

支持：

* 默认值兜底
* 强类型映射
* 热更新快照替换
* system_reflex 运行时修改

---

# 🛡 运行时安全模型

系统强制边界：

* Gate 不调用 Agent
* Agent 不能直接修改 Gate
* Agent 只能“建议”调节
* system_reflex 是唯一可执行 override 的层
* 所有状态变化都会发出事件

防止出现不可控的反馈环。

---

# 📈 当前完成阶段

已完成：

* 输入主干
* 多 session 隔离
* Gate 反射系统
* YAML 配置 + 热更新
* 运行时 overrides
* System 自调节闭环
* Agent 通知机制
* Agent 调节建议机制

系统已具备：

> 输入 → 门控 → 认知 → 反馈 → 自调节 的完整主循环。

---

# 📚 文档

详细文档请查阅 `docs/` 目录：

* [docs/README.md](docs/README.md) - 文档总入口（先看这里）
* [PROJECT_MODULE_DEEP_DIVE.md](docs/PROJECT_MODULE_DEEP_DIVE.md) - 当前代码对齐的模块深潜文档
* [DESIGN_DECISIONS.md](docs/DESIGN_DECISIONS.md) - 设计决策记录

---

# 🚀 下一阶段

重点进入认知层建设：

* IntentJudge
* QueryPlan
* Memory 优化
* Tool 子系统
* 多模型协作

结构地基已完成。

---

# 🎯 最终愿景

本项目目标是构建：

> 一个可长期运行、可自我保护、可调节、可恢复的智能体系统。

不是单纯“更聪明”，
而是“结构上更稳定”。

---
