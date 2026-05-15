# ═══════════════════════════════════════════════════════════════
# BackEnd/Dockerfile
# 输入：BackEnd/ 目录源码
# 输出：生产就绪的 Quart + Hypercorn 镜像（含 Playwright Chromium）
#
# 关键设计决策：
#   - 使用 python:3.11-slim-bookworm（Debian 12）以兼容 Playwright
#   - 多阶段构建：builder 安装依赖 → runtime 仅复制必要产物
#   - Playwright 浏览器安装走官方 playwright install-deps 避免手动罗列系统库
#   - requirements.txt 先在 builder 中安装，避免每次改代码都重装依赖
# ═══════════════════════════════════════════════════════════════

# ── Stage 1: builder（编译依赖、下载 Chromium） ──
FROM python:3.11-slim-bookworm AS builder

WORKDIR /build

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libffi-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir --user -r requirements.txt

# ── 安装 Playwright 浏览器（Chromium + 系统依赖） ──
RUN pip install --no-cache-dir --user playwright && \
    python -m playwright install --with-deps chromium

# ── Stage 2: runtime（仅运行时依赖 + 源码） ──
FROM python:3.11-slim-bookworm

RUN groupadd -r appuser && useradd -r -g appuser -s /bin/false appuser && \
    mkdir -p /app /app/logs /app/data/cookies && \
    chown -R appuser:appuser /app

WORKDIR /app

# ── 继承 builder 中 Playwright 安装的系统依赖 ──
# playwright install-deps 已安装过，这里只补字体 + bash（entrypoint 脚本需要）
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        fonts-noto-cjk fonts-liberation bash && \
    rm -rf /var/lib/apt/lists/*

# ── 从 builder 复制 Python 包 + Playwright 浏览器 ──
COPY --from=builder /root/.local /home/appuser/.local
COPY --from=builder /root/.cache/ms-playwright /home/appuser/.cache/ms-playwright

# 环境变量：让 Python 能找到用户安装的包，让 Playwright 知道浏览器位置
ENV PATH="/home/appuser/.local/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH="/home/appuser/.cache/ms-playwright"

# ── 复制源码（放在最后，利用 Docker 缓存层） ──
COPY --chown=appuser:appuser . /app

# ── 入口脚本（建表 + 种子数据 + 启动服务） ──
COPY --chown=appuser:appuser docker-entrypoint.sh /app/docker-entrypoint.sh

USER root
RUN chmod +x /app/docker-entrypoint.sh
USER appuser

EXPOSE 8000

# 健康检查：每 30s 探测 /docs（OpenAPI 文档接口），无认证需求
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/docs')" || exit 1

# 入口脚本负责：等待数据库 → 建表 → 种子数据 → 启动 Hypercorn
ENTRYPOINT ["/app/docker-entrypoint.sh"]
