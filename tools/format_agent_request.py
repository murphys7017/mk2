"""
格式化 AgentRequest 输出的工具
"""
from datetime import datetime
from typing import Any, Dict
import json


def format_value(value: Any, indent: int = 0) -> str:
    """递归格式化值"""
    indent_str = "  " * indent
    next_indent_str = "  " * (indent + 1)
    
    if value is None:
        return "None"
    elif isinstance(value, bool):
        return str(value)
    elif isinstance(value, (int, float)):
        return str(value)
    elif isinstance(value, str):
        return f"'{value}'"
    elif isinstance(value, datetime):
        return f"datetime({value.isoformat()})"
    elif isinstance(value, set):
        if not value:
            return "set()"
        items = ", ".join(format_value(v, 0) for v in value)
        return f"{{{items}}}"
    elif isinstance(value, (list, tuple)):
        if not value:
            return "[]" if isinstance(value, list) else "()"
        formatted = [f"{next_indent_str}{format_value(v, indent + 1)}" for v in value]
        bracket = "[]" if isinstance(value, list) else "()"
        return f"{bracket[0]}\n" + ",\n".join(formatted) + f"\n{indent_str}{bracket[1]}"
    elif isinstance(value, dict):
        if not value:
            return "{}"
        items = []
        for k, v in value.items():
            formatted_v = format_value(v, indent + 1)
            items.append(f"{next_indent_str}{k}: {formatted_v}")
        return "{\n" + ",\n".join(items) + f"\n{indent_str}}}"
    elif hasattr(value, '__dict__'):
        # 是一个对象（dataclass 或其他）
        class_name = value.__class__.__name__
        attrs = value.__dict__
        if not attrs:
            return f"{class_name}()"
        items = []
        for k, v in attrs.items():
            formatted_v = format_value(v, indent + 1)
            items.append(f"{next_indent_str}{k}={formatted_v}")
        return f"{class_name}(\n" + ",\n".join(items) + f"\n{indent_str})"
    else:
        return str(value)


def format_agent_request(req_str: str) -> str:
    """
    格式化 AgentRequest 输出
    
    使用方式:
        from tools.format_agent_request import format_agent_request
        # 或直接在命令行：python -m tools.format_agent_request
    """
    # 简单优化：为换行添加更多可读性
    lines = []
    
    # 顶层字段
    print("=" * 100)
    print("📋 AgentRequest 结构概览")
    print("=" * 100)
    
    sections = {
        "obs": "【当前观察】Observation - 本次收到的消息/事件",
        "gate_decision": "【网关决策】GateDecision - 是否通过、使用哪个模型、预算等",
        "session_state": "【会话状态】SessionState - 会话历史、处理次数等",
        "now": "【当前时间】datetime - 处理时的时间戳",
        "gate_hint": "【网关提示】GateHint - (可选) 详细的预算和资源提示",
    }
    
    for key, description in sections.items():
        print(f"\n{description}")
        print(f"  └─ Key: {key}")


def extract_key_fields(data_str: str) -> Dict[str, Any]:
    """
    提取关键字段的摘要
    """
    result = {
        "obs_id": None,
        "message_text": None,
        "session_key": None,
        "gate_action": None,
        "model_tier": None,
        "response_policy": None,
        "session_created_at": None,
        "session_processed_total": None,
    }
    
    # 简单的字符串提取（用正则或手动）
    import re
    
    # obs_id
    match = re.search(r"obs_id='([^']+)'", data_str)
    if match:
        result["obs_id"] = match.group(1)
    
    # message 内容
    match = re.search(r"text='([^']+)'", data_str)
    if match:
        result["message_text"] = match.group(1)
    
    # session_key
    match = re.search(r"session_key='([^']+)'", data_str)
    if match:
        result["session_key"] = match.group(1)
    
    # gate_action
    match = re.search(r"action=<GateAction\.(\w+):", data_str)
    if match:
        result["gate_action"] = match.group(1)
    
    # model_tier
    match = re.search(r"model_tier='(\w+)'", data_str)
    if match:
        result["model_tier"] = match.group(1)
    
    # response_policy
    match = re.search(r"response_policy='([^']+)'", data_str)
    if match:
        result["response_policy"] = match.group(1)
    
    return result


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        # 从文件读取
        with open(sys.argv[1], 'r', encoding='utf-8') as f:
            data = f.read()
    else:
        # 从标准输入读取
        print("请粘贴 AgentRequest 的输出（Ctrl+D 结束）:")
        data = sys.stdin.read()
    
    format_agent_request(data)
    
    print("\n" + "=" * 100)
    print("⚡ 关键字段摘要")
    print("=" * 100)
    
    summary = extract_key_fields(data)
    for key, value in summary.items():
        if value:
            print(f"{key:30s}: {value}")
