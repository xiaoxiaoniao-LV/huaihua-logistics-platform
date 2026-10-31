FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# 用 Python 自带库做健康检查，避免额外安装 curl（构建环境不依赖 apt 源）
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).status == 200 else 1)"

# 先执行数据库迁移再启动服务。
# 注意：实时推送依赖进程内的 BroadcastHub 与 MQTT 订阅线程，
# 因此固定单进程运行（--workers 1），多进程会导致 WS 事件无法跨进程广播。
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --proxy-headers"]
