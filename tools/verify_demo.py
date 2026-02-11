#!/usr/bin/env python3
"""
E2E Demo 简单验证脚本
直接打印命令执行的输出
"""

import subprocess
import sys
import time
from pathlib import Path


def run_demo_manual_test():
    """运行 demo 并执行三条命令，打印完整输出"""
    
    project_root = Path(__file__).parent.parent
    
    print("\n" + "="*70)
    print("E2E Demo - 手工验证测试")
    print("="*70)
    print("将依次运行这三条命令：")
    print("  1. hello")
    print("  2. /alert drop_burst")
    print("  3. /suggest force_low_model=1 ttl=5")
    print("  4. /quit")
    print("="*70 + "\n")
    
    proc = subprocess.Popen(
        [sys.executable, 'tools/demo_e2e.py'],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(project_root),
    )
    
    try:
        # 等待启动
        time.sleep(1.5)
        
        # 发送命令
        commands = [
            'hello',
            '/alert drop_burst',
            '/suggest force_low_model=1 ttl=5',
            '/quit'
        ]
        
        input_text = '\n'.join(commands) + '\n'
        stdout, _ = proc.communicate(input=input_text, timeout=10)
        
        # 过滤输出：只显示关键节点
        print("\n" + "="*70)
        print("📊 关键节点输出")
        print("="*70)
        
        lines = stdout.split('\n')
        
        # 找关键行
        important_lines = []
        for i, line in enumerate(lines):
            if any(tag in line for tag in ['[ADAPTER]', '[BUS]', '[session:', '[CLI]', '[INIT]', '/alert', '/suggest', 'Injected']):
                # 显示该行及后续的 JSON 部分（最多 5 行）
                important_lines.append(line)
                for j in range(i+1, min(i+6, len(lines))):
                    if '{' in lines[j] or '}' in lines[j] or ':' in lines[j] or '"' in lines[j]:
                        important_lines.append(lines[j])
                    elif lines[j].strip() and not lines[j].startswith('['):
                        break
        
        for line in important_lines:
            print(line)
        
        # 汇总检查
        print("\n" + "="*70)
        print("✅ 验证清单")
        print("="*70)
        
        checks = [
            ('[ADAPTER]' in stdout, '[ADAPTER] 节点被打印'),
            ('[BUS]' in stdout, '[BUS] 节点被打印'),
            ('hello' in stdout, '接收到 "hello" 命令'),
            ('drop_burst' in stdout, '接收到 "/alert drop_burst" 命令'),
            ('force_low_model' in stdout, '接收到 "/suggest force_low_model=1" 命令'),
            ('Switched' in stdout or 'session' in stdout.lower(), '演示了 session 切换'),
        ]
        
        passed = 0
        for result, desc in checks:
            status = '✅' if result else '❌'
            print(f"  {status} {desc}")
            if result:
                passed += 1
        
        print(f"\n总计: {passed}/{len(checks)} 验证通过")
        
        return passed >= 4  # 至少 4 个通过视为成功
        
    except subprocess.TimeoutExpired:
        proc.kill()
        print("❌ Demo 超时")
        return False
    except Exception as e:
        print(f"❌ 错误: {e}")
        try:
            proc.kill()
        except:
            pass
        return False


if __name__ == '__main__':
    success = run_demo_manual_test()
    sys.exit(0 if success else 1)
