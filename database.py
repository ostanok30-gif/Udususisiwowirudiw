import sqlite3
from datetime import datetime, timedelta
from config import WARN_EXPIRE_DAYS


class Database:
    def __init__(self, db_path="moderator.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self._create_tables()

    def _create_tables(self):
        # Запрещённые слова
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS forbidden_words (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                word TEXT UNIQUE NOT NULL,
                added_by INTEGER,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Админы
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                role TEXT NOT NULL DEFAULT 'admin',
                added_by INTEGER,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Варны
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS warns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                admin_id INTEGER,
                reason TEXT,
                silent INTEGER DEFAULT 0,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Муты и баны
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS punishments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                type TEXT NOT NULL,
                until TIMESTAMP,
                admin_id INTEGER,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        self.conn.commit()

    # ========== СЛОВА ==========
    def add_word(self, word, added_by):
        try:
            self.cursor.execute(
                "INSERT INTO forbidden_words (word, added_by) VALUES (?, ?)",
                (word.lower(), added_by)
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def remove_word(self, word):
        self.cursor.execute(
            "DELETE FROM forbidden_words WHERE word = ?",
            (word.lower(),)
        )
        self.conn.commit()
        return self.cursor.rowcount > 0

    def get_all_words(self):
        self.cursor.execute("SELECT word FROM forbidden_words")
        return [row[0] for row in self.cursor.fetchall()]

    def is_forbidden(self, text):
        text_lower = text.lower()
        for word in self.get_all_words():
            if word in text_lower:
                return word
        return None

    # ========== АДМИНЫ ==========
    def add_admin(self, user_id, role="admin", added_by=None):
        self.cursor.execute(
            "INSERT OR REPLACE INTO admins (user_id, role, added_by, added_date) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            (user_id, role, added_by)
        )
        self.conn.commit()

    def remove_admin(self, user_id):
        self.cursor.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
        self.conn.commit()
        return self.cursor.rowcount > 0

    def get_admin(self, user_id):
        self.cursor.execute(
            "SELECT role FROM admins WHERE user_id = ?",
            (user_id,)
        )
        result = self.cursor.fetchone()
        return result[0] if result else None

    def get_all_admins(self):
        self.cursor.execute("SELECT user_id, role FROM admins")
        return self.cursor.fetchall()

    # ========== ВАРНЫ ==========
    def add_warn(self, user_id, admin_id, reason="", silent=0):
        self.cursor.execute(
            "INSERT INTO warns (user_id, admin_id, reason, silent) VALUES (?, ?, ?, ?)",
            (user_id, admin_id, reason, silent)
        )
        self.conn.commit()
        return self.cursor.lastrowid

    def remove_warn(self, user_id, warn_id):
        self.cursor.execute(
            "DELETE FROM warns WHERE id = ? AND user_id = ?",
            (warn_id, user_id)
        )
        self.conn.commit()
        return self.cursor.rowcount > 0

    def get_warns(self, user_id):
        expire_date = datetime.now() - timedelta(days=WARN_EXPIRE_DAYS)
        self.cursor.execute(
            "SELECT id, reason, date, silent FROM warns WHERE user_id = ? AND date >= ? ORDER BY date DESC",
            (user_id, expire_date)
        )
        return self.cursor.fetchall()

    def count_warns(self, user_id):
        expire_date = datetime.now() - timedelta(days=WARN_EXPIRE_DAYS)
        self.cursor.execute(
            "SELECT COUNT(*) FROM warns WHERE user_id = ? AND date >= ?",
            (user_id, expire_date)
        )
        return self.cursor.fetchone()[0]

    # ========== НАКАЗАНИЯ ==========
    def add_punishment(self, user_id, ptype, until=None, admin_id=None):
        self.cursor.execute(
            "INSERT INTO punishments (user_id, type, until, admin_id) VALUES (?, ?, ?, ?)",
            (user_id, ptype, until, admin_id)
        )
        self.conn.commit()

    def get_active_punishment(self, user_id):
        self.cursor.execute(
            "SELECT type, until FROM punishments WHERE user_id = ? AND (until IS NULL OR until > ?) ORDER BY date DESC LIMIT 1",
            (user_id, datetime.now())
        )
        return self.cursor.fetchone()

    def remove_punishment(self, user_id):
        self.cursor.execute(
            "UPDATE punishments SET until = ? WHERE user_id = ? AND (until IS NULL OR until > ?)",
            (datetime.now(), user_id, datetime.now())
        )
        self.conn.commit()

    def close(self):
        self.conn.close()