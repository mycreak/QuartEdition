"""
crawler/storage.py

持久化层 — 将解析后的数据写入 MySQL 和 MongoDB。

职责：
    1. save_movies(movie_service, movies)         → MySQL 8 张表 (via MovieService)
    2. save_directors(movie_service, movie_id, dirs)→ MySQL people + movie_credits
    3. save_reviews(douban_id, reviews)         → MongoDB (via ReviewService)
    4. save_comments(douban_id, comments)       → MongoDB (via ReviewService)

设计原则：
    - MySQL 写操作用 MovieService（已有幂等保护，如 INSERT ON DUPLICATE KEY）
    - MongoDB 评论操作委托 ReviewService（upsert 逻辑 + 并发安全集中管理）
    - 每个函数内异常独立捕获，不中断批量操作
    - 人员/类型通过 _find_or_create_person / _resolve_type_num 幂等处理

数据流：
    parser.parse_movie_list(list) → list[dict]
        ↓
    storage.save_movies(service, dicts)
        ↓
    MovieService.create_movie() → movie_id
    → _find_or_create_person() → person_id
    → MovieService.add_credit(movie_id, person_id, role)
    → _resolve_type_num() → type_num
    → MovieService.add_genre_to_movie(movie_id, type_num)
    → MovieService.set_rating(movie_id, rating_data)
"""

import json
import logging
from datetime import date
from typing import Any, Dict, List, Optional

from models.movie_models import MovieCreate, RatingCreate

logger = logging.getLogger(__name__)


class StorageError(Exception):
    """持久化失败（detail 会自动并入异常消息确保不被丢弃）。"""

    def __init__(self, message: str, detail: str = ""):
        full = f"{message}" + (f" | detail={detail}" if detail else "")
        super().__init__(full)
        self.detail = detail


# ═══════════════════════════════════════════
# 公共服务
# ═══════════════════════════════════════════

async def _safe_execute(action_desc: str, coro):
    """
    安全执行一个异步操作，捕获异常并记录日志。

    输入：
        action_desc: 操作描述（用于日志）
        coro:        异步协程对象
    输出：
        成功返回结果，失败返回 None
    副作用：
        记录异常到日志
    """
    try:
        return await coro
    except Exception as e:
        logger.error(f"{action_desc} 失败: {e}")
        return None


async def _mirror_poster(poster_url: str, douban_id: str) -> str:
    """
    将海报从豆瓣 CDN 转存到 TOS，失败则返回原 URL。

    输入：
        poster_url: 豆瓣 CDN 海报链接
        douban_id:  豆瓣电影 ID
    输出：
        成功 → TOS URL，失败/未配置 → 原 URL
    副作用：
        aiohttp 下载 + TOS 上传（不通不阻塞）
    """
    if not poster_url or not douban_id:
        return poster_url

    try:
        from utils.tos_client import get_tos_client
        client = get_tos_client()
        if client is None or not client.enabled:
            return poster_url

        ext = ".webp"
        if ".jpg" in poster_url.lower():
            ext = ".jpg"
        elif ".png" in poster_url.lower():
            ext = ".png"

        dest_key = f"covers/poster_{douban_id}{ext}"
        max_size = 5 * 1024 * 1024

        tos_url = await client.mirror_from_url(poster_url, dest_key, max_size=max_size)
        if tos_url:
            logger.debug(f"海报已转存 TOS: douban_id={douban_id}")
            return tos_url
        return poster_url
    except Exception:
        return poster_url


# ═══════════════════════════════════════════
# 人员/类型字典管理（幂等查找或创建）
# ═══════════════════════════════════════════

async def _find_or_create_person(db_layer, name: str, douban_id: str = "") -> Optional[int]:
    """
    查找人员 ID（先 douban_id 再 name），不存在则创建。幂等。

    输入：
        db_layer:   DatabaseLayer 实例
        name:       人员姓名
        douban_id:  豆瓣人员 ID（来自详情页 personage URL，如 "27218173"）
    输出：
        person_id 或 None
    副作用：
        可能 INSERT INTO people（name + douban_id）
    """
    if not name or not name.strip():
        return None

    name = name.strip()

    # 优先按 douban_id 查找（过滤无效人员）
    if douban_id:
        rows = await _safe_execute(
            f"按 douban_id 查找人员 '{douban_id}'",
            db_layer.execute_raw("SELECT * FROM people WHERE douban_id = %s AND is_duplicate != -1 LIMIT 1", (douban_id,))
        )
        person = rows[0] if rows else None
        if person:
            return person["id"]

    # 按 name 查找（过滤无效人员）
    rows = await _safe_execute(
        f"查找人员 '{name}'",
        db_layer.execute_raw("SELECT * FROM people WHERE name = %s AND is_duplicate != -1 LIMIT 1", (name,))
    )
    person = rows[0] if rows else None
    if person:
        # 如果已有记录没有 douban_id，补充
        if douban_id and not person.get("douban_id"):
            await _safe_execute(
                f"补充人员 douban_id",
                db_layer.update("people", {"id": person["id"]}, {"douban_id": douban_id})
            )
        return person["id"]

    pid = await _safe_execute(
        f"创建人员 '{name}'",
        db_layer.insert("people", {"name": name, "douban_id": douban_id or None})
    )
    return pid


async def _resolve_type_num(db_layer, type_name: str) -> Optional[int]:
    """
    从 crawl_progress 查找类型名对应的 type_num。

    输入：
        db_layer:  DatabaseLayer 实例
        type_name: 类型中文名（如 "剧情"）
    输出：
        type_num 或 None
    副作用：只读
    """
    if not type_name or not type_name.strip():
        return None

    name = type_name.strip()
    row = await _safe_execute(
        f"查找类型编号 '{name}'",
        db_layer.find_one("crawl_progress", {"type_name": name})
    )
    if row:
        return row["type_num"]
    return None


async def _find_or_create_region(db_layer, name: str) -> Optional[int]:
    """
    查找地区 ID，不存在则创建。幂等。

    输入：
        db_layer: DatabaseLayer 实例
        name:     地区名（如 "美国"、"中国大陆"）
    输出：
        region_id 或 None
    副作用：
        可能 INSERT INTO regions
    """
    if not name or not name.strip():
        return None

    name = name.strip()
    region = await _safe_execute(
        f"查找地区 '{name}'",
        db_layer.find_one("regions", {"name": name})
    )
    if region:
        return region["id"]

    rid = await _safe_execute(
        f"创建地区 '{name}'",
        db_layer.insert("regions", {"name": name})
    )
    return rid


# ═══════════════════════════════════════════
# 2a: 电影保存 (MySQL via MovieService)
# ═══════════════════════════════════════════

async def save_movies(movie_service, movies: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    批量保存电影数据到 MySQL。

    写入顺序（遵守外键依赖链）：
        1. movies          → MovieService.create_movie()（先按 douban_id 去重）
        2. people          → _find_or_create_person()
        3. types           → _resolve_type_num() (crawl_progress 预填充)
        4. regions         → _find_or_create_region()
        5. movie_credits   → MovieService.add_credit()
        6. movie_genres    → MovieService.add_genre_to_movie()
        7. movie_regions   → MovieService.add_region_to_movie()
        8. movie_ratings   → MovieService.set_rating()

    输入：
        movie_service: MovieService 实例
        movies:        parser.parse_movie_list() 返回的 dict 列表
    输出：
        {
            "created": N,
            "skipped": M,    # 去重跳过 + 异常跳过之和
            "failures": [    # 异常跳过的详情，供上层写入 task_failures
                {"movie_data": dict, "error": str},
                ...
            ]
        }
    副作用：
        写入 MySQL 8 张表（逐电影处理）
    错误处理：
        单部电影失败不会中断整个批量操作，失败信息收集后由调用方决定是否上报
    """
    created = 0
    skipped = 0
    failures = []

    for movie_data in movies:
        try:
            movie_id = await _save_single_movie(movie_service, movie_data)
            if movie_id:
                created += 1
                logger.info(f"电影已保存: id={movie_id} title='{movie_data.get('title', '')}'")
            else:
                skipped += 1
        except Exception as e:
            logger.exception(f"保存电影失败: {movie_data.get('title', '')}: {e}")
            skipped += 1
            failures.append({
                "movie_data": movie_data,
                "error": str(e),
            })

    logger.info(f"save_movies 完成: created={created} skipped={skipped} failures={len(failures)}")
    return {"created": created, "skipped": skipped, "failures": failures}


async def _save_single_movie(movie_service, data: Dict[str, Any]) -> Optional[int]:
    """
    事务内原子保存单部电影及其全部关联数据。

    写入内容：movies + people + movie_credits + movie_genres + movie_regions + movie_ratings
    全部在同一个事务内：任何一步失败 → 全部回滚，不残留中间数据。

    输入：
        movie_service: MovieService 实例
        data:          parser 输出的单部电影 dict
    输出：
        movie_id 或 None (duplicate 时返回 None 表示跳过)
    """
    douban_id = data.get("douban_id", "")
    title = data.get("title", "")
    if not douban_id or not title:
        return None

    # 去重在事务外 — LIMIT 1 纯读，不占长事务锁
    existing = await movie_service.get_movie_by_douban_id(douban_id)
    if existing:
        logger.debug(f"电影已存在，跳过: douban_id={douban_id} title='{title}'")
        return None

    release_date = None
    release_date_str = data.get("release_date", "")
    if release_date_str:
        try:
            release_date = date.fromisoformat(release_date_str.split(" ")[0])
        except (ValueError, TypeError):
            pass

    db_layer = movie_service.db

    # 海报转存 TOS（在事务外，避免长事务阻塞）
    poster_url = await _mirror_poster(data.get("poster_url", ""), douban_id)

    # 事务内：movies + 演职人员 + 类型 + 地区 + 评分 原子执行
    async with db_layer.transaction() as tx:
        # 1. movies 主表
        values = {
            "douban_id": douban_id,
            "title": title,
            "original_title": data.get("original_title") or "",
            "release_year": data.get("release_year") or None,
            "release_date": str(release_date) if release_date else "",
            "duration": data.get("duration") or None,
            "poster_url": poster_url,
            "imdb_id": None,
        }
        movie_id = await tx.insert("movies", values, return_id=True)

        # 2. 演职人员 + people（幂等）
        crew_list: list[dict] = data.get("crew", [])
        if crew_list:
            for person in crew_list:
                pid = await _find_or_create_person_in_tx(
                    tx, person["name"],
                    douban_id=person.get("douban_id", ""),
                )
                if pid:
                    await tx.insert("movie_credits", {
                        "movie_id": movie_id,
                        "person_id": pid,
                        "role_type": person["role_type"],
                    }, return_id=False)
        else:
            # 降级：详情页快速视图 — 演员列表（纯名字字符串）
            for actor_name in data.get("actors", []):
                pid = await _find_or_create_person_in_tx(tx, actor_name)
                if pid:
                    await tx.insert("movie_credits", {
                        "movie_id": movie_id,
                        "person_id": pid,
                        "role_type": "actor",
                    }, return_id=False)
            # 详情页快速视图 — 导演列表（含 douban_id）
            for d in data.get("directors", []):
                pid = await _find_or_create_person_in_tx(
                    tx, d["name"],
                    douban_id=d.get("douban_id", ""),
                )
                if pid:
                    await tx.insert("movie_credits", {
                        "movie_id": movie_id,
                        "person_id": pid,
                        "role_type": "director",
                    }, return_id=False)

        # 3. 类型关联（幂等）
        for genre_name in data.get("types", []):
            tn = await _resolve_type_num_in_tx(tx, genre_name)
            if tn:
                await tx.insert("movie_genres", {
                    "movie_id": movie_id, "type_num": tn,
                }, return_id=False)

        # 4. 地区关联（幂等）
        for region_name in data.get("regions", []):
            rid = await _find_or_create_region_in_tx(tx, region_name)
            if rid:
                await tx.insert("movie_regions", {
                    "movie_id": movie_id, "region_id": rid,
                }, return_id=False)

        # 5. 评分（幂等 — 首次写入）
        score = data.get("score", 0)
        vote_count = data.get("vote_count", 0)
        if score > 0 or vote_count > 0:
            await tx.insert("movie_ratings", {
                "movie_id": movie_id,
                "average": score,
                "count": vote_count,
            }, return_id=False)

    logger.info(f"电影已保存: id={movie_id} title='{title}'")
    return movie_id


# ═══════════════════════════════════════════
# 2a1: 电影基础信息保存（原子事务，不含演职人员）
# ═══════════════════════════════════════════

async def save_movie_basic(movie_service, data: Dict[str, Any]) -> Optional[int]:
    """
    事务内原子写入电影基础信息（不含演职人员）。

    写入内容：movies + movie_genres(+history) + movie_regions(+history) + movie_ratings
    全部在一个事务内：任何一步失败 → 全部回滚。

    输入：
        movie_service: MovieService 实例
        data:          parser.parse_movie_detail() 的输出
    输出：
        movie_id 或 None（已存在则跳过）
    副作用：
        INSERT movies / movie_genres / regions / movie_regions / movie_ratings（同一事务）
    """
    douban_id = data.get("douban_id", "")
    title = data.get("title", "")
    if not douban_id or not title:
        return None

    # 去重在事务外 — LIMIT 1 纯读，不占长事务锁
    existing = await movie_service.get_movie_by_douban_id(douban_id)
    if existing:
        logger.debug(f"电影已存在，跳过: douban_id={douban_id} title='{title}'")
        return None

    release_date = None
    release_date_str = data.get("release_date", "")
    if release_date_str:
        try:
            release_date = date.fromisoformat(release_date_str.split(" ")[0])
        except (ValueError, TypeError):
            pass

    db_layer = movie_service.db
    genre_names = data.get("types", [])
    region_names = data.get("regions", [])
    score = data.get("score", 0)
    vote_count = data.get("vote_count", 0)

    genre_written = 0
    region_written = 0

    # 海报转存 TOS（在事务外，避免长事务阻塞）
    poster_url = await _mirror_poster(
        data.get("poster_url", ""), douban_id
    )

    async with db_layer.transaction() as tx:
        # 1. movies 主表
        values = {
            "douban_id": douban_id,
            "title": title,
            "original_title": data.get("original_title") or "",
            "release_year": data.get("release_year") or None,
            "release_date": str(release_date) if release_date else "",
            "duration": data.get("duration") or None,
            "poster_url": poster_url,
            "imdb_id": None,
        }
        movie_id = await tx.insert("movies", values, return_id=True)

        # 2. movie_genres（类型关联）
        for genre_name in genre_names:
            tn = await _resolve_type_num_in_tx(tx, genre_name)
            if tn:
                await tx.insert("movie_genres", {
                    "movie_id": movie_id, "type_num": tn,
                }, return_id=False)
                genre_written += 1
            else:
                logger.warning(
                    f"save_movie_basic: 类型名未在 crawl_progress 中找到, "
                    f"genre='{genre_name}' douban_id={douban_id}"
                )

        # 3. regions + movie_regions（地区关联/创建）
        for region_name in region_names:
            rid = await _find_or_create_region_in_tx(tx, region_name)
            if rid:
                await tx.insert("movie_regions", {
                    "movie_id": movie_id, "region_id": rid,
                }, return_id=False)
                region_written += 1

        # 4. movie_ratings（幂等 — 首次写入）
        if score > 0 or vote_count > 0:
            distribution_str = None
            if data.get("rating_distribution"):
                import json as _json
                distribution_str = _json.dumps(data["rating_distribution"])
            await tx.execute_raw(
                "INSERT INTO movie_ratings (movie_id, average, `count`, distribution) "
                "VALUES (%s, %s, %s, %s)",
                (movie_id, str(score), vote_count, distribution_str),
            )

    logger.info(
        f"save_movie_basic: movie_id={movie_id} title='{title}' "
        f"genres={genre_written}/{len(genre_names)} regions={region_written}/{len(region_names)}"
    )
    return movie_id


# ═══════════════════════════════════════════
# 2a2: 演职人员保存（原子事务）
# ═══════════════════════════════════════════

async def save_crew(movie_service, movie_id: int, crew: List[Dict[str, Any]]) -> int:
    """
    事务内原子写入演职人员关联。

    输入：
        movie_service: MovieService 实例
        movie_id:      本地 MySQL movie_id
        crew:          [{name, douban_id?, role_type}, ...]
                       role_type: "director" / "actor" / "writer" / "producer" / "art_director" / "music" / "other"
    输出：
        成功写入的人数
    副作用：
        INSERT people（幂等） + INSERT movie_credits（同一事务）
    设计决策：
        people 和 credits 写在同一个事务中，避免"人已创建但关联失败"的孤儿记录。
        去重在事务内（_find_or_create_person_in_tx 先查 people 再决定是否 INSERT）。
    """
    saved = 0
    db_layer = movie_service.db

    async with db_layer.transaction() as tx:
        for person in crew:
            name = person.get("name", "").strip()
            if not name:
                continue
            douban_id = person.get("douban_id", "")
            role_type = person.get("role_type", "other")
            if role_type not in ("director", "actor", "writer", "producer",
                                 "art_director", "music", "other"):
                role_type = "other"

            pid = await _find_or_create_person_in_tx(tx, name, douban_id)
            if not pid:
                continue

            try:
                await tx.insert("movie_credits", {
                    "movie_id": movie_id,
                    "person_id": pid,
                    "role_type": role_type,
                }, return_id=False)
                saved += 1
            except Exception as e:
                exc_msg = str(e)
                # 1062: (movie_id, person_id, role_type) 已存在 → 幂等跳过
                if "1062" in exc_msg or "Duplicate" in exc_msg:
                    logger.debug(
                        "[save_crew] 演职人员关联已存在: movie_id=%s person_id=%s role=%s",
                        movie_id, pid, role_type,
                    )
                    continue
                raise StorageError(
                    f"[save_crew] movie_credits 写入失败: movie_id={movie_id} "
                    f"person_id={pid} role_type={role_type}",
                    detail=exc_msg,
                ) from e

    logger.info(f"save_crew: movie={movie_id} saved={saved}/{len(crew)}")
    return saved


async def _find_or_create_person_in_tx(tx, name: str, douban_id: str = "") -> Optional[int]:
    """
    事务内查找或创建人员（幂等）。

    先按 douban_id 查，再按 name 查，都不存在则 INSERT。
    """
    if not name or not name.strip():
        return None
    name = name.strip()

    if douban_id:
        # 优先按 douban_id 查找（过滤无效人员）
        rows = await tx.execute_raw("SELECT * FROM people WHERE douban_id = %s AND is_duplicate != -1 LIMIT 1", (douban_id,))
        existing = rows[0] if rows else None
        if existing:
            return existing["id"]

    # 按 name 查找（过滤无效人员）
    rows = await tx.execute_raw("SELECT * FROM people WHERE name = %s AND is_duplicate != -1 LIMIT 1", (name,))
    existing = rows[0] if rows else None
    if existing:
        if douban_id and not existing.get("douban_id"):
            await tx.update("people", {"id": existing["id"]}, {"douban_id": douban_id})
        return existing["id"]

    return await tx.insert("people", {
        "name": name,
        "douban_id": douban_id or None,
    }, return_id=True)


async def _find_or_create_region_in_tx(tx, name: str) -> Optional[int]:
    """
    事务内查找或创建地区（幂等）。
    """
    if not name or not name.strip():
        return None
    name = name.strip()

    existing = await tx.find_one("regions", {"name": name})
    if existing:
        return existing["id"]

    return await tx.insert("regions", {"name": name}, return_id=True)


async def _resolve_type_num_in_tx(tx, type_name: str) -> Optional[int]:
    """
    事务内从 crawl_progress 查找类型名对应的 type_num。

    输入：
        tx:        TransactionContext（同一事务连接）
        type_name: 类型中文名（如 "剧情"）
    输出：
        type_num 或 None
    
    注意：在事务内查询，若 crawl_progress 在该事务中刚被写入，
    此查询可读到（同一连接可见未提交数据）。
    """
    if not type_name or not type_name.strip():
        return None
    name = type_name.strip()
    existing = await tx.find_one("crawl_progress", {"type_name": name})
    return existing["type_num"] if existing else None


# ═══════════════════════════════════════════
# 2a3: 导演保存 (MySQL via MovieService)
# ═══════════════════════════════════════════

async def save_directors(
    movie_service,
    movie_id: int,
    directors: List[Dict[str, Any]],
) -> int:
    """
    批量保存导演关联到 MySQL。

    输入：
        movie_service: MovieService 实例
        movie_id:      本地 MySQL movie_id
        directors:     parser.parse_directors() 返回的 dict 列表
                       每个 dict: {name: "弗兰克·德拉邦特", douban_id: "27218173"}
    输出：
        成功写入的导演数
    副作用：
        INSERT INTO people（如新导演）+ INSERT INTO movie_credits (role_type="director")
    幂等：
        _find_or_create_person 先查后插
        MovieService.add_credit 内部也是幂等的
    """
    saved = 0
    db_layer = movie_service.db

    for d in directors:
        name = d.get("name", "")
        douban_id = d.get("douban_id", "")
        if not name:
            continue

        pid = await _find_or_create_person(db_layer, name, douban_id=douban_id or None)
        if pid:
            await _safe_execute(
                f"添加导演: movie={movie_id} person={pid} name='{name}'",
                movie_service.add_credit(movie_id, pid, "director")
            )
            saved += 1

    logger.info(f"save_directors: movie={movie_id} saved={saved}/{len(directors)}")
    return saved


# ═══════════════════════════════════════════
# 2b: 长评保存 (MongoDB reviews)
# ═══════════════════════════════════════════

async def save_reviews(
    douban_id: str,
    reviews: List[Dict[str, Any]],
    movie_id: Optional[int] = None,
) -> int:
    """
    批量保存长评到 MongoDB reviews 集合。

    委托 ReviewService.upsert_review 处理 upsert + 并发安全。

    输入：
        douban_id: 豆瓣电影 ID（如 "1292052"），最终以 movie_douban_id 存入 MongoDB
        reviews:   parser.parse_review_full() 输出的 dict 列表
        movie_id:  本地 MySQL movie_id（可选）
    输出：
        成功写入的条数
    副作用：
        写入 MongoDB reviews 集合（via ReviewService）
    """
    from services.review_service import _get_review_service
    svc = _get_review_service()
    saved = 0
    for review in reviews:
        rid = review.get("review_id", "")
        if not rid:
            continue
        ok = await svc.upsert_review(rid, movie_douban_id=douban_id, review=review, movie_id=movie_id)
        if ok:
            saved += 1
    logger.info(f"save_reviews: douban_id={douban_id} saved={saved}/{len(reviews)}")
    return saved


# ═══════════════════════════════════════════
# 2c: 短评保存 (MongoDB comments)
# ═══════════════════════════════════════════

async def save_comments(
    douban_id: str,
    comments: List[Dict[str, Any]],
    movie_id: Optional[int] = None,
) -> int:
    """
    批量保存短评到 MongoDB comments 集合。

    委托 ReviewService.upsert_comment 处理 upsert + 并发安全。

    输入：
        douban_id: 豆瓣电影 ID（如 "1292052"），最终以 movie_douban_id 存入 MongoDB
        comments:  parser.parse_comments() 输出的 dict 列表
        movie_id:  本地 MySQL movie_id（可选）
    输出：
        成功写入的条数
    副作用：
        写入 MongoDB comments 集合（via ReviewService）
    """
    from services.review_service import _get_review_service
    svc = _get_review_service()
    saved = 0
    for cmt in comments:
        cid = cmt.get("comment_id", "")
        if not cid:
            continue
        ok = await svc.upsert_comment(cid, movie_douban_id=douban_id, comment=cmt, movie_id=movie_id)
        if ok:
            saved += 1
    logger.info(f"save_comments: douban_id={douban_id} saved={saved}/{len(comments)}")
    return saved
