# 构建阶段（uni-app：H5 产物）
FROM node:22-alpine AS build

WORKDIR /app

ARG NPM_REGISTRY=https://registry.npmmirror.com

COPY package.json package-lock.json ./
RUN npm ci --registry=$NPM_REGISTRY

COPY . .
# 生产构建：不读取 .env（已被 .dockerignore 排除），API 走同源 /api 由 Nginx 反代
RUN npm run build:h5

# 运行阶段
FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist/build/h5 /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
    CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
