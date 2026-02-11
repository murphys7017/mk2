"""
GetTimeSkill: 获取并格式化当前时间
"""
from ..tools.time_tool import CurrentTimeTool


class GetTimeSkill:
    """获取时间技能"""
    
    def __init__(self):
        self.tool = CurrentTimeTool()
    
    def run(self) -> str:
        """执行技能，返回格式化的时间字符串"""
        result = self.tool.run()
        
        # 格式化输出
        timestamp = result["timestamp"]
        timezone = result["timezone"]
        
        return f"当前时间是：{timestamp} ({timezone})"
