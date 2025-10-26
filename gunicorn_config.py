# Gunicorn 配置文件

# 绑定地址和端口
bind = "0.0.0.0:15000"

# 工作进程数
workers = 2

# 工作模式
worker_class = "sync"

# 最大请求数
max_requests = 1000
max_requests_jitter = 50

# 超时时间
timeout = 60

# 日志输出到 STDOUT/STDERR，便于 docker logs 查看
accesslog = "-"
errorlog = "-"
loglevel = "info"

# 进程名称
proc_name = "lucky-wheel"

# 预加载
preload_app = True
