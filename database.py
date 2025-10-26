import sqlite3
from datetime import datetime
from contextlib import contextmanager
import threading


class DatabaseImproved:
    """改进的 SQLite 数据库管理类，支持并发安全和原子操作"""

    def __init__(self, db_name='lucky.db'):
        self.db_name = db_name
        self.lock = threading.Lock()
        self.init_db()

    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(self.db_name, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA locking_mode=NORMAL')
        try:
            yield conn
            conn.commit()
        except Exception as exc:  # pylint:disable=broad-except
            conn.rollback()
            raise exc
        finally:
            conn.close()

    def init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    linuxdo_id TEXT UNIQUE NOT NULL,
                    username TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS lottery_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    quota INTEGER NOT NULL,
                    redemption_code TEXT NOT NULL,
                    lottery_date DATE NOT NULL,
                    status TEXT DEFAULT 'pending',
                    attempt_number INTEGER DEFAULT 1,
                    cost INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sign_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    reward INTEGER NOT NULL,
                    sign_date DATE NOT NULL,
                    status TEXT DEFAULT 'completed',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')

            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_lottery_user_date
                ON lottery_records(user_id, lottery_date)
            ''')

            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_sign_user_date
                ON sign_records(user_id, sign_date)
            ''')

            self._ensure_lottery_columns(cursor)
            self._ensure_sign_constraints(cursor)

    def _ensure_lottery_columns(self, cursor):
        cursor.execute("PRAGMA table_info(lottery_records)")
        columns = {row[1] for row in cursor.fetchall()}
        if 'status' not in columns:
            cursor.execute("ALTER TABLE lottery_records ADD COLUMN status TEXT DEFAULT 'completed'")
            cursor.execute("UPDATE lottery_records SET status = 'completed' WHERE status IS NULL OR status = ''")
        if 'attempt_number' not in columns:
            cursor.execute("ALTER TABLE lottery_records ADD COLUMN attempt_number INTEGER DEFAULT 1")
        if 'cost' not in columns:
            cursor.execute("ALTER TABLE lottery_records ADD COLUMN cost INTEGER DEFAULT 0")

        cursor.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_lottery_user_date_attempt
            ON lottery_records(user_id, lottery_date, attempt_number)
            """
        )

    def _ensure_sign_constraints(self, cursor):
        cursor.execute("PRAGMA table_info(sign_records)")
        columns = {row[1] for row in cursor.fetchall()}
        if 'status' not in columns:
            cursor.execute("ALTER TABLE sign_records ADD COLUMN status TEXT DEFAULT 'completed'")
            cursor.execute("UPDATE sign_records SET status = 'completed' WHERE status IS NULL OR status = ''")

        cursor.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_sign_user_date
            ON sign_records(user_id, sign_date)
            """
        )

    def get_or_create_user(self, linuxdo_id, username):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE linuxdo_id = ?', (linuxdo_id,))
            user = cursor.fetchone()
            if user:
                return dict(user)

            cursor.execute(
                'INSERT INTO users (linuxdo_id, username) VALUES (?, ?)',
                (linuxdo_id, username)
            )
            cursor.execute('SELECT * FROM users WHERE linuxdo_id = ?', (linuxdo_id,))
            return dict(cursor.fetchone())

    def get_today_lottery_summary(self, user_id):
        today = datetime.now().date().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT COUNT(*) as cnt, MAX(attempt_number) as max_attempt FROM lottery_records WHERE user_id = ? AND lottery_date = ?',
                (user_id, today)
            )
            row = cursor.fetchone()
            if row is None:
                total = 0
            else:
                raw = row['cnt']
                total = raw if isinstance(raw, int) else int(raw or 0)

            cursor.execute(
                '''SELECT * FROM lottery_records
                   WHERE user_id = ? AND lottery_date = ?
                   ORDER BY attempt_number DESC, created_at DESC
                   LIMIT 1''',
                (user_id, today)
            )
            last = cursor.fetchone()
            return total, (dict(last) if last else None)

    def check_today_lottery(self, user_id):
        _, last = self.get_today_lottery_summary(user_id)
        return last

    def create_lottery_record_atomic(self, user_id, quota, redemption_code, cost=0, max_attempts=1):
        today = datetime.now().date().isoformat()
        with self.lock:
            try:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        'SELECT MAX(attempt_number) as attempt_num, COUNT(*) as total FROM lottery_records WHERE user_id = ? AND lottery_date = ?',
                        (user_id, today)
                    )
                    row = cursor.fetchone()
                    current_total = row['total'] if row and row['total'] else 0
                    next_attempt = (row['attempt_num'] or 0) + 1

                    if current_total >= max_attempts:
                        return None

                    cursor.execute(
                        '''INSERT INTO lottery_records
                           (user_id, quota, redemption_code, lottery_date, status, attempt_number, cost)
                           VALUES (?, ?, ?, ?, 'pending', ?, ?)''',
                        (user_id, quota, redemption_code, today, next_attempt, cost)
                    )

                    record_id = cursor.lastrowid
                    cursor.execute('SELECT * FROM lottery_records WHERE id = ?', (record_id,))
                    return dict(cursor.fetchone())
            except sqlite3.IntegrityError:
                return None

    def update_lottery_status(self, record_id, status):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE lottery_records SET status = ? WHERE id = ?', (status, record_id))
            return cursor.rowcount > 0

    def delete_lottery_record(self, record_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM lottery_records WHERE id = ?', (record_id,))
            return cursor.rowcount > 0

    def get_user_lottery_history(self, user_id, limit=10):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                '''SELECT * FROM lottery_records
                   WHERE user_id = ? AND status = 'completed'
                   ORDER BY created_at DESC
                   LIMIT ?''',
                (user_id, limit)
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_today_lottery_totals(self, limit=10):
        today = datetime.now().date().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                '''SELECT
                       u.id as user_id,
                       u.username as username,
                       COALESCE(SUM(l.quota), 0) as total_quota,
                       COALESCE(SUM(l.cost), 0) as total_cost,
                       COALESCE(SUM(l.quota - l.cost), 0) as net_change,
                       COUNT(l.id) as attempts
                   FROM lottery_records l
                   JOIN users u ON u.id = l.user_id
                   WHERE l.lottery_date = ? AND l.status = 'completed'
                   GROUP BY l.user_id, u.username
                   ORDER BY net_change DESC, total_quota DESC
                   LIMIT ?''',
                (today, limit)
            )
            rows = cursor.fetchall()
            return [
                {
                    'user_id': row['user_id'],
                    'username': row['username'],
                    'total_quota': row['total_quota'] or 0,
                    'total_cost': row['total_cost'] or 0,
                    'net_change': row['net_change'] or 0,
                    'attempts': row['attempts'] or 0
                }
                for row in rows
            ]

    def get_today_lottery_summary_for_user(self, user_id):
        today = datetime.now().date().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                '''SELECT
                       COALESCE(SUM(l.quota), 0) as total_quota,
                       COALESCE(SUM(l.cost), 0) as total_cost,
                       COALESCE(SUM(l.quota - l.cost), 0) as net_change,
                       COUNT(l.id) as attempts
                   FROM lottery_records l
                   WHERE l.user_id = ? AND l.lottery_date = ? AND l.status = 'completed'
                ''',
                (user_id, today)
            )
            row = cursor.fetchone()
            if not row:
                return {
                    'total_quota': 0,
                    'total_cost': 0,
                    'net_change': 0,
                    'attempts': 0
                }

            return {
                'total_quota': row['total_quota'] or 0,
                'total_cost': row['total_cost'] or 0,
                'net_change': row['net_change'] or 0,
                'attempts': row['attempts'] or 0
            }

    # 签到相关 --------------------------------------------------------------
    def check_today_sign(self, user_id):
        today = datetime.now().date().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT * FROM sign_records WHERE user_id = ? AND sign_date = ?',
                (user_id, today)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def create_sign_record_atomic(self, user_id, reward):
        today = datetime.now().date().isoformat()
        with self.lock:
            try:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        'SELECT id FROM sign_records WHERE user_id = ? AND sign_date = ?',
                        (user_id, today)
                    )
                    if cursor.fetchone():
                        return None

                    cursor.execute(
                        '''INSERT INTO sign_records
                           (user_id, reward, sign_date, status)
                           VALUES (?, ?, ?, 'pending')''',
                        (user_id, reward, today)
                    )
                    cursor.execute('SELECT * FROM sign_records WHERE id = ?', (cursor.lastrowid,))
                    return dict(cursor.fetchone())
            except sqlite3.IntegrityError:
                return None

    def get_recent_sign_history(self, user_id, limit=7):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                '''SELECT * FROM sign_records
                   WHERE user_id = ?
                   ORDER BY created_at DESC
                   LIMIT ?''',
                (user_id, limit)
            )
            return [dict(row) for row in cursor.fetchall()]

    def update_sign_status(self, record_id, status):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE sign_records SET status = ? WHERE id = ?', (status, record_id))
            return cursor.rowcount > 0

    def delete_sign_record(self, record_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM sign_records WHERE id = ?', (record_id,))
            return cursor.rowcount > 0
