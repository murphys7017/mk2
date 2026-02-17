# tests/conftest.py
# Pytest 配置

import pytest


def pytest_configure(config):
    """注册自定义 marker"""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test (requires external services)"
    )
    config.addinivalue_line(
        "markers", "offline: mark test as offline test (no external services required)"
    )


# 默认给所有不标记的测试加上 offline marker
def pytest_collection_modifyitems(config, items):
    """自动标记没有 marker 的测试为 offline"""
    for item in items:
        # 如果没有 integration marker，则标记为 offline
        if "integration" not in item.keywords:
            item.add_marker(pytest.mark.offline)
