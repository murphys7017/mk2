"""
Markdown Vault 混合架构使用示例
演示配置文件（全量注入）+ 知识库（碎片检索）+ MD5 追踪
"""

from pathlib import Path
from src.memory.backends.markdown_hybrid import MarkdownVaultHybrid


def example_basic_usage():
    """基础使用示例"""
    print("=== 示例 1: 基础使用 ===\n")
    
    # 1. 初始化 Vault
    vault = MarkdownVaultHybrid("memory_vault")
    
    # 2. 设置配置文件（第一类：全量注入）
    vault.upsert_config(
        key="system",
        content="""
# 系统设定

你是一个友好的 AI 助手。

## 核心特质
- 有帮助的
- 知识渊博
- 耐心细致
        """.strip(),
        frontmatter={
            "version": "1.0",
            "author": "system",
        }
    )
    print("✓ 系统配置已保存")
    
    vault.upsert_config(
        key="world",
        content="""
# 世界观设定

这是一个科幻世界，时间设定在 2150 年。

## 科技水平
- 星际旅行已实现
- AI 已广泛应用
- 量子计算普及
        """.strip(),
        frontmatter={
            "version": "1.0",
            "setting": "sci-fi",
        }
    )
    print("✓ 世界观配置已保存")
    
    vault.upsert_config(
        key="user:alice",
        content="""
# 用户信息

姓名：Alice
职业：软件工程师

## 偏好
- 喜欢详细解释
- 偏好代码示例
        """.strip(),
        frontmatter={
            "user_id": "alice",
            "created_at": "2024-01-01",
        }
    )
    print("✓ 用户配置已保存")
    
    # 3. 添加知识条目（第二类：碎片检索）
    vault.upsert_knowledge(
        key="experiences/first_meeting",
        content="""
# 第一次见面

时间：2024-01-15
地点：咖啡厅

Alice 询问了关于 Python 装饰器的问题。
        """.strip(),
        frontmatter={
            "date": "2024-01-15",
            "participants": ["Alice"],
            "tags": ["python", "meeting"],
        }
    )
    print("✓ 经历条目已保存")
    
    vault.upsert_knowledge(
        key="facts/python_decorators",
        content="""
# Python 装饰器

装饰器是一种设计模式，允许在不修改函数代码的情况下增强函数功能。

## 基本语法
```python
@decorator
def function():
    pass
```
        """.strip(),
        frontmatter={
            "topic": "python",
            "difficulty": "intermediate",
        }
    )
    print("✓ 知识条目已保存")
    
    # 4. 读取配置
    print("\n--- 读取配置 ---")
    system_config = vault.get_system_config()
    print(f"系统配置长度: {len(system_config)} 字符")
    
    world_config = vault.get_world_config()
    print(f"世界观配置长度: {len(world_config)} 字符")
    
    user_config = vault.get_user_config("alice")
    print(f"用户配置长度: {len(user_config)} 字符")
    
    # 5. 读取知识
    print("\n--- 读取知识 ---")
    experience = vault.get_knowledge("experiences/first_meeting")
    print(f"经历条目长度: {len(experience)} 字符")
    
    fact = vault.get_knowledge("facts/python_decorators")
    print(f"知识条目长度: {len(fact)} 字符")
    
    # 6. 列出知识
    print("\n--- 知识列表 ---")
    all_experiences = vault.list_knowledge("experiences")
    print(f"所有经历: {all_experiences}")
    
    all_facts = vault.list_knowledge("facts")
    print(f"所有知识: {all_facts}")
    
    # 7. 查看统计
    print("\n--- 统计信息 ---")
    stats = vault.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    print("\n✅ 示例 1 完成\n")


def example_md5_tracking():
    """MD5 追踪示例"""
    print("=== 示例 2: MD5 追踪 ===\n")
    
    vault = MarkdownVaultHybrid("memory_vault")
    
    # 1. 创建一个配置文件
    vault.upsert_config(
        key="system",
        content="原始版本",
        frontmatter={"version": "1.0"}
    )
    
    # 查看元数据
    info = vault.get_file_info("system")
    if info:
        print(f"文件创建:")
        print(f"  MD5: {info.md5}")
        print(f"  版本: {info.version}")
        print(f"  大小: {info.size} 字节")
    
    # 2. 修改文件
    vault.upsert_config(
        key="system",
        content="修改后的版本（内容更长了）",
        frontmatter={"version": "2.0"}
    )
    
    # 查看新元数据
    info = vault.get_file_info("system")
    if info:
        print(f"\n文件更新:")
        print(f"  MD5: {info.md5}")
        print(f"  版本: {info.version}")
        print(f"  大小: {info.size} 字节")
    
    # 3. 模拟重启：重新初始化 Vault
    print("\n--- 模拟系统重启 ---")
    vault2 = MarkdownVaultHybrid("memory_vault")
    
    # 由于内容没变，不会触发同步
    print("✓ Vault 重新加载（未变化的文件从缓存加载）")
    
    # 4. 手动修改文件（模拟外部编辑）
    config_file = Path("memory_vault/config/system.md")
    config_file.write_text(
        "---\nversion: '3.0'\n---\n外部修改的内容",
        encoding="utf-8"
    )
    
    # 重新加载
    vault2.reload()
    print("✓ 检测到文件变化，重新加载")
    
    info = vault2.get_file_info("system")
    if info:
        print(f"  新 MD5: {info.md5}")
        print(f"  新版本: {info.version}")
    
    print("\n✅ 示例 2 完成\n")


def example_directory_structure():
    """展示目录结构"""
    print("=== 示例 3: 目录结构 ===\n")
    
    vault = MarkdownVaultHybrid("memory_vault")
    
    # 添加各种文件
    vault.upsert_config("system", "系统配置")
    vault.upsert_config("world", "世界观")
    vault.upsert_config("user:alice", "Alice 的配置")
    vault.upsert_config("user:bob", "Bob 的配置")
    
    vault.upsert_knowledge("experiences/exp_001", "经历1")
    vault.upsert_knowledge("experiences/exp_002", "经历2")
    vault.upsert_knowledge("facts/fact_001", "知识1")
    vault.upsert_knowledge("facts/fact_002", "知识2")
    vault.upsert_knowledge("facts/fact_003", "知识3")
    
    print("创建的目录结构:")
    print("""
    memory_vault/
    ├── config/
    │   ├── system.md           ← 系统配置（全量注入）
    │   ├── world.md            ← 世界观（全量注入）
    │   └── users/
    │       ├── alice.md        ← Alice 配置（全量注入）
    │       └── bob.md          ← Bob 配置（全量注入）
    ├── knowledge/
    │   ├── experiences/
    │   │   ├── exp_001.md      ← 经历片段（碎片检索）
    │   │   └── exp_002.md
    │   └── facts/
    │       ├── fact_001.md     ← 知识条目（碎片检索）
    │       ├── fact_002.md
    │       └── fact_003.md
    └── metadata.json           ← MD5 索引表
    """)
    
    stats = vault.get_stats()
    print(f"统计:")
    print(f"  配置文件: {stats['config_files']} 个")
    print(f"  知识文件: {stats['knowledge_files']} 个")
    print(f"  总文件数: {stats['total_files']} 个")
    
    print("\n✅ 示例 3 完成\n")


def example_usage_pattern():
    """典型使用模式"""
    print("=== 示例 4: 典型使用模式 ===\n")
    
    vault = MarkdownVaultHybrid("memory_vault")
    
    # 场景：构建 Agent 的上下文
    print("场景：构建 Agent 上下文\n")
    
    # 1. 获取全量注入的配置（用于 system prompt）
    system_config = vault.get_system_config()
    world_config = vault.get_world_config()
    user_config = vault.get_user_config("alice")
    
    # 构建 system prompt
    system_prompt = f"""
{system_config}

{world_config}

当前用户信息：
{user_config}
    """.strip()
    
    print(f"✓ System Prompt 构建完成 ({len(system_prompt)} 字符)")
    
    # 2. 获取相关的知识片段（用于 RAG 检索）
    # 注意：这里只是演示，实际应该通过向量搜索或关键词检索
    all_experiences = vault.list_knowledge("experiences")
    print(f"✓ 可检索经历: {len(all_experiences)} 条")
    
    all_facts = vault.list_knowledge("facts")
    print(f"✓ 可检索知识: {len(all_facts)} 条")
    
    # 3. 假设检索到相关知识
    relevant_fact = vault.get_knowledge("facts/python_decorators")
    if relevant_fact:
        print(f"✓ 检索到相关知识: {relevant_fact[:50]}...")
    
    print("\n使用模式总结:")
    print("  1. config/ → 全文注入到 system prompt")
    print("  2. knowledge/ → 通过检索添加相关片段到 context")
    print("  3. MD5 追踪确保数据库与文件同步")
    
    print("\n✅ 示例 4 完成\n")


def example_metadata_json():
    """展示 metadata.json 的内容"""
    print("=== 示例 5: metadata.json ===\n")
    
    vault = MarkdownVaultHybrid("memory_vault")
    
    # 添加一些文件
    vault.upsert_config("system", "系统配置", {"version": "1.0"})
    vault.upsert_knowledge("facts/example", "示例知识", {"topic": "demo"})
    
    # 查看 metadata.json
    metadata_file = Path("memory_vault/metadata.json")
    if metadata_file.exists():
        import json
        metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
        
        print("metadata.json 内容:")
        print(json.dumps(metadata, indent=2, ensure_ascii=False))
    
    print("\n字段说明:")
    print("  md5: 文件的 MD5 校验和")
    print("  synced_at: 上次同步到数据库的时间戳")
    print("  size: 文件大小（字节）")
    print("  version: 版本号（每次修改递增）")
    print("  file_type: 文件类型（config | knowledge）")
    
    print("\n✅ 示例 5 完成\n")


def main():
    """运行所有示例"""
    # 清理旧数据
    import shutil
    if Path("memory_vault").exists():
        shutil.rmtree("memory_vault")
    
    try:
        example_basic_usage()
        example_md5_tracking()
        example_directory_structure()
        example_usage_pattern()
        example_metadata_json()
        
        print("🎉 所有示例运行完成！")
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
