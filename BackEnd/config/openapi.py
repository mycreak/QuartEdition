"""
config/openapi.py

OpenAPI 文档配置。

集中管理 Quart 应用的 API 文档信息（标题、版本、标签）。
通过 quart-schema 扩展自动生成 OpenAPI 3.0 JSON + Swagger UI / ReDoc / Scalar。

使用方式（见 app.py）：
    from quart_schema import QuartSchema
    from config.openapi import DOC_INFO, DOC_TAGS

    QuartSchema(app, info=DOC_INFO, tags=DOC_TAGS)
    # → 自动提供 /openapi.json, /docs, /redocs, /scalar

标签说明：
    - tags 是 OpenAPI 的分类标签，用于 Swagger UI 中将端点分组。
    - 每个蓝图对应一个 tag，按功能域划分。
"""

from quart_schema import Info, Tag

# ═══════════════════════════════════════════════════════════════
# API 信息
# ═══════════════════════════════════════════════════════════════

DOC_INFO = Info(
    title="QuartEdition — 豆瓣电影数据采集与管理平台 API",
    version="1.0.0",
    description="""
QuartEdition 是一个基于 Quart（异步 Flask）构建的豆瓣电影数据采集与管理系统。

## 数据采集流程
1. **管理员提交爬虫任务** → `POST /admin/tasks`
2. **Puller 从 Redis 延迟队列拉取任务** → 放入 asyncio.Queue
3. **BrowserPool Worker 消费任务** → Crawler 双引擎（aiohttp + Playwright）爬取数据
4. **数据持久化至 MySQL（结构化）/ MongoDB（文档型）**
5. **Monitor 实时采集状态** → 通过 WebSocket `/ws/notifications` 推送给管理员

## 认证方式
- **JWT Token**：`POST /auth/login` 获取，有效期 7 天
- **请求头格式**：`Authorization: Bearer <token>`

## 三层权限模型
| 级别 | 路由前缀 | 鉴权要求 |
|------|---------|---------|
| 公开 | `/auth/*` | 无，仅登录/注册 |
| 用户 | `/user/*` | JWT + 任意有效用户 |
| 管理 | `/admin/*` | JWT + 特定权限码 |

## 数据库架构
| 数据库 | 用途 |
|--------|------|
| MySQL | 用户、权限、电影结构数据、爬虫进度、版本历史 |
| MongoDB | 长评、短评（文档型非结构化文本） |
| Redis | 延迟任务队列（ZSet）、请求限速 |
""",
)

# ═══════════════════════════════════════════════════════════════
# API 标签分组
# ═══════════════════════════════════════════════════════════════

DOC_TAGS = [
    Tag(
        name="认证",
        description="用户注册、登录、获取当前用户信息（公开端点）",
    ),
    Tag(
        name="电影浏览",
        description="用户端电影列表/详情查看（仅已上架内容，需登录）",
    ),
    Tag(
        name="分类与统计",
        description="用户端电影类型列表和统计信息（需登录）",
    ),
    Tag(
        name="评论浏览",
        description="用户端长评/短评浏览（仅已上架，需登录）",
    ),
    Tag(
        name="过滤器",
        description="用户端过滤器数据包（类型 + 评分区间，需登录）",
    ),
    Tag(
        name="爬虫任务",
        description="提交爬虫任务、查看爬取进度（需管理员权限）",
    ),
    Tag(
        name="失败任务管理",
        description="失败任务认领/重爬/解决（需管理员权限）",
    ),
    Tag(
        name="电影管理",
        description="电影数据上下架管理（需管理员权限）",
    ),
    Tag(
        name="评论管理",
        description="长评/短评上下架管理（需管理员权限）",
    ),
    Tag(
        name="用户管理",
        description="后台用户创建与权限分配（需管理员权限）",
    ),
    Tag(
        name="系统监控",
        description="系统状态（Worker/Puller/队列/数据库健康）实时查看（需管理员权限）",
    ),
    Tag(
        name="WebSocket",
        description="管理员实时通知推送（任务失败/系统状态）",
    ),
]
