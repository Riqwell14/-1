import sqlite3
from dataclasses import dataclass
from typing import Optional


@dataclass
class Profile:
    user_id: int
    username: Optional[str]
    name: str
    age: int
    city: str
    gender: str
    looking_for: str
    bio: str


class Database:
    def __init__(self, path: str) -> None:
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS profiles (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                name TEXT NOT NULL,
                age INTEGER NOT NULL,
                city TEXT NOT NULL,
                gender TEXT NOT NULL,
                looking_for TEXT NOT NULL,
                bio TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS likes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_user_id INTEGER NOT NULL,
                to_user_id INTEGER NOT NULL,
                value INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(from_user_id, to_user_id)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_a INTEGER NOT NULL,
                user_b INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_a, user_b)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS active_chats (
                user_id INTEGER PRIMARY KEY,
                partner_id INTEGER NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.conn.commit()

    def upsert_profile(self, profile: Profile) -> None:
        self.conn.execute(
            """
            INSERT INTO profiles (user_id, username, name, age, city, gender, looking_for, bio, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username,
                name=excluded.name,
                age=excluded.age,
                city=excluded.city,
                gender=excluded.gender,
                looking_for=excluded.looking_for,
                bio=excluded.bio,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                profile.user_id,
                profile.username,
                profile.name,
                profile.age,
                profile.city,
                profile.gender,
                profile.looking_for,
                profile.bio,
            ),
        )
        self.conn.commit()

    def update_profile_field(self, user_id: int, field: str, value: str) -> None:
        if field not in {"name", "age", "city", "gender", "looking_for", "bio"}:
            return
        self.conn.execute(
            f"UPDATE profiles SET {field} = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
            (value, user_id),
        )
        self.conn.commit()

    def get_profile(self, user_id: int) -> Optional[sqlite3.Row]:
        cur = self.conn.execute("SELECT * FROM profiles WHERE user_id = ?", (user_id,))
        return cur.fetchone()

    def get_candidate(self, user_id: int) -> Optional[sqlite3.Row]:
        profile = self.get_profile(user_id)
        if profile is None:
            return None

        looking_for = profile["looking_for"]
        params = [user_id]
        filters = ["p.user_id != ?"]

        if looking_for != "any":
            filters.append("p.gender = ?")
            params.append(looking_for)

        query = f"""
            SELECT p.*
            FROM profiles p
            LEFT JOIN likes l ON l.from_user_id = ? AND l.to_user_id = p.user_id
            WHERE {' AND '.join(filters)}
              AND l.id IS NULL
            ORDER BY p.updated_at DESC
            LIMIT 1
        """
        params.insert(0, user_id)
        cur = self.conn.execute(query, params)
        return cur.fetchone()

    def set_like(self, from_user_id: int, to_user_id: int, value: int) -> bool:
        self.conn.execute(
            """
            INSERT INTO likes(from_user_id, to_user_id, value)
            VALUES (?, ?, ?)
            ON CONFLICT(from_user_id, to_user_id) DO UPDATE SET value = excluded.value
            """,
            (from_user_id, to_user_id, value),
        )
        self.conn.commit()

        if value != 1:
            return False
        cur = self.conn.execute(
            "SELECT value FROM likes WHERE from_user_id = ? AND to_user_id = ?",
            (to_user_id, from_user_id),
        )
        reverse = cur.fetchone()
        if reverse and reverse["value"] == 1:
            self._create_match(from_user_id, to_user_id)
            return True
        return False

    def _create_match(self, user_a: int, user_b: int) -> None:
        a, b = sorted([user_a, user_b])
        self.conn.execute(
            "INSERT OR IGNORE INTO matches(user_a, user_b) VALUES(?, ?)",
            (a, b),
        )
        self.conn.commit()

    def get_matches(self, user_id: int) -> list[sqlite3.Row]:
        cur = self.conn.execute(
            """
            SELECT p.*
            FROM matches m
            JOIN profiles p ON p.user_id = CASE WHEN m.user_a = ? THEN m.user_b ELSE m.user_a END
            WHERE m.user_a = ? OR m.user_b = ?
            ORDER BY m.created_at DESC
            """,
            (user_id, user_id, user_id),
        )
        return cur.fetchall()

    def are_matched(self, user_a: int, user_b: int) -> bool:
        a, b = sorted([user_a, user_b])
        cur = self.conn.execute(
            "SELECT 1 FROM matches WHERE user_a = ? AND user_b = ?",
            (a, b),
        )
        return cur.fetchone() is not None

    def set_active_chat(self, user_id: int, partner_id: int) -> None:
        self.conn.execute(
            """
            INSERT INTO active_chats(user_id, partner_id, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                partner_id = excluded.partner_id,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, partner_id),
        )
        self.conn.commit()

    def get_active_chat_partner(self, user_id: int) -> Optional[int]:
        cur = self.conn.execute(
            "SELECT partner_id FROM active_chats WHERE user_id = ?",
            (user_id,),
        )
        row = cur.fetchone()
        return row["partner_id"] if row else None

    def clear_active_chat(self, user_id: int) -> None:
        self.conn.execute("DELETE FROM active_chats WHERE user_id = ?", (user_id,))
        self.conn.commit()
