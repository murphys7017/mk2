# memory/vault.py
# =========================
# Markdown Vault（权威源）
# 管理用户信息、设定、经历、知识库等可编辑的条目
# =========================

from __future__ import annotations

import os
import re
import json
import yaml
from pathlib import Path
from dataclasses import fields
from typing import Optional

from .models import MemoryItem, MemoryScope


# =============================================================================
# Markdown File Reader/Writer
# =============================================================================

class MarkdownVaultError(Exception):
    """Markdown Vault 相关错误"""
    pass


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    """
    解析 YAML frontmatter
    
    格式：
    ---
    key: value
    ---
    content here
    """
    if not content.startswith("---"):
        return {}, content
    
    # 找到第二个 ---
    match = re.match(r"^---\n(.*?)\n---\n(.*)", content, re.DOTALL)
    if not match:
        return {}, content
    
    try:
        frontmatter = yaml.safe_load(match.group(1)) or {}
        body = match.group(2)
        return frontmatter, body
    except yaml.YAMLError:
        return {}, content


def _create_frontmatter(data: dict) -> str:
    """
    创建 YAML frontmatter
    """
    return "---\n" + yaml.dump(data, allow_unicode=True, default_flow_style=False) + "---\n"


# =============================================================================
# MarkdownItemStore - Markdown 项目存储
# =============================================================================

class MarkdownItemStore:
    """
    Markdown 文件存储实现
    
    目录结构：
    memory_vault/
      global/
        persona.md
        knowledge/
          item1.md
          item2.md
      users/<user_id>/
        profile.md
        constraints.md
      episodic/
        <user_id>/
          timeline.md
      kb/
        *.md
    """
    
    def __init__(self, vault_root: str | Path = "memory_vault"):
        self.vault_root = Path(vault_root)
        self.vault_root.mkdir(parents=True, exist_ok=True)
    
    def _get_file_path(self, scope: MemoryScope, kind: str, key: str) -> Path:
        """
        根据 scope/kind/key 计算文件路径
        """
        if scope == "global":
            if kind == "persona":
                return self.vault_root / "global" / "persona.md"
            else:
                return self.vault_root / "global" / kind / f"{key}.md"
        elif scope == "user":
            # 假设 key 格式为 "user_id/field" 或直接使用 key
            if "/" in key:
                user_id, field = key.rsplit("/", 1)
            else:
                user_id = key
                field = "profile"
            return self.vault_root / "users" / user_id / f"{field}.md"
        elif scope == "episodic":
            # key 格式为 "user_id/event_name"
            if "/" in key:
                user_id, event_name = key.rsplit("/", 1)
            else:
                user_id = key
                event_name = "timeline"
            return self.vault_root / "episodic" / user_id / f"{event_name}.md"
        elif scope == "kb":
            return self.vault_root / "kb" / f"{key}.md"
        elif scope == "session":
            # session 也存到 markdown，但在 sessions 目录
            return self.vault_root / "sessions" / f"{key}.md"
        else:
            raise MarkdownVaultError(f"Unknown scope: {scope}")
    
    def get(self, scope: MemoryScope, kind: str, key: str) -> Optional[MemoryItem]:
        """
        获取 MemoryItem
        """
        file_path = self._get_file_path(scope, kind, key)
        if not file_path.exists():
            return None
        
        try:
            content = file_path.read_text(encoding="utf-8")
            frontmatter, body = _parse_frontmatter(content)
            
            # 从 frontmatter 合并必要的字段
            return MemoryItem(
                scope=frontmatter.get("scope", scope),
                kind=frontmatter.get("kind", kind),
                key=frontmatter.get("key", key),
                content=body.strip(),
                data=frontmatter.get("data", {}),
                source=frontmatter.get("source", "markdown_vault"),
                confidence=frontmatter.get("confidence", 1.0),
                created_ts=frontmatter.get("created_ts"),
                updated_ts=frontmatter.get("updated_ts"),
                ttl_sec=frontmatter.get("ttl_sec"),
                meta=frontmatter.get("meta", {}),
            )
        except Exception as e:
            raise MarkdownVaultError(f"Failed to read {file_path}: {e}")
    
    def list(self, scope: MemoryScope, kind: Optional[str] = None) -> list[MemoryItem]:
        """
        列出指定 scope（和 kind）的所有条目
        """
        items = []
        
        if scope == "global":
            scope_dir = self.vault_root / "global"
            if scope_dir.exists():
                # 扫描所有 md 文件
                for file_path in scope_dir.rglob("*.md"):
                    rel_path = file_path.relative_to(scope_dir)
                    # 从路径推导 kind
                    parts = rel_path.parts
                    if len(parts) == 1:
                        # 直接在 global/ 下 (persona.md)
                        item_kind = rel_path.stem
                        item_key = rel_path.stem
                    else:
                        # 在子目录下: global/kind/key.md
                        item_kind = parts[0]
                        item_key = rel_path.stem  # 只使用文件名作为 key
                    
                    if kind is None or item_kind == kind:
                        item = self.get("global", item_kind, item_key)
                        if item:
                            items.append(item)
        
        elif scope == "user":
            users_dir = self.vault_root / "users"
            if users_dir.exists():
                for user_dir in users_dir.iterdir():
                    if user_dir.is_dir():
                        user_id = user_dir.name
                        for file_path in user_dir.glob("*.md"):
                            field = file_path.stem
                            if kind is None or field == kind:
                                item = self.get("user", field, f"{user_id}/{field}")
                                if item:
                                    items.append(item)
        
        elif scope == "episodic":
            episodic_dir = self.vault_root / "episodic"
            if episodic_dir.exists():
                for user_dir in episodic_dir.iterdir():
                    if user_dir.is_dir():
                        user_id = user_dir.name
                        for file_path in user_dir.glob("*.md"):
                            event_name = file_path.stem
                            if kind is None or event_name == kind:
                                item = self.get("episodic", event_name, f"{user_id}/{event_name}")
                                if item:
                                    items.append(item)
        
        elif scope == "kb":
            kb_dir = self.vault_root / "kb"
            if kb_dir.exists():
                for file_path in kb_dir.glob("*.md"):
                    item_key = file_path.stem
                    item = self.get("kb", "knowledge", item_key)
                    if item:
                        items.append(item)
        
        elif scope == "session":
            sessions_dir = self.vault_root / "sessions"
            if sessions_dir.exists():
                for file_path in sessions_dir.glob("*.md"):
                    item_key = file_path.stem
                    item = self.get("session", "summary", item_key)
                    if item:
                        items.append(item)
        
        return items
    
    def upsert(self, item: MemoryItem) -> None:
        """
        新增或更新条目
        """
        file_path = self._get_file_path(item.scope, item.kind, item.key)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 构造 frontmatter
        frontmatter = {
            "scope": item.scope,
            "kind": item.kind,
            "key": item.key,
            "source": item.source,
            "confidence": item.confidence,
        }
        
        if item.created_ts is not None:
            frontmatter["created_ts"] = item.created_ts
        if item.updated_ts is not None:
            frontmatter["updated_ts"] = item.updated_ts
        if item.ttl_sec is not None:
            frontmatter["ttl_sec"] = item.ttl_sec
        if item.data:
            frontmatter["data"] = item.data
        if item.meta:
            frontmatter["meta"] = item.meta
        
        # 写文件
        content = _create_frontmatter(frontmatter) + item.content
        
        try:
            file_path.write_text(content, encoding="utf-8")
        except Exception as e:
            raise MarkdownVaultError(f"Failed to write {file_path}: {e}")
    
    def delete(self, scope: MemoryScope, kind: str, key: str) -> bool:
        """
        删除条目
        """
        file_path = self._get_file_path(scope, kind, key)
        if not file_path.exists():
            return False
        
        try:
            file_path.unlink()
            # 如果目录为空，删除目录
            try:
                if file_path.parent != self.vault_root:
                    file_path.parent.rmdir()
            except OSError:
                pass
            return True
        except Exception as e:
            raise MarkdownVaultError(f"Failed to delete {file_path}: {e}")
    
    def search_text(self, query: str, scope: Optional[MemoryScope] = None) -> list[MemoryItem]:
        """
        简单的文本搜索
        """
        results = []
        query_lower = query.lower()
        
        # 确定要搜索的范围
        if scope:
            scopes = [scope]
        else:
            scopes = ["global", "user", "episodic", "kb", "session"]
        
        for s in scopes:
            for item in self.list(s):
                if (query_lower in item.content.lower() or 
                    query_lower in item.key.lower() or
                    any(query_lower in str(v).lower() for v in item.data.values())):
                    results.append(item)
        
        return results
