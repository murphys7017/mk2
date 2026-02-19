# Memory Vault 重构设计文档

## 问题分析

### 原设计的问题

1. **目录结构过于复杂**
   ```
   memory_vault/
   ├── global/persona.md          # 单文件
   ├── global/knowledge/*.md      # 多个小文件（碎片化）
   ├── users/<id>/profile.md      # 每个用户多个文件
   ├── users/<id>/constraints.md
   ├── users/<id>/preferences.md
   ├── episodic/<id>/*.md         # 事件分散
   ├── kb/*.md                    # 知识库（定位不明）
   └── sessions/*.md              # 会话（应该在DB）
   ```

2. **功能过度设计**
   - `search_text()` - 不需要搜索
   - `list()` - 递归扫描目录效率低
   - 向量索引集成 - 这些是静态配置，不需要语义搜索
   - 复杂的路径计算 - `_get_file_path()` 逻辑复杂

3. **性能问题**
   - 每次 `get()` 都读磁盘
   - 重复解析 YAML frontmatter
   - 没有缓存机制

4. **职责不清**
   - `episodic/` - 短期事件应该在数据库 Events 表
   - `kb/` - 知识库定位不明确
   - `sessions/` - 会话摘要应该在数据库 Turns 表

---

## 新设计方案

### 核心理念

```
这些 Markdown 文件的真实用途：
1. system.md  → 系统人设（全文注入 system prompt）
2. users/*.md → 用户画像（全文注入 user context）

特点：
- 文件少（系统1个 + 每用户1个）
- 内容静态（不频繁更改）
- 全文使用（不需要搜索/检索/分片）

→ 最优策略：启动时全部加载到内存
```

### 新目录结构

```
memory_vault/
├── system.md           # 系统配置（原 global/persona.md）
└── users/
    ├── user_001.md     # 用户配置（合并 profile/constraints/preferences）
    ├── user_002.md
    └── ...

[删除的目录]
❌ episodic/  → 移到数据库 Events 表
❌ kb/        → 删除或合并到 system.md
❌ sessions/  → 移到数据库 Turns 表
```

### 文件格式示例

#### system.md
```markdown
---
version: 1.0
updated_at: 2024-02-19
type: system_prompt
---
# 系统人设

你是一个友好的AI助手。

## 核心特质
- 有帮助的
- 知识渊博的
- 耐心细致的

## 约束
- 不能提供医疗建议
- 不能参与政治讨论
```

#### users/user_001.md
```markdown
---
user_id: user_001
name: 张三
created_at: 2024-01-01
preferences:
  language: zh-CN
  tone: formal
---
# 用户画像

职业：软件工程师
兴趣：AI、编程、阅读

## 偏好设置
- 喜欢详细的技术解释
- 偏好使用代码示例

## 约束
- 工作时间请简短回复
```

---

## 新实现：MarkdownVault

### 核心特性

```python
class MarkdownVault:
    """
    轻量级 Markdown 配置存储
    
    特点：
    1. 启动时加载所有文件到内存（配置不多，可全部加载）
    2. 运行时纯内存访问（零 I/O）
    3. 修改时同步更新文件和内存
    4. 简单的 key-value 接口
    """
    
    def __init__(self, vault_root: str):
        self.vault_root = Path(vault_root)
        self._documents: dict[str, MarkdownDocument] = {}
        self._load_all()  # 启动时加载
    
    # 核心 API（简单高效）
    def get(self, key: str) -> Optional[str]:
        """从内存获取（极速）"""
        ...
    
    def upsert(self, key: str, content: str, metadata: dict = None):
        """更新文件 + 内存"""
        ...
    
    # 便利方法
    def get_system_prompt(self) -> str:
        """获取系统 prompt"""
        return self.get("system") or ""
    
    def get_user_profile(self, user_id: str) -> str:
        """获取用户配置"""
        return self.get(f"user:{user_id}") or ""
```

### Key 设计

| Key 格式 | 文件路径 | 用途 |
|---------|---------|------|
| `system` | `memory_vault/system.md` | 系统 prompt |
| `user:123` | `memory_vault/users/123.md` | 用户123的配置 |
| `context:xxx` | `memory_vault/context/xxx.md` | 长期上下文（可选） |

---

## 性能对比

### 原设计
```python
# 每次调用都需要：
def get_recent_events(...):
    persona = markdown_store.get("global", "persona", "main")
    # ↓
    # 1. 计算路径: _get_file_path()
    # 2. 读磁盘: file_path.read_text()
    # 3. 解析 YAML: _parse_frontmatter()
    # 4. 构造对象: MemoryItem(...)
```

### 新设计
```python
# 启动时加载一次：
vault = MarkdownVault()  # 加载所有文件到内存

# 运行时：
system_prompt = vault.get_system_prompt()
# ↓ 纯内存访问，O(1)
# 无磁盘 I/O，无解析开销
```

**性能提升**：
- 读取速度：`1000x+`（内存 vs 磁盘）
- 启动时间：`+50ms`（一次性加载所有文件）
- 内存占用：`<1MB`（假设10个用户，每个10KB）

---

## 迁移指南

### Step 1: 整理现有文件

```bash
# 原目录
memory_vault/
  global/persona.md
  users/user_123/profile.md
  users/user_123/constraints.md
  ...

# 迁移后
memory_vault/
  system.md                    # ← global/persona.md
  users/user_123.md            # ← 合并 profile + constraints
```

### Step 2: 合并用户文件

对于每个用户 `<id>`，合并：
- `users/<id>/profile.md`
- `users/<id>/constraints.md`
- `users/<id>/preferences.md`

→ `users/<id>.md`

### Step 3: 更新代码

```python
# 旧代码
from src.memory.backends.markdown import MarkdownItemStore
store = MarkdownItemStore("memory_vault")
persona = store.get("global", "persona", "main")

# 新代码
from src.memory.backends.markdown_simple import MarkdownVault
vault = MarkdownVault("memory_vault")
persona = vault.get_system_prompt()
```

---

## 删除/移动的功能

| 功能 | 原位置 | 新位置 | 原因 |
|------|--------|--------|------|
| `episodic/*` | Markdown 文件 | 数据库 Events 表 | 短期事件应该结构化存储 |
| `kb/*` | 单独目录 | 合并到 `system.md` 或删除 | 定位不明确 |
| `sessions/*` | Markdown 文件 | 数据库 Turns 表 | 会话数据应该结构化 |
| `search_text()` | MarkdownItemStore | ❌ 删除 | 不需要搜索 |
| `list(scope, kind)` | MarkdownItemStore | `list_all()` | 简化为列出所有 key |
| 向量索引集成 | MarkdownItemStore | ❌ 删除 | 静态配置不需要向量搜索 |

---

## 未来增强（可选）

### 1. 数据库同步（推荐）

```python
class MarkdownVault:
    def __init__(self, vault_root: str, db_backend: Optional[DB] = None):
        self.db = db_backend
        self._load_all()
        
        # 如果有DB，同步到数据库
        if self.db:
            self._sync_to_db()
    
    def _sync_to_db(self):
        """启动时将所有文档同步到数据库"""
        for key, doc in self._documents.items():
            self.db.upsert_config(key, doc.content, doc.metadata)
    
    def upsert(self, key, content, metadata):
        # 1. 写文件
        self._write_file(key, content, metadata)
        # 2. 更新内存
        self._documents[key] = ...
        # 3. 同步到数据库
        if self.db:
            self.db.upsert_config(key, content, metadata)
```

### 2. 热重载（监听文件变化）

```python
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class VaultFileWatcher(FileSystemEventHandler):
    def on_modified(self, event):
        if event.src_path.endswith('.md'):
            vault.reload()  # 重新加载
```

### 3. 版本管理

在 frontmatter 中记录版本：
```yaml
---
version: 2.0
previous_versions:
  - version: 1.0
    updated_at: 2024-01-01
    hash: abc123
---
```

---

## 总结

### 优化成果

| 指标 | 原设计 | 新设计 | 改进 |
|------|--------|--------|------|
| 目录数 | 6+ | 2 | -67% |
| 代码行数 | ~320 行 | ~260 行 | -19% |
| 读取性能 | 磁盘 I/O | 内存访问 | 1000x+ |
| 启动时间 | 0ms | +50ms | 可接受 |
| 功能复杂度 | 高（搜索/索引/多层级） | 低（简单 KV） | 大幅简化 |

### 设计原则

✅ **YAGNI** (You Aren't Gonna Need It) - 删除不需要的功能  
✅ **KISS** (Keep It Simple, Stupid) - 简单的 key-value 存储  
✅ **性能优先** - 启动时加载，运行时零 I/O  
✅ **职责单一** - 只管理静态配置，事件数据归数据库
