# tests/conftest.py
# Pytest 配置

import asyncio
import inspect
import pytest


def pytest_addoption(parser):
    """兼容没有 pytest-asyncio 插件时的 ini 配置。"""
    parser.addini(
        "asyncio_mode",
        "Compatibility option when pytest-asyncio is unavailable",
        default="auto",
    )


def pytest_configure(config):
    """注册自定义 marker"""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test (requires external services)"
    )
    config.addinivalue_line(
        "markers", "offline: mark test as offline test (no external services required)"
    )
    config.addinivalue_line(
        "markers", "asyncio: mark test as asyncio coroutine test"
    )


# 默认给所有不标记的测试加上 offline marker
def pytest_collection_modifyitems(config, items):
    """自动标记没有 marker 的测试为 offline"""
    for item in items:
        # 如果没有 integration marker，则标记为 offline
        if "integration" not in item.keywords:
            item.add_marker(pytest.mark.offline)


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem):
    """
    当 pytest-asyncio 不可用时，兜底执行 async 测试函数。
    """
    plugin_manager = pyfuncitem.config.pluginmanager
    if plugin_manager.hasplugin("pytest_asyncio") or plugin_manager.hasplugin("asyncio"):
        return None

    test_function = pyfuncitem.obj
    if not inspect.iscoroutinefunction(test_function):
        return None

    test_args = {
        arg: pyfuncitem.funcargs[arg]
        for arg in pyfuncitem._fixtureinfo.argnames
    }
    asyncio.run(test_function(**test_args))
    return True
