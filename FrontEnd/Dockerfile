# ═══════════════════════════════════════════════════════════════
# FrontEnd/Dockerfile
# 输入：FrontEnd/ 目录源码
# 输出：Nginx 托管 Vue 3 静态文件的轻量镜像
#
# 关键设计决策：
#   - 多阶段构建：node 编译 → nginx:alpine 运行时（最终镜像 < 30MB）
#   - VITE_API_BASE_URL / VITE_WS_URL 在构建阶段通过 ARG 注入
#   - Nginx 作为反向代理：/ → 前端页面, /api/ → 后端, /ws/ → WebSocket
# ═══════════════════════════════════════════════════════════════

# ── Stage 1: build（Node.js 编译 Vue 应用） ──
FROM node:22-alpine AS build

WORKDIR /build

# 构建参数：允许在 docker build 时指定后端地址
ARG VITE_API_BASE_URL=/api
ARG VITE_WS_URL=ws://localhost:8000/ws/notifications
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL} \
    VITE_WS_URL=${VITE_WS_URL}

# 先复制 package.json + lock 文件，利用 Docker 缓存层
COPY package.json package-lock.json* yarn.lock* pnpm-lock.yaml* ./

# 根据锁文件自动选择包管理器
RUN if [ -f yarn.lock ]; then yarn install --frozen-lockfile; \
    elif [ -f package-lock.json ]; then npm ci; \
    elif [ -f pnpm-lock.yaml ]; then corepack pnpm install --frozen-lockfile; \
    else npm install; fi

# 复制源码并编译
COPY . .
RUN npm run build

# ── Stage 2: runtime（Nginx 托管静态文件） ──
FROM nginx:alpine

# 删除默认配置
RUN rm /etc/nginx/conf.d/default.conf

# 复制自定义 Nginx 配置
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 复制构建产物
COPY --from=build /build/dist /usr/share/nginx/html

EXPOSE 80

# 健康检查：Nginx 自带 stub_status 或直接 curl 首页
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -q --spider http://localhost:80/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
