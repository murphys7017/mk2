#!/usr/bin/env python3
"""
E2E Demo 自动化测试脚本
通过管道向 demo 发送命令并验证输出
"""

import subprocess
import sys
import time
from pathlib import Path

def run_demo_with_commands(commands: list[str], timeout: int = 5) -> str:
    """
    运行 demo，发送命令，并返回输出
    
    参数：
    - commands: 要发送的命令列表
    - timeout: 总超时时间
    """
    project_root = Path(__file__).parent.parent
    
    proc = subprocess.Popen(
        [sys.executable, 'tools/demo_e2e.py'],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(project_root),
    )
    
    try:
        # 等待 demo 启动并显示提示符
        time.sleep(1)
        
        # 发送命令
        input_text = '\n'.join(commands) + '\n'
        stdout, _ = proc.communicate(input=input_text, timeout=timeout)
        return stdout
        
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, _ = proc.communicate()
        return stdout
    except Exception as e:
        try:
            proc.kill()
        except:
            pass
        raise


def run_hello_case() -> bool:
    """运行场景：发送普通文本"""
    print("\n" + "="*70)
    print("测试 1: 发送普通文本 'hello'")
    print("="*70)
    
    output = run_demo_with_commands(['hello', '/quit'])
    
    # 检查关键输出
    checks = [
        ('[ADAPTER]', '生成 Observation'),
        ('[BUS]', 'Bus 发布'),
        ('[WORKER:IN]', 'Worker 接收'),
        ('[GATE:OUT]', 'Gate 决策'),
    ]
    
    passed = 0
    for tag, desc in checks:
        if tag in output:
            print(f"  ✅ {tag:20} - {desc}")
            passed += 1
        else:
            print(f"  ❌ {tag:20} - {desc}")
    
    print(f"\n结果: {passed}/{len(checks)} 通过")
    return passed == len(checks)


def run_alert_case() -> bool:
    """运行场景：注入告警"""
    print("\n" + "="*70)
    print("测试 2: 注入告警 '/alert drop_burst'")
    print("="*70)
    
    output = run_demo_with_commands(['/alert drop_burst', '/quit'])
    
    checks = [
        ('[ADAPTER]', '生成 Alert Observation'),
        ('alert', '包含 alert 关键字'),
        ('system', '进入 system session'),
    ]
    
    passed = 0
    for tag, desc in checks:
        if tag.lower() in output.lower():
            print(f"  ✅ {tag:20} - {desc}")
            passed += 1
        else:
            print(f"  ❌ {tag:20} - {desc}")
    
    print(f"\n结果: {passed}/{len(checks)} 通过")
    return passed == len(checks)


def run_session_switch_case() -> bool:
    """运行场景：切换 session"""
    print("\n" + "="*70)
    print("测试 3: 切换 session '/session user123'")
    print("="*70)
    
    output = run_demo_with_commands(['/session user123', 'hello from user123', '/quit'])
    
    checks = [
        ('user123', '成功切换到 user123 session'),
        ('Switched', '显示切换确认'),
    ]
    
    passed = 0
    for tag, desc in checks:
        if tag in output:
            print(f"  ✅ {tag:20} - {desc}")
            passed += 1
        else:
            print(f"  ❌ {tag:20} - {desc}")
    
    print(f"\n结果: {passed}/{len(checks)} 通过")
    return passed == len(checks)


def test_hello():
    """测试：发送普通文本"""
    assert run_hello_case()


def test_alert():
    """测试：注入告警"""
    assert run_alert_case()


def test_session_switch():
    """测试：切换 session"""
    assert run_session_switch_case()


def main():
    print("\n")
    print("╔" + "="*68 + "╗")
    print("║" + " E2E Demo 自动化测试".center(68) + "║")
    print("╚" + "="*68 + "╝")
    
    results = []
    
    try:
        results.append(("hello 文本", run_hello_case()))
    except Exception as e:
        print(f"❌ 测试异常: {e}")
        results.append(("hello 文本", False))
    
    try:
        results.append(("Alert 注入", run_alert_case()))
    except Exception as e:
        print(f"❌ 测试异常: {e}")
        results.append(("Alert 注入", False))
    
    try:
        results.append(("Session 切换", run_session_switch_case()))
    except Exception as e:
        print(f"❌ 测试异常: {e}")
        results.append(("Session 切换", False))
    
    # 汇总
    print("\n" + "="*70)
    print("测试汇总")
    print("="*70)
    
    passed_count = sum(1 for _, result in results if result)
    total_count = len(results)
    
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"  {status} - {name}")
    
    print(f"\n总计: {passed_count}/{total_count} 通过")
    
    if passed_count == total_count:
        print("\n🎉 所有测试通过！")
        return 0
    else:
        print(f"\n⚠️  {total_count - passed_count} 个测试失败")
        return 1


if __name__ == '__main__':
    sys.exit(main())
