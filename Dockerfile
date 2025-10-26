# 使用官方Python运行时作为基础镜像
FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai \
    FLASK_ENV=production

# 安装系统依赖和健康检查工具
RUN apt-get update && apt-get install -y \
    gcc \
    pkg-config \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制requirements文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir gunicorn

# 复制应用代码
COPY . .

# 创建数据目录（用于SQLite数据库）
RUN mkdir -p /app/data /app/logs \
    && chmod 755 /app/start.sh

# 暴露端口
EXPOSE 15000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:15000/ || exit 1

# 启动命令（生产环境使用gunicorn）
CMD ["bash", "/app/start.sh"]
