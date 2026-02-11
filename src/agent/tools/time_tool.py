"""
CurrentTimeTool: 获取当前时间的工具
"""
from datetime import datetime, timezone
from typing import Dict, Any


class CurrentTimeTool:
    """当前时间工具"""
    
    def run(self) -> Dict[str, Any]:
        """获取当前时间"""
        now = datetime.now(timezone.utc)
        
        return {
            "timestamp": now.isoformat(),
            "unix": now.timestamp(),
            "timezone": "UTC",
        }
