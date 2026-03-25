import pytest

# 让 pytest-asyncio 对所有 async 测试自动应用 asyncio mode
def pytest_configure(config):
    config.addinivalue_line(
        "markers", "asyncio: mark test as async"
    )
