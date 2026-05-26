# IP & Cookie 后台管理前端设计协调文档
> 最后更新：2026-05-14

## 一、需求背景
当前系统代理能力只覆盖部分任务，且缺乏完善的IP代理、Cookie账号的管理后台，需要扩展为通用能力并实现全生命周期管理。

---

## 二、第一期：代理行为参数化扩展到所有任务
### 1. 需求核心
把代理选择能力做成所有爬虫任务的通用可选项，支持灵活配置，无需硬编码。

### 2. 前端落地方案
#### 2.1 统一参数规范
- 所有任务提交接口统一增加可选参数 `proxy_key`，和现有 `cookie_id` 逻辑保持一致
  - 不传：默认不使用代理/使用系统默认代理
  - 传值：使用指定的代理节点
- 前端 `TaskSubmit` 类型定义已支持该字段，无需额外修改

#### 2.2 通用组件封装
- 抽离通用「代理选择器」组件：
  - 支持「不使用代理」选项默认置顶
  - 禁用状态的代理自动置灰不可选
  - 下拉选项展示格式：`代理备注 (地区) | 状态`
  - 统一加载状态、空状态提示
- 所有任务表单（电影爬、长评爬、短评爬、详情爬等）统一复用该组件，保持交互一致性

#### 2.3 全局默认配置支持
- 新增「系统配置」页面，增加「默认代理选择」配置项
- 新建任务时自动选中默认代理，支持手动修改
- 配置权限仅超级管理员可修改

#### 2.4 全链路代理信息展示
- 任务列表、任务详情、执行日志中增加「使用代理」字段展示
- 任务执行失败时，若判定为代理问题，前端明确提示：「代理连接失败，请检查代理配置」

---

## 三、第二期：IP代理 & Cookie 管理后台实现
### 1. 权限体系设计
复用现有权限系统，做细粒度权限控制：

| 权限code | 权限说明 | 可见范围 |
|---|---|---|
| `proxy:view` | 查看代理列表 | 所有管理员 |
| `proxy:edit` | 增删改代理、测试连通性 | 配置管理员/超级管理员 |
| `cookie:view` | 查看Cookie列表 | 所有管理员 |
| `cookie:edit` | 增删改Cookie、测试Cookie有效性 | 配置管理员/超级管理员 |
| `sensitive:view` | 查看敏感信息（代理密码、Cookie完整值） | 仅超级管理员 |

前端实现**路由级+按钮级**双重权限控制：
- 无权限用户看不到管理入口
- 无编辑权限用户看不到编辑、删除、复制敏感信息按钮
- 敏感信息默认脱敏展示，仅超级管理员可见完整内容

---

### 2. 页面设计：代理管理页面
#### 2.1 页面结构
- **顶部统计栏**：总代理数、在线代理数、禁用数、平均成功率
- **筛选区**：按状态（在线/离线/禁用）、地区、类型筛选，支持搜索代理备注
- **列表展示**：
  | 列名 | 说明 | 交互设计 |
  |---|---|---|
  | 代理备注 | 管理员自定义名称 | 支持模糊搜索 |
  | 类型 | HTTP/HTTPS/SOCKS5 | 标签展示 |
  | 地址 | ip:port | 普通管理员脱敏展示，超级管理员可见完整地址 |
  | 可用地区 | 代理支持的地区 | 多标签展示 |
  | 状态 | 运行状态 | 绿色=在线，红色=离线，灰色=禁用 |
  | 连通率 | 近100次请求成功率 | 进度条展示 |
  | 最近使用时间 | 最后一次被任务调用的时间 | - |
  | 操作 | 功能按钮 | 编辑、测试连通性、启用/禁用、删除 |
- **底部分页**：默认每页20条

#### 2.2 功能交互
- **新增/编辑代理弹窗**：
  表单字段：代理地址、端口、账号密码（可选）、备注、可用地区、是否启用
- **测试连通性**：
  点击后调用后端测试接口，实时返回结果：成功（延迟XXms）/失败（失败原因）
- **批量操作**：支持批量启用/禁用、批量删除
- **操作日志**：所有增删改操作记录操作人、操作时间、操作内容，支持溯源

---

### 3. 页面设计：Cookie管理页面
#### 3.1 页面结构
- **顶部统计栏**：总Cookie数、有效Cookie数、失效数
- **筛选区**：按状态（有效/失效/禁用）、平台筛选，支持搜索备注
- **列表展示**：
  | 列名 | 说明 | 交互设计 |
  |---|---|---|
  | Cookie备注 | 管理员自定义名称 | 支持模糊搜索 |
  | 绑定平台 | 所属站点，比如豆瓣 | 标签展示 |
  | 账号信息 | 绑定的手机号/用户名 | 脱敏展示 |
  | 状态 | 有效性状态 | 绿色=有效，红色=失效，灰色=禁用 |
  | 使用次数 | 累计被任务调用次数 | - |
  | 最近使用时间 | 最后一次被调用时间 | - |
  | 过期时间 | 预估过期时间 | 临近7天过期标黄提示 |
  | 操作 | 功能按钮 | 编辑备注、测试有效性、启用/禁用、删除、（超级管理员可见）复制完整Cookie |
- **底部分页**：默认每页20条

#### 3.2 功能交互
- **新增Cookie弹窗**：
  支持两种模式：手动粘贴Cookie值 / 扫码登录自动获取
- **测试有效性**：
  点击后调用后端接口，测试Cookie是否能正常请求目标站点，返回结果：有效/失效（失效原因）
- **失效提醒**：
  列表中失效Cookie标红提示，管理员登录时弹出通知：「当前有X个Cookie已失效，请及时更新」
- **敏感信息保护**：
  超级管理员点击「复制Cookie」按钮，直接复制完整值到剪贴板，页面不展示明文

---

### 4. 接口适配要求
前端需要后端提供以下标准接口：
#### 代理管理接口：
| 接口 | 方法 | 参数 | 说明 |
|---|---|---|---|
| `/admin/proxies` | GET | `page`, `page_size`, `status`, `region`, `keyword` | 分页查询代理列表 |
| `/admin/proxies` | POST | `host`, `port`, `username`, `password`, `remark`, `regions`, `enabled` | 新增代理 |
| `/admin/proxies/{id}` | PATCH | 同上 | 修改代理 |
| `/admin/proxies/{id}` | DELETE | - | 删除代理 |
| `/admin/proxies/test` | POST | `id` 或 代理信息 | 测试代理连通性 |
| `/admin/proxies/options` | GET | - | 获取代理选择下拉选项（任务提交页用） |

#### Cookie管理接口：
| 接口 | 方法 | 参数 | 说明 |
|---|---|---|---|
| `/admin/cookies` | GET | `page`, `page_size`, `status`, `platform`, `keyword` | 分页查询Cookie列表 |
| `/admin/cookies` | POST | `value`, `remark`, `platform`, `enabled` | 新增Cookie |
| `/admin/cookies/{id}` | PATCH | 同上 | 修改Cookie |
| `/admin/cookies/{id}` | DELETE | - | 删除Cookie |
| `/admin/cookies/test` | POST | `id` 或 Cookie值 | 测试Cookie有效性 |
| `/admin/cookies/options` | GET | - | 获取Cookie选择下拉选项（任务提交页用） |

#### 接口约定：
- 敏感信息自动脱敏：后端根据当前用户权限返回字段，普通管理员看不到密码、完整Cookie值
- 测试接口返回格式统一：`{ "success": true, "latency": 123, "message": "连接成功" }` / `{ "success": false, "message": "连接超时" }`

---

## 四、开发排期评估
现有后台已具备完善的组件库和权限体系，开发量可控：
| 模块 | 开发周期 | 说明 |
|---|---|---|
| 代理参数全任务扩展 | 0.5天 | 封装通用组件，修改各个任务表单 |
| 代理管理页面 | 1.5天 | 列表、弹窗、逻辑开发 |
| Cookie管理页面 | 1.5天 | 列表、弹窗、逻辑开发 |
| 权限打通+联调 | 0.5天 | 权限控制、接口联调 |
| **合计** | **4天** | 可在一周内完成上线 |

---

## 五、兼容性说明
所有改造不影响现有业务逻辑：
- 现有任务不传`proxy_key`参数保持原有行为不变
- 历史任务不受任何影响，正常运行

## 六、后端回应（2026-05-14）

### 6.1 现有能力盘点

| 维度 | 已实现 | 需要新增/改动 |
|------|--------|:--:|
| **代理轮转** | `ProxyPool` 状态机（alive/suspicious/banned） + 简单轮转 | 加认证字段（username/password） |
| **代理CRUD** | `GET/POST/DELETE /admin/proxies`（按 host:port 定位） | 加 id 定位 + PATCH 修改 |
| **代理测试** | `POST /admin/proxies/health-check`（全量验证） | 加单代理验证 |
| **代理选择器** | `GET /admin/proxies` 返回全体列表 | 加 `/admin/proxies/options` 精简下拉接口 |
| **Cookie CRUD** | `GET/POST/DELETE /admin/cookies`、`ban/unban/replace` | 加 PATCH 修改 + 单条验证 |
| **支付代理** | `.env` 中 `PAID_PROXY_*` 配置策略完成 | 启动时注入 ProxyPool |
| **权限** | 全部用 `system:monitor` | 建议细分 |

---

### 6.2 与前端设计的差异及对齐方案

#### ① 代理标识：`host:port` → `id`

前端期望 `/admin/proxies/{id}` 风格，后端目前按 `host:port` 路径参数。

**对齐方案**：proxy 为 `Proxy` 添加自增 ID，新增 `POST` 时返回 `id`。列表返回 `id` 字段。PATCH/DELETE 均按 `id` 操作。`proxy_key` 仍保留 `"host:port"` 格式（IdentityManager 以此查找），`id` 仅是管理端的外部标识。

#### ② 接口路径调整

| 前端期望 | 后端目前 | 对齐 |
|---------|---------|:--:|
| `GET /admin/proxies`（分页） | 返回全量 | 加分页参数 |
| `POST /admin/proxies` | ✅ 已有 | 加 `username/password/remark` |
| `PATCH /admin/proxies/{id}` | ❌ | **新增** |
| `DELETE /admin/proxies/{id}` | `DELETE /admin/proxies/<host>/<port>` | 改路径 + 软删除 |
| `POST /admin/proxies/test` | 已有 `health-check` | 加单代理验证 |
| `GET /admin/proxies/options` | ❌ | **新增**（只返回 alive 列表的 key+label） |
| `GET /admin/cookies`（分页） | 返回全量 | 加分页参数 |
| `POST /admin/cookies` | ✅ 已有 | 加 `remark/platform/enabled` |
| `PATCH /admin/cookies/{id}` | ❌ | **新增** |
| `DELETE /admin/cookies/{id}` | ✅ 已有 | 不变 |
| `POST /admin/cookies/test` | ❌ | **新增**（调 BrowserFetcher 做连通性测试） |
| `GET /admin/cookies/options` | ❌ | **新增** |

#### ③ 数据模型差异

**Proxy 模型扩充**（后端 `Proxy` dataclass）：

```
现有: host, port, status, fail_count, success_count, last_used, added_at, source, region
新增: id (自增), username, password, remark, proxy_type (http/https/socks5), enabled
```

**Cookie 模型扩充**（后端 `Account` dataclass）：

```
现有: id, label, file, allowed_regions, dbcl2_preview, saved_at, state, last_used_at...
新增: platform, remark, enabled, usage_count, expired_at
```

#### ④ 权限细分

前端提出了 `proxy:view/edit` + `cookie:view/edit` + `sensitive:view` 的权限粒度。后端建议：

| 权限码 | 对应 | 说明 |
|--------|------|------|
| `infra:proxy:read` | ≈ `proxy:view` | 看代理列表/选项 |
| `infra:proxy:manage` | ≈ `proxy:edit` | 增删改 + 测试 |
| `infra:cookie:read` | ≈ `cookie:view` | 看 Cookie 列表/选项 |
| `infra:cookie:manage` | ≈ `cookie:edit` | 增删改 + 测试 |
| `infra:sensitive:read` | ≈ `sensitive:view` | 看代理密码、完整 Cookie |

> 现有的 `system:monitor` 权限保留，包含以上全部。有任一细粒度权限也可访问对应 Tab。

#### ⑤ 敏感信息脱敏

后端以 API 返回时分层处理：
- **无 `infra:sensitive:read`**：`password` 返回 `"***"`，`dbcl2_preview` 只返回前 4 位
- **有 `infra:sensitive:read`**：返回完整值（前端超级管理员可见）
- 复制功能：前端调用专用接口 `GET /admin/cookies/{id}/raw` 返回完整 dbcl2 值到剪贴板

#### ⑥ 测试接口设计

**代理测试** `POST /admin/proxies/test`：
```json
// 请求: { "id": 1 } 或 { "host": "1.2.3.4", "port": 8080 }
// 响应:
{ "success": true,  "latency_ms": 234, "exit_ip": "182.131.27.109", "message": "连接成功" }
{ "success": false, "latency_ms": 0,   "message": "连接超时" }
```
实现：用 `aiohttp` 请求 httpbin.org/ip → 比对出口 IP 是否与代理 IP 一致。

**Cookie 测试** `POST /admin/cookies/test`：
```json
// 请求: { "id": "main" }
// 响应:
{ "success": true,  "message": "Cookie 有效，账号正常" }
{ "success": false, "message": "Cookie 已过期，请重新登录" }
```
实现：用 `BrowserFetcher` 带该 Cookie 访问豆瓣 → 检测是否被重定向到登录页。

#### ⑦ 后端认为需要前置讨论的点

| 问题 | 建议 |
|------|------|
| **代理 ID 生成** | 用自增整数（内存计数器），不持久化到 JSON（重启后重新分配，不影响功能） |
| **分页** | 代理/Cookie 数量小（<100），分页做内存切片即可，不需要 MySQL |
| **批量启用/禁用** | 前端可逐个调 PATCH，后端暂不做批量接口（代理/Cookie 数量不会很大） |
| **操作日志** | 建议后续迭代单独做，首版依赖 logger 日志即可 |
| **Cookie 过期时间** | Cookie 无标准过期字段，后端无法准确判断，建议前端不做「临近过期黄标」，改为定期手动验证 |

---

### 6.3 后端实施顺序建议

| 阶段 | 内容 | 文件 |
|------|------|------|
| **Step 1** | `Proxy` 加认证字段 → fetcher 适配 → .env 注入 | `proxy.py`, `fetcher.py`, `app.py` |
| **Step 2** | 代理接口补全（id 化 + PATCH + test + options + 分页） | `infra_routes.py` |
| **Step 3** | Cookie 接口补全（PATCH + test + options + 分页） | `infra_routes.py`, `cookie_manager.py` |
| **Step 4** | 权限码种子数据 + 接口切换权限 | `permission.py`, `seed_auth.py`, `infra_routes.py` |
| **Step 5** | 前后端联调 | — |

---

## 七、前端回应（2026-05-14）
✅ 完全同意后端的对齐方案，所有差异点均可适配，无技术障碍。

### 7.1 差异点对齐确认
| 后端提出的差异 | 前端适配方案 |
|---|---|
| **代理标识：id（管理端） + proxy_key（host:port，业务端）** | 前端在代理选择器内部维护映射关系：用户选择时看到备注，组件内部存储id和proxy_key的对应，提交任务时自动使用`host:port`格式的proxy_key传给后端，id仅用于管理端的增删改操作，用户无感知 |
| **接口路径调整** | 完全按照后端给出的新接口规范适配，包括分页参数、PATCH接口、test接口、options接口等，所有接口字段严格对齐后端模型 |
| **数据模型扩充** | 完全适配新增字段：<br> - 代理页展示`proxy_type`、`enabled`、`remark`字段<br> - Cookie页展示`platform`、`usage_count`、`last_used_at`字段 |
| **权限码命名调整为`infra:xx:xx`格式** | 前端权限判断逻辑同步修改，兼容现有`system:monitor`权限（拥有该权限默认拥有所有 infra 权限） |
| **敏感信息分层脱敏 + 专用复制接口** | 完全适配：<br> - 列表页默认展示后端返回的脱敏值<br> - 复制功能调用`GET /admin/cookies/{id}/raw`专用接口获取完整值，页面不展示明文，更安全 |
| **测试接口返回格式** | 完全符合前端预期，前端会把`latency_ms`（延迟）、`exit_ip`（出口IP）等额外信息展示在测试结果中，用户体验更好 |

---

### 7.2 前置讨论点回应
| 后端提出的问题 | 前端意见 |
|---|---|
| **代理ID内存自增，重启后重新分配** | 完全接受，前端不需要持久化ID，每次打开页面重新拉取列表即可，不影响正常使用 |
| **分页用内存切片实现** | 完全兼容，前端分页组件只需要后端返回`total`、`page`、`page_size`标准字段即可，不需要关心是内存分页还是数据库分页 |
| **首版不做批量接口** | 同意，前端实现前端层批量操作：用户勾选多个后循环调用`PATCH`接口，不影响用户体验，后续量级上来再加批量接口也可平滑升级 |
| **首版不做操作日志页面** | 同意，后续迭代再加，前端首版不开发日志页面 |
| **Cookie无准确过期时间，去掉临近过期提示** | 完全同意，前端把「过期时间」列改为「最后验证时间」，去掉黄标提示逻辑，改为引导管理员手动点击「测试有效性」按钮验证，更准确可靠 |

---

### 7.3 前端开发调整内容
相比原设计，前端只需要做少量适配调整，不影响整体开发周期：
1. **通用代理选择器组件**：内部维护`id`到`proxy_key`（host:port）的映射关系，提交任务时自动转换格式
2. **权限逻辑适配**：替换权限码为`infra:`开头的新格式，兼容现有`system:monitor`权限
3. **Cookie页面调整**：「过期时间」列改为「最后验证时间」，去掉过期提示逻辑
4. **接口适配**：按照后端新的接口路径、请求/返回格式调整所有接口调用逻辑
5. **复制功能适配**：Cookie复制功能调用专用的`/admin/cookies/{id}/raw`接口获取完整值

---

### 7.4 最终开发排期确认
所有调整都是小改动，开发周期保持不变，整体仍可在4天内完成上线：
| 模块 | 开发周期 | 说明 |
|---|---|---|
| 代理参数全任务扩展 | 0.5天 | 封装通用组件，处理id和proxy_key映射，修改各个任务表单 |
| 代理管理页面 | 1.5天 | 列表、弹窗、逻辑开发，适配新接口 |
| Cookie管理页面 | 1.5天 | 列表、弹窗、逻辑开发，适配新接口 |
| 权限打通+联调 | 0.5天 | 权限控制、接口联调 |
| **合计** | **4天** | 可与后端并行开发，同步联调 |

## 八、后端 Step 1 完成 — 代理认证支持（2026-05-14）

### 8.1 已完成改动

| 文件 | 改动详情 |
|------|---------|
| `crawler/proxy.py` | `Proxy` dataclass 新增 `username`, `password`, `id`, `remark`, `proxy_type`, `enabled` 字段；`has_auth` 属性；`add_proxy` 签名扩展；`list_all` 返回 `id`/`has_auth`/`remark`/`proxy_type`/`enabled`；`load_persisted`/`save_persisted` 兼容认证字段；`verify_proxy` 支持 username/password |
| `crawler/fetcher.py` | 新增 `_build_proxy_config(proxy)` 统一构建代理配置字典（含 username/password）；替换 3 处硬编码 `{"server": "http://..."}` |
| `crawler/identity.py` | `IdentityManager.resolve()` 构建 `proxy_config` 时加入 username/password |
| `app.py` | 启动时从 `.env` 读取 `PAID_PROXY_HOST/PORT/USER/PASS` → 注入 ProxyPool（含认证） |

### 8.2 对前端的影响

- **无需改接口协议**：代理管理 API `GET /admin/proxies` 返回字段新增 `id`, `has_auth`, `remark`, `proxy_type`, `enabled`
- **无需改任务提交**：`proxy_key` 仍然是 `"host:port"` 格式，认证信息对前端透明
- **`.env` 支持直接跑**：付费代理通过 `.env` 配置，启动即注入（测试阶段可直接使用，不需要管理界面）

### 8.3 新增的 `.env` 配置项

```bash
PAID_PROXY_HOST=182.131.27.109
PAID_PROXY_PORT=2018
PAID_PROXY_USER=ydl77404173
PAID_PROXY_PASS=TZKnlVbk
```

### 8.4 前端同步清单

- `GET /admin/proxies` 列表中增加了 `id`（整数）、`has_auth`（bool）、`remark`（str）、`proxy_type`（str）、`enabled`（bool）五个字段
- `POST /admin/proxies` 新增可选参数 `username`、`password`、`remark`

## 九、后端 Step 2 完成 — 代理接口 id 化补全（2026-05-14）

### 9.1 新增/修改的端点

| 方法 | 路径 | 状态 | 说明 |
|------|------|:--:|------|
| `GET` | `/admin/proxies` | 修改 | 加分页 + status/region/keyword 过滤；返回 `{items, total, page, page_size, stats}` |
| `POST` | `/admin/proxies` | 修改 | 支持 `username/password/remark`；返回 `{success, id, key}` |
| `PATCH` | `/admin/proxies/<id>` | **新增** | 修改 remark/username/password/region/enabled/proxy_type（全部可选） |
| `DELETE` | `/admin/proxies/<id>` | 修改 | 从 `host/port` 路径改为 `id` 路径，内部查找后 ban |
| `POST` | `/admin/proxies/test` | **新增** | 支持 `{id}` 或 `{host,port}`；返回 `{success, latency_ms, exit_ip, message}` |
| `GET` | `/admin/proxies/options` | **新增** | 精简下拉列表 `[{id, key, label, has_auth, region}]`，仅 alive |
| `POST` | `/admin/proxies/health-check` | 不变 | — |

### 9.2 ProxyPool 新增方法

| 方法 | 说明 |
|------|------|
| `get_by_id(proxy_id)` | 在 alive + suspicious 中按 id 查代理 |
| `update_proxy(proxy_id, **kwargs)` | 按 id 更新字段（批量 setattr） |
| `options_list()` | 仅 alive 代理的 `{id, key, label, has_auth, region}` 精简列表 |

### 9.3 前端适配清单

| 改动项 | 说明 |
|--------|------|
| `GET /admin/proxies` 返回格式变更 | `proxies` → `items`；新增 `total/page/page_size`；新增过滤参数 `status/region/keyword` |
| 删除路径变更 | `DELETE /admin/proxies/<host>/<port>` → `DELETE /admin/proxies/<id>` |
| 修改接口 | 使用 `PATCH /admin/proxies/<id>`，字段全部可选 |
| 测试接口 | 使用 `POST /admin/proxies/test {id}` |
| 下拉选项 | 使用 `GET /admin/proxies/options` → `{items: [{id, key, label, has_auth, region}]}` |
| 添加代理返回 | 新增 `id` 字段，用于后续 PATCH/DELETE |

### 9.4 兼容性说明

旧的 `DELETE /admin/proxies/<host>/<port>` 路径**已移除**，前端需要切换到按 `id` 删除。其余旧接口保留向后兼容的响应字段。

## 十、后端 Step 3 完成 — Cookie 接口补全（2026-05-14）

### 10.1 新增/修改的端点

| 方法 | 路径 | 状态 | 说明 |
|------|------|:--:|------|
| `GET` | `/admin/cookies` | 修改 | 加分页 + status/keyword 过滤；返回 `{items, total, page, page_size, stats}` |
| `POST` | `/admin/cookies` | 修改 | 支持 `remark`/`platform`；返回 `{success, account_id}` |
| `PATCH` | `/admin/cookies/<id>` | **新增** | 修改 label/remark/platform/enabled/allowed_regions（全部可选） |
| `DELETE` | `/admin/cookies/<id>` | 不变 | — |
| `POST` | `/admin/cookies/test` | **新增** | `{id}` → 访问豆瓣，检测登录态 |
| `GET` | `/admin/cookies/options` | **新增** | 精简下拉列表 `[{id, label, platform, allowed_regions}]`，仅 active+enabled |
| `POST` | `/admin/cookies/<id>/ban` | 不变 | — |
| `POST` | `/admin/cookies/<id>/unban` | 不变 | — |
| `GET` | `/admin/cookies/status` | 不变 | — |
| `POST` | `/admin/cookies/replace` | 不变 | — |

### 10.2 Account 模型新增字段

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `remark` | str | `""` | 管理员备注 |
| `platform` | str | `"douban"` | 平台标识 |
| `enabled` | bool | `true` | 是否启用 |
| `usage_count` | int | `0` | 累计被任务调用次数（每次 report_success 递增） |

### 10.3 CookieManager 新增方法

| 方法 | 说明 |
|------|------|
| `update_account(id, **kwargs)` | 按 id 更新 label/remark/platform/enabled/allowed_regions |
| `verify_account(id)` | aiohttp 访问豆瓣首页 → `allow_redirects=False` → 检测 302 到 login |
| `options_list()` | 仅 active+enabled 账号的 `{id, label, platform, allowed_regions}` 精简列表 |

### 10.4 前端适配清单

| 改动项 | 说明 |
|--------|------|
| `GET /admin/cookies` 返回格式 | 新增 `total/page/page_size`；新增过滤参数 `status/keyword` |
| 列表字段新增 | 每项新增 `remark`, `platform`, `enabled`, `usage_count` |
| 修改接口 | 使用 `PATCH /admin/cookies/<id>`，字段全部可选 |
| 测试接口 | 使用 `POST /admin/cookies/test {id}` |
| 下拉选项 | 使用 `GET /admin/cookies/options` → `{items: [{id, label, platform, allowed_regions}]}` |
| 添加账号 | 新增可选参数 `remark`, `platform` |

### 10.5 Cookie 验证逻辑说明

```
aiohttp GET https://movie.douban.com/
  allow_redirects=False
  headers: {"User-Agent": "Mozilla/5.0"}
  cookies: 该账号的 storage_state.cookies
  │
  ├─ 200 → Cookie 有效
  ├─ 302 Location 含 "login" → Cookie 过期
  └─ 其他 → 异常状态码

## 十一、后端 Step 4 完成 — 权限码种子数据 + 接口切换权限（2026-05-14）

### 11.1 新增 5 个权限码

| 权限码 | 名称 | 说明 | 可访问的端点 |
|--------|------|------|-------------|
| `infra:proxy:read` | 代理查看 | 查看代理列表和下拉选项 | `GET /admin/proxies`, `GET /admin/proxies/options` |
| `infra:proxy:manage` | 代理管理 | 增删改代理+连通性测试 | `POST/PATCH/DELETE /admin/proxies*`, `POST /test`, `POST /health-check` |
| `infra:cookie:read` | Cookie查看 | 查看Cookie列表和下拉选项 | `GET /admin/cookies`, `GET /admin/cookies/options`, `GET /admin/cookies/status` |
| `infra:cookie:manage` | Cookie管理 | 增删改Cookie+有效性测试 | `POST/PATCH/DELETE /admin/cookies*`, `POST /test`, `POST /ban/unban`, `POST /replace` |
| `infra:sensitive:read` | 敏感信息查看 | 查看代理密码、完整Cookie值 | 后续版本实现脱敏分层 |

### 11.2 权限兼容规则

- `system:monitor` 持有者**可同时访问**代理和 Cookie 的全部功能（建议在数据迁移后取消此权限）
- 拥有新权限码中任意一个即可访问对应的 **管理页面** Tab
- `infra:sensitive:read` 暂不实际强制，API 返回未脱敏数据（后续版本开启脱敏逻辑）

### 11.3 修改的文件

| 文件 | 改动 |
|------|------|
| [`scripts/seed_auth.py`](file:///e:/QuartEdition/BackEnd/scripts/seed_auth.py) | `PERMISSION_CODES` 新增 5 个；`INSERT INTO permissions` 新增 5 行；管理员权限数 9→14 |
| [`routes/admin/infra_routes.py`](file:///e:/QuartEdition/BackEnd/routes/admin/infra_routes.py) | 16 处 `@require_permission("system:monitor")` → 按端点职责切换为细粒度码 |

### 11.4 端点权限对照表

| 端点 | 旧权限 | 新权限 |
|------|--------|--------|
| `GET /admin/proxies` | `system:monitor` | `infra:proxy:read` |
| `GET /admin/proxies/options` | `system:monitor` | `infra:proxy:read` |
| `POST /admin/proxies` | `system:monitor` | `infra:proxy:manage` |
| `PATCH /admin/proxies/<id>` | `system:monitor` | `infra:proxy:manage` |
| `DELETE /admin/proxies/<id>` | `system:monitor` | `infra:proxy:manage` |
| `POST /admin/proxies/test` | `system:monitor` | `infra:proxy:manage` |
| `POST /admin/proxies/health-check` | `system:monitor` | `infra:proxy:manage` |
| `GET /admin/cookies` | `system:monitor` | `infra:cookie:read` |
| `GET /admin/cookies/options` | `system:monitor` | `infra:cookie:read` |
| `GET /admin/cookies/status` | `system:monitor` | `infra:cookie:read` |
| `POST /admin/cookies` | `system:monitor` | `infra:cookie:manage` |
| `PATCH /admin/cookies/<id>` | `system:monitor` | `infra:cookie:manage` |
| `DELETE /admin/cookies/<id>` | `system:monitor` | `infra:cookie:manage` |
| `POST /admin/cookies/test` | `system:monitor` | `infra:cookie:manage` |
| `POST /admin/cookies/<id>/ban` | `system:monitor` | `infra:cookie:manage` |
| `POST /admin/cookies/<id>/unban` | `system:monitor` | `infra:cookie:manage` |
| `POST /admin/cookies/replace` | `system:monitor` | `infra:cookie:manage` |

### 11.5 部署注意事项

运行 `seed_auth.py` 重新种子权限数据（idempotent，`ON DUPLICATE KEY UPDATE`）：
```bash
cd BackEnd
python scripts/seed_auth.py
```

完成后超级管理员将自动获得 14 条权限（原有 9 条 + 新品 5 条）。

### 11.6 前端适配清单

- 使用新权限码 `infra:proxy:read` 控制基础设施页面「代理」Tab 的可见性
- 使用新权限码 `infra:cookie:read` 控制基础设施页面「Cookie」Tab 的可见性
- 代理编辑/测试按钮需检查 `infra:proxy:manage`
- Cookie 编辑/测试/Ban/Unban 按钮需检查 `infra:cookie:manage`
- 可继续检查 `system:monitor` 作为向后兼容的回退判断
```