# 后端 TODO — 迭代需求记录

> 最后更新：2026-05-11
> 用途：记录后续迭代需要后端支持的功能，追踪实施进度

***

## 〇、火山引擎 TOS 图床 — 基础设施 🚧 设计中

> 解决头像和电影海报的统一图片存储问题。
> **本节是第一章（头像）和第二章（海报）的共同前置依赖。**

### 0.1 为什么选 TOS

| 考量     | 说明                                                     |
| ------ | ------------------------------------------------------ |
| **头像** | 用户上传的图片不能存本地磁盘（多实例不共享、备份困难）                            |
| **海报** | 豆瓣 CDN 外链不稳定（`doubanio.com` 可能限流/Referer 校验），需要转存到自有存储 |
| **统一** | 头像 + 海报共用同一套上传/签名 URL 逻辑，避免两套存储方案                      |
| **成本** | TOS 按量付费，开发期免费额度足够（10GB 存储 + 10GB 外网流量/月）              |

### 0.2 涉及改动

```
BackEnd/
├── requirements.txt                       # + volcengine-python-sdk (或 boto3 + S3 兼容 endpoint)
├── config/settings.py                     # + TOS_* 配置项
├── utils/tos_client.py                    # 新增: TOSClient 封装（上传/删除/签名 URL）
├── utils/tos_client.py                    # 核心方法:
│   ├── upload(key, data_bytes, content_type) → url   # 上传字节流
│   ├── delete(key)                                   # 删除文件
│   ├── sign_url(key, ttl=3600) → str                 # 生成带签名临时 URL
│   └── mirror_from_url(src_url, dest_key) → url     # 从外部 URL 下载并转存到 TOS
├── crawler/__init__.py / storage.py        # 修改: 电影爬取完成后海报转存 TOS
├── routes/user/profile_routes.py           # 修改: 头像上传切到 TOS
├── docs/数据库设计&使用/数据库设计.md        # 修改: poster_url / avatar_key 字段注释
└── scripts/migrate_posters.py             # 新增: 存量海报迁移脚本
```

### 0.3 配置（.env）

```bash
# ── 火山引擎 TOS ──
TOS_ENDPOINT=https://tos-cn-beijing.volces.com
TOS_REGION=cn-beijing
TOS_ACCESS_KEY=AKLTxxxxxxxxxxxxxxxx
TOS_SECRET_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TOS_BUCKET=quartedition-images
TOS_SIGNED_URL_TTL=86400                   # 签名 URL 有效期（秒），默认 24h

# ── 头像限制 ──
AVATAR_MAX_SIZE_MB=2
AVATAR_ALLOWED_TYPES=image/png,image/jpeg,image/webp

# ── 海报限制 ──
POSTER_MAX_SIZE_MB=5
```

### 0.4 TOS 目录结构（对象 Key 命名规范）

```
quartedition-images/
├── avatars/
│   ├── avatar_123456789012345678.webp      # 用户头像 (user.uuid)
│   └── avatar_987654321098765432.jpg
└── posters/
    ├── poster_1292052.webp                 # 电影海报 (movie.douban_id)
    ├── poster_3541415.jpg
    └── poster_27060077.png
```

### 0.5 TOSClient 核心接口

```python
# utils/tos_client.py

class TOSClient:
    """
    火山引擎 TOS 对象存储客户端。

    职责：
        1. 上传文件（头像 / 海报）
        2. 生成带签名的临时访问 URL（防止盗链）
        3. 从外部 URL 下载并转存到 TOS（海报场景核心方法）
        4. 删除文件
    """

    async def upload(
        self,
        key: str,                         # "posters/poster_1292052.webp"
        data: bytes,
        content_type: str = "image/webp",
    ) -> str:
        """上传字节流 → 返回完整对象 URL。"""

    async def mirror_from_url(
        self,
        src_url: str,                     # "https://img3.doubanio.com/view/photo/....jpg"
        dest_key: str,                    # "posters/poster_1292052.jpg"
        max_size: int = 5 * 1024 * 1024,  # 5MB 上限
    ) -> str | None:
        """
        从外部 URL 下载图片 → 转存到 TOS → 返回签名 URL。
        返回值：成功 → "https://tos-cn-beijing.volces.com/...?sign=..."，失败 → None
        不抛异常（爬虫容忍图片下载失败，不阻塞电影入库流程）。
        """

    async def sign_url(self, key: str, ttl: int = 86400) -> str:
        """生成带签名的临时 URL（前端直读 TOS，不经过后端代理）。"""

    async def delete(self, key: str) -> bool:
        """删除 TOS 上的文件。"""
```

### 0.6 签名 URL 机制（为什么不用公开读）

```
┌──────────────────────────────────────────────────────────────┐
│ 方案 A: 公开读（无签名）                                      │
│   前端直接访问固定 URL，但任何人都可以遍历读取                   │
│   不适合用户头像（隐私风险）                                    │
│                                                              │
│ 方案 B: 签名 URL（当前方案）                                   │
│   每次请求 API 时，后端生成有效期 24h 的临时签名 URL             │
│   过期后前端重新请求 API 获取新签名                             │
│   适合头像 + 海报（海报虽然是公开内容，签名也能防盗链）           │
└──────────────────────────────────────────────────────────────┘
```

### 0.7 性能考量

| 场景            | 策略                                                                              |
| ------------- | ------------------------------------------------------------------------------- |
| **海报转存**      | 爬虫 `asyncio.gather` 并发下载 `doubanio.com` → 并发上传 TOS（`BROWSER_SEMAPHORE` 已限 2 并发） |
| **头像上传**      | 前端 → 后端 → TOS，单次上传 \~200ms（内网直连）                                                |
| **签名 URL 缓存** | 不缓存——每次 API 请求动态生成，防止前端拿到过期 URL                                                 |
| **海报断点续爬**    | `mirror_from_url` 失败返回 None → `poster_url` 保持旧值（豆瓣 CDN 兜底），不阻塞电影入库              |

### 0.8 注意事项

| 风险           | 防御                                                                          |
| ------------ | --------------------------------------------------------------------------- |
| **TOS 未初始化** | `TOSClient` 实例化时 `ping` bucket 可访问性，不可用时降级：头像用本地文件兜底，海报保留豆瓣原 URL            |
| **SDK 选择**   | 火山引擎提供 `volcengine-python-sdk`（官方），或 `boto3` + S3 兼容 endpoint（社区成熟度更高，签名稳定） |
| **图片处理**     | TOS 原生支持图片处理——裁剪/缩略/WebP 转换可在 URL 参数中指定，无需后端处理                              |
| **成本控制**     | 签名 URL TTL=24h 防止过度签名请求；海报转存时 `max_size=5MB` 筛选异常大图                         |

### 0.9 待完成TODO：公开读转签名制

> 当前TOS Bucket配置为公开读，存在盗链和隐私风险，需要切换为签名制访问。

| 工作项            | 内容                                            | 优先级 |
| -------------- | --------------------------------------------- | --- |
| **Bucket权限修改** | 火山引擎控制台关闭Bucket公开读权限，改为私有读写                   | 高   |
| **签名逻辑落地**     | 完善`TOSClient.sign_url`方法，所有对外暴露的图片URL都通过签名生成  | 高   |
| **接口适配**       | 所有返回头像/海报的接口，都调用`sign_url`生成临时URL，不再返回固定公开URL | 高   |
| **前端适配**       | 前端图片加载逻辑兼容签名URL（无需修改，正常使用即可）                  | 中   |
| **缓存策略**       | 签名URL有效期设为24h，接口不缓存签名结果，每次请求动态生成              | 中   |

***

## 二、电影海报转存到 TOS — 爬虫侧重构 🚧 设计中

> 当前爬虫直接把豆瓣 CDN 的 `poster_url` 存入 MySQL。
> 豆瓣 CDN 不稳定且可能限制外链 Referer，需将海报下载后转存到自有 TOS。

### 2.1 现状基线

| 维度       | 现有逻辑                                                                                                                                   | 问题                           |
| -------- | -------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------- |
| **提取**   | [parser.py](file:///e:/QuartEdition/BackEnd/crawler/parser.py#L154-L165) 从 HTML 提取 `poster_url`（`img3.doubanio.com/view/photo/...jpg`） | 豆瓣 CDN 域名，外链可能被限             |
| **存储**   | [storage.py](file:///e:/QuartEdition/BackEnd/crawler/storage.py#L288) `poster_url=data.get("poster_url")` 直写 MySQL                     | 无转存逻辑                        |
| **数据库**  | `movies.poster_url VARCHAR(2048)` 存豆瓣原始 URL                                                                                            | 字段长度够用（TOS URL 约 200-400 字符） |
| **前端渲染** | `<img src="{{ poster_url }}">`                                                                                                         | 可能受 Referer 校验影响             |

### 2.2 重构方案（海报转存全流程）

```
爬取流程（修改后）：

movie_scrape_task → BrowserFetcher.fetch(detail_url)
→ parse_movie_detail(html)
   → poster_url = "https://img3.doubanio.com/view/photo/....jpg"
→ 转存: tos_url = await tos_client.mirror_from_url(poster_url, f"posters/poster_{douban_id}.jpg")
   ├─ 成功 → poster字段 = tos_url（TOS 带签名 URL）
   └─ 失败 → poster字段 = poster_url（保留豆瓣 CDN 兜底，不阻塞入库）
→ save_movie_basic(poster_url=tos_url | poster_url)
```

### 2.3 爬虫模块具体改动点

| 文件                                                                          | 改动详情                                                                                                                                                                                        |
| --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [crawler/__init__.py](file:///e:/QuartEdition/BackEnd/crawler/__init__.py)  | **新增 TOS 客户端注入**：1. 爬虫初始化时传入 `TOSClient` 实例2. 在 `_handle_movie_scrape_task()` 中，`parse_movie_detail` 返回后、`save_movie_basic` 之前插入海报转存逻辑3. 在 `_handle_movie_detail_crawl()` 中同样插入转存逻辑（增量爬取场景） |
| [crawler/parser.py](file:///e:/QuartEdition/BackEnd/crawler/parser.py)      | **不变**：继续提取原始豆瓣海报 URL                                                                                                                                                                       |
| [crawler/storage.py](file:///e:/QuartEdition/BackEnd/crawler/storage.py)    | **不变**：仍然接收 `poster_url` 参数，不关心是豆瓣还是 TOS URL                                                                                                                                                |
| [utils/tos\_client.py](file:///e:/QuartEdition/BackEnd/utils/tos_client.py) | **新增异常容忍**：`mirror_from_url` 方法全包 `try/except`，捕获所有异常（网络错误、下载超时、TOS 上传失败等），失败返回 None，不抛异常                                                                                                   |

### 2.4 转存逻辑核心实现（示例代码）

```python
# crawler/__init__.py 核心代码片段

async def _handle_movie_scrape_task(self, task: MovieScrapeTask) -> None:
    """处理单条电影爬取任务"""
    try:
        # 1. 爬取详情页
        html = await self._fetcher.fetch(task.detail_url)
        
        # 2. 解析电影数据
        movie_data = parse_movie_detail(html, task.douban_id)
        poster_url = movie_data.get("poster_url", "")
        
        # 3. 新增：海报转存 TOS
        if poster_url and self._tos_client:
            dest_key = f"posters/poster_{task.douban_id}.jpg"
            tos_poster_url = await self._tos_client.mirror_from_url(poster_url, dest_key)
            if tos_poster_url:
                movie_data["poster_url"] = tos_poster_url
                logger.info(f"[海报转存成功] douban_id={task.douban_id}, url={tos_poster_url[:80]}...")
            else:
                logger.warning(f"[海报转存失败] douban_id={task.douban_id}, 保留原URL={poster_url[:80]}...")
        
        # 4. 保存到数据库（原有逻辑不变）
        await self._storage.save_movie_basic(movie_data)
        
        logger.info(f"[爬取完成] douban_id={task.douban_id}, title={movie_data.get('title')}")
        
    except Exception as e:
        logger.error(f"[爬取失败] douban_id={task.douban_id}, err={str(e)}", exc_info=True)
        raise
```

### 2.5 容错与降级策略

| 场景                    | 处理方式                                      |
| --------------------- | ----------------------------------------- |
| **海报 URL 为空**         | 跳过转存，直接写入空字符串                             |
| **下载海报超时（>10s）**      | 捕获 `asyncio.TimeoutError`，返回 None，保留原 URL |
| **下载失败（4xx/5xx 状态码）** | 捕获 HTTP 异常，返回 None，保留原 URL                |
| **图片过大（>5MB）**        | 放弃转存，保留原 URL，防止占用过多存储                     |
| **TOS 上传失败**          | 捕获 TOS SDK 异常，返回 None，保留原 URL             |
| **TOS 服务不可用**         | 全局降级，所有海报都保留原 URL，不影响爬虫运行                 |

### 2.6 存量海报迁移脚本

```python
# scripts/migrate_posters.py — 运行方式: python -m scripts.migrate_posters

import asyncio
from config.settings import settings
from utils.tos_client import TOSClient
from db.database import db

async def migrate_posters(batch_size: int = 50, limit: int = None):
    """
    遍历 movies 表，取出 poster_url 为 doubanio.com 域名的记录，
    下载后转存到 TOS，更新 poster_url 字段。
    幂等：已转存为 TOS URL 的记录会自动跳过。
    """
    tos = TOSClient(settings.TOS_CONFIG)
    offset = 0
    migrated_count = 0
    
    while True:
        # 分页查询未转存的记录
        rows = await db.execute_raw(
            "SELECT id, douban_id, poster_url FROM movies "
            "WHERE poster_url LIKE '%doubanio.com%' "
            "AND poster_url != '' "
            "LIMIT %s OFFSET %s",
            (batch_size, offset)
        )
        
        if not rows:
            break
            
        for row in rows:
            try:
                dest_key = f"posters/poster_{row['douban_id']}.jpg"
                new_url = await tos.mirror_from_url(row["poster_url"], dest_key)
                if new_url:
                    await db.execute_update(
                        "UPDATE movies SET poster_url = %s WHERE id = %s",
                        (new_url, row["id"])
                    )
                    migrated_count += 1
                    logger.info(f"[迁移成功] id={row['id']}, douban_id={row['douban_id']}")
                else:
                    logger.warning(f"[迁移失败] id={row['id']}, douban_id={row['douban_id']}")
                    
            except Exception as e:
                logger.error(f"[迁移异常] id={row['id']}, err={str(e)}")
                continue
                
        offset += batch_size
        
        # 限制迁移总数（测试用）
        if limit and migrated_count >= limit:
            break
            
    logger.info(f"[迁移完成] 共处理 {migrated_count} 条记录")

if __name__ == "__main__":
    asyncio.run(migrate_posters())
```

### 2.7 实施步骤（可独立执行，不依赖头像功能）

| 步骤                   | 工作                                                                                                                                          | 可验证产出                                         |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------- |
| **Step 1: TOS 基础就绪** | ① 注册火山引擎账号 → 创建 `movie-poster` Bucket② 生成 AccessKey → 配置 .env TOS 相关参数③ 安装 SDK → `TOSClient(upload/sign_url/delete/mirror_from_url)` 方法测试通过 | 运行 `test_tos_upload.py` 上传测试图片成功，可通过签名 URL 访问 |
| **Step 2: 爬虫代码改造**   | ① 爬虫初始化时注入 TOSClient 实例② 在两个爬取入口插入海报转存逻辑③ 测试单条电影爬取：爬完后 poster\_url 为 TOS 链接                                                                 | 新增电影爬取后，数据库中 poster\_url 为 TOS URL，浏览器可正常显示   |
| **Step 3: 存量迁移**     | ① 运行迁移脚本，分批处理存量 426 部电影② 监控迁移进度，失败记录可二次重试                                                                                                   | 所有电影 poster\_url 完成转存，豆瓣链接占比 < 1%             |
| **Step 4: 上线验证**     | ① 爬虫生产环境运行 24h，监控转存成功率② 抽查前端海报渲染是否正常                                                                                                        | 转存成功率 > 99%，前端无海报加载失败问题                       |

***

## 三、电影评论AI总结功能 🚧 规划中

### 3.1 功能概述

> 针对豆瓣爬取的长评/短评，通过大模型生成AI总结，降低用户信息获取成本：
>
> - **单条长评摘要**：将上千字的长评压缩为100字以内的核心观点
> - **全量评论综合总结**：聚合所有长短评，提炼影片的核心评价、优缺点、观众画像
> - **评价标签生成**：自动生成"剧情紧凑""演技在线""结局烂尾"这类标签，辅助用户快速决策

### 3.2 整体流程设计

```
爬取评论 → 写入数据库 → 推送异步任务 → Worker调用AI生成 → 存储总结结果 → 接口返回给前端
```

### 3.3 数据库设计

#### 新增表：review\_summary（评论总结表）

```sql
CREATE TABLE `review_summary` (
  `id` int UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `movie_id` int NOT NULL COMMENT '关联电影ID',
  `long_review_summary` text COMMENT '单条长评摘要列表（JSON数组，每条对应一个长评）',
  `full_review_summary` text COMMENT '全量评论综合总结',
  `review_tags` json COMMENT '评价标签数组',
  `sentiment_ratio` json COMMENT '情感占比：{"positive": 0.7, "neutral": 0.2, "negative": 0.1}',
  `status` tinyint NOT NULL DEFAULT '0' COMMENT '状态：0=待生成, 1=生成成功, 2=生成失败',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_movie_id` (`movie_id`),
  KEY `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='电影评论AI总结表';
```

### 3.4 AI服务适配层设计

通用接口支持多模型切换（豆包/通义千问/开源模型），配置参数通过环境变量注入，避免硬编码密钥。核心方法：

- `generate_long_review_summary(review_content)`：生成单条长评摘要
- `generate_full_review_summary(reviews)`：生成全量评论综合总结、标签、情感占比

### 3.5 异步任务处理

复用现有后台Worker系统：

1. 爬虫爬取完某部电影评论后自动推送生成任务
2. 后台Worker消费任务，异步调用AI接口（不阻塞主流程）
3. 失败自动重试3次，重试失败标记为失败状态，支持手动重跑

### 3.6 API设计

- **原有接口扩展**：`GET /user/movies/{id}` 响应新增`review_summary`字段，包含总结、标签、情感占比
- **管理接口**：`POST /admin/movies/{id}/generate-summary` 支持手动触发重生成

### 3.7 容错与成本控制

| 风险            | 防御策略                        |
| ------------- | --------------------------- |
| **AI调用超时/失败** | 自动重试3次，失败后前端展示"暂无总结"，不影响主流程 |
| **重复调用浪费成本**  | 每部电影只生成一次，成功后不再调用，支持手动重跑    |
| **API费用超支**   | 配置调用频率限制，新增用量监控告警           |
| **内容异常**      | 增加返回内容格式校验，异常时重试，避免脏数据      |

### 3.8 实施步骤

| 步骤               | 工作                                        | 可验证产出              |
| ---------------- | ----------------------------------------- | ------------------ |
| **Step 1: 基础支持** | ① 新增review\_summary表② 实现AI服务适配层，完成单模型对接调试 | 调用AI接口可正常返回预期格式的总结 |
| **Step 2: 任务链路** | ① 新增异步任务类型② 爬虫端新增任务触发逻辑③ Worker端实现任务消费逻辑  | 爬取新电影后自动生成总结并入库    |
| **Step 3: 接口对接** | ① 电影详情接口新增summary字段返回② 新增管理员手动触发接口        | 前端请求电影详情可获取到总结内容   |
| **Step 4: 存量迁移** | 开发存量评论批量生成脚本，处理历史426部电影                   | 所有有评论的电影都有对应的总结    |
| **Step 5: 优化迭代** | ① 优化Prompt提升总结质量② 新增多模型支持切换③ 完善用量监控       | 总结准确率达90%以上        |

***

## 更新记录

| 日期         | 更新                                      |
| ---------- | --------------------------------------- |
| 2026-05-11 | 初稿：个人详情页 + 头像昵称编辑                       |
| 2026-05-11 | 新增：火山引擎 TOS 图床（头像 + 海报）                 |
| 2026-05-13 | 新增：TOS公开读转签名制TODO、爬虫海报重构方案、电影评论AI总结功能设计 |

***

## 一、用户个人详情页 + 头像昵称编辑 🚧 设计中

> 前端需求：用户/管理员可查看个人详情页、编辑自己的头像和昵称

### 1.1 现状基线

| 维度                            | 现有能力                                                                         | 缺口                           |
| ----------------------------- | ---------------------------------------------------------------------------- | ---------------------------- |
| **数据表**                       | `users` 含 `display_name`，无头像字段                                               | 需加 `avatar_key` 列            |
| **响应模型**                      | `UserRead` 含 `id/uuid/username/display_name/is_active/created_at/updated_at` | 需加 `avatar_url` 字段           |
| **更新模型**                      | `UserUpdate` 含 `display_name + is_active`                                    | 已有 display\_name，需另加头像入口     |
| **`GET /auth/me`**            | ✅ 已存在，返回当前用户信息                                                               | 返回体需补 `avatar_url`           |
| **`PATCH /admin/users/<id>`** | ✅ 管理员可改任何人                                                                   | —                            |
| **用户端 self-update**           | ❌ 不存在                                                                        | 需新增 `PUT /user/profile`      |
| **头像上传**                      | ❌ 不存在                                                                        | 需新增 `POST /user/avatar`      |
| **文件存储**                      | ❌ 无通用文件服务                                                                    | 由 §〇 TOS 图床统一接管              |
| **前端用户路由**                    | `user/` 仅有 movie/review/genre/filter                                         | 需新增 `user/profile_routes.py` |

### 1.2 需要新增/修改的文件

```
BackEnd/
├── models/user.py                      # 新增: UserProfileUpdate, UserProfileRead
├── routes/user/profile_routes.py       # 新增: GET /user/profile, PUT /user/profile, POST /user/avatar, DELETE /user/avatar
├── routes/user/__init__.py             # 修改: 注册 profile_bp
├── routes/public/auth_routes.py        # 修改: GET /auth/me 返回 avatar_url
├── services/auth_service.py            # 新增: update_profile(), update_avatar(), remove_avatar()
├── utils/tos_client.py                 # 依赖: §〇 TOSClient.upload/delete/sign_url
├── docs/数据库设计&使用/数据库设计.md    # 修改: users 表加 avatar_key 列
├── config/settings.py                  # + AVATAR_MAX_SIZE_MB / AVATAR_ALLOWED_TYPES
└── app.py                              # 修改: 注册 /static/avatars/ 静态路由（TOS 失效时的本地降级）
```

### 1.3 数据库变更

```sql
-- users 表新增头像字段
ALTER TABLE users
ADD COLUMN avatar_key VARCHAR(128) DEFAULT '' COMMENT '头像文件名 (如 avatar_1234567890.webp)'
AFTER display_name;
```

### 1.4 API 契约

#### 1.4.1 `GET /user/profile` — 查看自己的完整资料

```
请求:     GET /user/profile
认证:     Bearer JWT
响应 200: {
  "id": 1,
  "uuid": 123456789012345678,
  "username": "alice",
  "display_name": "Alice",
  "avatar_url": "/static/avatars/avatar_1234567890.webp",  // 空字符串=默认头像
  "is_active": true,
  "created_at": "2026-05-01T12:00:00+08:00",
  "updated_at": "2026-05-10T18:30:00+08:00"
}
```

#### 1.4.2 `PUT /user/profile` — 编辑自己的昵称

```
请求:     PUT /user/profile
Content:  application/json
Body:     {"display_name": "Alice Wang"}
认证:     Bearer JWT
响应 200: {"success": true, "display_name": "Alice Wang"}
```

#### 1.4.3 `POST /user/avatar` — 上传/替换头像

```
请求:     POST /user/avatar
Content:  multipart/form-data
Body:     avatar=<binary file>
认证:     Bearer JWT
限制:     - 仅允许 image/png, image/jpeg, image/webp
         - 最大 2MB
         - 上传后由后端写入 TOS，返回签名 URL
响应 200: {"success": true, "avatar_url": "https://tos-cn-beijing.volces.com/...?sign=..."}
错误 400: {"error": "仅支持 PNG/JPEG/WebP 格式", "code": "INVALID_AVATAR_TYPE"}
错误 413: {"error": "头像文件不能超过 2MB", "code": "AVATAR_TOO_LARGE"}
```

#### 1.4.4 `DELETE /user/avatar` — 移除头像（恢复默认）

```
请求:     DELETE /user/avatar
认证:     Bearer JWT
响应 200: {"success": true, "avatar_url": ""}
```

#### 1.4.5 管理员可选增强

```
GET  /admin/users/<id>/profile   — 管理员查看任意用户详情（含头像）
                                    （未来扩展：封面上传、个人简介、社交链接等）
```

### 1.5 安全问题

| 风险          | 防御措施                                      |
| ----------- | ----------------------------------------- |
| **文件扩展名欺骗** | 不信任上传文件名，通过 `filetype` 库检测真实 MIME 类型      |
| **路径穿越**    | 文件名用 `uuid.uuid4().hex` 生成，不包含用户输入        |
| **SVG XSS** | 禁止 `image/svg+xml` 类型                     |
| **越权修改**    | PUT/DELETE 只能操作自己，通过 `g.user_id` 从 JWT 解析 |
| **磁盘爆满**    | 单项 2MB 限制 + 总数=用户数约束（每个用户只保留最新一张）         |
| **旧头像未删除**  | 上传新头像时先删旧文件，原子操作：写新成功后才 unlink 旧文件        |

### 1.6 头像存储策略（由 §〇 TOS 图床接管）

```
用户上传头像:
  multipart/form-data → 后端接收 bytes
  → tos_client.upload(f"avatars/avatar_{user.uuid}.{ext}", data, content_type)
  → UPDATE users SET avatar_key = "avatar_{user.uuid}.webp"
  → 返回 tos_client.sign_url(avatar_key) → 前端直接渲染 <img>

读取头像:
  GET /auth/me → avatar_key → tos_client.sign_url(avatar_key, ttl=86400)
  前端: <img src="{{ avatar_url }}">  （TOS 直读，不经过后端代理）

删除头像:
  DELETE /user/avatar → tos_client.delete(avatar_key)
  → UPDATE users SET avatar_key = ""
```

> 不再需要本地 `data/avatars/` 目录——TOS 替代本地存储。

### 1.7 权限码（如需要 admin 管理）

```sql
-- 如果管理员需要查看/编辑任意用户资料（非常规操作，暂不新增权限码）
-- 当前 admin 已通过 PATCH /admin/users/<id> 覆盖 display_name
-- 未来如需扩展 "编辑任意用户头像"，建议新增:
-- INSERT INTO permissions VALUES ('user:profile:manage', '用户资料管理', '编辑任意用户的个人资料和头像');
```

### 1.8 实施拆分（建议 3 步）

| 步骤             | 工作                                                                                                                                             | 可验证产出                                     |
| -------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------- |
| **Step 1: 底子** | ① `ALTER TABLE` 加 `avatar_key` 列② `UserProfileRead` 模型 + `avatar_url` 构建（通过 TOS sign\_url）③ `GET /auth/me` 返回 avatar\_url④ TOS 基础就绪（§〇 Step 1） | `GET /auth/me` 返回 `avatar_url: ""`        |
| **Step 2: 上传** | ① `POST /user/avatar` 端点 + MIME 检测 + 2MB 限制② `auth_service.update_avatar()` → TOS upload③ `DELETE /user/avatar` 端点 → TOS delete                | curl 上传头像 → `GET /auth/me` 返回带签名的 TOS URL |
| **Step 3: 编辑** | ① `PUT /user/profile` 编辑 display\_name② `GET /user/profile` 完整个人资料③ admin user\_routes 中补 avatar\_url④ 前端对接                                    | 全流程闭环                                     |

