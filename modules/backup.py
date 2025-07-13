# ShiCheng_Writer/modules/backup.py
import os
import shutil
import json
import zipfile
import tempfile
from datetime import datetime

class BackupManager:
    """
    备份管理器，支持三层备份策略，所有备份文件存储于根备份目录中。
    - 快照线 (Snapshot Line): 高频增量备份。
    - 阶段点 (Stage Point): 关键节点完整备份。
    - 日终归档 (End-of-Day Archive): 每日完整备份。
    """
    def __init__(self, data_manager, base_backup_dir="backups"):
        self.data_manager = data_manager
        self.base_backup_dir = base_backup_dir
        
        # 确保根备份目录存在
        if not os.path.exists(self.base_backup_dir):
            os.makedirs(self.base_backup_dir)

        self.last_snapshot_check_time = datetime.now()

    def create_snapshot_backup(self):
        """
        创建一次增量备份 (快照线)。
        """
        modified_chapters = self.data_manager.get_chapters_modified_since(self.last_snapshot_check_time)
        
        if not modified_chapters:
            return

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_data = {
            "backup_time": datetime.now().isoformat(),
            "chapters": []
        }

        for chapter in modified_chapters:
            backup_data["chapters"].append({
                "id": chapter['id'],
                "title": chapter['title'],
                "book_id": chapter['book_id'],
                "content": chapter['content'],
                "modified_time": chapter['lastEditTime'] 
            })
        
        # 文件名带有明确前缀以作区分
        backup_filename = os.path.join(self.base_backup_dir, f"backup_snapshot_{timestamp}.json")
        try:
            with open(backup_filename, 'w', encoding='utf-8') as f:
                json.dump(backup_data, f, ensure_ascii=False, indent=2)
            print(f"快照线备份成功: {os.path.basename(backup_filename)}")
        except Exception as e:
            print(f"创建快照线备份失败: {e}")

        self.last_snapshot_check_time = datetime.now()
        self._cleanup_backups("backup_snapshot_", 15)

    def create_stage_point_backup(self):
        """创建一次完整的项目备份 (阶段点)。"""
        print("正在创建阶段点备份...")
        if self._create_full_backup("backup_stage_"):
            self._cleanup_backups("backup_stage_", 5)

    def create_archive_backup(self):
        """创建每日首次启动时的备份 (日终归档)。"""
        today_str = datetime.now().strftime("%Y-%m-%d")
        # 检查文件名是否以 'backup_archive_YYYY-MM-DD' 开头
        if any(f.startswith(f"backup_archive_{today_str}") for f in os.listdir(self.base_backup_dir)):
            print(f"今日已存在日终归档备份，将跳过。")
            return
            
        print("正在创建日终归档备份...")
        if self._create_full_backup("backup_archive_"):
            self._cleanup_backups("backup_archive_", 15)

    def _create_full_backup(self, prefix):
        """
        创建并压缩一个完整的项目备份。
        """
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                book_root_path = os.path.join(temp_dir, 'book')
                os.makedirs(book_root_path)

                all_books = self.data_manager.get_all_books()
                if not all_books:
                    print("没有书籍可以备份。")
                    return False

                book_list_data = []
                
                for book in all_books:
                    book_folder_name = str(book['createTime'])
                    book_path = os.path.join(book_root_path, book_folder_name)
                    content_path = os.path.join(book_path, 'content')
                    os.makedirs(content_path)

                    chapters = self.data_manager.get_chapters_for_book(book['id'])
                    total_word_count = 0
                    last_edit_chapter = "无章节"

                    volumes_structure = {}
                    for chapter in chapters:
                        total_word_count += chapter['word_count']
                        last_edit_chapter = chapter['title']
                        
                        chapter_content_data = {
                            "content": chapter['content'],
                            "count": chapter['word_count'],
                            "hash": chapter.get('hash', '')
                        }
                        chapter_filename = os.path.join(content_path, f"{chapter['createTime']}.json")
                        with open(chapter_filename, 'w', encoding='utf-8') as f:
                            json.dump(chapter_content_data, f, ensure_ascii=False, indent=4)

                        vol_name = chapter['volume'] or "未分卷"
                        if vol_name not in volumes_structure:
                            volumes_structure[vol_name] = {
                                "name": vol_name,
                                "children": [],
                                "createTime": None
                            }
                        volumes_structure[vol_name]['children'].append({
                            "name": chapter['title'],
                            "count": chapter['word_count'],
                            "createTime": chapter['createTime'],
                            "volumeName": vol_name
                        })

                    book_json_data = {
                        "name": book['title'], "summary": book.get('description', ''),
                        "children": list(volumes_structure.values()),
                        "createTime": book['createTime'], "lastEditTime": book['lastEditTime'],
                        "group": book.get('group', '未分组')
                    }
                    book_json_path = os.path.join(book_path, 'book.json')
                    with open(book_json_path, 'w', encoding='utf-8') as f:
                        json.dump(book_json_data, f, ensure_ascii=False, indent=4)
                    
                    book_list_data.append({
                        "name": book['title'], "author": "", "createTime": book['createTime'],
                        "totalCount": total_word_count, "lastEditInfo": last_edit_chapter
                    })
                
                booklist_path = os.path.join(book_root_path, 'bookList.json')
                with open(booklist_path, 'w', encoding='utf-8') as f:
                    json.dump(book_list_data, f, ensure_ascii=False, indent=4)

                timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                zip_filename = f"{prefix}{timestamp}.zip"
                zip_filepath = os.path.join(self.base_backup_dir, zip_filename)

                with zipfile.ZipFile(zip_filepath, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for root, _, files in os.walk(temp_dir):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, temp_dir)
                            zipf.write(file_path, arcname)
                
                print(f"成功创建完整备份: {zip_filename}")
                return True
        except Exception as e:
            import traceback
            print(f"创建完整备份时发生错误: {e}")
            traceback.print_exc()
            return False

    def _cleanup_backups(self, prefix, keep_count):
        """清理指定类型的备份文件。"""
        try:
            # 从根备份目录中筛选出特定前缀的文件
            files = [f for f in os.listdir(self.base_backup_dir) if f.startswith(prefix)]
            files.sort(key=lambda name: os.path.getmtime(os.path.join(self.base_backup_dir, name)), reverse=True)
            
            if len(files) > keep_count:
                files_to_delete = files[keep_count:]
                for f in files_to_delete:
                    os.remove(os.path.join(self.base_backup_dir, f))
        except Exception as e:
            print(f"清理 {prefix} 备份时出错: {e}")

    def list_backups(self):
        """列出所有可供恢复的完整备份 (阶段点、日终归档和 .bcb 文件)。"""
        backups = []
        try:
            files = os.listdir(self.base_backup_dir)
            for file in files:
                backup_info = {"file": file, "dir": self.base_backup_dir}
                if file.startswith('backup_stage_'):
                    backup_info["type"] = "阶段点"
                    backups.append(backup_info)
                elif file.startswith('backup_archive_'):
                    backup_info["type"] = "日终归档"
                    backups.append(backup_info)
                elif file.lower().endswith('.bcb'):
                    backup_info["type"] = "BCB 备份"
                    backups.append(backup_info)
        except OSError:
            pass
        
        backups.sort(key=lambda x: x['file'], reverse=True)
        return backups

    def restore_from_backup(self, backup_info):
        """
        从指定的完整备份文件恢复。
        """
        backup_path = os.path.join(backup_info['dir'], backup_info['file'])
        if not os.path.exists(backup_path):
            print("备份文件不存在。")
            return False

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                with zipfile.ZipFile(backup_path, 'r') as zipf:
                    zipf.extractall(temp_dir)
                
                print(f"正在从 {backup_info['type']} 备份 '{backup_info['file']}' 恢复...")
                
                book_root_path = os.path.join(temp_dir, 'book')
                if not os.path.exists(book_root_path):
                    print("错误: 备份文件中未找到 'book' 文件夹")
                    return False
                
                booklist_path = os.path.join(book_root_path, 'bookList.json')
                if not os.path.exists(booklist_path):
                    print(f"错误: 在路径 {book_root_path} 中未找到 bookList.json")
                    return False
                
                self.data_manager.clear_all_writing_data()

                with open(booklist_path, 'r', encoding='utf-8') as f:
                    book_list = json.load(f)
                
                for book_info in book_list:
                    book_folder_name = str(book_info['createTime'])
                    book_json_path = os.path.join(book_root_path, book_folder_name, 'book.json')

                    if not os.path.exists(book_json_path): continue
                    
                    with open(book_json_path, 'r', encoding='utf-8') as f:
                        book_data = json.load(f)

                    new_book_id = self.data_manager.add_book_from_backup(book_data)

                    for volume in book_data.get('children', []):
                        for chapter in volume.get('children', []):
                            content_filename = os.path.join(book_root_path, book_folder_name, 'content', f"{chapter['createTime']}.json")
                            if not os.path.exists(content_filename): continue
                            
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
            
    def delete_backup(self, backup_info):
        """删除指定的备份文件"""
        backup_path = os.path.join(backup_info['dir'], backup_info['file'])
        if not os.path.exists(backup_path):
            print("要删除的备份文件不存在。")
            return False
        
        try:
            os.remove(backup_path)
            print(f"已删除备份: {backup_info['file']}")
            return True
        except Exception as e:
            print(f"删除失败: {e}")
            return False