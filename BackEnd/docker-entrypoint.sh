#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# BackEnd/docker-entrypoint.sh
# 输入: 环境变量（MYSQL_HOST, REDIS_HOST, MONGO_HOST 等）
# 输出: 初始化数据库后启动 Hypercorn 服务
#
# 执行时机: BackEnd 容器启动时，在 DB 服务 healthcheck 全部通过后
# 副作用: 首次启动执行 seed_auth.py + seed_crawl_progress.py 写入 DB
# ═══════════════════════════════════════════════════════════════
set -e

echo "============================================="
echo " QuartEdition BackEnd — Docker 启动"
echo "============================================="
echo "  MYSQL_HOST  = ${MYSQL_HOST}"
echo "  REDIS_HOST  = ${REDIS_HOST}"
echo "  MONGO_HOST  = ${MONGO_HOST}"
echo "  JWT_SECRET  = $(echo ${JWT_SECRET} | head -c 8)..."
echo "============================================="

# ── 1. 等待数据库就绪（双重保险：docker-compose healthcheck 已做，但网络可能抖动） ──
echo "[ENTRYPOINT] 等待 MySQL 就绪..."
for i in $(seq 1 30); do
    if python -c "
import asyncio, asyncmy
async def check():
    try:
        conn = await asyncmy.connect(host='${MYSQL_HOST}', port=3306, user='${MYSQL_USER}', password='${MYSQL_PASSWORD}', db='${MYSQL_DATABASE}')
        await conn.ping()
        await conn.ensure_closed()
        return True
    except:
        return False
print(asyncio.run(check()))
" 2>/dev/null | grep -q True; then
        echo "[ENTRYPOINT] MySQL 已就绪"
        break
    fi
    echo "[ENTRYPOINT] 等待 MySQL... (${i}/30)"
    sleep 3
done

# ── 2. 首次启动时初始化数据库结构（幂等：所有语句 CREATE IF NOT EXISTS） ──
echo "[ENTRYPOINT] 运行 seed_auth.py（建表 + 权限种子 + 默认管理员）..."
python scripts/seed_auth.py

echo "[ENTRYPOINT] 运行 seed_crawl_progress.py（类型进度种子）..."
python scripts/seed_crawl_progress.py

# ── 3. 启动 Hypercorn（接管 CMD） ──
echo "[ENTRYPOINT] 启动 Hypercorn 服务..."
exec hypercorn app:app --bind 0.0.0.0:8000 --keep-alive 30 --access-logfile - --error-logfile -
