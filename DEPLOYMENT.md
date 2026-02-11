# MK2 快速部署指南

**最后更新**: Session 10  
**版本**: 1.0  
**状态**: Production Ready ✅

---

## 1. 环境要求

```bash
# 系统要求
- Python 3.11+
- uv package manager (https://docs.astral.sh/uv/getting-started/)
- 200MB 磁盘空间
- 可选: Docker + docker-compose

# Python 依赖 (自动处理)
asyncio         # 标准库
pytest          # 测试
pyyaml          # 配置解析
```

---

## 2. 一键安装

### 2.1 克隆与初始化

```bash
# 假设项目已在 d:\BaiduSyncdisk\Code\mk2
cd d:\BaiduSyncdisk\Code\mk2

# 初始化 Python 环境
uv sync

# 验证安装
uv run pytest --version
```

### 2.2 验证测试

```bash
# 运行全部测试 (应该通过 30/30)
uv run pytest -v

# 输出示例:
# test_core_metrics_0.py::test_session_isolation PASSED
# test_core_metrics_0.py::test_metrics_incremented PASSED
# ... (28 more)
# ========================== 30 passed in 4.34s ==========================
```

### 2.3 快速启动

```bash
# 启动系统 (控制台)
uv run python main.py

# 输出示例:
# [2024-xx-xx 10:30:45] Starting Core...
# [2024-xx-xx 10:30:45] Core initialized with 1000-item bus
# [2024-xx-xx 10:30:45] TextAdapter (text_input) running
# [2024-xx-xx 10:30:45] TimerTickAdapter (timer_tick) running
# [2024-xx-xx 10:30:45] GC loop started
# [2024-xx-xx 10:30:45] System ready. Press Ctrl+C to stop.
```

---

## 3. 配置文件

### 3.1 Gate 配置 (`config/gate.yaml`)

**位置**: `d:\BaiduSyncdisk\Code\mk2\config\gate.yaml`

**关键参数**:

```yaml
# 场景阈值 (0.0-1.0, 越高越严格)
scene_policies:
  DIALOGUE:
    deliver_threshold: 0.75      # 低于 0.75 不交付给 Agent
  GROUP:
    deliver_threshold: 0.85      # 更严格
  ALERT:
    deliver_threshold: 0.0       # 总是交付 (痛觉)
  SYSTEM:
    deliver_threshold: 0.0       # 总是交付

# 规则权重 (影响评分计算)
rules:
  dialogue:
    weights:
      text_len: 0.2              # 文本长度权重
      has_question: 0.3          # 含问号权重
      has_bot_mention: 0.25      # 提及 bot 权重

# DROP 突发监控 (自动进入紧急模式)
drop_escalation:
  critical_count_threshold: 20   # 60 秒内 20 个 DROP → 紧急模式

# 动态覆盖 (由系统或 Agent 设置)
overrides:
  emergency_mode: false          # 系统自动设置 (痛觉突发)
  force_low_model: false         # Agent 可以设置 (TTL=60 sec)
```

**修改方式**:

```bash
# 编辑配置文件
vim config/gate.yaml  # 或用 VS Code

# 保存后, 下一个观察会自动应用新配置 (热加载)
# 无需重启系统
```

### 3.2 运行时参数 (`main.py`)

```python
# main.py 中的 Core 初始化参数
core = Core(
    bus_maxsize=1000,                    # 输入总线缓冲大小
    gc_check_interval_sec=1.0,          # GC 检查间隔 (秒)
    session_idle_timeout_sec=300.0      # 会话空闲超时 (秒, 默认 5 分钟)
)
```

---

## 4. 生产环保境设置

### 4.1 日志配置

```bash
# 创建日志目录
mkdir -p logs

# 日志文件
# - logs/mk2.log          # 主日志 (实时)
# - logs/metrics.log      # 指标日志 (定期flush)
# - logs/error.log        # 错误日志 (仅异常)
```

### 4.2 Systemd 服务配置

**文件**: `/etc/systemd/system/mk2.service`

```ini
[Unit]
Description=MK2 Agent Core
After=network.target

[Service]
Type=simple
User=mk2
WorkingDirectory=/opt/mk2
Environment="PYTHONUNBUFFERED=1"
ExecStart=/usr/local/bin/uv run python main.py
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

**启动**:

```bash
sudo systemctl daemon-reload
sudo systemctl enable mk2
sudo systemctl start mk2
sudo systemctl status mk2

# 查看日志
sudo journalctl -u mk2 -f
```

### 4.3 Docker 容器化

**文件**: `Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# 安装 uv
RUN curl -sSL https://astral.sh/uv/install.sh | sh

# 复制项目
COPY . .

# 安装依赖
RUN /root/.local/bin/uv sync

# 暴露指标端口 (可选)
EXPOSE 8080

# 运行
CMD ["/root/.local/bin/uv", "run", "python", "main.py"]
```

**构建与运行**:

```bash
# 构建镜像
docker build -t mk2:latest .

# 运行容器
docker run -d \
  --name mk2 \
  -v $(pwd)/config:/app/config \
  -v $(pwd)/logs:/app/logs \
  -p 8080:8080 \
  mk2:latest

# 查看日志
docker logs -f mk2
```

---

## 5. 监控与诊断

### 5.1 实时指标查询

```python
# 在运行系统中 (需要暴露接口)
import asyncio
from src.core import Core

# 假设 core 实例存在
metrics = core.metrics

# 全局指标
print(f"总发布数: {metrics.bus_publishes}")
print(f"痛觉总数: {metrics.pain_total}")
print(f"DROP 总数: {metrics.drop_monitored}")

# 会话指标
for session_key, session_m in metrics.session_metrics.items():
    print(f"\n{session_key}:")
    print(f"  处理: {session_m.processed}")
    print(f"  错误: {session_m.error_total}")
    print(f"  交付: {session_m.gate_decisions.get('DELIVER', 0)}")
    print(f"  缓冲: {session_m.gate_decisions.get('SINK', 0)}")

# 冷却状态
print(f"\n冷却中的适配器: {metrics.adapter_cooldowns}")
```

### 5.2 日志标记

```
[TRACE]   细粒度调试信息
[DEBUG]   开发调试信息
[INFO]    正常流程信息
[WARN]    警告信息 (可恢复问题)
[ERROR]   错误 (需人工处理)
[FATAL]   致命错误 (系统崩溃)
```

**搜索特定事件**:

```bash
# 查找所有痛觉事件
grep "pain_alert\|ALERT" logs/mk2.log

# 查找冷却触发
grep "adapter_cooldown\|burst_detected" logs/mk2.log

# 查找配置重载
grep "config_reloaded\|override_applied" logs/mk2.log

# 查找 GC 活动
grep "gc_iteration\|session_destroyed" logs/mk2.log

# 实时监控 (Linux/Mac)
tail -f logs/mk2.log | grep -E "ERROR|FATAL|burst|cooldown"
```

### 5.3 健康检查

```bash
#!/bin/bash
# health_check.sh

# 检查进程运行状态
ps aux | grep "uv run python main.py" | grep -v grep
if [ $? -eq 0 ]; then
    echo "[OK] Core process running"
else
    echo "[FAIL] Core process not running"
    exit 1
fi

# 检查配置文件
if [ -f "config/gate.yaml" ]; then
    echo "[OK] Config file exists"
else
    echo "[FAIL] Config file missing"
    exit 1
fi

# 检查日志目录
if [ -d "logs" ]; then
    echo "[OK] Logs directory exists"
else
    echo "[FAIL] Logs directory missing"
    exit 1
fi

# 检查最近日志 (应该有活动)
LAST_LOG=$(tail -1 logs/mk2.log)
if [ ! -z "$LAST_LOG" ]; then
    echo "[OK] Recent logs: $LAST_LOG"
else
    echo "[WARN] No logs found"
fi

echo "[OK] All health checks passed"
```

**运行**:

```bash
chmod +x health_check.sh
./health_check.sh
```

---

## 6. 常见问题排查

### 问题: 导入错误 "No module named 'src'"

**解决方案**:

```bash
# 确保从项目根目录运行
cd d:\BaiduSyncdisk\Code\mk2

# 使用 uv run
uv run python main.py

# 或设置 PYTHONPATH
export PYTHONPATH=$PYTHONPATH:$(pwd)
python main.py
```

### 问题: 配置文件不被加载

**解决方案**:

```bash
# 检查文件是否存在且可读
ls -la config/gate.yaml

# 检查 YAML 语法
python -m yaml -c "import yaml; yaml.safe_load(open('config/gate.yaml'))"

# 检查路径 (在 config_provider.py 中)
grep -n "gate.yaml" src/config_provider.py
```

### 问题: 性能下降 / CPU 高

**诊断**:

```python
# 1. 检查会话数量
print(f"活跃会话: {len(core._states)}")

# 2. 检查队列深度
print(f"总线堆积: {core.bus.qsize()}")

# 3. 检查痛觉 (可能造成冷却导致堆积)
print(f"痛觉总数: {core.metrics.pain_total}")
print(f"冷却中: {core.metrics.adapter_cooldowns}")

# 4. 降低配置:
#    - 增大 session_idle_timeout_sec (更快清理)
#    - 增大 bus_maxsize (但消耗更多内存)
#    - 调高场景 deliver_threshold (更少送到 Agent)
```

### 问题: 内存泄漏

**检查**:

```bash
# 监控内存使用
# Linux
watch -n 1 'ps aux | grep "python main.py" | grep -v grep'

# macOS
while true; do
    ps aux | grep "python main.py" | grep -v grep
    sleep 1
done

# Windows
# 用任务管理器或:
Get-Process python | Select Name, Id, @{Name="Memory(MB)";Expression={[math]::Round($_.WorkingSet/1MB)}}
```

**可能原因**:
- 会话未清理 (GC 超时太长)
- 池缓冲溢出 (SinkPool/DropPool 不清空)
- 指标累积 (建议定期 flush)

**解决方案**:

```python
# 减小 GC 超时
core = Core(session_idle_timeout_sec=60.0)  # 更激进清理

# 定期清空池
if len(core.gate.sink_pool.items) > 1000:
    core.gate.sink_pool.clear()
```

---

## 7. 备份与恢复

### 7.1 备份关键文件

```bash
# 备份脚本
#!/bin/bash
BACKUP_DIR="/backup/mk2/$(date +%Y%m%d)"
mkdir -p $BACKUP_DIR

# 备份配置
cp -r config/ $BACKUP_DIR/

# 备份代码
tar czf $BACKUP_DIR/src.tar.gz src/

# 备份日志 (可选)
tar czf $BACKUP_DIR/logs.tar.gz logs/

echo "Backup completed: $BACKUP_DIR"
```

### 7.2 恢复步骤

```bash
# 1. 停止系统
systemctl stop mk2

# 2. 恢复配置
cp -r /backup/mk2/20240101/config/* config/

# 3. 验证配置
python -m yaml -c "import yaml; yaml.safe_load(open('config/gate.yaml'))"

# 4. 重启
systemctl start mk2
systemctl status mk2
```

---

## 8. 性能优化

### 8.1 调整参数

| 参数 | 默认值 | 低负载 | 高负载 |
|------|--------|--------|--------|
| bus_maxsize | 1000 | 500 | 2000 |
| gc_check_interval_sec | 1.0 | 5.0 | 0.5 |
| session_idle_timeout_sec | 300 | 600 | 60 |
| DIALOGUE threshold | 0.75 | 0.6 | 0.85 |
| DROP critical_count | 20 | 10 | 50 |

### 8.2 Feature Extraction 优化

```python
# 在 src/gate/pipeline/feature.py 中
# 目前计算: text_len, has_question, has_bot_mention, alert_severity

# 高负载下可以：
# 1. 缓存已知问题的特征
# 2. 跳过昂贵的正则表达式
# 3. 批量处理特征提取
```

### 8.3 Dedup 窗口优化

```python
# 当前: 20 天秒窗口 (很长, 防止重复)
# 高吞吐场景:
# - 减小窗口 (5 天秒)
# - 或改为概率去重 (bloom filter)
```

---

## 9. 升级步骤

### 9.1 小版本升级 (1.0.0 → 1.0.1)

```bash
# 1. 备份当前代码
git stash

# 2. 拉取更新
git pull origin main

# 3. 重新安装依赖
uv sync

# 4. 运行测试
uv run pytest -v

# 5. 启动测试 (手动验证)
uv run python main.py
# 输入几个观察, 验证功能

# 6. 生产重启
systemctl restart mk2
```

### 9.2 大版本升级 (1.0 → 2.0)

```bash
# 1-5. 同上
# 6. 迁移配置
# 比较 config/gate.yaml 格式
git diff config/gate.yaml.sample config/gate.yaml

# 7. 迁移代据 (如有)
# 如果有持久化数据, 需要转换格式

# 8. 验证指标
# 确保新版本能读取旧数据

# 9. 分阶段升级 (金丝雀部署)
# - 先升级测试环境
# - 再升级 10% 生产流量
# - 最后 100%
```

---

## 10. 快速参考卡

### 启动/停止

```bash
# 开发环境
uv run python main.py         # 前台运行
uv run python main.py &       # 后台运行

# 生产环境 (systemd)
systemctl start mk2           # 启动
systemctl stop mk2            # 停止
systemctl restart mk2         # 重启
systemctl status mk2          # 状态
```

### 配置修改

```bash
# 编辑配置
vim config/gate.yaml

# 校验语法
python -c "import yaml; yaml.safe_load(open('config/gate.yaml'))"

# 立即生效 (热加载)
# 无需重启, 下一个观察会应用
```

### 日志查看

```bash
# 实时日志
tail -f logs/mk2.log

# 搜索错误
grep ERROR logs/mk2.log

# 统计指标
grep "METRIC\|pain_total\|drop_monitored" logs/mk2.log
```

### 测试运行

```bash
# 全部测试
uv run pytest

# 单个测试
uv run pytest tests/test_core_metrics.py -v

# 覆盖率
uv run pytest --cov=src --cov-report=html
```

---

## 11. 支持与反馈

- **文档**: 查阅 [README.md](README.md) 和 [ARCHITECTURE.md](ARCHITECTURE.md)
- **问题排查**: 运行 `health_check.sh` 和 `uv run pytest -v`
- **代码**: 查看 [src/](src/) 中的类型注解和文档字符串

---

**祝部署顺利！🚀**
