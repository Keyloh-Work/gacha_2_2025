import os
import sqlite3
import logging

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH", "/data/db.sqlite")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # ユーザーポイントテーブル
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_points (
        user_id INTEGER PRIMARY KEY,
        points INTEGER NOT NULL
    );
    """)

    # ユーザーカードテーブル
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_cards (
        user_id INTEGER,
        card_no TEXT,
        PRIMARY KEY(user_id, card_no)
    );
    """)

    # ガチャデータテーブル
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS gacha_items (
        no TEXT PRIMARY KEY,
        url TEXT,
        chname TEXT,
        rarity TEXT,
        rate REAL,
        title TEXT
    );
    """)
    conn.commit()
    conn.close()
    logger.info("Database initialized.")

def load_gacha_data(csv_path):
    """CSVからgacha_itemsテーブルへデータを読み込む。
       既に同じNoが存在する場合はスキップする。
    """
    import csv
    import chardet

    if not os.path.exists(csv_path):
        logger.error(f"CSVファイルが見つかりません: {csv_path}")
        return

    # エンコーディング検出
    with open(csv_path, 'rb') as f:
        result = chardet.detect(f.read())
    encoding = result['encoding']

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    with open(csv_path, newline='', encoding=encoding) as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            no = row["No."]
            url = row["url"]
            chname = row["chname"]
            rarity = row["rarity"]
            rate = float(row["rate"])
            title = row["title"]

            # 既存データがある場合はスキップ（初回起動時のみ実行想定）
            cursor.execute("SELECT no FROM gacha_items WHERE no=?", (no,))
            if cursor.fetchone():
                continue

            cursor.execute("""
            INSERT INTO gacha_items (no, url, chname, rarity, rate, title)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (no, url, chname, rarity, rate, title))

    conn.commit()
    conn.close()
    logger.info("Gacha data loaded into DB.")

def get_points(user_id: int) -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT points FROM user_points WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    if not row:
        # 初期10ポイント
        conn.execute("INSERT INTO user_points(user_id, points) VALUES(?, ?)", (user_id, 10))
        conn.commit()
        conn.close()
        return 10
    conn.close()
    return row[0]

def set_points(user_id: int, points: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO user_points(user_id, points) VALUES(?,?)
    ON CONFLICT(user_id) DO UPDATE SET points=excluded.points
    """, (user_id, points))
    conn.commit()
    conn.close()

def add_card(user_id: int, card_no: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO user_cards (user_id, card_no) VALUES (?,?)", (user_id, card_no))
    conn.commit()
    conn.close()

def get_user_cards(user_id: int) -> list:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT card_no FROM user_cards WHERE user_id=?", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]

def add_daily_points():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, points FROM user_points")
    rows = cursor.fetchall()
    for user_id, pt in rows:
        new_pt = pt if pt >= 10 else pt + 1
        cursor.execute("UPDATE user_points SET points=? WHERE user_id=?", (new_pt, user_id))
    conn.commit()
    conn.close()
    logger.info("Daily points added to all users.")

def get_random_item_from_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT no, url, chname, rarity, rate, title FROM gacha_items")
    items = cursor.fetchall()
    conn.close()

    if not items:
        return None

    total_rate = sum(i[4] for i in items)
    import random
    r = random.uniform(0, total_rate)
    current = 0
    for i in items:
        current += i[4]
        if r <= current:
            return {
                "no": i[0],
                "url": i[1],
                "chname": i[2],
                "rarity": i[3],
                "rate": i[4],
                "title": i[5]
            }
    return None
