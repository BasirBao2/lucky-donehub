import random
import time
from datetime import datetime, timedelta
import requests
from flask import Flask, render_template, redirect, url_for, session, jsonify, request

from database import DatabaseImproved as Database

from donehub_api import DoneHubAPI, DoneHubAPIError

try:
    import config
except ImportError:
    print("错误: 请先创建 config.py 文件，可参考 config.py.example")
    exit(1)

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
_db = Database()

# LinuxDo OAuth2 配置
LINUXDO_AUTHORIZE_URL = "https://connect.linux.do/oauth2/authorize"
LINUXDO_TOKEN_URL = "https://connect.linux.do/oauth2/token"
LINUXDO_USER_INFO_URL = "https://connect.linux.do/api/user"

# 娱乐站（抽奖）配置
LOTTERY_COST = 20
LOTTERY_MAX_DAILY_SPINS = 5
LOTTERY_OPTIONS = [10, 20, 30, 50, 60, 100]
LOTTERY_WEIGHTS = [0.50, 0.25, 0.15, 0.05, 0.04, 0.01]

LOTTERY_EXTRA_PURCHASE_COST = 5
LOTTERY_EXTRA_PURCHASE_LIMIT = 5

# 加油站（签到）配置
SIGN_REWARD_MIN = 50
SIGN_REWARD_MAX = 100

CURRENCY_UNIT = getattr(config, 'QUOTA_UNIT', 500000)
DONEHUB_BASE_URL = getattr(config, 'DONEHUB_BASE_URL', getattr(config, 'NEW_API_BASE_URL', None))
DONEHUB_ACCESS_TOKEN = getattr(config, 'DONEHUB_ACCESS_TOKEN', getattr(config, 'NEW_API_ADMIN_TOKEN', None))

try:
    donehub_api = DoneHubAPI(DONEHUB_BASE_URL, DONEHUB_ACCESS_TOKEN, CURRENCY_UNIT)
except ValueError as exc:
    print(f"配置错误: {exc}")
    exit(1)


def _serialize_lottery_record(record):
    if not record:
        return None
    return {
        'id': record.get('id'),
        'quota': record.get('quota'),
        'redemption_code': record.get('redemption_code'),
        'lottery_date': record.get('lottery_date'),
        'status': record.get('status', 'completed'),
        'attempt_number': record.get('attempt_number'),
        'cost': record.get('cost', 0),
        'created_at': record.get('created_at')
    }


def _serialize_lottery_history(records):
    return [_serialize_lottery_record(record) for record in records] if records else []


def _serialize_sign_record(record):
    if not record:
        return None
    return {
        'id': record.get('id'),
        'reward': record.get('reward'),
        'sign_date': record.get('sign_date'),
        'status': record.get('status', 'completed'),
        'created_at': record.get('created_at')
    }


def _serialize_sign_history(records):
    return [_serialize_sign_record(record) for record in records] if records else []


def _get_donehub_user(user):
    if not user:
        return None

    linuxdo_id = str(user.get('linuxdo_id') or '').strip()
    username = user.get('username')

    try:
        if linuxdo_id and linuxdo_id != '0':
            profile = donehub_api.get_user_by_linuxdo_id(linuxdo_id)
            if profile:
                return profile

        if username:
            return donehub_api.get_user_by_linuxdo_username(username)

        return None
    except DoneHubAPIError as exc:
        raise DoneHubAPIError(f"DoneHub 查询失败: {exc}")


def _available_units(user_profile):
    quota_units = user_profile.get('quota') or 0
    used_units = user_profile.get('used_quota') or 0
    return quota_units - used_units


def _current_balance_dollars(user_profile):
    total_units = user_profile.get('quota') or 0
    return round(total_units / CURRENCY_UNIT, 2)


def _default_personal_summary():
    return {
        'total_quota': 0,
        'total_cost': 0,
        'net_change': 0,
        'attempts': 0
    }


def _verify_quota_increment(profile_id, initial_units, added_units):
    expected_units = initial_units + added_units
    latest_profile = None

    for _ in range(3):
        try:
            latest_profile = donehub_api.get_user_by_id(profile_id)
        except DoneHubAPIError:
            latest_profile = None

        if latest_profile:
            current_units = latest_profile.get('quota') or 0
            if current_units >= expected_units:
                return latest_profile

        time.sleep(0.3)

    return latest_profile


def _build_dashboard_data(user):
    user_id = user['id']

    spins_today, last_lottery = (getattr(_db, 'get_today_lottery_summary')(user_id)
                                 if hasattr(_db, 'get_today_lottery_summary')
                                 else (0, None))
    extra_purchases = getattr(_db, 'get_today_extra_purchases')(user_id) if hasattr(_db, 'get_today_extra_purchases') else 0
    total_attempt_limit = LOTTERY_MAX_DAILY_SPINS + extra_purchases
    remaining_attempts = max(0, total_attempt_limit - (spins_today or 0))
    lottery_history = _serialize_lottery_history(
        _db.get_user_lottery_history(user_id, limit=10)
        if hasattr(_db, 'get_user_lottery_history') else []
    )

    sign_today = getattr(_db, 'check_today_sign')(user_id) if hasattr(_db, 'check_today_sign') else None
    sign_history = _serialize_sign_history(
        getattr(_db, 'get_recent_sign_history')(user_id, limit=7) if hasattr(_db, 'get_recent_sign_history') else []
    )

    raw_leaderboard_records = getattr(_db, 'get_today_lottery_totals')(limit=10) if hasattr(_db, 'get_today_lottery_totals') else []
    leaderboard_records = [
        {
            'username': record.get('username') or '未知用户',
            'total_prize': int(record.get('total_quota') or 0),
            'total_cost': int(record.get('total_cost') or 0),
            'net_change': int(record.get('net_change') or 0),
            'attempts': int(record.get('attempts') or 0)
        }
        for record in raw_leaderboard_records
    ]

    personal_summary = (
        getattr(_db, 'get_today_lottery_summary_for_user')(user_id)
        if hasattr(_db, 'get_today_lottery_summary_for_user') else _default_personal_summary()
    ) or _default_personal_summary()

    donehub_user = None
    try:
        donehub_user = _get_cached_donehub_profile(user) or _get_donehub_user(user)
        if donehub_user:
            _store_donehub_profile_in_session(user, donehub_user)
    except DoneHubAPIError:
        donehub_user = None

    current_balance = _current_balance_dollars(donehub_user) if donehub_user else 0.0

    data = {
        'is_authenticated': True,
        'balance': current_balance,
        'sign': {
            'today_signed': bool(sign_today),
            'today_reward': sign_today.get('reward') if sign_today else None,
            'history': sign_history
        },
        'lottery': {
            'remaining_attempts': remaining_attempts,
            'history': lottery_history,
            'last_record': _serialize_lottery_record(last_lottery),
            'cost': LOTTERY_COST,
            'max_attempts': total_attempt_limit,
            'base_attempts': LOTTERY_MAX_DAILY_SPINS,
            'extra_purchased': extra_purchases,
            'extra_purchase_limit': LOTTERY_EXTRA_PURCHASE_LIMIT,
            'extra_purchase_cost': LOTTERY_EXTRA_PURCHASE_COST,
            'can_purchase_extra': extra_purchases < LOTTERY_EXTRA_PURCHASE_LIMIT
        },
        'leaderboard': leaderboard_records,
        'leaderboard_self': personal_summary
    }

    return data, current_balance


@app.route('/')
def index():
    if 'user' not in session:
        initial_data = {'is_authenticated': False}
        return render_template(
            'index.html',
            logged_in=False,
            initial_data=initial_data,
            lottery_max=LOTTERY_MAX_DAILY_SPINS,
            cost_per_spin=LOTTERY_COST,
            extra_purchase_cost=LOTTERY_EXTRA_PURCHASE_COST,
            extra_purchase_limit=LOTTERY_EXTRA_PURCHASE_LIMIT,
            user=None,
            current_balance=0
        )

    user = session['user']
    initial_data, current_balance = _build_dashboard_data(user)

    return render_template(
        'index.html',
        logged_in=True,
        user=user,
        current_balance=current_balance,
        initial_data=initial_data,
        lottery_max=LOTTERY_MAX_DAILY_SPINS,
        cost_per_spin=LOTTERY_COST,
        extra_purchase_cost=LOTTERY_EXTRA_PURCHASE_COST,
        extra_purchase_limit=LOTTERY_EXTRA_PURCHASE_LIMIT
    )


@app.route('/login')
def login():
    params = {
        'client_id': config.LINUXDO_CLIENT_ID,
        'redirect_uri': config.LINUXDO_REDIRECT_URI,
        'response_type': 'code',
        'scope': 'read'
    }
    auth_url = (
        f"{LINUXDO_AUTHORIZE_URL}?client_id={params['client_id']}&redirect_uri={params['redirect_uri']}&response_type={params['response_type']}&scope={params['scope']}"
    )
    return redirect(auth_url)


@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code:
        return "授权失败", 400

    token_data = {
        'client_id': config.LINUXDO_CLIENT_ID,
        'client_secret': config.LINUXDO_CLIENT_SECRET,
        'code': code,
        'grant_type': 'authorization_code',
        'redirect_uri': config.LINUXDO_REDIRECT_URI
    }

    try:
        token_response = requests.post(LINUXDO_TOKEN_URL, data=token_data, timeout=10)
        token_response.raise_for_status()
        token_json = token_response.json()
        access_token = token_json.get('access_token')
        if not access_token:
            return "获取 access_token 失败", 400

        headers = {'Authorization': f'Bearer {access_token}'}
        user_response = requests.get(LINUXDO_USER_INFO_URL, headers=headers, timeout=10)
        user_response.raise_for_status()
        user_info = user_response.json()

        linuxdo_id = str(user_info.get('id'))
        username = user_info.get('username', 'unknown')
        user = _db.get_or_create_user(linuxdo_id, username)

        session['user'] = {
            'id': user['id'],
            'username': user['username'],
            'linuxdo_id': user['linuxdo_id']
        }
        return redirect(url_for('index'))
    except Exception as exc:  # pylint:disable=broad-except
        print(f"OAuth2 错误: {exc}")
        return f"登录失败: {exc}", 500


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


@app.route('/dashboard-data')
def dashboard_data():
    if 'user' not in session:
        return jsonify({'success': False, 'message': '请先登录'}), 401

    user = session['user']
    data, _ = _build_dashboard_data(user)
    return jsonify({'success': True, 'data': data})


@app.after_request
def add_no_cache_headers(response):
    """避免登录后的个性化页面被中间层缓存，保护用户数据"""
    if request.path.startswith('/static'):
        return response

    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0, private'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


def _get_cached_donehub_profile(user):
    cached = session.get('donehub_profile') or {}
    cached_user_id = cached.get('donehub_user_id')
    cached_username = cached.get('username')
    cached_linuxdo_id = cached.get('linuxdo_id')
    cached_updated = cached.get('updated_at')
    cached_profile = cached.get('profile')

    if cached_updated:
        try:
            updated = datetime.fromisoformat(cached_updated)
            if datetime.utcnow() - updated > timedelta(minutes=5):
                cached_user_id = None  # force refresh
        except ValueError:
            cached_user_id = None

    if (
        cached_user_id
        and cached_username == user.get('username')
        and cached_linuxdo_id == user.get('linuxdo_id')
    ):
        try:
            profile = donehub_api.get_user_by_id(cached_user_id)
            if profile:
                return profile
        except DoneHubAPIError:
            pass

        if cached_profile:
            return cached_profile

    return None


def _store_donehub_profile_in_session(user, profile):
    if not profile:
        session.pop('donehub_profile', None)
        return

    session['donehub_profile'] = {
        'donehub_user_id': profile.get('id'),
        'username': user.get('username'),
        'linuxdo_id': user.get('linuxdo_id'),
        'updated_at': datetime.utcnow().isoformat(),
        'profile': profile
    }


def _get_donehub_profile_or_response(user, force_refresh=False):
    if not user:
        return None, jsonify({'success': False, 'message': '未登录', 'code': 'UNAUTHORIZED'}), 401

    if force_refresh:
        session.pop('donehub_profile', None)
    else:
        cached_profile = _get_cached_donehub_profile(user)
        if cached_profile:
            return cached_profile, None, None

    try:
        profile = _get_donehub_user(user)
    except DoneHubAPIError as exc:
        session.pop('donehub_profile', None)
        return None, jsonify({'success': False, 'message': str(exc), 'code': 'USER_LOOKUP_FAILED'}), 500

    if not profile or not profile.get('id'):
        session.pop('donehub_profile', None)
        return None, jsonify({'success': False, 'message': '未在 DoneHub 中找到对应用户，请先绑定账号', 'code': 'USER_NOT_FOUND'}), 400

    _store_donehub_profile_in_session(user, profile)
    return profile, None, None


@app.route('/sign', methods=['POST'])
def sign_action():
    if 'user' not in session:
        return jsonify({'success': False, 'message': '请先登录'}), 401

    user = session['user']
    user_id = user['id']
    profile, error_response, status_code = _get_donehub_profile_or_response(user, force_refresh=True)
    if error_response:
        return error_response, status_code

    initial_quota_units = profile.get('quota') or 0
    current_balance = _current_balance_dollars(profile)

    today_record = getattr(_db, 'check_today_sign')(user_id) if hasattr(_db, 'check_today_sign') else None
    if today_record:
        sign_history = _serialize_sign_history(
            getattr(_db, 'get_recent_sign_history')(user_id, limit=7) if hasattr(_db, 'get_recent_sign_history') else []
        )
        return jsonify({
            'success': False,
            'message': '今天已经签到啦，明天再来！',
            'code': 'ALREADY_SIGNED',
            'reward': today_record.get('reward'),
            'sign_history': sign_history,
            'current_balance': current_balance
        }), 400

    reward_amount = random.randint(SIGN_REWARD_MIN, SIGN_REWARD_MAX)

    if hasattr(_db, 'create_sign_record_atomic'):
        record = _db.create_sign_record_atomic(user_id, reward_amount)
    else:
        record = _db.create_sign_record(user_id, reward_amount)

    if not record:
        sign_history = _serialize_sign_history(
            getattr(_db, 'get_recent_sign_history')(user_id, limit=7) if hasattr(_db, 'get_recent_sign_history') else []
        )
        return jsonify({
            'success': False,
            'message': '今天已经签到啦，明天再来！',
            'code': 'ALREADY_SIGNED',
            'sign_history': sign_history,
            'current_balance': current_balance
        }), 400

    reward_units = reward_amount * CURRENCY_UNIT
    try:
        donehub_api.change_user_quota(profile['id'], reward_units, f"签到奖励 {reward_amount} $")
    except DoneHubAPIError as exc:
        if record and 'id' in record and hasattr(_db, 'delete_sign_record'):
            try:
                _db.delete_sign_record(record['id'])
            except Exception:  # pylint:disable=broad-except
                pass
        return jsonify({
            'success': False,
            'message': str(exc),
            'code': 'SIGN_FAILED',
            'current_balance': current_balance
        }), 500

    if record and 'id' in record and hasattr(_db, 'update_sign_status'):
        _db.update_sign_status(record['id'], 'completed')

    sync_profile = _verify_quota_increment(
        profile['id'],
        initial_quota_units,
        reward_units
    )

    if not sync_profile or (sync_profile.get('quota') or 0) < (initial_quota_units + reward_units):
        if record and 'id' in record and hasattr(_db, 'delete_sign_record'):
            try:
                _db.delete_sign_record(record['id'])
            except Exception:  # pylint:disable=broad-except
                pass
        sign_history = _serialize_sign_history(
            getattr(_db, 'get_recent_sign_history')(user_id, limit=7) if hasattr(_db, 'get_recent_sign_history') else []
        )
        return jsonify({
            'success': False,
            'message': 'DoneHub 额度同步失败，请稍后再试',
            'code': 'SIGN_SYNC_FAILED',
            'current_balance': current_balance,
            'sign_history': sign_history
        }), 500

    updated_profile = sync_profile
    current_balance = _current_balance_dollars(updated_profile)
    _store_donehub_profile_in_session(user, updated_profile)

    sign_history = _serialize_sign_history(
        getattr(_db, 'get_recent_sign_history')(user_id, limit=7) if hasattr(_db, 'get_recent_sign_history') else []
    )

    return jsonify({
        'success': True,
        'message': f'签到成功，奖励 {reward_amount} $',
        'reward': reward_amount,
        'current_balance': current_balance,
        'sign_history': sign_history
    })


@app.route('/lottery', methods=['POST'])
def lottery():
    if 'user' not in session:
        return jsonify({'success': False, 'message': '请先登录'}), 401

    user = session['user']
    user_id = user['id']

    spins_today, last_lottery = (getattr(_db, 'get_today_lottery_summary')(user_id)
                                 if hasattr(_db, 'get_today_lottery_summary')
                                 else (0, None))
    spins_today = spins_today or 0
    extra_purchases = getattr(_db, 'get_today_extra_purchases')(user_id) if hasattr(_db, 'get_today_extra_purchases') else 0
    max_attempts_today = LOTTERY_MAX_DAILY_SPINS + extra_purchases
    remaining_attempts = max(0, max_attempts_today - spins_today)

    profile, error_response, status_code = _get_donehub_profile_or_response(user)
    if error_response:
        return error_response, status_code

    available_units = _available_units(profile)
    current_balance = round(available_units / CURRENCY_UNIT, 2)

    if remaining_attempts <= 0:
        return jsonify({
            'success': False,
            'message': '今天已经抽过奖了，明天再来吧！',
            'quota': last_lottery['quota'] if last_lottery else None,
            'attempt_number': last_lottery.get('attempt_number') if last_lottery else None,
            'remaining_attempts': 0,
            'current_balance': current_balance,
            'available_balance': round(available_units / CURRENCY_UNIT, 2),
            'lottery_history': _serialize_lottery_history(_db.get_user_lottery_history(user_id, limit=10))
        }), 400

    required_units = LOTTERY_COST * CURRENCY_UNIT
    if available_units < required_units:
        return jsonify({
            'success': False,
            'message': '余额不足，无法抽奖，请先充值',
            'code': 'INSUFFICIENT_FUNDS',
            'remaining_attempts': remaining_attempts,
            'current_balance': current_balance,
            'available_balance': round(available_units / CURRENCY_UNIT, 2),
            'lottery_history': _serialize_lottery_history(_db.get_user_lottery_history(user_id, limit=10))
        }), 400

    prize_amount = random.choices(LOTTERY_OPTIONS, weights=LOTTERY_WEIGHTS, k=1)[0]
    redemption_code = f"DIRECT_{prize_amount}$"

    if hasattr(_db, 'create_lottery_record_atomic'):
        record = _db.create_lottery_record_atomic(
            user_id,
            prize_amount,
            redemption_code,
            cost=LOTTERY_COST,
            max_attempts=max_attempts_today
        )
    else:
        record = _db.create_lottery_record(user_id, prize_amount, redemption_code, cost=LOTTERY_COST,
                                           max_attempts=max_attempts_today)

    if not record:
        spins_today, last_lottery = (getattr(_db, 'get_today_lottery_summary')(user_id)
                                     if hasattr(_db, 'get_today_lottery_summary')
                                     else (LOTTERY_MAX_DAILY_SPINS, None))
        extra_purchases = getattr(_db, 'get_today_extra_purchases')(user_id) if hasattr(_db, 'get_today_extra_purchases') else 0
        max_attempts_today = LOTTERY_MAX_DAILY_SPINS + extra_purchases
        return jsonify({
            'success': False,
            'message': '今天已经抽过奖了，明天再来吧！',
            'quota': last_lottery['quota'] if last_lottery else None,
            'attempt_number': last_lottery.get('attempt_number') if last_lottery else None,
            'remaining_attempts': max(0, max_attempts_today - (spins_today or 0)),
            'current_balance': current_balance,
            'lottery_history': _serialize_lottery_history(_db.get_user_lottery_history(user_id, limit=10))
        }), 400

    cost_units = LOTTERY_COST * CURRENCY_UNIT
    prize_units = prize_amount * CURRENCY_UNIT

    try:
        donehub_api.change_user_quota(profile['id'], -cost_units, f"抽奖扣除 {LOTTERY_COST} $")
    except DoneHubAPIError as exc:
        if record and 'id' in record and hasattr(_db, 'delete_lottery_record'):
            try:
                _db.delete_lottery_record(record['id'])
            except Exception:  # pylint:disable=broad-except
                pass
        return jsonify({
            'success': False,
            'message': str(exc),
            'code': 'LOTTERY_FAILED',
            'remaining_attempts': remaining_attempts,
            'current_balance': current_balance
        }), 500

    try:
        donehub_api.change_user_quota(profile['id'], prize_units, f"抽奖奖励 {prize_amount} $")
    except DoneHubAPIError as exc:
        try:
            donehub_api.change_user_quota(profile['id'], cost_units, "抽奖失败回滚")
        except DoneHubAPIError as rollback_exc:
            print(f"抽奖回滚失败: {rollback_exc}")
            if isinstance(rollback_exc, DoneHubAPIError):
                return jsonify({
                    'success': False,
                    'message': f"奖励回滚失败，请联系管理员：{rollback_exc}",
                    'code': 'ROLLBACK_FAILED',
                    'remaining_attempts': remaining_attempts,
                    'current_balance': current_balance
                }), 500
        if record and 'id' in record and hasattr(_db, 'delete_lottery_record'):
            try:
                _db.delete_lottery_record(record['id'])
            except Exception:  # pylint:disable=broad-except
                pass
        return jsonify({
            'success': False,
            'message': str(exc),
            'code': 'LOTTERY_FAILED',
            'remaining_attempts': remaining_attempts,
            'current_balance': current_balance
        }), 500

    if record and 'id' in record and hasattr(_db, 'update_lottery_status'):
        _db.update_lottery_status(record['id'], 'completed')

    updated_profile = None
    try:
        updated_profile = donehub_api.get_user_by_id(profile['id'])
        if updated_profile:
            _store_donehub_profile_in_session(user, updated_profile)
    except DoneHubAPIError:
        updated_profile = None

    if updated_profile:
        current_balance = _current_balance_dollars(updated_profile)
    else:
        total_units = profile.get('quota') or 0
        current_balance = round((total_units - cost_units + prize_units) / CURRENCY_UNIT, 2)

    attempt_number = record.get('attempt_number') if isinstance(record, dict) else (spins_today + 1)
    extra_purchases = getattr(_db, 'get_today_extra_purchases')(user_id) if hasattr(_db, 'get_today_extra_purchases') else extra_purchases
    max_attempts_today = LOTTERY_MAX_DAILY_SPINS + extra_purchases
    remaining_after = max(0, max_attempts_today - attempt_number)

    lottery_history = _serialize_lottery_history(_db.get_user_lottery_history(user_id, limit=10))

    return jsonify({
        'success': True,
        'message': '恭喜你抽中了！额度已直接充值到账户',
        'quota': prize_amount,
        'cost': LOTTERY_COST,
        'attempt_number': attempt_number,
        'remaining_attempts': remaining_after,
        'redemption_code': redemption_code,
        'current_balance': current_balance,
        'net_change': round(prize_amount - LOTTERY_COST, 2),
        'lottery_history': lottery_history
    })


@app.route('/lottery/purchase', methods=['POST'])
def purchase_lottery_attempt():
    if 'user' not in session:
        return jsonify({'success': False, 'message': '请先登录'}), 401

    user = session['user']
    user_id = user['id']

    extra_purchases = getattr(_db, 'get_today_extra_purchases')(user_id) if hasattr(_db, 'get_today_extra_purchases') else 0
    if extra_purchases >= LOTTERY_EXTRA_PURCHASE_LIMIT:
        return jsonify({
            'success': False,
            'message': '今日可购买次数已达上限',
            'code': 'PURCHASE_LIMIT_REACHED'
        }), 400

    payload = request.get_json(silent=True) or {}
    try:
        requested_quantity = int(payload.get('quantity', 1))
    except (TypeError, ValueError):
        requested_quantity = 1

    requested_quantity = max(1, min(LOTTERY_EXTRA_PURCHASE_LIMIT, requested_quantity))

    remaining_quota = LOTTERY_EXTRA_PURCHASE_LIMIT - extra_purchases
    if requested_quantity > remaining_quota:
        return jsonify({
            'success': False,
            'message': f'今日最多还能购买 {remaining_quota} 次',
            'code': 'PURCHASE_LIMIT_REACHED',
            'remaining_quota': remaining_quota
        }), 400

    profile, error_response, status_code = _get_donehub_profile_or_response(user, force_refresh=True)
    if error_response:
        return error_response, status_code

    purchase_units = LOTTERY_EXTRA_PURCHASE_COST * CURRENCY_UNIT
    total_purchase_units = purchase_units * requested_quantity
    available_units = _available_units(profile)
    if available_units < total_purchase_units:
        return jsonify({
            'success': False,
            'message': '余额不足，无法购买额外抽奖次数',
            'code': 'INSUFFICIENT_FUNDS',
            'current_balance': round(available_units / CURRENCY_UNIT, 2)
        }), 400

    records = None
    if hasattr(_db, 'add_extra_purchase_atomic'):
        records = _db.add_extra_purchase_atomic(user_id, LOTTERY_EXTRA_PURCHASE_LIMIT, count=requested_quantity)
    else:
        return jsonify({
            'success': False,
            'message': '暂不支持购买额外次数'
        }), 500

    if not records:
        return jsonify({
            'success': False,
            'message': '今日可购买次数已达上限',
            'code': 'PURCHASE_LIMIT_REACHED'
        }), 400

    try:
        donehub_api.change_user_quota(profile['id'], -total_purchase_units,
                                      f"购买抽奖次数 {LOTTERY_EXTRA_PURCHASE_COST} $ × {requested_quantity}")
    except DoneHubAPIError as exc:
        if records and hasattr(_db, 'delete_extra_purchase'):
            for inserted in records:
                record_id = inserted.get('id') if isinstance(inserted, dict) else None
                if record_id:
                    try:
                        _db.delete_extra_purchase(record_id)
                    except Exception:  # pylint:disable=broad-except
                        pass
        return jsonify({
            'success': False,
            'message': str(exc),
            'code': 'PURCHASE_FAILED'
        }), 500

    updated_profile = None
    try:
        updated_profile = donehub_api.get_user_by_id(profile['id'])
        if updated_profile:
            _store_donehub_profile_in_session(user, updated_profile)
    except DoneHubAPIError:
        updated_profile = None

    dashboard_data, current_balance = _build_dashboard_data(user)

    return jsonify({
        'success': True,
        'message': f'成功购买 {requested_quantity} 次抽奖机会',
        'current_balance': current_balance,
        'data': dashboard_data
    })


def check_api_token():
    print("当前模式：DoneHub API 接入")
    print("正在校验 Access Token...")
    try:
        current_user = donehub_api.get_current_user()
    except DoneHubAPIError as exc:
        print(f"❌ DoneHub API 校验失败: {exc}")
        return False

    if not current_user:
        print("⚠️ DoneHub API 未返回用户信息")
        return False

    balance = _current_balance_dollars(current_user)
    print("✅ DoneHub API 校验成功")
    print(f"   管理员: {current_user.get('username')} (ID: {current_user.get('id')})")
    print(f"   当前余额: {balance:.2f} 美元")
    return True


if __name__ == '__main__':
    print("=" * 50)
    print("🎰 包子铺 幸运大转盘系统启动")
    print("=" * 50)
    print("访问地址: http://localhost:15000")
    print(f"DoneHub API: {DONEHUB_BASE_URL}")
    print("=" * 50)

    if not check_api_token():
        print("=" * 50)
        print("⚠️  警告: DoneHub API 校验失败")
        print("   请检查 config.py 中的 DONEHUB 配置")
        print("=" * 50)
    else:
        print("=" * 50)
        print("✅ 运行模式：DoneHub API 直连")
        print("   抽奖与签到奖励将直接同步至用户账户")
        print("   抽奖奖池：10/20/30/50/60/100 $")
        print("=" * 50)

    app.run(debug=True, host='0.0.0.0', port=15000)
