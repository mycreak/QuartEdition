
"""
测试共享配置和 Fixture
"""

import pytest
import asyncio
import time
import random
from typing import AsyncGenerator, Dict, Any

import sys
import os

# 确保可以导入项目模块
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.mysql import init_mysql, close_mysql, get_mysql_pool
from db.mongodb import init_mongodb, close_mongodb, get_mongodb
from db.redis import init_redis, close_redis, get_redis
from db.database_v2 import DatabaseLayerV2
from db.query_builder import ConditionBuilder, QueryBuilder
from config.db_config import get_mysql_config, get_mongo_config, get_redis_config
from utils.snowflake import init_snowflake
from services.auth_service import init_auth_service, AuthService
from models.user import UserCreate, UserUpdate
from app import create_app


# 在所有测试开始前初始化 Snowflake
def pytest_sessionstart(session):
    init_snowflake(machine_id=1)


# 测试标记
def pytest_configure(config):
    config.addinivalue_line(
        "markers", "slow: 标记慢速测试"
    )
    config.addinivalue_line(
        "markers", "unit: 单元测试"
    )
    config.addinivalue_line(
        "markers", "integration: 集成测试"
    )
    config.addinivalue_line(
        "markers", "db: 数据库相关测试"
    )
    config.addinivalue_line(
        "markers", "auth: 认证相关测试"
    )
    config.addinivalue_line(
        "markers", "admin: 管理端测试"
    )


@pytest.fixture(scope="session")
def event_loop():
    """创建 session 级别的事件循环"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def mysql_pool():
    """MySQL 连接池 fixture - function 级别"""
    await init_mysql()
    yield get_mysql_pool()
    await close_mysql()


@pytest.fixture(scope="function")
async def db(mysql_pool, mongodb_pool, redis_pool):
    """DatabaseLayerV2 实例 - function 级别，每个测试都有干净状态"""
    db_layer = DatabaseLayerV2()
    await db_layer.initialize("mysql")
    
    # 创建测试表
    async with mysql_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS test_table (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            # 清空表
            await cur.execute("TRUNCATE TABLE test_table")
    
    yield db_layer
    
    # 清理
    async with mysql_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DROP TABLE IF EXISTS test_table")


@pytest.fixture(scope="function")
async def mongodb_pool():
    """MongoDB 连接池 fixture - function 级别"""
    await init_mongodb()
    yield get_mongodb()
    await close_mongodb()


@pytest.fixture(scope="function")
async def db_mongodb(mongodb_pool):
    """DatabaseLayerV2 实例（MongoDB 模式）- function 级别，每个测试都有干净状态"""
    db_layer = DatabaseLayerV2()
    await db_layer.initialize("mongodb")
    
    test_collection = "test_collection"
    
    # 清空测试集合
    try:
        await mongodb_pool[test_collection].delete_many({})
    except Exception:
        pass
    
    yield db_layer
    
    # 清理测试集合
    try:
        await mongodb_pool[test_collection].delete_many({})
        await mongodb_pool.drop_collection(test_collection)
    except Exception:
        pass


@pytest.fixture(scope="function")
async def redis_pool():
    """Redis 连接池 fixture - function 级别"""
    await init_redis()
    redis_client = get_redis()
    
    # 清理所有测试和限流 key
    cleanup_patterns = ["test:*", "crawler:*", "ratelimit:*"]
    for pattern in cleanup_patterns:
        keys = []
        async for key in redis_client.scan_iter(match=pattern):
            keys.append(key)
        if keys:
            await redis_client.delete(*keys)
    
    yield redis_client
    await close_redis()


@pytest.fixture(scope="function")
async def db_redis(redis_pool):
    """DatabaseLayerV2 实例（Redis 模式）- function 级别，每个测试都有干净状态"""
    db = DatabaseLayerV2()
    await db.initialize("redis")
    
    # 清理测试使用的 key
    test_keys = await redis_pool.keys("test:*")
    test_keys.extend(await redis_pool.keys("crawler:*"))
    test_keys.extend(await redis_pool.keys("ratelimit:*"))
    if test_keys:
        await redis_pool.delete(*test_keys)
    
    yield db
    
    # 清理测试使用的 key
    test_keys = await redis_pool.keys("test:*")
    test_keys.extend(await redis_pool.keys("crawler:*"))
    test_keys.extend(await redis_pool.keys("ratelimit:*"))
    if test_keys:
        await redis_pool.delete(*test_keys)


@pytest.fixture(scope="function")
async def app(db):
    """Quart 应用实例 fixture"""
    app = create_app()
    
    # 手动设置 app.services（因为我们不会运行 before_serving 钩子）
    from services.movie_service import MovieService
    from services.review_service import init_review_service
    from services.task_history_service import init_task_history_service
    from services.app_services import AppServices
    movie_service = MovieService(db)
    app.services = AppServices(db=db, movie_service=movie_service)
    
    # 初始化所有服务
    init_auth_service(db)
    init_review_service(db)
    init_task_history_service(db)
    
    yield app


@pytest.fixture(scope="function")
async def client(app):
    """Quart 测试客户端 fixture"""
    async with app.test_client() as client:
        yield client


@pytest.fixture(scope="function")
async def clean_auth_data(db):
    """清理认证相关测试数据的 fixture"""
    # 清理前备份现有的管理员（如果有）
    async def _clean():
        await db.execute_raw("DELETE FROM user_permissions WHERE user_id IN (SELECT id FROM users WHERE username LIKE 'test_%')")
        await db.execute_raw("DELETE FROM users WHERE username LIKE 'test_%'")
    
    await _clean()
    yield
    await _clean()


@pytest.fixture(scope="function")
async def test_user(db, clean_auth_data):
    """创建测试用户 fixture"""
    auth_service = AuthService(db)
    timestamp = str(int(time.time() * 1000))
    random_suffix = str(random.randint(1000, 9999))
    username = f"test_user_{timestamp}_{random_suffix}"
    
    user_data = UserCreate(
        username=username,
        password="TestPass123",
        display_name=f"测试用户_{random_suffix}"
    )
    user = await auth_service.create_user(user_data)
    return user


@pytest.fixture(scope="function")
async def admin_user(db, clean_auth_data):
    """创建管理员用户 fixture（带权限）"""
    auth_service = AuthService(db)
    timestamp = str(int(time.time() * 1000))
    random_suffix = str(random.randint(1000, 9999))
    username = f"test_admin_{timestamp}_{random_suffix}"
    
    # 创建用户
    user_data = UserCreate(
        username=username,
        password="AdminPass123",
        display_name=f"测试管理员_{random_suffix}"
    )
    user = await auth_service.create_user(user_data)
    
    # 授予所有权限
    all_permissions = [
        "user:manage",
        "crawler:task:read",
        "crawler:task:write",
        "crawler:failure:manage",
        "movie:manage",
        "movie:read",
        "comment:read",
        "comment:manage",
        "system:monitor"
    ]
    for perm in all_permissions:
        await db.insert("user_permissions", {
            "user_id": user.id,
            "permission_code": perm,
            "granted_by": user.id
        }, return_id=False)
    
    return user


@pytest.fixture(scope="function")
async def disabled_user(db, clean_auth_data):
    """创建已禁用用户 fixture"""
    auth_service = AuthService(db)
    timestamp = str(int(time.time() * 1000))
    random_suffix = str(random.randint(1000, 9999))
    username = f"test_disabled_{timestamp}_{random_suffix}"
    
    user_data = UserCreate(
        username=username,
        password="TestPass123",
        display_name=f"禁用用户_{random_suffix}"
    )
    user = await auth_service.create_user(user_data)
    
    # 禁用用户
    await auth_service.update_user(user.id, UserUpdate(is_active=False))
    
    return user


def generate_unique_username(prefix="test"):
    """生成唯一用户名的辅助函数"""
    timestamp = str(int(time.time() * 1000))
    random_suffix = str(random.randint(1000, 9999))
    # 确保用户名是 6-32 字符，仅字母数字下划线
    username = f"{prefix}{timestamp[-4:]}{random_suffix}"
    return username[:32]

def generate_valid_password():
    """生成符合要求的密码（包含大写、小写、数字）"""
    return f"Pwd{random.randint(1000, 9999)}"

def generate_test_movie_data(published: bool = True, title_prefix: str = "测试电影") -> Dict[str, Any]:
    """生成测试电影数据"""
    timestamp = int(time.time() * 1000)
    return {
        "title": f"{title_prefix}_{timestamp}",
        "original_title": f"Test_{title_prefix}_{timestamp}",
        "release_year": 2020 + random.randint(0, 10),
        "release_date": "2020-01-01",
        "duration": random.randint(90, 180),
        "poster_url": "https://example.com/poster.jpg",
        "douban_id": f"test_{timestamp}",
        "is_published": 1 if published else 0
    }

async def create_test_movie(db, data: Dict[str, Any]) -> int:
    """创建测试电影并返回 movie_id"""
    from services.movie_service import MovieService
    from models.movie_models import MovieCreate
    movie_service = MovieService(db)
    movie = await movie_service.create_movie(MovieCreate(**data))
    return movie.id

async def create_test_movie_with_rating(db, movie_id: int, average: float, count: int = 1000) -> int:
    """为测试电影添加评分"""
    from services.movie_service import MovieService
    from models.movie_models import RatingCreate
    movie_service = MovieService(db)
    await movie_service.set_rating(movie_id, RatingCreate(average=average, count=count))
    return movie_id

def update_test_movies():
    return
