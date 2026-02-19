# Markdown Vault 混合架构设计

## 核心设计思想

### 问题分析

用户提出的关键洞察：
1. **分类需求不同**：
   - 系统设定、人格、用户信息 → 大文件，全文使用
   - 经历、知识 → 小文件，碎片检索

2. **变更追踪需求**：
   - 需要知道哪些文件被修改了
   - 修改后自动同步到数据库
   - 避免重复同步未变化的文件

3. **性能与灵活性平衡**：
   - 配置文件：启动时加载，运行时内存访问
   - 知识库：支持动态添加，支持检索

---

## 架构设计

### 目录结构

```
memory_vault/
├── config/              # 第一类：全量注入配置
│   ├── system.md        # 系统设定（AI 人格、能力、约束）
│   ├── world.md         # 世界观设定（背景、规则）
│   └── users/
│       ├── alice.md     # 用户信息（偏好、画像、约束）
│       └── bob.md
│
├── knowledge/           # 第二类：碎片化知识
│   ├── experiences/     # 经历片段（时间线事件）
│   │   ├── exp_001.md   # 单次对话记录
│   │   └── exp_002.md   # 重要事件
│   └── facts/           # 知识条目（可检索的事实）
│       ├── fact_001.md  # 领域知识
│       └── fact_002.md  # 用户特定规则
│
└── metadata.json        # MD5 索引表
```

### metadata.json 格式

```json
{
  "config/system.md": {
    "md5": "5d41402abc4b2a76b9719d911017c592",
    "synced_at": 1708249200.123,
    "size": 1024,
    "version": 3,
    "file_type": "config"
  },
  "knowledge/experiences/exp_001.md": {
    "md5": "098f6bcd4621d373cade4e832627b4f6",
    "synced_at": 1708249300.456,
    "size": 512,
    "version": 1,
    "file_type": "knowledge"
  }
}
```

---

## 文件分类详解

### 第一类：config/（全量注入）

**特点**：
- 文件数量少（系统级1-2个，每用户1个）
- 文件较大（1-10KB）
- 修改频率低
- **使用方式**：全文注入到 system prompt

**结构**：
```
config/
├── system.md           # 系统级配置
├── world.md            # 世界观（可选）
└── users/<id>.md       # 每个用户一个文件
```

**文件示例**：

#### config/system.md
```markdown
---
version: 1.0
author: system
updated_at: 2024-02-19
---
# 系统人设

你是一个友好、专业的 AI 助手。

## 核心特质
- 有帮助的：始终尝试回答用户问题
- 知识渊博：涵盖多个领域
- 耐心细致：提供详细解释

## 能力范围
- ✓ 回答技术问题
- ✓ 提供建议和指导
- ✓ 编写代码示例
- ✗ 不提供医疗建议
- ✗ 不参与政治讨论

## 交互风格
- 使用清晰、简洁的语言
- 提供代码示例时添加注释
- 遇到不确定的问题时明确说明
```

#### config/users/alice.md
```markdown
---
user_id: alice
name: Alice
role: software_engineer
created_at: 2024-01-01
preferences:
  language: zh-CN
  code_style: detailed
  explanation_level: advanced
---
# 用户: Alice

## 基本信息
- 职业：软件工程师
- 兴趣：AI、Python、系统设计
- 经验水平：高级

## 交互偏好
- 喜欢详细的技术解释
- 偏好完整的代码示例（带注释）
- 喜欢探讨底层原理

## 约束
- 工作时间（9-18点）请简短回复
- 避免使用过于简化的比喻
- 不需要重复基础概念
```

---

### 第二类：knowledge/（碎片检索）

**特点**：
- 文件数量多（可能数百上千）
- 文件较小（0.5-2KB）
- 修改频率高
- **使用方式**：通过检索添加相关片段到上下文

**结构**：
```
knowledge/
├── experiences/        # 经历片段
│   ├── exp_001.md     # 单次重要对话
│   ├── exp_002.md     # 关键事件
│   └── ...
└── facts/             # 知识条目
    ├── fact_001.md    # 领域知识
    ├── fact_002.md    # 用户规则
    └── ...
```

**文件示例**：

#### knowledge/experiences/first_python_question.md
```markdown
---
date: 2024-01-15
time: "10:30"
participants: [alice]
topic: python装饰器
sentiment: positive
tags: [python, learning, decorator]
---
# 第一次询问 Python 装饰器

Alice 询问了关于 Python 装饰器的问题，特别是：
- 装饰器的基本语法
- 带参数的装饰器
- 类装饰器 vs 函数装饰器

她表示之前对这个概念感到困惑，但在详细解释后理解了。
```

#### knowledge/facts/alice_code_preferences.md
```markdown
---
user_id: alice
category: coding_style
priority: high
tags: [preference, code_style]
---
# Alice 的代码风格偏好

## 变量命名
- 使用描述性名称（避免 a, b, c）
- 遵循 snake_case（Python）

## 注释风格
- 每个函数都要有 docstring
- 复杂逻辑添加行内注释
- 使用类型注解

## 示例
```python
def calculate_user_score(user_id: str, metrics: dict) -> float:
    """计算用户分数
    
    Args:
        user_id: 用户唯一标识
        metrics: 评分指标字典
        
    Returns:
        综合分数 (0-100)
    """
    # 实现...
```
```

---

## MD5 追踪机制

### 工作流程

```
系统启动
    ↓
扫描所有 .md 文件
    ↓
计算每个文件的 MD5
    ↓
对比 metadata.json 中的 MD5
    ↓
识别变化的文件
    ↓
┌─────────────────┬─────────────────┐
│ 未变化的文件    │ 变化的文件      │
├─────────────────┼─────────────────┤
│ 直接加载到内存  │ 1. 加载到内存   │
│ (跳过数据库)    │ 2. 同步到数据库 │
│                 │ 3. 更新metadata │
└─────────────────┴─────────────────┘
```

### 变更检测逻辑

```python
def _scan_and_sync(self):
    changed_files = []
    
    for file_path in all_md_files:
        # 1. 计算当前 MD5
        current_md5 = compute_md5(file_path)
        
        # 2. 获取旧 MD5
        old_metadata = self.metadata.get(rel_path)
        old_md5 = old_metadata.md5 if old_metadata else None
        
        # 3. 判断是否变化
        if current_md5 != old_md5:
            changed_files.append(file_path)
            
            # 4. 同步到数据库
            self._sync_to_db(file_path)
            
            # 5. 更新元数据
            self.metadata[rel_path] = FileMetadata(
                md5=current_md5,
                synced_at=now(),
                version=old_metadata.version + 1 if old_metadata else 1,
                ...
            )
    
    # 6. 保存 metadata.json
    self._save_metadata()
```

### 版本管理

每次文件修改，版本号自动递增：

```
Version 1: 初始创建
    ↓ 修改内容
Version 2: 第一次修改
    ↓ 再次修改
Version 3: 第二次修改
```

---

## 数据库同步策略

### config/ → 数据库（全文存储）

```sql
CREATE TABLE markdown_configs (
    key VARCHAR(255) PRIMARY KEY,
    content TEXT,              -- 正文全文
    frontmatter JSON,          -- 元数据
    md5 CHAR(32),              -- MD5 校验
    version INT,               -- 版本号
    synced_at TIMESTAMP,
    INDEX idx_md5 (md5)
);
```

**同步时机**：
- 文件 MD5 变化时
- 手动调用 `upsert_config()` 时

**用途**：
- 快速读取（无需读文件）
- 版本追溯
- 分布式部署时的一致性

---

### knowledge/ → 数据库（索引存储）

```sql
CREATE TABLE markdown_knowledge (
    id SERIAL PRIMARY KEY,
    key VARCHAR(255) UNIQUE,
    content TEXT,
    frontmatter JSON,
    md5 CHAR(32),
    category VARCHAR(50),      -- experiences | facts
    tags JSON,                 -- 标签列表
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    INDEX idx_category (category),
    INDEX idx_tags ((tags::text))  -- JSON 索引
);
```

**同步时机**：
- 文件 MD5 变化时
- 手动调用 `upsert_knowledge()` 时
- 手动调用 `delete_knowledge()` 时

**用途**：
- 全文检索（配合 FTS）
- 向量检索（配合 embedding）
- 标签过滤
- 分类查询

---

## API 设计

### 配置管理 API

```python
# 读取（从内存缓存，极速）
vault.get_system_config() -> str
vault.get_world_config() -> str
vault.get_user_config(user_id: str) -> str
vault.get_config(key: str) -> Optional[str]

# 写入（文件 + 内存 + 数据库）
vault.upsert_config(
    key: str,
    content: str,
    frontmatter: Optional[dict] = None
)
```

### 知识管理 API

```python
# 读取（从内存缓存）
vault.get_knowledge(key: str) -> Optional[str]
vault.list_knowledge(category: Optional[str] = None) -> list[str]

# 写入（文件 + 内存 + 数据库）
vault.upsert_knowledge(
    key: str,
    content: str,
    frontmatter: Optional[dict] = None
)

# 删除（文件 + 内存 + 数据库）
vault.delete_knowledge(key: str) -> bool
```

### 元数据 API

```python
# 获取文件元信息
vault.get_file_info(key: str) -> Optional[FileMetadata]

# 统计信息
vault.get_stats() -> dict

# 重新加载
vault.reload()
```

---

## 使用场景

### 场景 1: Agent 启动时构建上下文

```python
vault = MarkdownVaultHybrid("memory_vault")

# 构建 system prompt（全量注入）
system_prompt = f"""
{vault.get_system_config()}

{vault.get_world_config()}

当前用户：
{vault.get_user_config(user_id)}
"""

# 发送到 LLM
response = llm.chat(
    messages=[{"role": "system", "content": system_prompt}]
)
```

### 场景 2: 检索相关知识片段

```python
# 用户问题：Python 装饰器怎么用？

# 1. 通过向量检索找到相关知识
query = "Python 装饰器怎么用"
results = vector_search(query, scope="knowledge")
# → ["facts/python_decorators", "experiences/first_python_question"]

# 2. 加载相关片段
relevant_knowledge = [
    vault.get_knowledge(key)
    for key in results[:3]
]

# 3. 添加到上下文
context = "\n\n".join(relevant_knowledge)
messages.append({"role": "user", "content": f"背景知识:\n{context}\n\n问题: {query}"})
```

### 场景 3: 添加新经历

```python
# 对话结束后，保存重要信息
vault.upsert_knowledge(
    key=f"experiences/{session_id}",
    content=f"""
# 对话摘要 - {date}

主题：{topic}
重点：{highlights}
决策：{decisions}
    """,
    frontmatter={
        "date": date,
        "user_id": user_id,
        "tags": tags,
    }
)

# 自动：
# 1. 写入文件
# 2. 计算 MD5
# 3. 更新内存缓存
# 4. 同步到数据库
# 5. 更新 metadata.json
```

---

## 性能特性

### 启动时间

```
配置文件：10 个 × 5KB = 50KB
知识文件：100 个 × 1KB = 100KB
总计：150KB

加载时间：
- 读取文件：~20ms
- 计算 MD5：~30ms
- 解析 YAML：~50ms
总计：~100ms
```

### 运行时性能

| 操作 | 时间复杂度 | 实际耗时 |
|------|-----------|---------|
| `get_config()` | O(1) | <0.01ms |
| `get_knowledge()` | O(1) | <0.01ms |
| `list_knowledge()` | O(n) | ~0.1ms |
| `upsert_config()` | O(1) + I/O | ~5ms |
| `upsert_knowledge()` | O(1) + I/O | ~5ms |

### 内存占用

```
配置文件：50KB（内存）
知识文件：100KB（内存）
元数据：~10KB
总计：~160KB
```

---

## 优势总结

### 1. 分类清晰
- ✅ config/ 用于全量注入
- ✅ knowledge/ 用于碎片检索
- ✅ 职责单一，易于维护

### 2. 性能优异
- ✅ 启动时一次性加载（~100ms）
- ✅ 运行时纯内存访问（<0.01ms）
- ✅ 内存占用极低（~160KB）

### 3. 变更追踪
- ✅ MD5 自动识别文件变化
- ✅ 只同步变化的文件到数据库
- ✅ 版本号管理

### 4. 灵活扩展
- ✅ 支持数据库同步
- ✅ 支持向量检索集成
- ✅ 支持热重载

### 5. 人工友好
- ✅ 纯 Markdown 文件
- ✅ 可直接编辑
- ✅ Git 版本控制

---

## 与旧设计的对比

| 特性 | 旧设计 | 新设计（混合） | 改进 |
|------|--------|--------------|------|
| 目录层级 | 6+ | 2 | **-67%** |
| 文件分类 | 混乱 | 清晰（config/knowledge） | ✅ |
| 变更检测 | 无 | MD5 追踪 | ✅ |
| 数据库同步 | 无 | 自动同步 | ✅ |
| 性能 | 磁盘 I/O | 内存访问 | **1000x** |
| 可维护性 | 低 | 高 | ✅ |

---

## 未来增强

### 1. 向量检索集成
```python
# 为 knowledge/ 自动生成向量索引
vault.build_vector_index()

# 语义搜索
results = vault.search_knowledge(
    query="Python 装饰器",
    top_k=5
)
```

### 2. 自动摘要
```python
# 自动为长文件生成摘要
vault.generate_summary(
    key="experiences/long_conversation",
    max_length=200
)
```

### 3. 标签管理
```python
# 基于标签的快速检索
vault.get_knowledge_by_tags(
    tags=["python", "advanced"],
    operator="AND"
)
```

### 4. 全文搜索
```python
# 在 frontmatter 和 content 中搜索
vault.full_text_search(
    query="装饰器",
    scope="knowledge"
)
```
