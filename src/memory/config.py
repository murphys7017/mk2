# src/memory/config.py
# =========================
# Memory 子系统配置
# =========================

from __future__ import annotations

import os
import yaml
from pathlib import Path
from dataclasses import dataclass, field, fields
from typing import Optional


@dataclass
class DatabaseConfig:
    """数据库配置"""
    dsn: str = "sqlite:///:memory:"
    pool_size: int = 10
    max_overflow: int = 20


@dataclass
class VaultConfig:
    """Vault 配置"""
    root_path: str = "memory_vault"


@dataclass
class EmbeddingConfig:
    """Embedding 配置"""
    type: str = "deterministic"  # openai, huggingface, deterministic
    dimension: int = 128


@dataclass
class VectorConfig:
    """向量索引配置"""
    enabled: bool = False
    type: str = "memory"  # memory, qdrant, milvus, weaviate, pgvector
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)


@dataclass
class FailureQueueConfig:
    """失败事件队列配置"""
    max_in_memory: int = 10000
    spill_batch_size: int = 200
    max_dump_file_size_mb: int = 50
    max_dump_backups: int = 3
    max_retries: int = 20


@dataclass
class MemoryConfig:
    """Memory 子系统配置"""
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    vault: VaultConfig = field(default_factory=VaultConfig)
    vector: VectorConfig = field(default_factory=VectorConfig)
    failure_queue: FailureQueueConfig = field(default_factory=FailureQueueConfig)
    
    @classmethod
    def from_dict(cls, data: dict) -> MemoryConfig:
        """从字典创建配置（忽略未知字段，兼容扩展配置）"""
        data = _as_dict(data)
        database_block = _as_dict(data.get("database"))
        vault_block = _as_dict(data.get("vault"))
        vector_block = _as_dict(data.get("vector"))
        embedding_block = _as_dict(vector_block.get("embedding"))
        failure_queue_block = _as_dict(data.get("failure_queue"))

        vector_kwargs = _filter_dataclass_kwargs(VectorConfig, vector_block)
        vector_kwargs.pop("embedding", None)

        return cls(
            database=DatabaseConfig(**_filter_dataclass_kwargs(DatabaseConfig, database_block)),
            vault=VaultConfig(**_filter_dataclass_kwargs(VaultConfig, vault_block)),
            vector=VectorConfig(
                embedding=_build_embedding_config(embedding_block),
                **vector_kwargs,
            ),
            failure_queue=FailureQueueConfig(
                **_filter_dataclass_kwargs(FailureQueueConfig, failure_queue_block)
            ),
        )
    
    @classmethod
    def from_yaml(cls, config_path: str | Path) -> MemoryConfig:
        """从 YAML 文件加载配置"""
        config_path = Path(config_path)
        
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        
        # 处理环境变量替换（<ENV_VAR> 格式）
        data = _replace_env_vars(data)
        
        return cls.from_dict(data)


def _replace_env_vars(obj):
    """
    递归替换 <ENV_VAR> 占位符为环境变量值
    """
    if isinstance(obj, str):
        if obj.startswith("<") and obj.endswith(">"):
            env_var = obj[1:-1]
            return os.environ.get(env_var, obj)
        return obj
    elif isinstance(obj, dict):
        return {k: _replace_env_vars(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_replace_env_vars(item) for item in obj]
    else:
        return obj


def _as_dict(value: object) -> dict:
    """将输入规范化为 dict。"""
    return value if isinstance(value, dict) else {}


def _filter_dataclass_kwargs(dataclass_type, raw: dict) -> dict:
    """过滤 dataclass 未定义的键，避免配置扩展字段导致构造失败。"""
    allowed_keys = {f.name for f in fields(dataclass_type)}
    return {k: v for k, v in _as_dict(raw).items() if k in allowed_keys}


def _build_embedding_config(raw: dict) -> EmbeddingConfig:
    """构建 EmbeddingConfig，并兼容 embedding.<provider>.dimension 写法。"""
    raw = _as_dict(raw)
    kwargs = _filter_dataclass_kwargs(EmbeddingConfig, raw)

    # 兼容旧/扩展配置：当未提供 embedding.dimension 时，从当前 provider 子块读取。
    if "dimension" not in kwargs:
        provider = str(kwargs.get("type", EmbeddingConfig.type))
        provider_block = _as_dict(raw.get(provider))
        provider_dim = provider_block.get("dimension")
        if isinstance(provider_dim, (int, float)):
            kwargs["dimension"] = int(provider_dim)
        elif isinstance(provider_dim, str):
            try:
                kwargs["dimension"] = int(provider_dim)
            except ValueError:
                pass

    return EmbeddingConfig(**kwargs)


# =============================================================================
# MemoryConfigProvider
# =============================================================================

class MemoryConfigProvider:
    """Memory 配置提供者（仿 GateConfigProvider）"""
    
    def __init__(self, config_path: str | Path):
        self._path = Path(config_path)
        self._ref: MemoryConfig = MemoryConfig()
        self.force_reload()
    
    def snapshot(self) -> MemoryConfig:
        """获取当前配置快照"""
        return self._ref
    
    def force_reload(self) -> bool:
        """强制重新加载配置"""
        try:
            cfg = MemoryConfig.from_yaml(self._path)
            self._ref = cfg
            return True
        except Exception:
            return False
