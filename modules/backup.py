# shicheng_writer/modules/backup.py
import os
import shutil
import json
import zipfile
import tempfile
from datetime import datetime

class BackupManager:
    """备份管理器，使用zip和json格式进行备份"""
    def __init__(self, data_manager, backup_dir="backups"):
        self.data_manager = data_manager
        self.backup_dir = backup_dir
        if not os.path.exists(self.backup_dir):
            os.makedirs(self.backup_dir)

    def create_backup(self, force=False):
        """
        创建一个新的JSON结构化备份，并压缩为.zip文件
        """
        # 使用临时目录来构建备份结构
        with tempfile.TemporaryDirectory() as temp_dir:
            # 【修正】直接在根目录下创建book文件夹，移除了多余的'123'
            book_root_path = os.path.join(temp_dir, 'book')
            os.makedirs(book_root_path)

            all_books = self.data_manager.get_all_books()
            if not all_books:
                print("没有书籍可以备份。")
                return True

            book_list_data = []
            
            for book in all_books:
                # 1. 创建书籍文件夹
                book_folder_name = str(book['createTime'])
                book_path = os.path.join(book_root_path, book_folder_name)
                content_path = os.path.join(book_path, 'content')
                os.makedirs(content_path)

                # 2. 处理章节和目录结构
                chapters = self.data_manager.get_chapters_for_book(book['id'])
                total_word_count = 0
                last_edit_chapter = "无章节"

                volumes_structure = {}
                for chapter in chapters:
                    total_word_count += chapter['word_count']
                    last_edit_chapter = chapter['title']
                    
                    # 创建章节JSON文件
                    chapter_content_data = {
                        "content": chapter['content'],
                        "count": chapter['word_count'],
                        "hash": chapter.get('hash', '') # 使用.get保证健壮性
                    }
                    chapter_filename = os.path.join(content_path, f"{chapter['createTime']}.json")
                    with open(chapter_filename, 'w', encoding='utf-8') as f:
                        json.dump(chapter_content_data, f, ensure_ascii=False, indent=4)

                    # 构建 book.json 的目录结构
                    vol_name = chapter['volume'] or "未分卷"
                    if vol_name not in volumes_structure:
                        volumes_structure[vol_name] = {
                            "name": vol_name,
                            "children": [],
                            "createTime": None # 卷没有独立时间戳
                        }
                    volumes_structure[vol_name]['children'].append({
                        "name": chapter['title'],
                        "count": chapter['word_count'],
                        "createTime": chapter['createTime'],
                        "volumeName": vol_name
                    })

                # 3. 创建 book.json
                book_json_data = {
                    "name": book['title'],
                    "summary": book.get('description', ''),
                    "children": list(volumes_structure.values()),
                    "createTime": book['createTime'],
                    "lastEditTime": book['lastEditTime'],
                    "group": book.get('group', '未分组')
                }
                book_json_path = os.path.join(book_path, 'book.json')
                with open(book_json_path, 'w', encoding='utf-8') as f:
                    json.dump(book_json_data, f, ensure_ascii=False, indent=4)
                
                # 4. 准备 bookList.json 的条目
                book_list_data.append({
                    "name": book['title'],
                    "author": "", # schema中存在，但我们数据库没有，留空
                    "createTime": book['createTime'],
                    "totalCount": total_word_count,
                    "lastEditInfo": last_edit_chapter
                })
            
            # 5. 创建 bookList.json
            booklist_path = os.path.join(book_root_path, 'bookList.json')
            with open(booklist_path, 'w', encoding='utf-8') as f:
                json.dump(book_list_data, f, ensure_ascii=False, indent=4)

            # 6. 压缩为 .zip 文件
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            zip_filename = f"backup_{timestamp}.zip"
            zip_filepath = os.path.join(self.backup_dir, zip_filename)

            with zipfile.ZipFile(zip_filepath, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, _, files in os.walk(temp_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        # 写入zip时，使用相对路径
                        arcname = os.path.relpath(file_path, temp_dir)
                        zipf.write(file_path, arcname)
            
            print(f"成功创建备份: {zip_filename}")
            return True

    def list_backups(self):
        """列出所有.zip和.bcb备份文件，按时间倒序排列"""
        try:
            # .zip 和兼容的 .bcb 格式
            files = [f for f in os.listdir(self.backup_dir) if (f.endswith('.zip') or f.endswith('.bcb'))]
            return sorted(files, reverse=True)
        except OSError:
            return []

    def restore_from_backup(self, backup_file_name):
        """
        从指定的.zip备份文件恢复数据库。
        此操作会清空现有数据！
        """
        backup_path = os.path.join(self.backup_dir, backup_file_name)
        if not os.path.exists(backup_path):
            print("备份文件不存在。")
            return False

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                # 1. 解压备份文件
                with zipfile.ZipFile(backup_path, 'r') as zipf:
                    zipf.extractall(temp_dir)
                
                print(f"正在从 {backup_file_name} 恢复...")
                
                # --- 【修正】路径查找逻辑，使其更健壮 ---
                # 首先尝试新的、正确的路径
                book_root_path = os.path.join(temp_dir, 'book')
                if not os.path.exists(book_root_path):
                    # 如果不存在，则尝试旧的、错误的路径以实现兼容
                    book_root_path = os.path.join(temp_dir, '123', 'book')
                    if not os.path.exists(book_root_path):
                        print("错误: 备份文件中未找到 'book' 或 '123/book' 文件夹")
                        return False
                
                booklist_path = os.path.join(book_root_path, 'bookList.json')
                if not os.path.exists(booklist_path):
                    print(f"错误: 在路径 {book_root_path} 中未找到 bookList.json")
                    return False
                
                # 2. 清空当前数据库
                self.data_manager.clear_all_writing_data()

                # 3. 读取 bookList.json 并开始恢复
                with open(booklist_path, 'r', encoding='utf-8') as f:
                    book_list = json.load(f)
                
                for book_info in book_list:
                    book_folder_name = str(book_info['createTime'])
                    book_json_path = os.path.join(book_root_path, book_folder_name, 'book.json')

                    if not os.path.exists(book_json_path):
                        continue
                    
                    with open(book_json_path, 'r', encoding='utf-8') as f:
                        book_data = json.load(f)

                    # 4. 插入书籍
                    new_book_id = self.data_manager.add_book_from_backup(book_data)

                    # 5. 遍历卷和章，插入章节数据
                    for volume in book_data.get('children', []):
                        for chapter in volume.get('children', []):
                            content_filename = os.path.join(book_root_path, book_folder_name, 'content', f"{chapter['createTime']}.json")
                            if not os.path.exists(content_filename):
                                continue
                            
                            with open(content_filename, 'r', encoding='utf-8') as f:
                                content_data = json.load(f)

                            self.data_manager.add_chapter_from_backup(new_book_id, chapter, content_data)

            print("数据库恢复成功。请重启应用以刷新界面。")
            return True
        except Exception as e:
            print(f"恢复失败: {e}")
            import traceback
            traceback.print_exc()
            return False
            
    def delete_backup(self, backup_file_name):
        """删除指定的备份文件"""
        backup_path = os.path.join(self.backup_dir, backup_file_name)
        if not os.path.exists(backup_path):
            print("要删除的备份文件不存在。")
            return False
        
        try:
            os.remove(backup_path)
            print(f"已删除备份: {backup_file_name}")
            return True
        except Exception as e:
            print(f"删除失败: {e}")
            return False