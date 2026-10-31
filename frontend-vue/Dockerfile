# 构建阶段
FROM node:22-alpine AS build

WORKDIR /app

# npm 源可通过构建参数覆盖（默认使用国内镜像，加速依赖安装）
ARG NPM_REGISTRY=https://registry.npmmirror.com

# 依赖层单独缓存
COPY package.json package-lock.json ./
RUN npm ci --registry=$NPM_REGISTRY

COPY . .
# 生产构建：不读取 .env（已被 .dockerignore 排除），API/WS 走同源相对路径
RUN npm run build

# 运行阶段
FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
    CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
