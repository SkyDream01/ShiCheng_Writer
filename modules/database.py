# ShiCheng_Writer/modules/database.py
import sqlite3
import os
import json
from datetime import datetime
import threading
import hashlib
import logging
from .utils import get_app_root

DB_FILE = os.path.join(get_app_root(), "ShiCheng_Writer.db")
logger = logging.getLogger(__name__)

def calculate_hash(content):
    return hashlib.md5(content.encode('utf-8')).hexdigest()

def get_db_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def initialize_database():
    """初始化数据库"""
    conn = get_db_connection()
    cursor = conn.cursor()

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
    CREATE TABLE IF NOT EXISTS materials (
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
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS timelines (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        book_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        description TEXT,
        FOREIGN KEY (book_id) REFERENCES books (id) ON DELETE CASCADE
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS timeline_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timeline_id INTEGER NOT NULL,
        parent_id INTEGER,
        title TEXT NOT NULL,
        content TEXT,
        event_time TEXT,
        order_index INTEGER DEFAULT 0,
        status TEXT,
        referenced_materials TEXT,
        FOREIGN KEY (timeline_id) REFERENCES timelines (id) ON DELETE CASCADE,
        FOREIGN KEY (parent_id) REFERENCES timeline_events (id) ON DELETE CASCADE
    )
    """)

    # 创建性能索引
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chapters_book_id ON chapters(book_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chapters_last_edit ON chapters(lastEditTime DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chapters_volume ON chapters(volume)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_books_group ON books(\"group\")")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_materials_book_id ON materials(book_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_timelines_book_id ON timelines(book_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_timeline_events_timeline_id ON timeline_events(timeline_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_recycle_bin_deleted_at ON recycle_bin(deleted_at DESC)")

    # 迁移逻辑
    try:
        cursor.execute("PRAGMA table_info(settings)")
        if cursor.fetchone():
            cursor.execute("ALTER TABLE settings RENAME TO materials")
    except sqlite3.OperationalError:
        pass 
        
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
        self._local = threading.local()
        self.lock = threading.Lock()

    @property
    def conn(self):
        if not hasattr(self._local, 'connection'):
            self._local.connection = get_db_connection()
        return self._local.connection

    def get_preference(self, key, default=None):
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT value FROM preferences WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row['value'] if row else default

    def set_preference(self, key, value):
        with self.lock:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("INSERT OR REPLACE INTO preferences (key, value) VALUES (?, ?)", (key, value))


    def get_books_and_groups(self):
        with self.lock:
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
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM books")
            return [dict(row) for row in cursor.fetchall()]

    def get_book_details(self, book_id):
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM books WHERE id = ?", (book_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_book_word_count(self, book_id):
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT SUM(word_count) as total FROM chapters WHERE book_id = ?", (book_id,))
            result = cursor.fetchone()
            return result['total'] if result and result['total'] is not None else 0

    def add_book(self, title, description="", cover_path="", group=""):
        with self.lock:
            with self.conn:
                current_time = int(datetime.now().timestamp() * 1000)
                cursor = self.conn.cursor()
                cursor.execute("""
                    INSERT INTO books (title, description, cover_path, "group", createTime, lastEditTime)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """, (title, description, cover_path, group, current_time, current_time))
                return cursor.lastrowid

    def add_book_from_backup(self, book_data):
        with self.lock:
            with self.conn:
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
                if backup_id is None:
                    return cursor.lastrowid
                return backup_id

    def update_book(self, book_id, title, description, cover_path, group):
        with self.lock:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("""
                    UPDATE books
                    SET title = ?, description = ?, cover_path = ?, `group` = ?
                    WHERE id = ?
                """, (title, description, cover_path, group, book_id))

    def delete_book(self, book_id):
        with self.lock:
            with self.conn:
                # 获取书籍数据
                cursor = self.conn.cursor()
                cursor.execute("SELECT * FROM books WHERE id = ?", (book_id,))
                row = cursor.fetchone()
                if not row:
                    return
                book_data = dict(row)
                
                # 插入回收站
                cursor.execute("INSERT INTO recycle_bin (item_type, item_id, item_data) VALUES (?, ?, ?)",
                            ('book', book_id, json.dumps(book_data)))
                cursor.execute("DELETE FROM books WHERE id = ?", (book_id,))

    def get_chapters_for_book(self, book_id):
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT id, book_id, volume, title, word_count, createTime, lastEditTime, hash 
                FROM chapters WHERE book_id = ? ORDER BY volume, id
            """, (book_id,))
            return [dict(row) for row in cursor.fetchall()]

    def get_chapter_details(self, chapter_id):
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM chapters WHERE id = ?", (chapter_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_chapter_content(self, chapter_id):
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT content, word_count FROM chapters WHERE id = ?", (chapter_id,))
            result = cursor.fetchone()
            return (result['content'], result['word_count']) if result else ("", 0)

    def get_chapter_info(self, chapter_id):
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT id, book_id, volume, title, content, word_count, createTime, lastEditTime, hash FROM chapters WHERE id = ?", (chapter_id,))
            result = cursor.fetchone()
            return dict(result) if result else None

    def add_chapter(self, book_id, volume, title):
        with self.lock:
            with self.conn:
                current_time = int(datetime.now().timestamp() * 1000)
                content = f"# {title}\n\n　　"
                word_count = len(content.strip())
                content_hash = calculate_hash(content)
                
                cursor = self.conn.cursor()
                cursor.execute("""
                    INSERT INTO chapters (book_id, volume, title, content, word_count, createTime, lastEditTime, hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (book_id, volume, title, content, word_count, current_time, current_time, content_hash))
                
                last_row_id = cursor.lastrowid
                book_edit_time = int(datetime.now().timestamp() * 1000)
                cursor.execute("UPDATE books SET lastEditTime = ? WHERE id = ?", (book_edit_time, book_id))
                return last_row_id

    def add_chapter_from_backup(self, book_id, chapter_data, content_data):
        with self.lock:
            with self.conn:
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
                return cursor.lastrowid

    def update_chapter_content(self, chapter_id, content):
        with self.lock:
            with self.conn:
                word_count = len(content.strip())
                content_hash = calculate_hash(content)
                current_time_ms = int(datetime.now().timestamp() * 1000)
                
                cursor = self.conn.cursor()
                cursor.execute("UPDATE chapters SET content = ?, word_count = ?, lastEditTime = ?, hash = ? WHERE id = ?",
                            (content, word_count, current_time_ms, content_hash, chapter_id))
                if cursor.rowcount == 0:
                    return  # 章节不存在，无需更新书籍时间戳

                cursor.execute("SELECT book_id FROM chapters WHERE id = ?", (chapter_id,))
                book_id_result = cursor.fetchone()
                if book_id_result:
                    book_id = book_id_result['book_id']
                    cursor.execute("UPDATE books SET lastEditTime = ? WHERE id = ?", (current_time_ms, book_id))

    def update_chapter_title(self, chapter_id, new_title):
        with self.lock:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("UPDATE chapters SET title = ? WHERE id = ?", (new_title, chapter_id))

    def delete_chapter(self, chapter_id):
        with self.lock:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("SELECT * FROM chapters WHERE id = ?", (chapter_id,))
                row = cursor.fetchone()
                if not row:
                    return
                chapter_data = dict(row)
                
                cursor.execute("INSERT INTO recycle_bin (item_type, item_id, item_data) VALUES (?, ?, ?)",
                            ('chapter', chapter_id, json.dumps(chapter_data)))
                cursor.execute("DELETE FROM chapters WHERE id = ?", (chapter_id,))

    def update_volume_name(self, book_id, old_volume_name, new_volume_name):
        with self.lock:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("UPDATE chapters SET volume = ? WHERE book_id = ? AND volume = ?",
                            (new_volume_name, book_id, old_volume_name))

    def get_recycle_bin_items(self):
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM recycle_bin ORDER BY deleted_at DESC")
            return [dict(row) for row in cursor.fetchall()]

    def restore_recycle_item(self, recycle_id):
        with self.lock:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("SELECT * FROM recycle_bin WHERE id = ?", (recycle_id,))
                row = cursor.fetchone()
                if not row: return False
                
                item_type = row['item_type']
                item_data = json.loads(row['item_data'])
                
                if item_type == 'book':
                    try:
                        cursor.execute("""
                            INSERT INTO books (id, title, description, cover_path, "group", createTime, lastEditTime)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (item_data['id'], item_data['title'], item_data.get('description'), 
                              item_data.get('cover_path'), item_data.get('group'), 
                              item_data.get('createTime'), item_data.get('lastEditTime')))
                    except sqlite3.IntegrityError:
                        cursor.execute("""
                            INSERT INTO books (title, description, cover_path, "group", createTime, lastEditTime)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (item_data['title'], item_data.get('description'), 
                              item_data.get('cover_path'), item_data.get('group'), 
                              item_data.get('createTime'), item_data.get('lastEditTime')))
                    
                elif item_type == 'chapter':
                    book_id = item_data['book_id']
                    cursor.execute("SELECT id FROM books WHERE id = ?", (book_id,))
                    if not cursor.fetchone():
                        return "parent_missing"

                    try:
                         cursor.execute("""
                            INSERT INTO chapters (id, book_id, volume, title, content, word_count, createTime, lastEditTime, hash)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (item_data['id'], item_data['book_id'], item_data['volume'], 
                              item_data['title'], item_data['content'], item_data['word_count'],
                              item_data['createTime'], item_data['lastEditTime'], item_data.get('hash')))
                    except sqlite3.IntegrityError:
                         cursor.execute("""
                            INSERT INTO chapters (book_id, volume, title, content, word_count, createTime, lastEditTime, hash)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """, (item_data['book_id'], item_data['volume'], 
                              item_data['title'], item_data['content'], item_data['word_count'],
                              item_data['createTime'], item_data['lastEditTime'], item_data.get('hash')))

                cursor.execute("DELETE FROM recycle_bin WHERE id = ?", (recycle_id,))
                return True

    def delete_recycle_item(self, recycle_id):
        with self.lock:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("DELETE FROM recycle_bin WHERE id = ?", (recycle_id,))
                return True
            
    def empty_recycle_bin(self):
        with self.lock:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("DELETE FROM recycle_bin")

    def get_all_materials_names(self, book_id=None):
        with self.lock:
            cursor = self.conn.cursor()
            if book_id:
                cursor.execute("SELECT name FROM materials WHERE book_id IS NULL OR book_id = ?", (book_id,))
            else:
                cursor.execute("SELECT name FROM materials WHERE book_id IS NULL")
            return [row['name'] for row in cursor.fetchall()]

    def get_materials(self, book_id=None):
        with self.lock:
            cursor = self.conn.cursor()
            if book_id:
                cursor.execute("SELECT * FROM materials WHERE book_id IS NULL OR book_id = ?", (book_id,))
            else:
                cursor.execute("SELECT * FROM materials WHERE book_id IS NULL")
            return [dict(row) for row in cursor.fetchall()]

    def get_all_materials(self):
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM materials")
            return [dict(row) for row in cursor.fetchall()]

    def get_material_details(self, material_id):
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM materials WHERE id = ?", (material_id,))
            row = cursor.fetchone()
            if not row:
                return None
            
            material_data = dict(row)
            if material_data['content']:
                try:
                    material_data['content'] = json.loads(material_data['content'])
                except (json.JSONDecodeError, TypeError):
                    material_data['content'] = {'value': material_data['content']}
            else:
                material_data['content'] = {}
                
            return material_data

    def add_material(self, name, type, description, book_id=None, content=None):
        try:
            with self.lock:
                with self.conn:
                    content_json = json.dumps(content if content is not None else {})
                    cursor = self.conn.cursor()
                    cursor.execute("INSERT INTO materials (name, type, description, book_id, content) VALUES (?, ?, ?, ?, ?)",
                                (name, type, description, book_id, content_json))
                    return cursor.lastrowid
        except sqlite3.IntegrityError:
            logger.warning(f"添加素材 '{name}' 失败：名称已存在。")
            return None

    def add_material_from_backup(self, material_data):
        with self.lock:
            with self.conn:
                cursor = self.conn.cursor()
                content = material_data.get('content') or material_data.get('settings')
                cursor.execute("INSERT OR REPLACE INTO materials (id, name, type, description, content, book_id) VALUES (?, ?, ?, ?, ?, ?)",
                            (material_data['id'], material_data['name'], material_data['type'],
                                material_data.get('description', ''), content, material_data.get('book_id')))

    def update_material(self, material_id, name, type, description, content=None):
        try:
            with self.lock:
                with self.conn:
                    content_json = json.dumps(content if content is not None else {})
                    cursor = self.conn.cursor()
                    cursor.execute("""
                        UPDATE materials SET name = ?, type = ?, description = ?, content = ?
                        WHERE id = ?
                    """, (name, type, description, content_json, material_id))
                    return True
        except sqlite3.IntegrityError:
            logger.warning(f"更新素材 '{name}' 失败：名称已存在。")
            return False
        except sqlite3.Error as e:
            logger.error(f"数据库更新素材失败: {e}", exc_info=True)
            return False

    def delete_material(self, material_id):
        try:
            with self.lock:
                with self.conn:
                    cursor = self.conn.cursor()
                    cursor.execute("DELETE FROM materials WHERE id = ?", (material_id,))
                    return True
        except sqlite3.Error as e:
            logger.error(f"删除素材失败: {e}", exc_info=True)
            return False

    def get_all_groups(self):
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT DISTINCT `group` FROM books WHERE `group` IS NOT NULL AND `group` != '' ORDER BY `group`")
            return [row['group'] for row in cursor.fetchall()]

    def get_books_by_group(self, group_name):
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM books WHERE `group` = ? ORDER BY title", (group_name,))
            return [dict(row) for row in cursor.fetchall()]

    def rename_group(self, old_name, new_name):
        with self.lock:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("UPDATE books SET `group` = ? WHERE `group` = ?", (new_name, old_name))
                return cursor.rowcount > 0

    def delete_group(self, group_name):
        with self.lock:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("UPDATE books SET `group` = '未分组' WHERE `group` = ?", (group_name,))
                return cursor.rowcount > 0

    def get_inspiration_fragments(self):
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM inspiration_fragments ORDER BY created_at DESC")
            return [dict(row) for row in cursor.fetchall()]

    def get_all_inspiration_fragments(self):
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM inspiration_fragments")
            return [dict(row) for row in cursor.fetchall()]

    def add_inspiration_fragment(self, type, content, source=""):
        with self.lock:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("INSERT INTO inspiration_fragments (type, content, source) VALUES (?, ?, ?)",
                            (type, content, source))
                return cursor.lastrowid

    def add_inspiration_fragment_from_backup(self, fragment_data):
        with self.lock:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("INSERT OR REPLACE INTO inspiration_fragments (id, type, content, source, created_at) VALUES (?, ?, ?, ?, ?)",
                            (fragment_data['id'], fragment_data['type'], fragment_data['content'],
                                fragment_data.get('source', ''), fragment_data.get('created_at')))

    def update_inspiration_fragment(self, fragment_id, type=None, content=None, source=None):
        with self.lock:
            with self.conn:
                cursor = self.conn.cursor()
                updates = []
                params = []
                if type is not None:
                    updates.append("type = ?")
                    params.append(type)
                if content is not None:
                    updates.append("content = ?")
                    params.append(content)
                if source is not None:
                    updates.append("source = ?")
                    params.append(source)
                if not updates:
                    return False
                params.append(fragment_id)
                query = f"UPDATE inspiration_fragments SET {', '.join(updates)} WHERE id = ?"
                cursor.execute(query, params)
                return cursor.rowcount > 0

    def delete_inspiration_fragment(self, fragment_id):
        with self.lock:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("DELETE FROM inspiration_fragments WHERE id = ?", (fragment_id,))
                return cursor.rowcount > 0

    def get_inspiration_items(self):
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM inspiration_items ORDER BY parent_id, title")
            return [dict(row) for row in cursor.fetchall()]

    def get_all_inspiration_items(self):
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM inspiration_items")
            return [dict(row) for row in cursor.fetchall()]

    def add_inspiration_item(self, title, content="", tags="", parent_id=None):
        with self.lock:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("INSERT INTO inspiration_items (title, content, tags, parent_id) VALUES (?, ?, ?, ?)",
                            (title, content, tags, parent_id))
                return cursor.lastrowid

    def add_inspiration_item_from_backup(self, item_data):
        with self.lock:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("INSERT OR REPLACE INTO inspiration_items (id, title, content, tags, parent_id) VALUES (?, ?, ?, ?, ?)",
                            (item_data['id'], item_data['title'], item_data.get('content', ''),
                                item_data.get('tags', ''), item_data.get('parent_id')))

    def update_inspiration_item(self, item_id, title=None, content=None, tags=None, parent_id=None):
        with self.lock:
            with self.conn:
                cursor = self.conn.cursor()
                updates = []
                params = []
                if title is not None:
                    updates.append("title = ?")
                    params.append(title)
                if content is not None:
                    updates.append("content = ?")
                    params.append(content)
                if tags is not None:
                    updates.append("tags = ?")
                    params.append(tags)
                if parent_id is not None:
                    updates.append("parent_id = ?")
                    params.append(parent_id)
                if not updates:
                    return False
                params.append(item_id)
                query = f"UPDATE inspiration_items SET {', '.join(updates)} WHERE id = ?"
                cursor.execute(query, params)
                return cursor.rowcount > 0

    def delete_inspiration_item(self, item_id):
        with self.lock:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("DELETE FROM inspiration_items WHERE id = ?", (item_id,))
                return cursor.rowcount > 0

    def get_timelines_for_book(self, book_id):
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM timelines WHERE book_id = ? ORDER BY name", (book_id,))
            return [dict(row) for row in cursor.fetchall()]

    def get_all_timelines(self):
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM timelines")
            return [dict(row) for row in cursor.fetchall()]

    def add_timeline(self, book_id, name, description=""):
        with self.lock:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("INSERT INTO timelines (book_id, name, description) VALUES (?, ?, ?)",
                            (book_id, name, description))
                return cursor.lastrowid

    def add_timeline_from_backup(self, timeline_data):
        with self.lock:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("INSERT OR REPLACE INTO timelines (id, book_id, name, description) VALUES (?, ?, ?, ?)",
                            (timeline_data['id'], timeline_data['book_id'], timeline_data['name'],
                                timeline_data.get('description', '')))

    def get_timeline_events(self, timeline_id):
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM timeline_events WHERE timeline_id = ? ORDER BY order_index", (timeline_id,))
            return [dict(row) for row in cursor.fetchall()]

    def get_all_timeline_events(self):
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM timeline_events")
            return [dict(row) for row in cursor.fetchall()]

    def add_timeline_event_from_backup(self, event_data):
        with self.lock:
            with self.conn:
                cursor = self.conn.cursor()
                referenced_materials = event_data.get('referenced_materials')
                if isinstance(referenced_materials, str):
                    try: 
                        json.loads(referenced_materials)
                    except json.JSONDecodeError: 
                        referenced_materials = json.dumps([])
                else:
                    referenced_materials = json.dumps(referenced_materials or [])

                cursor.execute("""
                    INSERT OR REPLACE INTO timeline_events
                    (id, timeline_id, parent_id, title, content, event_time, order_index, status, referenced_materials)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    event_data['id'], event_data['timeline_id'], event_data.get('parent_id'),
                    event_data['title'], event_data.get('content'), event_data.get('event_time'),
                    event_data.get('order_index', 0), event_data.get('status'),
                    referenced_materials
                ))

    def update_timeline_events(self, timeline_id, events_data):
        with self.lock:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("DELETE FROM timeline_events WHERE timeline_id = ?", (timeline_id,))
                for event in events_data:
                    referenced_materials_json = json.dumps(event.get('referenced_materials', []))

                    cursor.execute("""
                    INSERT INTO timeline_events
                    (id, timeline_id, parent_id, title, content, event_time, order_index, status, referenced_materials)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        event.get('id'), timeline_id, event.get('parent_id'), event.get('title'),
                        event.get('content'), event.get('event_time'), event.get('order_index'),
                        event.get('status'), referenced_materials_json
                    ))

    def clear_all_writing_data(self):
        with self.lock:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("DELETE FROM timeline_events")
                cursor.execute("DELETE FROM timelines")
                cursor.execute("DELETE FROM chapters")
                cursor.execute("DELETE FROM materials")
                cursor.execute("DELETE FROM books")
                cursor.execute("DELETE FROM inspiration_items")
                cursor.execute("DELETE FROM inspiration_fragments")

    def get_recent_chapters(self, limit=10):
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT c.id, c.book_id, c.title, c.content, c.lastEditTime, b.title as book_title
                FROM chapters c
                JOIN books b ON c.book_id = b.id
                WHERE c.lastEditTime IS NOT NULL
                ORDER BY c.lastEditTime DESC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def get_chapters_modified_since(self, check_time):
        with self.lock:
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
        if hasattr(self._local, 'connection'):
            self._local.connection.close()
            del self._local.connection

    def close_local_connection(self):
        """关闭当前线程的数据库连接"""
        if hasattr(self._local, 'connection'):
            try:
                self._local.connection.close()
            except Exception as e:
                logger.error(f"Error closing database connection: {e}")
            finally:
                del self._local.connection