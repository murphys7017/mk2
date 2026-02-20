#!/usr/bin/env python3
"""
清理 src 目录中的所有 logger 调用
将 logger.xxx() 行注释掉，保留导入语句
"""
import re
from pathlib import Path

# 需要处理的文件列表
files_to_clean = [
    "src/core.py",
    "src/config_provider.py",
    "src/nociception.py",
    "src/memory/service.py",
    "src/memory/backends/markdown_hybrid.py",
    "src/agent/orchestrator.py",
    "src/adapters/interface/base.py",
    "src/adapters/cli_adapter.py",
]

# 日志方法的正则表达式
log_pattern = re.compile(
    r'^(\s*)(?:self\.)?logger\.(debug|info|warning|error|exception|critical|success|trace)\(',
    re.MULTILINE
)

def comment_out_logger_calls(content: str) -> tuple[str, int]:
    """注释掉所有 logger 调用，返回修改后的内容和修改行数"""
    lines = content.split('\n')
    modified_count = 0
    result_lines = []
    i = 0
    
    while i < len(lines):
        line = lines[i]
        match = log_pattern.match(line)
        
        if match:
            # 找到 logger 调用
            indent = match.group(1)
            # 注释掉当前行
            result_lines.append(f"{indent}# {line.lstrip()}")
            modified_count += 1
            
            # 检查是否是多行调用（括号未闭合）
            open_parens = line.count('(') - line.count(')')
            j = i + 1
            
            while open_parens > 0 and j < len(lines):
                next_line = lines[j]
                result_lines.append(f"{indent}# {next_line.lstrip()}")
                open_parens += next_line.count('(') - next_line.count(')')
                modified_count += 1
                j += 1
            
            i = j
        else:
            result_lines.append(line)
            i += 1
    
    return '\n'.join(result_lines), modified_count

def main():
    repo_root = Path(__file__).parent.parent
    total_modified = 0
    total_files = 0
    
    print("开始清理 src 目录中的日志输出...\n")
    
    for file_path in files_to_clean:
        full_path = repo_root / file_path
        
        if not full_path.exists():
            print(f"⚠️  文件不存在: {file_path}")
            continue
        
        # 读取文件
        content = full_path.read_text(encoding='utf-8')
        
        # 注释掉日志调用
        new_content, modified_count = comment_out_logger_calls(content)
        
        if modified_count > 0:
            # 写回文件
            full_path.write_text(new_content, encoding='utf-8')
            print(f"✅ {file_path}: 注释了 {modified_count} 行日志调用")
            total_modified += modified_count
            total_files += 1
        else:
            print(f"ℹ️  {file_path}: 无需修改")
    
    print(f"\n完成！共处理 {total_files} 个文件，注释了 {total_modified} 行日志调用。")
    print("\n注意：logger 的导入语句仍然保留，方便后续手动添加日志。")

if __name__ == "__main__":
    main()
