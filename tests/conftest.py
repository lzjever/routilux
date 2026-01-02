"""
pytest 配置和 fixtures
"""

import os
import sys
from pathlib import Path

# Add project root to Python path so tests can import routilux
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import pytest  # noqa: E402


@pytest.fixture
def temp_file(tmp_path):
    """提供临时文件路径"""
    return str(tmp_path / "test_file.json")


@pytest.fixture
def temp_dir(tmp_path):
    """提供临时目录路径"""
    return str(tmp_path)


@pytest.fixture
def cleanup_files():
    """清理函数，用于删除测试文件"""
    files_to_cleanup = []

    def _add_file(filepath):
        files_to_cleanup.append(filepath)

    yield _add_file

    # 清理
    for filepath in files_to_cleanup:
        if os.path.exists(filepath):
            os.remove(filepath)
