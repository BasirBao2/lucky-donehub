# DoneHub Lucky Hub

一个通过 LinuxDo OAuth2 登录的额度签到 + 抽奖站，所有额度操作通过 DoneHub API 完成。项目提供每日签到、幸运大转盘和实时榜单，并支持在页面内实时刷新余额及排行榜数据。

## 功能特性

- 🔐 LinuxDo OAuth2 登录
- ⛽ 加油站每日签到：随机奖励 50 – 100 $
- 🎡 娱乐站抽奖：消耗 20 $ 抽取 10 – 100 $
- 🏆 实时榜单：展示当日净收益前 10 与个人净收益概况
- 🔄 导航切换自动刷新数据，签到/抽奖结束后自动获取最新额度
- 🔌 DoneHub API 直连，包含额度调整与用户信息缓存

## 技术栈

- 后端：Flask (Python)
- 前端：原生 HTML + CSS + JavaScript
- 数据库：SQLite（`database.py`）
- 第三方：LinuxDo OAuth2、DoneHub API

## 项目结构

```
funny_done_hub/
├── app.py               # Flask 主应用入口（OAuth、业务路由、Dashboard 数据）
├── config.py            # 项目配置（需根据 config.py.example 自行创建）
├── database.py          # 线程安全的 SQLite 管理类与数据聚合
├── donehub_api.py       # DoneHub API 客户端封装
├── lucky.db             # SQLite 数据文件（运行后生成）
├── templates/index.html # 前端页面与交互逻辑
├── static/              # 静态资源
├── requirements.txt     # Python 依赖
└── README.md
```

## 环境配置

1. 安装依赖

```bash
pip install -r requirements.txt
```

2. 创建配置文件

```bash
cp config.py.example config.py
# 根据自身环境修改 config.py
```

`config.py` 关键项：

- LinuxDo OAuth2：`LINUXDO_CLIENT_ID`、`LINUXDO_CLIENT_SECRET`、`LINUXDO_REDIRECT_URI`
- DoneHub API：`DONEHUB_BASE_URL`、`DONEHUB_ACCESS_TOKEN`、`QUOTA_UNIT`
- 其他：`SECRET_KEY`

3. 运行应用

```bash
python app.py
```

访问 `http://localhost:25000`，按照页面提示使用 LinuxDo 账号授权登录。

## 主要接口

后端路由：

- `GET /`：首页，返回带初始数据的 HTML
- `GET /login`：跳转至 LinuxDo OAuth2 授权
- `GET /callback`：处理 OAuth2 回调并建立会话
- `POST /sign`：每日签到
- `POST /lottery`：幸运抽奖
- `GET /dashboard-data`：返回实时 Dashboard 数据（余额、历史、榜单）
- `GET /logout`：退出登录

前端在切换导航、签到、抽奖后会调用 `/dashboard-data` 获取最新数据并刷新页面元素。

## 数据说明

- `users`：LinuxDo 账号与内部用户映射
- `sign_records`：签到记录，限制每日一次
- `lottery_records`：抽奖记录，包含奖品、扣费及净变化
- `database.py` 提供聚合查询（今日净收益 Top 10、个人当日汇总等）

## 注意事项

1. `config.py` 含敏感信息，请勿提交到版本控制
2. 生产环境请启用 HTTPS，并使用真实回调域名
3. `QUOTA_UNIT` 需与 DoneHub 配置保持一致，否则额度换算会出错
4. 若 DoneHub 用户名已修改，系统会优先以 `linuxdo_id` 匹配，确保绑定准确

## 许可证

MIT License
