# memory/backends/markdown_hybrid.py
# =========================
# Markdown Vault（混合版 - 最终设计）
# 分类管理：配置文件（全量注入）+ 知识库（碎片检索）
# MD5 追踪文件变化，自动同步到数据库
# =========================

from __future__ import annotations

import json
import yaml
import hashlib
from pathlib import Path
from typing import Optional, TYPE_CHECKING
from dataclasses import dataclass, asdict
from datetime import datetime
from loguru import logger

if TYPE_CHECKING:
    from ..backends.relational import SQLAlchemyBackend

# =============================================================================
# 数据模型
# =============================================================================

@dataclass
class FileMetadata:
    """文件元数据"""
    md5: str                    # MD5 校验和
    synced_at: float            # 上次同步时间戳
    size: int                   # 文件大小（字节）
    version: int                # 版本号
    file_type: str              # 文件类型：config | knowledge
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> FileMetadata:
        return cls(**data)


@dataclass
class MarkdownDocument:
    """Markdown 文档"""
    key: str                    # 唯一标识符（相对路径）
    content: str                # 正文内容
    frontmatter: dict           # YAML 头部元数据
    file_path: Path             # 绝对路径
    file_type: str              # config | knowledge
    md5: str                    # 当前 MD5


class MarkdownVaultError(Exception):
    """Markdown Vault 错误"""
    pass


# =============================================================================
# 工具函数
# =============================================================================

def compute_md5(file_path: Path) -> str:
    """计算文件的 MD5"""
    hasher = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """
    解析 YAML frontmatter
    
    Returns:
        (frontmatter_dict, body_content)
    """
    # 兼容 UTF-8 BOM
    if content.startswith("\ufeff"):
        content = content[1:]
    
    lines = content.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, content
    
    # 查找第二个 ---
    closing_index = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            closing_index = i
            break
    
    if closing_index is None:
        return {}, content
    
    # 解析 YAML
    fm_text = "".join(lines[1:closing_index])
    body = "".join(lines[closing_index + 1:])
    
    try:
        frontmatter = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError as e:
        # logger.warning(f"Failed to parse frontmatter: {e}")
        return {}, content
    
    if not isinstance(frontmatter, dict):
        return {}, content
    
    return frontmatter, body


def create_frontmatter(metadata: dict) -> str:
    """创建 YAML frontmatter"""
    if not metadata:
        return ""
    return "---\n" + yaml.dump(metadata, allow_unicode=True, default_flow_style=False) + "---\n"


# =============================================================================
# MarkdownVaultHybrid - 混合架构
# =============================================================================

class MarkdownVaultHybrid:
    """
    Markdown 混合存储（最终设计）
    
    设计理念：
    1. 分类管理：
       - config/: 系统设定、世界观、用户信息（大文件，全量注入）
       - knowledge/: 经历、知识、记忆（小文件，碎片检索）
    
    2. MD5 追踪：
       - 每个文件都有 MD5 校验和
       - metadata.json 记录所有文件的 MD5 和同步状态
       - 启动时对比 MD5，识别变化的文件
    
    3. 数据库同步：
       - 变化的文件自动同步到数据库
       - config/ → 全文存储（用于 prompt 注入）
       - knowledge/ → 索引存储（用于检索）
    
    目录结构：
    memory_vault/
      ├── config/
      │   ├── system.md         # 系统设定
      │   ├── world.md          # 世界观
      │   └── users/<id>.md     # 用户信息
      ├── knowledge/
      │   ├── experiences/      # 经历片段
      │   │   └── *.md
      │   └── facts/            # 知识条目
      │       └── *.md
      └── metadata.json         # MD5 索引表
    """
    
    def __init__(
        self,
        vault_root: str | Path,
        db_backend: Optional[SQLAlchemyBackend] = None,
        auto_sync: bool = True,
    ):
        """
        初始化 Markdown Vault
        
        Args:
            vault_root: 根目录（必须，来自 config/memory.yaml 中的 vault.root_path）
            db_backend: 数据库后端（可选，用于同步）
            auto_sync: 是否自动同步变化的文件到数据库
        """
        self.vault_root = Path(vault_root)
        self.db_backend = db_backend
        self.auto_sync = auto_sync
        
        # 目录结构
        self.config_dir = self.vault_root / "md"
        self.knowledge_dir = self.vault_root / "knowledge"

        # 确保目录存在
        self.config_dir.mkdir(parents=True, exist_ok=True)
        (self.config_dir / "users").mkdir(parents=True, exist_ok=True)
        (self.knowledge_dir / "experiences").mkdir(parents=True, exist_ok=True)
        (self.knowledge_dir / "facts").mkdir(parents=True, exist_ok=True)
        
        # 元数据索引
        self.metadata_file = self.vault_root / "metadata.json"
        self.metadata: dict[str, FileMetadata] = {}
        
        # 内存缓存
        self._config_cache: dict[str, MarkdownDocument] = {}      # config 文件缓存
        self._knowledge_cache: dict[str, MarkdownDocument] = {}   # knowledge 文件缓存
        
        # 加载元数据和文件
        self._load_metadata()
        self._scan_and_sync()
        self._save_metadata()
        
        # logger.info(f"MarkdownVaultHybrid initialized: "
        # f"{len(self._config_cache)} config files, "
        # f"{len(self._knowledge_cache)} knowledge files")
    
    # =========================================================================
    # 配置文件管理（全量注入）
    # =========================================================================
    
    def get_config(self, key: str) -> Optional[str]:
        """
        获取配置文件内容（从内存缓存）
        
        Args:
            key: 配置键（system, world, user:<id>）
            
        Returns:
            文件正文内容
        """
        doc = self._config_cache.get(key)
        return doc.content if doc else None
    
    def get_system_config(self) -> str:
        """获取系统配置"""
        return self.get_config("system") or ""
    
    def get_world_config(self) -> str:
        """获取世界观配置"""
        return self.get_config("world") or ""
    
    def get_user_config(self, user_id: str) -> str:
        """获取用户配置"""
        return self.get_config(f"user:{user_id}") or ""
    
    def upsert_config(
        self,
        key: str,
        content: str,
        frontmatter: Optional[dict] = None,
    ) -> None:
        """
        新增或更新配置文件
        
        Args:
            key: 配置键
            content: 正文内容
            frontmatter: 元数据（可选）
        """
        file_path = self._get_config_path(key)
        frontmatter = frontmatter or {}
        
        # 1. 写入文件
        file_path.parent.mkdir(parents=True, exist_ok=True)
        full_content = create_frontmatter(frontmatter) + content
        file_path.write_text(full_content, encoding="utf-8")
        
        # 2. 计算 MD5
        md5 = compute_md5(file_path)
        
        # 3. 更新内存缓存
        self._config_cache[key] = MarkdownDocument(
            key=key,
            content=content,
            frontmatter=frontmatter,
            file_path=file_path,
            file_type="config",
            md5=md5,
        )
        
        # 4. 更新元数据
        rel_path = str(file_path.relative_to(self.vault_root))
        old_metadata = self.metadata.get(rel_path)
        version = (old_metadata.version + 1) if old_metadata else 1
        
        self.metadata[rel_path] = FileMetadata(
            md5=md5,
            synced_at=datetime.now().timestamp(),
            size=file_path.stat().st_size,
            version=version,
            file_type="config",
        )
        self._save_metadata()
        
        # 5. 同步到数据库
        if self.auto_sync and self.db_backend:
            self._sync_config_to_db(key, content, frontmatter, md5)
        
        # logger.debug(f"Config upserted: {key} (md5={md5[:8]}, version={version})")
    
    # =========================================================================
    # 知识库管理（碎片检索）
    # =========================================================================
    
    def get_knowledge(self, key: str) -> Optional[str]:
        """
        获取知识条目内容
        
        Args:
            key: 知识键（experiences/<name>, facts/<name>）
            
        Returns:
            文件正文内容
        """
        doc = self._knowledge_cache.get(key)
        return doc.content if doc else None
    
    def list_knowledge(self, category: Optional[str] = None) -> list[str]:
        """
        列出所有知识条目的键
        
        Args:
            category: 分类过滤（experiences, facts）
            
        Returns:
            知识条目键列表
        """
        if category:
            return [k for k in self._knowledge_cache.keys() if k.startswith(f"{category}/")]
        return list(self._knowledge_cache.keys())
    
    def upsert_knowledge(
        self,
        key: str,
        content: str,
        frontmatter: Optional[dict] = None,
    ) -> None:
        """
        新增或更新知识条目
        
        Args:
            key: 知识键（experiences/<name>, facts/<name>）
            content: 正文内容
            frontmatter: 元数据（可选）
        """
        file_path = self._get_knowledge_path(key)
        frontmatter = frontmatter or {}
        
        # 1. 写入文件
        file_path.parent.mkdir(parents=True, exist_ok=True)
        full_content = create_frontmatter(frontmatter) + content
        file_path.write_text(full_content, encoding="utf-8")
        
        # 2. 计算 MD5
        md5 = compute_md5(file_path)
        
        # 3. 更新内存缓存
        self._knowledge_cache[key] = MarkdownDocument(
            key=key,
            content=content,
            frontmatter=frontmatter,
            file_path=file_path,
            file_type="knowledge",
            md5=md5,
        )
        
        # 4. 更新元数据
        rel_path = str(file_path.relative_to(self.vault_root))
        old_metadata = self.metadata.get(rel_path)
        version = (old_metadata.version + 1) if old_metadata else 1
        
        self.metadata[rel_path] = FileMetadata(
            md5=md5,
            synced_at=datetime.now().timestamp(),
            size=file_path.stat().st_size,
            version=version,
            file_type="knowledge",
        )
        self._save_metadata()
        
        # 5. 同步到数据库
        if self.auto_sync and self.db_backend:
            self._sync_knowledge_to_db(key, content, frontmatter, md5)
        
        # logger.debug(f"Knowledge upserted: {key} (md5={md5[:8]}, version={version})")
    
    def delete_knowledge(self, key: str) -> bool:
        """删除知识条目"""
        if key not in self._knowledge_cache:
            return False
        
        doc = self._knowledge_cache[key]
        
        # 1. 删除文件
        if doc.file_path.exists():
            doc.file_path.unlink()
        
        # 2. 删除缓存
        del self._knowledge_cache[key]
        
        # 3. 删除元数据
        rel_path = str(doc.file_path.relative_to(self.vault_root))
        if rel_path in self.metadata:
            del self.metadata[rel_path]
            self._save_metadata()
        
        # 4. 从数据库删除
        if self.db_backend:
            self._delete_knowledge_from_db(key)
        
        # logger.debug(f"Knowledge deleted: {key}")
        return True
    
    # =========================================================================
    # 元数据管理
    # =========================================================================
    
    def _load_metadata(self) -> None:
        """加载元数据索引"""
        if not self.metadata_file.exists():
            self.metadata = {}
            return
        
        try:
            data = json.loads(self.metadata_file.read_text(encoding="utf-8"))
            self.metadata = {
                path: FileMetadata.from_dict(meta)
                for path, meta in data.items()
            }
            # logger.debug(f"Loaded metadata: {len(self.metadata)} files")
        except Exception as e:
            # logger.error(f"Failed to load metadata: {e}")
            self.metadata = {}
    
    def _save_metadata(self) -> None:
        """保存元数据索引"""
        try:
            data = {
                path: meta.to_dict()
                for path, meta in self.metadata.items()
            }
            self.metadata_file.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
        except Exception as e:
            # logger.error(f"Failed to save metadata: {e}")
    
    def _scan_and_sync(self) -> None:
        """扫描所有文件，识别变化并同步"""
        changed_files = []
        seen_paths: set[str] = set()
        
        # 扫描 config/
        for file_path in self.config_dir.rglob("*.md"):
            rel_path = str(file_path.relative_to(self.vault_root))
            seen_paths.add(rel_path)
            current_md5 = compute_md5(file_path)
            
            # 检查是否变化
            old_metadata = self.metadata.get(rel_path)
            changed = (old_metadata is None) or (old_metadata.md5 != current_md5)
            if changed:
                changed_files.append((file_path, "config", current_md5))
            self._load_config_file(file_path, current_md5, old_metadata, changed)
        
        # 扫描 knowledge/
        for file_path in self.knowledge_dir.rglob("*.md"):
            rel_path = str(file_path.relative_to(self.vault_root))
            seen_paths.add(rel_path)
            current_md5 = compute_md5(file_path)
            
            # 检查是否变化
            old_metadata = self.metadata.get(rel_path)
            changed = (old_metadata is None) or (old_metadata.md5 != current_md5)
            if changed:
                changed_files.append((file_path, "knowledge", current_md5))
            self._load_knowledge_file(file_path, current_md5, old_metadata, changed)

        # 清理已删除文件的残留元数据
        stale_paths = [path for path in self.metadata.keys() if path not in seen_paths]
        for stale_path in stale_paths:
            del self.metadata[stale_path]
        if stale_paths:
            # logger.info(f"Pruned {len(stale_paths)} stale metadata entries")
        
        # 同步变化的文件
        if changed_files and self.auto_sync and self.db_backend:
            synced_at = datetime.now().timestamp()
            # logger.info(f"Syncing {len(changed_files)} changed files to database...")
            for file_path, file_type, md5 in changed_files:
                if file_type == "config":
                    key = self._path_to_config_key(file_path)
                    doc = self._config_cache.get(key)
                    if doc:
                        self._sync_config_to_db(key, doc.content, doc.frontmatter, md5)
                        self._mark_synced(file_path, synced_at)
                elif file_type == "knowledge":
                    key = self._path_to_knowledge_key(file_path)
                    doc = self._knowledge_cache.get(key)
                    if doc:
                        self._sync_knowledge_to_db(key, doc.content, doc.frontmatter, md5)
                        self._mark_synced(file_path, synced_at)
    
    def _load_config_file(
        self,
        file_path: Path,
        md5: str,
        old_metadata: Optional[FileMetadata],
        changed: bool,
    ) -> None:
        """加载单个配置文件"""
        try:
            content = file_path.read_text(encoding="utf-8")
            frontmatter, body = parse_frontmatter(content)
            key = self._path_to_config_key(file_path)
            
            self._config_cache[key] = MarkdownDocument(
                key=key,
                content=body.strip(),
                frontmatter=frontmatter,
                file_path=file_path,
                file_type="config",
                md5=md5,
            )
            
            # 更新元数据
            rel_path = str(file_path.relative_to(self.vault_root))
            version = 1
            synced_at = 0.0
            if old_metadata:
                version = old_metadata.version + 1 if changed else old_metadata.version
                synced_at = old_metadata.synced_at
            self.metadata[rel_path] = FileMetadata(
                md5=md5,
                synced_at=synced_at,
                size=file_path.stat().st_size,
                version=version,
                file_type="config",
            )
        except Exception as e:
            # logger.error(f"Failed to load config file {file_path}: {e}")
    
    def _load_knowledge_file(
        self,
        file_path: Path,
        md5: str,
        old_metadata: Optional[FileMetadata],
        changed: bool,
    ) -> None:
        """加载单个知识文件"""
        try:
            content = file_path.read_text(encoding="utf-8")
            frontmatter, body = parse_frontmatter(content)
            key = self._path_to_knowledge_key(file_path)
            
            self._knowledge_cache[key] = MarkdownDocument(
                key=key,
                content=body.strip(),
                frontmatter=frontmatter,
                file_path=file_path,
                file_type="knowledge",
                md5=md5,
            )
            
            # 更新元数据
            rel_path = str(file_path.relative_to(self.vault_root))
            version = 1
            synced_at = 0.0
            if old_metadata:
                version = old_metadata.version + 1 if changed else old_metadata.version
                synced_at = old_metadata.synced_at
            self.metadata[rel_path] = FileMetadata(
                md5=md5,
                synced_at=synced_at,
                size=file_path.stat().st_size,
                version=version,
                file_type="knowledge",
            )
        except Exception as e:
            # logger.error(f"Failed to load knowledge file {file_path}: {e}")
    
    # =========================================================================
    # 路径转换
    # =========================================================================
    
    def _get_config_path(self, key: str) -> Path:
        """配置键 → 文件路径"""
        key = self._sanitize_config_key(key)
        if key == "system":
            return self.config_dir / "system.md"
        elif key == "world":
            return self.config_dir / "world.md"
        elif key.startswith("user:"):
            user_id = key[5:]
            return self.config_dir / "users" / f"{user_id}.md"
        else:
            return self.config_dir / f"{key}.md"
    
    def _get_knowledge_path(self, key: str) -> Path:
        """知识键 → 文件路径"""
        key = self._sanitize_knowledge_key(key)
        return self.knowledge_dir / f"{key}.md"

    def _sanitize_config_key(self, key: str) -> str:
        """验证并规范化配置 key，阻止目录穿越"""
        if key is None:
            raise MarkdownVaultError("Config key is required")
        key = key.strip()
        if not key:
            raise MarkdownVaultError("Config key is required")
        if key in ("system", "world"):
            return key
        if key.startswith("user:"):
            user_id = self._sanitize_user_id(key[5:])
            return f"user:{user_id}"
        if "/" in key or "\\" in key:
            raise MarkdownVaultError(f"Invalid config key: {key}")
        if key in (".", ".."):
            raise MarkdownVaultError(f"Invalid config key: {key}")
        if ":" in key:
            raise MarkdownVaultError(f"Invalid config key: {key}")
        return key

    def _sanitize_user_id(self, user_id: str) -> str:
        """验证并规范化 user_id，阻止目录穿越"""
        if user_id is None:
            raise MarkdownVaultError("User id is required")
        user_id = user_id.strip()
        if not user_id:
            raise MarkdownVaultError("User id is required")
        if any(ch in user_id for ch in ["/", "\\", ":"]):
            raise MarkdownVaultError(f"Invalid user id: {user_id}")
        if user_id in (".", ".."):
            raise MarkdownVaultError(f"Invalid user id: {user_id}")
        return user_id

    def _sanitize_knowledge_key(self, key: str) -> str:
        """验证并规范化知识 key，阻止目录穿越"""
        if key is None:
            raise MarkdownVaultError("Knowledge key is required")
        key = key.strip()
        if not key:
            raise MarkdownVaultError("Knowledge key is required")
        if key.startswith(("/", "\\")):
            raise MarkdownVaultError(f"Invalid knowledge key: {key}")
        if "\\" in key:
            raise MarkdownVaultError(f"Invalid knowledge key: {key}")
        if ":" in key:
            raise MarkdownVaultError(f"Invalid knowledge key: {key}")
        parts = key.split("/")
        if any(part in ("", ".", "..") for part in parts):
            raise MarkdownVaultError(f"Invalid knowledge key: {key}")
        return key

    def _mark_synced(self, file_path: Path, synced_at: float) -> None:
        """更新元数据的同步时间"""
        rel_path = str(file_path.relative_to(self.vault_root))
        if rel_path in self.metadata:
            self.metadata[rel_path].synced_at = synced_at
    
    def _path_to_config_key(self, file_path: Path) -> str:
        """文件路径 → 配置键"""
        rel_path = file_path.relative_to(self.config_dir)
        
        if rel_path == Path("system.md"):
            return "system"
        elif rel_path == Path("world.md"):
            return "world"
        elif rel_path.parent == Path("users"):
            return f"user:{rel_path.stem}"
        else:
            return rel_path.stem
    
    def _path_to_knowledge_key(self, file_path: Path) -> str:
        """文件路径 → 知识键"""
        rel_path = file_path.relative_to(self.knowledge_dir)
        return str(rel_path.with_suffix(""))
    
    # =========================================================================
    # 数据库同步（预留接口）
    # =========================================================================
    
    def _sync_config_to_db(
        self,
        key: str,
        content: str,
        frontmatter: dict,
        md5: str,
    ) -> None:
        """同步配置文件到数据库（全文存储）"""
        if not self.db_backend:
            return
        
        try:
            import json
            config_dict = {
                "config_key": key,
                "content": content,
                "frontmatter_json": json.dumps(frontmatter, ensure_ascii=False),
                "md5": md5,
            }
            self.db_backend.save_config_dict(config_dict)
            # logger.debug(f"Synced config to DB: {key}")
        except Exception as e:
            # logger.warning(f"Failed to sync config to DB: {key}, error: {e}")
    
    def _sync_knowledge_to_db(
        self,
        key: str,
        content: str,
        frontmatter: dict,
        md5: str,
    ) -> None:
        """同步知识条目到数据库（索引存储）"""
        if not self.db_backend:
            return
        
        try:
            import json
            knowledge_dict = {
                "knowledge_key": key,
                "content": content,
                "frontmatter_json": json.dumps(frontmatter, ensure_ascii=False),
                "md5": md5,
            }
            self.db_backend.save_knowledge_dict(knowledge_dict)
            # logger.debug(f"Synced knowledge to DB: {key}")
        except Exception as e:
            # logger.warning(f"Failed to sync knowledge to DB: {key}, error: {e}")
    
    def _delete_knowledge_from_db(self, key: str) -> None:
        """从数据库删除知识条目"""
        if not self.db_backend:
            return

        try:
            deleted = self.db_backend.delete_knowledge_dict(key)
            # logger.debug(f"Deleted knowledge from DB: {key} (deleted={deleted})")
        except Exception as e:
            # logger.warning(f"Failed to delete knowledge from DB: {key}, error: {e}")
    
    # =========================================================================
    # 工具方法
    # =========================================================================
    
    def get_file_info(self, key: str) -> Optional[FileMetadata]:
        """获取文件的元数据信息"""
        # 尝试从 config 和 knowledge 查找
        doc = self._config_cache.get(key) or self._knowledge_cache.get(key)
        if not doc:
            return None
        
        rel_path = str(doc.file_path.relative_to(self.vault_root))
        return self.metadata.get(rel_path)
    
    def reload(self) -> None:
        """重新扫描并加载所有文件"""
        self._config_cache.clear()
        self._knowledge_cache.clear()
        self._scan_and_sync()
        self._save_metadata()
        # logger.info("Vault reloaded")
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            "config_files": len(self._config_cache),
            "knowledge_files": len(self._knowledge_cache),
            "total_files": len(self.metadata),
            "metadata_size": self.metadata_file.stat().st_size if self.metadata_file.exists() else 0,
        }


__all__ = ["MarkdownVaultHybrid", "MarkdownDocument", "FileMetadata", "MarkdownVaultError"]
