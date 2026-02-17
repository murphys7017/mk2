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
    db_backend = SQLAlchemyBackend(config.database.dsn)
    
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
    )
    
    return service


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
    
    config = service.markdown_store
    
    # 如果向量索引未启用，提示
    if not service.vector_index and not force:
        logger.info("Vector index not enabled, skipping reindex")
        logger.info("Use --force to reindex anyway (to in-memory index)")
    
    logger.info("Starting reindex...")
    count = service.reindex_all_items()
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
    
    scopes = [scope] if scope else ["global", "user", "episodic", "kb", "session"]
    total = 0
    
    for s in scopes:
        items = service.get_items(s)
        logger.info(f"  {s}: {len(items)} items")
        for item in items:
            logger.info(f"    - {item.scope}/{item.kind}/{item.key}: {item.content[:50]}")
        total += len(items)
    
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
        help="作用域过滤（global/user/episodic/kb/session）"
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
