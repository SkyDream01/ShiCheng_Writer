# ShiCheng_Writer/modules/database.py
import sqlite3
import os
import json
from datetime import datetime

DB_FILE = "ShiCheng_Writer.db"

def get_db_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def initialize_database():
    """初始化数据库，创建所有需要的表，并执行迁移"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # --- 1. 创建所有表结构 (安全操作) ---
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS books (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT,
        cover_path TEXT,
        "group" TEXT,
        createTime INTEGER,
        lastEditTime INTEGER
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chapters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        book_id INTEGER NOT NULL,
        volume TEXT,
        title TEXT NOT NULL,
        content TEXT,
        word_count INTEGER DEFAULT 0,
        createTime INTEGER,
        lastEditTime INTEGER,
        hash TEXT,
        FOREIGN KEY (book_id) REFERENCES books (id) ON DELETE CASCADE
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        type TEXT NOT NULL,
        description TEXT,
        content TEXT,
        book_id INTEGER,
        FOREIGN KEY (book_id) REFERENCES books (id) ON DELETE CASCADE,
        UNIQUE(name, book_id)
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS recycle_bin (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_type TEXT NOT NULL,
        item_id INTEGER NOT NULL,
        item_data TEXT,
        deleted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS inspiration_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        content TEXT,
        tags TEXT,
        parent_id INTEGER,
        FOREIGN KEY (parent_id) REFERENCES inspiration_items (id) ON DELETE CASCADE
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS inspiration_fragments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT NOT NULL,
        content TEXT NOT NULL,
        source TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS preferences (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)

    # --- 2. 执行数据库迁移 ---
    cursor.execute("PRAGMA table_info(books)")
    columns = [row['name'] for row in cursor.fetchall()]
    if 'cover_path' not in columns:
        cursor.execute("ALTER TABLE books ADD COLUMN cover_path TEXT")
    if 'group' not in columns:
        cursor.execute("ALTER TABLE books ADD COLUMN 'group' TEXT")
    if 'createTime' not in columns:
        cursor.execute("ALTER TABLE books ADD COLUMN createTime INTEGER")
    if 'lastEditTime' not in columns:
        cursor.execute("ALTER TABLE books ADD COLUMN lastEditTime INTEGER")
        
    cursor.execute("PRAGMA table_info(chapters)")
    columns = [row['name'] for row in cursor.fetchall()]
    if 'createTime' not in columns:
        cursor.execute("ALTER TABLE chapters ADD COLUMN createTime INTEGER")
    if 'hash' not in columns:
        cursor.execute("ALTER TABLE chapters ADD COLUMN hash TEXT")
    if 'lastEditTime' not in columns:
        cursor.execute("ALTER TABLE chapters ADD COLUMN lastEditTime INTEGER")

    conn.commit()
    conn.close()

class DataManager:
    """数据管理类，封装所有数据库操作"""
    def __init__(self):
        self.conn = get_db_connection()

    def get_preference(self, key, default=None):
        cursor = self.conn.cursor()
        cursor.execute("SELECT value FROM preferences WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row['value'] if row else default

    def set_preference(self, key, value):
        cursor = self.conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO preferences (key, value) VALUES (?, ?)", (key, value))
        self.conn.commit()

    def get_books_and_groups(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM books ORDER BY `group`, title")
        books_by_group = {}
        for book in cursor.fetchall():
            group = book['group'] if book['group'] else "未分组"
            if group not in books_by_group:
                books_by_group[group] = []
            books_by_group[group].append(dict(book))
        return books_by_group

    def get_all_books(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM books")
        return [dict(row) for row in cursor.fetchall()]

    def get_book_details(self, book_id):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM books WHERE id = ?", (book_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def add_book(self, title, description="", cover_path="", group=""):
        current_time = int(datetime.now().timestamp() * 1000)
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO books (title, description, cover_path, "group", createTime, lastEditTime) 
            VALUES (?, ?, ?, ?, ?, ?)
            """, (title, description, cover_path, group, current_time, current_time))
        self.conn.commit()
        return cursor.lastrowid
        
    def add_book_from_backup(self, book_data):
        cursor = self.conn.cursor()
        backup_id = book_data.get('id')
        cursor.execute("""
            INSERT INTO books (id, title, description, "group", createTime, lastEditTime) 
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            backup_id,
            book_data.get('name', '无标题'), 
            book_data.get('summary', ''), 
            book_data.get('group', '未分组'), 
            book_data.get('createTime'), 
            book_data.get('lastEditTime', book_data.get('createTime'))
        ))
        self.conn.commit()
        if backup_id is None:
            return cursor.lastrowid
        return backup_id

    def update_book(self, book_id, title, description, cover_path, group):
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE books 
            SET title = ?, description = ?, cover_path = ?, `group` = ?
            WHERE id = ?
        """, (title, description, cover_path, group, book_id))
        self.conn.commit()

    def delete_book(self, book_id):
        book_data = self.get_book_details(book_id)
        if not book_data:
            return
        
        cursor = self.conn.cursor()
        cursor.execute("INSERT INTO recycle_bin (item_type, item_id, item_data) VALUES (?, ?, ?)",
                       ('book', book_id, json.dumps(dict(book_data))))
        
        cursor.execute("DELETE FROM books WHERE id = ?", (book_id,))
        self.conn.commit()

    def get_chapters_for_book(self, book_id):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM chapters WHERE book_id = ? ORDER BY volume, id", (book_id,))
        return [dict(row) for row in cursor.fetchall()]

    def get_chapter_details(self, chapter_id):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM chapters WHERE id = ?", (chapter_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
        
    def get_chapter_content(self, chapter_id):
        cursor = self.conn.cursor()
        cursor.execute("SELECT content, word_count FROM chapters WHERE id = ?", (chapter_id,))
        result = cursor.fetchone()
        return (result['content'], result['word_count']) if result else ("", 0)

    def add_chapter(self, book_id, volume, title):
        current_time = int(datetime.now().timestamp() * 1000)
        content = f"# {title}\n\n　　"
        word_count = len(content.strip())
        content_hash = hash(content)
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO chapters (book_id, volume, title, content, word_count, createTime, lastEditTime, hash) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (book_id, volume, title, content, word_count, current_time, current_time, content_hash))
        
        book_edit_time = int(datetime.now().timestamp() * 1000)
        cursor.execute("UPDATE books SET lastEditTime = ? WHERE id = ?", (book_edit_time, book_id))
        
        self.conn.commit()
        return cursor.lastrowid
        
    def add_chapter_from_backup(self, book_id, chapter_data, content_data):
        cursor = self.conn.cursor()
        last_edit_time = chapter_data.get('lastEditTime', chapter_data.get('createTime'))
        cursor.execute("""
            INSERT INTO chapters (book_id, volume, title, content, word_count, createTime, lastEditTime, hash) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            book_id, 
            chapter_data.get('volumeName', '未分卷'),
            chapter_data.get('name', '无标题'),
            content_data.get('content', ''),
            content_data.get('count', 0),
            chapter_data.get('createTime'),
            last_edit_time,
            content_data.get('hash', '')
        ))
        self.conn.commit()
        return cursor.lastrowid

    def update_chapter_content(self, chapter_id, content):
        word_count = len(content.strip())
        content_hash = hash(content)
        current_time_ms = int(datetime.now().timestamp() * 1000)
        cursor = self.conn.cursor()
        cursor.execute("UPDATE chapters SET content = ?, word_count = ?, lastEditTime = ?, hash = ? WHERE id = ?", 
                       (content, word_count, current_time_ms, content_hash, chapter_id))

        cursor.execute("SELECT book_id FROM chapters WHERE id = ?", (chapter_id,))
        book_id_result = cursor.fetchone()
        if book_id_result:
            book_id = book_id_result['book_id']
            cursor.execute("UPDATE books SET lastEditTime = ? WHERE id = ?", (current_time_ms, book_id))
        
        self.conn.commit()

    def update_chapter_title(self, chapter_id, new_title):
        cursor = self.conn.cursor()
        cursor.execute("UPDATE chapters SET title = ? WHERE id = ?", (new_title, chapter_id))
        self.conn.commit()

    def update_volume_name(self, book_id, old_volume_name, new_volume_name):
        cursor = self.conn.cursor()
        cursor.execute("UPDATE chapters SET volume = ? WHERE book_id = ? AND volume = ?",
                       (new_volume_name, book_id, old_volume_name))
        self.conn.commit()

    def get_all_settings_names(self, book_id=None):
        cursor = self.conn.cursor()
        if book_id:
            cursor.execute("SELECT name FROM settings WHERE book_id IS NULL OR book_id = ?", (book_id,))
        else:
            cursor.execute("SELECT name FROM settings WHERE book_id IS NULL")
        return [row['name'] for row in cursor.fetchall()]

    def get_settings(self, book_id=None):
        cursor = self.conn.cursor()
        if book_id:
             cursor.execute("SELECT * FROM settings WHERE book_id IS NULL OR book_id = ?", (book_id,))
        else:
             cursor.execute("SELECT * FROM settings WHERE book_id IS NULL")
        return [dict(row) for row in cursor.fetchall()]
        
    def get_all_settings(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM settings")
        return [dict(row) for row in cursor.fetchall()]

    def get_setting_details(self, setting_id):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM settings WHERE id = ?", (setting_id,))
        row = cursor.fetchone()
        if not row:
            return None
        
        setting_data = dict(row)
        if setting_data['content']:
            try:
                setting_data['content'] = json.loads(setting_data['content'])
            except (json.JSONDecodeError, TypeError):
                setting_data['content'] = {'value': setting_data['content']} # 兼容旧纯文本数据
        else:
            setting_data['content'] = {}
            
        return setting_data

    def add_setting(self, name, type, description, book_id=None, content=None):
        try:
            content_json = json.dumps(content if content is not None else {})
            cursor = self.conn.cursor()
            cursor.execute("INSERT INTO settings (name, type, description, book_id, content) VALUES (?, ?, ?, ?, ?)",
                           (name, type, description, book_id, content_json))
            self.conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None
            
    def add_setting_from_backup(self, setting_data):
        cursor = self.conn.cursor()
        cursor.execute("INSERT INTO settings (id, name, type, description, content, book_id) VALUES (?, ?, ?, ?, ?, ?)",
                       (setting_data['id'], setting_data['name'], setting_data['type'], 
                        setting_data['description'], setting_data['content'], setting_data['book_id']))
        self.conn.commit()


    def update_setting(self, setting_id, name, type, description, content=None):
        try:
            content_json = json.dumps(content if content is not None else {})
            cursor = self.conn.cursor()
            cursor.execute("""
                UPDATE settings SET name = ?, type = ?, description = ?, content = ?
                WHERE id = ?
            """, (name, type, description, content_json, setting_id))
            self.conn.commit()
            return True
        except Exception as e:
            # 保持这个print用于调试关键错误
            print(f"数据库更新设定失败: {e}")
            return False

    def delete_setting(self, setting_id):
        try:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM settings WHERE id = ?", (setting_id,))
            self.conn.commit()
            return True
        except Exception as e:
            # 保持这个print用于调试关键错误
            print(f"删除设定失败: {e}")
            return False

    def get_all_groups(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT DISTINCT `group` FROM books WHERE `group` IS NOT NULL AND `group` != '' ORDER BY `group`")
        return [row['group'] for row in cursor.fetchall()]

    def rename_group(self, old_name, new_name):
        cursor = self.conn.cursor()
        cursor.execute("UPDATE books SET `group` = ? WHERE `group` = ?", (new_name, old_name))
        self.conn.commit()
        return cursor.rowcount > 0

    def delete_group(self, group_name):
        cursor = self.conn.cursor()
        cursor.execute("UPDATE books SET `group` = '未分组' WHERE `group` = ?", (group_name,))
        self.conn.commit()
        return cursor.rowcount > 0

    def get_inspiration_fragments(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM inspiration_fragments ORDER BY created_at DESC")
        return [dict(row) for row in cursor.fetchall()]
        
    def get_all_inspiration_fragments(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM inspiration_fragments")
        return [dict(row) for row in cursor.fetchall()]
        
    def add_inspiration_fragment(self, type, content, source=""):
        cursor = self.conn.cursor()
        cursor.execute("INSERT INTO inspiration_fragments (type, content, source) VALUES (?, ?, ?)",
                       (type, content, source))
        self.conn.commit()
        return cursor.lastrowid
        
    def add_inspiration_fragment_from_backup(self, fragment_data):
        cursor = self.conn.cursor()
        cursor.execute("INSERT INTO inspiration_fragments (id, type, content, source, created_at) VALUES (?, ?, ?, ?, ?)",
                       (fragment_data['id'], fragment_data['type'], fragment_data['content'], 
                        fragment_data['source'], fragment_data['created_at']))
        self.conn.commit()

    def get_inspiration_items(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM inspiration_items ORDER BY parent_id, title")
        return [dict(row) for row in cursor.fetchall()]
        
    def get_all_inspiration_items(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM inspiration_items")
        return [dict(row) for row in cursor.fetchall()]

    def add_inspiration_item(self, title, content="", tags="", parent_id=None):
        cursor = self.conn.cursor()
        cursor.execute("INSERT INTO inspiration_items (title, content, tags, parent_id) VALUES (?, ?, ?, ?)",
                       (title, content, tags, parent_id))
        self.conn.commit()
        return cursor.lastrowid
        
    def add_inspiration_item_from_backup(self, item_data):
        cursor = self.conn.cursor()
        cursor.execute("INSERT INTO inspiration_items (id, title, content, tags, parent_id) VALUES (?, ?, ?, ?, ?)",
                       (item_data['id'], item_data['title'], item_data['content'], 
                        item_data['tags'], item_data['parent_id']))
        self.conn.commit()

        
    def clear_all_writing_data(self):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM chapters")
        cursor.execute("DELETE FROM settings")
        cursor.execute("DELETE FROM books")
        cursor.execute("DELETE FROM inspiration_items")
        cursor.execute("DELETE FROM inspiration_fragments")
        self.conn.commit()

    def get_chapters_modified_since(self, check_time):
        check_timestamp_ms = int(check_time.timestamp() * 1000)
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT c.id, c.book_id, c.title, c.content, c.lastEditTime, b.title as book_title
            FROM chapters c
            JOIN books b ON c.book_id = b.id
            WHERE c.lastEditTime > ?
        """, (check_timestamp_ms,))
        return [dict(row) for row in cursor.fetchall()]

    def close(self):
        if self.conn:
            self.conn.close()