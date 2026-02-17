# src/memory/config.py
# =========================
# Memory 子系统配置
# =========================

from __future__ import annotations

import os
import yaml
from pathlib import Path
from dataclasses import dataclass, field
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
class MemoryConfig:
    """Memory 子系统配置"""
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    vault: VaultConfig = field(default_factory=VaultConfig)
    vector: VectorConfig = field(default_factory=VectorConfig)
    
    @classmethod
    def from_dict(cls, data: dict) -> MemoryConfig:
        """从字典创建配置"""
        return cls(
            database=DatabaseConfig(**data.get("database", {})),
            vault=VaultConfig(**data.get("vault", {})),
            vector=VectorConfig(
                enabled=data.get("vector", {}).get("enabled", False),
                type=data.get("vector", {}).get("type", "memory"),
                embedding=EmbeddingConfig(**data.get("vector", {}).get("embedding", {})),
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
        except Exception as e:
            print(f"Memory config reload failed: {e}")
            return False
