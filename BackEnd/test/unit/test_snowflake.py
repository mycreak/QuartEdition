
"""
Snowflake ID 生成器 单元测试
"""

import pytest

# 导入被测试模块
from utils.snowflake import (
    SnowflakeGenerator,
    init_snowflake,
    generate_id,
    MAX_MACHINE_ID,
)


def test_snowflake_init_success():
    """测试正常初始化"""
    gen = SnowflakeGenerator(machine_id=0)
    assert gen._machine_id == 0

    gen = SnowflakeGenerator(machine_id=1)
    assert gen._machine_id == 1

    gen = SnowflakeGenerator(machine_id=MAX_MACHINE_ID)
    assert gen._machine_id == MAX_MACHINE_ID


def test_snowflake_init_invalid_machine_id():
    """测试无效机器ID"""
    with pytest.raises(ValueError):
        SnowflakeGenerator(machine_id=-1)

    with pytest.raises(ValueError):
        SnowflakeGenerator(machine_id=MAX_MACHINE_ID + 1)


def test_snowflake_generate_single_id():
    """测试生成单个ID"""
    gen = SnowflakeGenerator(machine_id=42)
    id_val = gen.next_id()
    assert isinstance(id_val, int)
    assert id_val != 0


def test_snowflake_generate_multiple_ids():
    """测试生成多个ID"""
    gen = SnowflakeGenerator(machine_id=42)
    id_list = [gen.next_id() for _ in range(10)]
    assert len(id_list) == 10
    for v in id_list:
        assert v != 0
    assert id_list == sorted(id_list)


def test_snowflake_ids_are_unique():
    """测试生成的ID唯一性"""
    gen = SnowflakeGenerator(machine_id=77)
    id_list = [gen.next_id() for _ in range(100)]
    assert len(id_list) == len(set(id_list))


def test_snowflake_module_api():
    """测试模块级API"""
    gen = init_snowflake(machine_id=123)
    assert gen is not None
    assert gen._machine_id == 123

    id_val = generate_id()
    assert isinstance(id_val, int)
    assert id_val != 0


def test_snowflake_generate_without_init():
    """测试未初始化生成ID"""
    import utils.snowflake as sf
    sf._generator = None

    with pytest.raises(RuntimeError):
        generate_id()
