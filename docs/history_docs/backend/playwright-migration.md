# Crawler 包架构变更记录

> 时间：2026-04-28 ~ 2026-05-05
> 范围：aiohttp → Playwright → 双引擎（aiohttp+Playwright）

---

## 一、演进路线

```
Phase 1 (2026-04-28):   纯 aiohttp
                          │  问题: SHA-512 JS挑战页，aiohttp 无法绕过
                          ▼
Phase 2 (2026-04-28):   纯 Playwright
                          │  问题: JSON API 不需要浏览器，Playwright 太重
                          ▼
Phase 3 (2026-05-03):   双引擎 (当前)
                          ApiFetcher (aiohttp) + BrowserFetcher (Playwright)
```

---

## 二、决策：双引擎架构

### 问题分析

豆瓣有两种不同的页面类型：

| 页面类型 | URL 示例 | 反爬措施 | 最佳工具 |
|------|------|------|:--:|
| JSON API | `/j/chart/top_list?type=11&...` | Cookie 校验 | aiohttp（**不受 SHA-512 影响**） |
| JSON API | `/j/review/{id}/full` | Cookie 校验 | aiohttp |
| HTML 页面 | `/subject/{id}/reviews` | SHA-512 JS 挑战 | Playwright |
| HTML 页面 | `/subject/{id}/comments` | SHA-512 JS 挑战 | Playwright |
| HTML 页面 | `/subject/{id}/` (详情页) | SHA-512 JS 挑战 | Playwright |

### 决策

**JSON API 走 aiohttp，HTML 页面走 Playwright。**

| 引擎 | 类 | 底层工具 | 单次耗时 | 适用 |
|------|------|------|:--:|------|
| API 引擎 | `ApiFetcher` | aiohttp | ~0.5s | 电影列表、长评正文 |
| 浏览器引擎 | `BrowserFetcher` | Playwright Chromium | ~3.7s | 长评列表、短评列表、电影详情页 |

---

## 三、fetcher.py 接口

### ApiFetcher（aiohttp）

```python
class ApiFetcher:
    def __init__(self, cookies=None, proxy_pool=None, timeout=10, max_retries=3, direct_fallback=True):
        # cookies:         豆瓣登录Cookie字典
        # proxy_pool:      ProxyPool实例（可选）
        # direct_fallback: 代理不可用时是否有直连兜底

    async def fetch(self, url: str) -> dict | list | str:
        # 自动判断 Content-Type:
        #   application/json → json.loads() → dict/list
        #   其他 → str

    async def _request(self, url: str, proxy: dict) -> aiohttp.ClientResponse:
        # 单次HTTP GET

    async def _decompress(self, raw: bytes, content_encoding: str) -> bytes:
        # gzip / brotli 解压

    async def close(self):
        # 释放 aiohttp.ClientSession
```

**实现要点**：
- `_get_session()` 懒初始化 `aiohttp.ClientSession`（连接复用）
- `auto_decompress=False` + 手动解压（避免 aiohttp 内置解压被豆瓣屏蔽）
- Cookie 注入支持爬虫登录态
- 代理轮换 + 直连兜底

### BrowserFetcher（Playwright）

```python
class BrowserFetcher:
    def __init__(self, browser, proxy_pool=None, semaphore=None, timeout=15):
        # browser:     Playwright Chromium 浏览器实例
        # semaphore:   asyncio.Semaphore 并发控制
        # proxy_pool:  代理池（通过 new_context(proxy=...) 注入）

    async def fetch(self, url: str) -> str:
        # 返回完整 HTML 字符串
```

---

## 四、任务分派矩阵（2026-05-04 更新）

```
__init__.py: execute(task_str)
  │
  ├─ task.type = "movie_crawl"                    ← 原子化：电影+演员+导演
  │   ├─ ApiFetcher.fetch(JSON API)               ~0.5s
  │   ├─ parse_movie_list(list)                   → list[dict]
  │   ├─ save_movies(MovieService→MySQL)          → 8 张表（电影+演员+类型+地区+评分）
  │   └─ BrowserFetcher 逐部详情页                ~3.7s/部 (并发=2)
  │       ├─ parse_directors(html)                → [{name, douban_id}]
  │       └─ save_directors → movie_credits("director")
  │
  ├─ task.type = "director_crawl"                 ← 存量补录
  │   └─ BrowserFetcher.fetch(详情页) → save_directors
  │
  ├─ task.type = "review_crawl"                   ← 翻页 + 正文 API 并发
  │   ├─ BrowserFetcher.fetch(HTML 列表页, 翻页)   ~3.7s/页 (默认2页)
  │   ├─ parse_review_list(html)                  → list[review_id]
  │   ├─ ApiFetcher 并发获取正文                   并发=5
  │   │   └─ fetch(/j/review/{id}/full)           ~0.5s/条
  │   ├─ parse_review_full(json)                  → dict
  │   └─ save_reviews(MongoDB)
  │
  └─ task.type = "comment_crawl"                  ← 翻页
      ├─ BrowserFetcher.fetch(HTML, 翻页)          ~3.7s/页 (默认5页)
      ├─ parse_comments(html)                     → list[dict]
      └─ save_comments(MongoDB)
```

---

## 五、Worker 架构

### BrowserPool

```
BrowserPool(max_workers=5)
  ├── 1× Chromium 浏览器实例（~250MB）
  ├── asyncio.Semaphore(5) 控制并发
  ├── ApiFetcher 调用不受 semaphore 限制（aiohttp 轻量）
  └── task_queue.get() → crawler.execute(task) → 自动选择引擎
```

`execute_func` 签名保持不变：
```python
async (task: str) -> None
```

---

## 六、app.py 启动

```python
app.playwright = await async_playwright().start()
app.browser = await app.playwright.chromium.launch(headless=True)
app.movie_service = MovieService(app.db)
init_crawler(app.browser, movie_service=app.movie_service)

await init_browser_pool(
    task_queue=app.task_queue,
    execute_func=crawler_execute,    # ← 不再用 dummy_execute
    event_queue=app.worker_event_queue,
)
```

---

## 七、电影详情页 — 导演数据获取 ✅ 已实现

### 实现摘要（2026-05-04）

### 目标

`review_crawl` 和 `comment_crawl` 都拿到了 HTML，但**导演信息不在这些页面中**。导演数据需要进入电影详情页获取。

### 详情页 URL

```
https://movie.douban.com/subject/{douban_id}/
```

示例：`https://movie.douban.com/subject/1292052/`（肖申克的救赎）

### 需要提取的信息

| 字段 | HTML 示例 | 存入 |
|------|------|------|
| 导演名 | `<a href="/personage/27218173/" ...>奥斯卡·伊萨克</a>` | `people.name` |
| 导演豆瓣ID | URL 中的 `27218173` | `people.douban_id` |

### 提取策略

```python
# 1. BrowserFetcher.fetch(subject_detail_url) → HTML
# 2. 正则提取导演区域：
#    re.search(r'<span class="attrs">(.*?)</span>', html, re.DOTALL)
# 3. 提取 personage URL 和导演名：
#    re.findall(r'<a[^>]*href="/personage/(\d+)/"[^>]*>(.*?)</a>', attrs)
# 4. _find_or_create_person(name, douban_id=director_id)
# 5. MovieService.add_credit(movie_id, person_id, "director")
```

### 注意事项

1. **SHA-512** — 详情页同样受保护，必须用 BrowserFetcher
2. **延迟加载** — 部分内容可能通过 JS 动态渲染，Playwright 需等待 `networkidle`
3. **多导演** — 一部电影可能有多个导演（如联合执导），需全部提取
4. **导演也是演员** — 自导自演场景下，同一 `person_id` 会有两条 `movie_credits` 记录（role_type 不同），由联合主键 `(movie_id, person_id, role_type)` 支持

### 调用时机

建议在 `review_crawl` 或 `movie_crawl` 的任务流中，电影基本信息写入后，补充一次详情页爬取：

```
movie_crawl 任务
  ├─ ApiFetcher.fetch(top_list API) → parse_movie_list → save_movies
  ├─ 对每部电影:
  │   └─ BrowserFetcher.fetch(subject/{douban_id}/)       ← 详情页
  │       ├─ parse_directors(html) → list[(name, douban_id)]
  │       └─ _find_or_create_person + add_credit("director")
  └─ 完成
```

---

## 八、资源估算

| 指标 | aiohttp | Playwright | 双引擎(当前) |
|------|:------:|:----------:|:----------:|
| 内存 | ~5MB | ~250MB | ~250MB（浏览器在，aiohttp 增量极小） |
| 并发数 | 20 | 5 | 5 (Browser) + 不限 (Api) |
| 电影列表(20条) | 0.5s | 3.7s | **0.5s**（走 ApiFetcher） |
| 短评列表(20条) | — | 3.7s | **3.7s**（必须 Playwright） |
| 长评列表(20条) | — | 3.7s | **3.7s**（列表页 HTML） |
| 长评正文(20条) | 10s(串行) | — | **10s**（跑 ApiFetcher，可并发） |
| 详情页(导演) | — | 3.7s | **3.7s**（待实现） |

---

## 九、Crawler 包最终进度（2026-05-04）

| 文件 | 状态 | 测试 |
|------|:--:|:--:|
| `fetcher.py` | ✅ 双引擎 + 崩溃自愈 | 13 passed |
| `parser.py` | ✅ 5 个纯函数 (含 parse_directors) | 29/29 |
| `storage.py` | ✅ 4 个函数 (含 save_directors) | — |
| `__init__.py` | ✅ 5 路分发 + 翻页 + 并发 | — |
| `failure_service.py` | ✅ 事件合同 + 错误分类 | — |
| `proxy.py` | ✅ 代理池状态机 | 37 passed |
| `proxy_fetcher.py` | ✅ 代理供给 | 13 passed |

**累计测试**：133 passed（browser_pool + crawler + puller）

### 新增功能（2026-05-04）

| 功能 | 文件 | 状态 |
|------|------|:--:|
| 详情页导演提取 | `parser.py` + `__init__.py` | ✅ |
| 评论翻页 | `__init__.py` | ✅ |
| 短评翻页 | `__init__.py` | ✅ |
| 豆瓣登录 + Cookie 持久化 | `scripts/douban_login.py` + `scripts/save_cookies.py` | ✅ |
| 长评正文并发 | `__init__.py` (API_SEMAPHORE) | ✅ |
| movie_crawl 原子化 | `__init__.py` | ✅ |
| 浏览器崩溃自愈 | `fetcher.py` | ✅ |
| 失败事件合同 | `failure_service.py` | ✅ |
| 失败任务认领 | `task_failure_service.py` + `routes/admin/` | ✅ |
| JWT 认证授权 | `services/auth_service.py` + `utils/auth.py` | ✅ |
| 导演跳过优化 | `movie_service.py` (has_director) | ✅ |

### 待完成

| 任务 | 说明 |
|------|------|
| 爬虫集成测试 | ApiFetcher/BrowserFetcher/parse/save 全链路 |
| API 限速 | Semaphore 已就位，速率算法待配 |
| Worker 宕机自检测 | Monitor 需补充 worker_idle 告警 |
| 前端 Vue 3 | 未开始 |

---

## 十、相关文档

| 文档 | 内容 |
|------|------|
| [`browser-crash-recovery.md`](browser-crash-recovery.md) | BrowserFetcher 崩溃自愈设计 |
| [`mysql-design.md`](mysql-design.md) | MySQL 18 张表 DDL |
| [`2026-05-04-summary.md`](2026-05-04-summary.md) | 认证授权+失败认领+原子化 对话总结 |
