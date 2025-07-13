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
    # 使用 "CREATE TABLE IF NOT EXISTS" 确保所有表都存在

    # 书籍表
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

    # 章节表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chapters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        book_id INTEGER NOT NULL,
        volume TEXT,
        title TEXT NOT NULL,
        content TEXT,
        word_count INTEGER DEFAULT 0,
        createTime INTEGER,
        hash TEXT,
        FOREIGN KEY (book_id) REFERENCES books (id) ON DELETE CASCADE
    )
    """)

    # 设定表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        type TEXT NOT NULL, -- 'text', 'object', 'template', 'list', 'timeline'
        description TEXT,
        content TEXT, -- for list items, object properties etc. (JSON)
        book_id INTEGER, -- NULL for global settings
        FOREIGN KEY (book_id) REFERENCES books (id) ON DELETE CASCADE,
        UNIQUE(name, book_id)
    )
    """)
    
    # 回收站表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS recycle_bin (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_type TEXT NOT NULL, -- 'book', 'chapter', 'setting'
        item_id INTEGER NOT NULL,
        item_data TEXT, -- JSON format of the deleted item
        deleted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 灵感仓库 (已整理)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS inspiration_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        content TEXT,
        tags TEXT, -- Comma-separated
        parent_id INTEGER, -- For folder structure
        FOREIGN KEY (parent_id) REFERENCES inspiration_items (id) ON DELETE CASCADE
    )
    """)

    # 灵感锦囊 (未整理)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS inspiration_fragments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT NOT NULL, -- 'text', 'image', 'audio'
        content TEXT NOT NULL, -- For text, it's the path
        source TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # 新增：偏好设置表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS preferences (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)

    # --- 2. 执行数据库迁移 (在表存在后) ---
    # 现在表肯定存在了，可以安全地检查和添加列

    # 检查 books 表
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
        
    # 检查 chapters 表
    cursor.execute("PRAGMA table_info(chapters)")
    columns = [row['name'] for row in cursor.fetchall()]
    if 'createTime' not in columns:
        cursor.execute("ALTER TABLE chapters ADD COLUMN createTime INTEGER")
    if 'hash' not in columns:
        cursor.execute("ALTER TABLE chapters ADD COLUMN hash TEXT")


    print("数据库初始化成功！")
    conn.commit()
    conn.close()

class DataManager:
    """数据管理类，封装所有数据库操作"""
    def __init__(self):
        self.conn = get_db_connection()

    # --- 新增：偏好设置方法 ---
    def get_preference(self, key, default=None):
        """获取一个偏好设置项"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT value FROM preferences WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row['value'] if row else default

    def set_preference(self, key, value):
        """设置一个偏好设置项"""
        cursor = self.conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO preferences (key, value) VALUES (?, ?)", (key, value))
        self.conn.commit()

    def get_books_and_groups(self):
        """获取所有书籍，按分组归类"""
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
        """获取所有书籍的列表"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM books")
        return [dict(row) for row in cursor.fetchall()]

    def get_book_details(self, book_id):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM books WHERE id = ?", (book_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def add_book(self, title, description="", cover_path="", group=""):
        """添加新书"""
        # 使用毫秒级时间戳
        current_time = int(datetime.now().timestamp() * 1000)
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO books (title, description, cover_path, "group", createTime, lastEditTime) 
            VALUES (?, ?, ?, ?, ?, ?)
            """, (title, description, cover_path, group, current_time, current_time))
        self.conn.commit()
        return cursor.lastrowid
        
    def add_book_from_backup(self, book_data):
        """从备份数据添加书籍"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO books (title, description, "group", createTime, lastEditTime) 
            VALUES (?, ?, ?, ?, ?)
        """, (
            book_data.get('name', '无标题'), 
            book_data.get('summary', ''), 
            book_data.get('group', '未分组'), 
            book_data.get('createTime'), 
            book_data.get('lastEditTime', book_data.get('createTime'))
        ))
        self.conn.commit()
        return cursor.lastrowid

    def update_book(self, book_id, title, description, cover_path, group):
        """更新书籍信息"""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE books 
            SET title = ?, description = ?, cover_path = ?, `group` = ?
            WHERE id = ?
        """, (title, description, cover_path, group, book_id))
        self.conn.commit()

    def delete_book(self, book_id):
        """删除书籍 (移入回收站)"""
        book_data = self.get_book_details(book_id)
        if not book_data:
            return
        
        # 1. 将数据备份到回收站
        cursor = self.conn.cursor()
        cursor.execute("INSERT INTO recycle_bin (item_type, item_id, item_data) VALUES (?, ?, ?)",
                       ('book', book_id, json.dumps(dict(book_data))))
        
        # 2. 从原表中删除
        cursor.execute("DELETE FROM books WHERE id = ?", (book_id,))
        # 关联的章节和设定会自动被`ON DELETE CASCADE`删除
        self.conn.commit()

    def get_chapters_for_book(self, book_id):
        """获取指定书籍的所有章节"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM chapters WHERE book_id = ? ORDER BY volume, id", (book_id,))
        return [dict(row) for row in cursor.fetchall()]

    def get_chapter_details(self, chapter_id):
        """获取单个章节的详细信息"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM chapters WHERE id = ?", (chapter_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
        
    def get_chapter_content(self, chapter_id):
        """获取章节内容"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT content, word_count FROM chapters WHERE id = ?", (chapter_id,))
        result = cursor.fetchone()
        return (result['content'], result['word_count']) if result else ("", 0)

    def add_chapter(self, book_id, volume, title):
        """添加新章节"""
        current_time = int(datetime.now().timestamp() * 1000)
        content = f"# {title}\n\n"
        word_count = len(content.strip())
        content_hash = hash(content)
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO chapters (book_id, volume, title, content, word_count, createTime, hash) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (book_id, volume, title, content, word_count, current_time, content_hash))
        
        # 更新书籍的最后编辑时间
        book_edit_time = int(datetime.now().timestamp() * 1000)
        cursor.execute("UPDATE books SET lastEditTime = ? WHERE id = ?", (book_edit_time, book_id))
        
        self.conn.commit()
        return cursor.lastrowid
        
    def add_chapter_from_backup(self, book_id, chapter_data, content_data):
        """从备份数据添加章节"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO chapters (book_id, volume, title, content, word_count, createTime, hash) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            book_id, 
            chapter_data.get('volumeName', '未分卷'),
            chapter_data.get('name', '无标题'),
            content_data.get('content', ''),
            content_data.get('count', 0),
            chapter_data.get('createTime'),
            content_data.get('hash', '')
        ))
        self.conn.commit()
        return cursor.lastrowid

    def update_chapter_content(self, chapter_id, content):
        """更新章节内容和字数"""
        word_count = len(content.strip())
        content_hash = hash(content)
        cursor = self.conn.cursor()
        cursor.execute("UPDATE chapters SET content = ?, word_count = ?, hash = ? WHERE id = ?", (content, word_count, content_hash, chapter_id))

        # 更新书籍的最后编辑时间
        cursor.execute("SELECT book_id FROM chapters WHERE id = ?", (chapter_id,))
        book_id_result = cursor.fetchone()
        if book_id_result:
            book_id = book_id_result['book_id']
            book_edit_time = int(datetime.now().timestamp() * 1000)
            cursor.execute("UPDATE books SET lastEditTime = ? WHERE id = ?", (book_edit_time, book_id))
        
        self.conn.commit()

    def update_chapter_title(self, chapter_id, new_title):
        """更新章节标题"""
        cursor = self.conn.cursor()
        cursor.execute("UPDATE chapters SET title = ? WHERE id = ?", (new_title, chapter_id))
        self.conn.commit()

    def update_volume_name(self, book_id, old_volume_name, new_volume_name):
        """更新卷名"""
        cursor = self.conn.cursor()
        cursor.execute("UPDATE chapters SET volume = ? WHERE book_id = ? AND volume = ?",
                       (new_volume_name, book_id, old_volume_name))
        self.conn.commit()

    def get_all_settings_names(self, book_id=None):
        """获取所有设定名称用于高亮"""
        cursor = self.conn.cursor()
        if book_id:
            cursor.execute("SELECT name FROM settings WHERE book_id IS NULL OR book_id = ?", (book_id,))
        else:
            cursor.execute("SELECT name FROM settings WHERE book_id IS NULL")
        return [row['name'] for row in cursor.fetchall()]

    def get_settings(self, book_id=None):
        """获取设定"""
        cursor = self.conn.cursor()
        if book_id:
             cursor.execute("SELECT * FROM settings WHERE book_id IS NULL OR book_id = ?", (book_id,))
        else:
             cursor.execute("SELECT * FROM settings WHERE book_id IS NULL")
        return cursor.fetchall()
    
    def add_setting(self, name, type, description, book_id=None, content=""):
        """添加设定"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("INSERT INTO settings (name, type, description, book_id, content) VALUES (?, ?, ?, ?, ?)",
                           (name, type, description, book_id, content))
            self.conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None # 名称已存在

    def get_all_groups(self):
        """获取所有唯一的分组名称"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT DISTINCT `group` FROM books WHERE `group` IS NOT NULL AND `group` != '' ORDER BY `group`")
        return [row['group'] for row in cursor.fetchall()]

    def rename_group(self, old_name, new_name):
        """重命名一个分组"""
        cursor = self.conn.cursor()
        cursor.execute("UPDATE books SET `group` = ? WHERE `group` = ?", (new_name, old_name))
        self.conn.commit()
        return cursor.rowcount > 0

    def delete_group(self, group_name):
        """删除一个分组（将其中的书籍移动到'未分组'）"""
        cursor = self.conn.cursor()
        cursor.execute("UPDATE books SET `group` = '未分组' WHERE `group` = ?", (group_name,))
        self.conn.commit()
        return cursor.rowcount > 0

    # --- 灵感系统方法 ---
    def get_inspiration_fragments(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM inspiration_fragments ORDER BY created_at DESC")
        return cursor.fetchall()
        
    def add_inspiration_fragment(self, type, content, source=""):
        cursor = self.conn.cursor()
        cursor.execute("INSERT INTO inspiration_fragments (type, content, source) VALUES (?, ?, ?)",
                       (type, content, source))
        self.conn.commit()
        return cursor.lastrowid

    def get_inspiration_items(self):
        """获取所有已整理的灵感，并构建成树"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM inspiration_items ORDER BY parent_id, title")
        # 在应用层面构建树状结构会更灵活
        return cursor.fetchall()

    def add_inspiration_item(self, title, content="", tags="", parent_id=None):
        cursor = self.conn.cursor()
        cursor.execute("INSERT INTO inspiration_items (title, content, tags, parent_id) VALUES (?, ?, ?, ?)",
                       (title, content, tags, parent_id))
        self.conn.commit()
        return cursor.lastrowid
        
    def clear_all_writing_data(self):
        """清空所有写作相关的数据表，用于恢复"""
        cursor = self.conn.cursor()
        print("正在清空 books, chapters, settings 表...")
        cursor.execute("DELETE FROM chapters")
        cursor.execute("DELETE FROM books")
        cursor.execute("DELETE FROM settings")
        self.conn.commit()
        print("数据表已清空。")

    def close(self):
        if self.conn:
            self.conn.close()