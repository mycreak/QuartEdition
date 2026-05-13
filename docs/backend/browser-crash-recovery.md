# BrowserFetcher 崩溃自愈设计

> 时间：2026-05-04
> 状态：已实现

---

## 一、问题背景

项目采用 1 个 Chromium 进程 + 5 个 Worker 协程共享架构：

```
app.py 启动
  └─ playwright.start() → browser (单例)
       └─ 注入 BrowserFetcher(self.browser = browser)
            ├─ Worker-0 ─ _do_fetch → browser.new_context()
            ├─ Worker-1 ─ _do_fetch → browser.new_context()
            ├─ Worker-2 ─ ...
            ├─ Worker-3 ─ ...
            └─ Worker-4 ─ _do_fetch → browser.new_context()
```

**共享 1 个 Chromium 进程，进程崩了 5 个 Worker 全废。**

| 崩溃类型 | 症状 | 旧行为 |
|------|------|------|
| 进程崩了（OOM/被 kill） | `browser.new_context()` 抛 `TargetClosedError` | Worker 上报 failure → 拿下个任务 → 又崩 → 循环 |
| 单次 page.goto 卡死 | `networkidle` 永不触发 | timeout 兜底，~15s 后返回 |
| Worker 自身崩 | `_worker_loop` 退出 | 该槽位永久丢失（5→4→3...→0） |

---

## 二、方案设计

### 核心原则：最小侵入，fether.py 内闭环

不新增异常类，不增加新文件，不修改 Worker/Queue/事件管线。

关键工具：
- `browser.is_connected()` — 检测进程是否活着（Playwright 内置）
- `asyncio.Lock` — 防 5 个 Worker 同时抢着重启

### 代码位置

全部集中在 `crawler/fetcher.py` 的 `BrowserFetcher` 类内：

```python
class BrowserFetcher:
    def __init__(self, browser, playwright=None, ...):
        self._playwright = playwright       # 保存引用以备重启
        self._restart_lock = asyncio.Lock() # 防并发重入

    async def _restart_browser(self):
        """带锁重启，二次检查 is_connected()"""
        async with self._restart_lock:
            if self.browser.is_connected():
                return               # 已被其他 Worker 重启过了
            await self.browser.close()
            self.browser = await self._playwright.chromium.launch(headless=True)

    # _do_fetch 的 except Exception:
    except Exception:
        if not self.browser.is_connected():
            await self._restart_browser()  # ← 只有这里新增了一行
        return "", False
```

### playwright 引用注入链路

```
app.py
  app.playwright = await async_playwright().start()
  init_crawler(browser, playwright=app.playwright)
       ↓
__init__.py
  BrowserFetcher(browser=browser, playwright=playwright, ...)
```

### 错误分类增强

`crawler/failure_service.py` — 新增 `FailureKind.BROWSER`：

```python
class FailureKind(str, Enum):
    BROWSER = "browser"  # Chromium 进程崩溃（已自动重启）
    ...

# classify_exception 中的关键字检测：
if any(kw in msg for kw in ("browser crashed", "target closed", "browser closed")):
    return FailureKind.BROWSER
```

---

## 三、恢复时间线

```
T=0    Worker-2 执行 _do_fetch
         → browser.new_context() → TargetClosedError (浏览器进程挂了)
         → except Exception → browser.is_connected() == False
         → self._restart_browser()
              ├─ lock 持有（Worker-0/1/3/4 如果也同时崩溃 → 排队等锁）
              ├─ browser.close() (best effort)
              ├─ playwright.chromium.launch(headless=True)
              └─ self.browser = new_browser
         → return "", False → fetch() 再试 → 代理切一轮全失败 → raise FetcherError
         → Worker 上报 failure (kind="browser" 或 "network")

T=1s   Worker-0 拿下一个任务 → browser.new_context() → 新进程，成功 ✅
T=2s   所有 Worker 恢复运行
```

---

## 四、设计取舍

| 决策 | 理由 |
|------|------|
| 不加新异常类 | `is_connected()` 比异常类名更可靠；Worker→Monitor 管线零改动 |
| `asyncio.Lock` 防并发 | 5 Worker 可能同时测到崩溃，只让第一个重启 |
| `is_connected()` 二次检查 | 进锁后可能浏览器已被其他 Worker 重启好了 |
| 不加 cooldown | Lock 本身就是串行化，连续崩溃也会逐次重启 |
| 不碰 Worker | 崩溃视为"这次 fetch 失败"，Worker 拿下个任务时自动用新浏览器 |

---

## 五、未覆盖的边界（已知限制）

| 场景 | 当前行为 | 后续可增强 |
|------|------|------|
| Worker 自身宕机 | 槽位丢失 | Monitor 检测 worker_idle=0 → 告警 |
| 连续崩 3 次 | 每次都会重启 | 可加衰减期（10s cooldown） |
| playwright 进程也死了 | `_playwright` 引用无效 | 需 app 级重启（极低概率） |
| 重启后登录态丢失 | `storage_state` dict 仍在内存 | 重启不丢失 |
