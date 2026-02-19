#!/usr/bin/env python3
# tools/memory_reindex.py
# =========================
# Memory 子系统重索引工具
# 用于重建 Markdown Vault 中所有项的向量索引
# =========================

from __future__ import annotations

import sys
import argparse
import logging
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.memory.config import MemoryConfigProvider
from src.memory.backends.relational import SQLAlchemyBackend
from src.memory.backends.vector import InMemoryVectorIndex, DeterministicEmbeddingProvider
from src.memory.service import MemoryService


# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def create_memory_service(config_path: str | Path) -> MemoryService:
    """
    从配置创建 MemoryService
    """
    config_provider = MemoryConfigProvider(config_path)
    config = config_provider.snapshot()
    
    # 创建数据库后端
    db_backend = SQLAlchemyBackend(
        config.database.dsn,
        pool_size=config.database.pool_size,
        max_overflow=config.database.max_overflow,
    )
    
    # 创建向量索引（如果启用）
    vector_index = None
    embedding_provider = None
    
    if config.vector.enabled:
        if config.vector.type == "memory":
            embedding_provider = DeterministicEmbeddingProvider(
                dim=config.vector.embedding.dimension
            )
            vector_index = InMemoryVectorIndex(embedding_provider)
        # 其他向量库的实现可以在这里添加
        else:
            logger.warning(f"Vector index type '{config.vector.type}' not yet implemented, using memory")
            embedding_provider = DeterministicEmbeddingProvider(
                dim=config.vector.embedding.dimension
            )
            vector_index = InMemoryVectorIndex(embedding_provider)
    
    # 创建 MemoryService
    service = MemoryService(
        db_backend=db_backend,
        markdown_vault_path=config.vault.root_path,
        vector_index=vector_index,
        embedding_provider=embedding_provider,
        failed_events_max_in_memory=config.failure_queue.max_in_memory,
        failed_events_spill_batch_size=config.failure_queue.spill_batch_size,
        failed_events_dump_max_bytes=config.failure_queue.max_dump_file_size_mb * 1024 * 1024,
        failed_events_dump_backups=config.failure_queue.max_dump_backups,
        failed_events_max_retries=config.failure_queue.max_retries,
    )
    
    return service


def _iter_vault_documents(service: MemoryService):
    """迭代当前 vault 中可用于向量索引的文档。"""
    if not service.markdown_vault:
        return []
    
    docs = []
    # Knowledge 文档：优先用于检索
    for key in service.markdown_vault.list_knowledge():
        content = service.markdown_vault.get_knowledge(key) or ""
        if not content.strip():
            continue
        docs.append(
            (
                f"kb/knowledge/{key}",
                content,
                {"scope": "kb", "kind": "knowledge", "key": key, "source": "markdown_vault"},
            )
        )
    
    # Config 文档：作为可选补充索引
    config_cache = getattr(service.markdown_vault, "_config_cache", {})
    for key, doc in config_cache.items():
        content = getattr(doc, "content", "") or ""
        if not content.strip():
            continue
        docs.append(
            (
                f"config/config/{key}",
                content,
                {"scope": "config", "kind": "config", "key": key, "source": "markdown_vault"},
            )
        )
    
    return docs


def reindex(config_path: str | Path, force: bool = False) -> int:
    """
    重建所有项的向量索引
    
    Args:
        config_path: 配置文件路径
        force: 是否强制重建（即使向量库未启用）
        
    Returns:
        重建的项数
    """
    logger.info(f"Loading config from {config_path}")
    
    try:
        service = create_memory_service(config_path)
    except Exception as e:
        logger.error(f"Failed to create MemoryService: {e}")
        return 0
    
    # 如果向量索引未启用，提示
    if not service.vector_index and not force:
        logger.info("Vector index not enabled, skipping reindex")
        logger.info("Use --force to reindex anyway (to in-memory index)")
        service.close()
        return 0
    
    if not service.vector_index:
        logger.warning("Vector index not available, reindex skipped")
        service.close()
        return 0
    
    logger.info("Starting reindex...")
    service.vector_index.clear()
    count = 0
    for item_id, content, metadata in _iter_vault_documents(service):
        service.vector_index.upsert(item_id, content, metadata)
        count += 1
    logger.info(f"Reindexed {count} items successfully")
    
    service.close()
    return count


def list_items(config_path: str | Path, scope: str | None = None) -> int:
    """
    列出 Vault 中的所有项
    
    Args:
        config_path: 配置文件路径
        scope: 作用域过滤（可选）
        
    Returns:
        项数
    """
    logger.info(f"Loading config from {config_path}")
    
    try:
        service = create_memory_service(config_path)
    except Exception as e:
        logger.error(f"Failed to create MemoryService: {e}")
        return 0
    
    logger.info("Listing items...")

    vault = service.markdown_vault
    if not vault:
        logger.warning("Markdown vault unavailable")
        service.close()
        return 0

    total = 0
    normalized_scope = (scope or "").strip().lower()

    list_configs = normalized_scope in ("", "config")
    list_knowledge = normalized_scope in ("", "knowledge", "kb")

    if normalized_scope and not (list_configs or list_knowledge):
        logger.warning("Unsupported scope '%s'. Use: config / knowledge / kb", scope)

    if list_configs:
        config_cache = getattr(vault, "_config_cache", {})
        config_keys = sorted(config_cache.keys())
        logger.info(f"  config: {len(config_keys)} items")
        for key in config_keys:
            content = vault.get_config(key) or ""
            logger.info(f"    - config/{key}: {content[:50]}")
        total += len(config_keys)

    if list_knowledge:
        knowledge_keys = sorted(vault.list_knowledge())
        logger.info(f"  knowledge: {len(knowledge_keys)} items")
        for key in knowledge_keys:
            content = vault.get_knowledge(key) or ""
            logger.info(f"    - knowledge/{key}: {content[:50]}")
        total += len(knowledge_keys)
    
    service.close()
    return total


def main():
    parser = argparse.ArgumentParser(description="Memory 子系统工具")
    subparsers = parser.add_subparsers(dest="command", help="命令")
    
    # reindex 命令
    reindex_parser = subparsers.add_parser("reindex", help="重建向量索引")
    reindex_parser.add_argument(
        "-c", "--config",
        default="config/memory.yaml",
        help="配置文件路径（default: config/memory.yaml）"
    )
    reindex_parser.add_argument(
        "--force",
        action="store_true",
        help="强制重建（即使向量库未启用）"
    )
    
    # list 命令
    list_parser = subparsers.add_parser("list", help="列出所有项")
    list_parser.add_argument(
        "-c", "--config",
        default="config/memory.yaml",
        help="配置文件路径（default: config/memory.yaml）"
    )
    list_parser.add_argument(
        "-s", "--scope",
        help="作用域过滤（config/knowledge/kb）"
    )
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    if args.command == "reindex":
        count = reindex(args.config, force=args.force)
        return 0 if count >= 0 else 1
    elif args.command == "list":
        count = list_items(args.config, scope=args.scope)
        return 0
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
