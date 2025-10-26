# New API 抽奖系统

一个简单的额度娱乐系统，用户通过 LinuxDo OAuth2 登录后，可在「加油站」每日签到获取 50-100 $补给，并在「娱乐站」消耗额度抽取 10-50 $奖励。所有额度通过 DoneHub API 实时发放，无需直接操作数据库。

## 功能特性

- 🔐 **LinuxDo OAuth2 登录** - 仅支持 LinuxDo 账号登录
- ✍️ **每日签到（加油站）** - 随机奖励 50 / 60 / 70 / 80 / 90 / 100 $
- 🎡 **额度抽奖（娱乐站）** - 消耗 20 $随机获得 10 / 20 / 30 / 50 / 60 / 100 $
- 🐾 **动物抽奖动画** - 可爱的动物图标闪烁抽奖效果
- 💾 **SQLite 数据库** - 轻量级本地数据存储
- 🔌 **DoneHub API 直连** - 扣费与派奖全部走后台接口，避免直连 DB

## 技术栈

- **后端**: Python + Flask
- **前端**: HTML + CSS + JavaScript
- **数据库**: SQLite
- **认证**: LinuxDo OAuth2

## 项目结构

```
new_api_lucky/
├── app.py                 # Flask 应用主文件（OAuth + 抽奖逻辑）
├── database.py            # 数据库管理类
├── config.py              # 配置文件（需自行创建）
├── lucky.db               # SQLite 数据库（自动生成）
├── requirements.txt       # Python 依赖
├── templates/
│   └── index.html        # 抽奖页面（动画 + UI）
└── README.md             # 项目说明
```

## 环境配置

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 创建配置文件

创建 `config.py` 文件，填入以下配置：

```python
# LinuxDo OAuth2 配置
LINUXDO_CLIENT_ID = "your_client_id"
LINUXDO_CLIENT_SECRET = "your_client_secret"
LINUXDO_REDIRECT_URI = "http://localhost:25000/callback"

# DoneHub API 配置
NEW_API_BASE_URL = "https://your-donehub.com"
NEW_API_ADMIN_TOKEN = "your_donehub_access_token"
DONEHUB_BASE_URL = NEW_API_BASE_URL
DONEHUB_ACCESS_TOKEN = NEW_API_ADMIN_TOKEN
NEW_API_USER_ID = "1"
QUOTA_UNIT = 500000  # 根据 DoneHub 设置调整

# Flask 配置
SECRET_KEY = "your_secret_key_here"
```

### 3. LinuxDo OAuth2 申请

1. 访问 LinuxDo 开发者设置
2. 创建新的 OAuth2 应用
3. 设置回调地址为: `http://localhost:25000/callback`
4. 获取 `Client ID` 和 `Client Secret`

## 快速开始

### 第一步：复制配置文件

```bash
cp config.py.example config.py
```

### 第二步：编辑配置文件

打开 `config.py`，填入以下配置：

**LinuxDo OAuth2 配置**:
1. 访问 https://linux.do/my/preferences/apps
2. 创建新应用
3. 设置回调 URL: `http://localhost:25000/callback`
4. 复制 Client ID 和 Client Secret 到配置文件

**New API 配置**:
1. 登录你的 New API 管理后台
2. 创建一个管理员 Token（在令牌管理页面）
3. 获取你的用户 ID（通常在个人设置中）
4. 填入配置文件

### 第三步：运行项目

```bash
python app.py
```

访问: `http://localhost:25000`

### 使用流程

1. 点击「LinuxDo 登录」按钮
2. 授权登录，进入主页
3. 在「加油站」签到领取 50-100 $补给
4. 在「娱乐站」开启幸运大转盘
5. DoneHub 余额实时更新，可后台查看日志

## 数据库结构

### users 表
- `id`: 用户 ID（主键）
- `linuxdo_id`: LinuxDo 用户 ID
- `username`: 用户名
- `created_at`: 注册时间

### lottery_records 表
- `id`: 记录 ID（主键）
- `user_id`: 用户 ID（外键）
- `quota`: 获得的额度（1-10）
- `redemption_code`: 兑换码
- `lottery_date`: 抽奖日期
- `created_at`: 创建时间

## API 接口说明

### 后端接口

- `GET /` - 首页（抽奖页面）
- `GET /login` - LinuxDo 登录跳转
- `GET /callback` - OAuth2 回调
- `POST /lottery` - 执行抽奖（自动检测今日是否已抽奖）
- `GET /logout` - 退出登录

## New API 兑换码接口

本项目调用 New API 的兑换码管理接口：

```
POST /api/redemption/
```

详细文档: https://www.newapi.ai/api/fei-redemption-code-management/

## 注意事项

⚠️ **重要提示**:

1. **生产环境**: 请使用 HTTPS，修改配置文件中的域名
2. **安全性**: 不要将 `config.py` 提交到 Git 仓库
3. **New API 权限**: 确保管理员 Token 有创建兑换码的权限
4. **额度单位**: 兑换码额度单位为"$"（USD），实际为 New API 的 quota 值（1$ = 100000）

## 开发说明

### 抽奖逻辑

1. 检查用户今天是否已抽奖（基于 `lottery_date`）
2. 随机生成 50-100 的额度（美元）
3. 保存抽奖记录到数据库


 

## 许可证

MIT License

## 鸣谢

- [New API](https://github.com/QuantumNous/new-api) - 大模型网关系统
- [LinuxDo](https://linux.do/) - 社区平台
