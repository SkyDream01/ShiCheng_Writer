# ShiCheng_Writer/modules/backup.py
import os
import shutil
import json
import zipfile
import tempfile
from datetime import datetime
from PySide6.QtCore import QObject, Signal

class BackupManager(QObject):
    """
    备份管理器，支持三层备份策略，所有备份文件存储于根备份目录中。
    - 快照线 (Snapshot Line): 高频增量备份。
    - 阶段点 (Stage Point): 关键节点完整备份。
    - 日终归档 (End-of-Day Archive): 每日完整备份。
    """
    log_message = Signal(str)

    def __init__(self, data_manager, base_backup_dir="backups"):
        super().__init__()
        self.data_manager = data_manager
        self.base_backup_dir = base_backup_dir
        
        if not os.path.exists(self.base_backup_dir):
            os.makedirs(self.base_backup_dir)

        self.last_snapshot_check_time = datetime.now()

    def create_snapshot_backup(self):
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
        
        backup_filename = os.path.join(self.base_backup_dir, f"backup_snapshot_{timestamp}.json")
        try:
            with open(backup_filename, 'w', encoding='utf-8') as f:
                json.dump(backup_data, f, ensure_ascii=False, indent=2)
            self.log_message.emit(f"快照线备份成功: {os.path.basename(backup_filename)}")
        except Exception as e:
            self.log_message.emit(f"创建快照线备份失败: {e}")

        self.last_snapshot_check_time = datetime.now()
        self._cleanup_backups("backup_snapshot_", 15)

    def create_stage_point_backup(self):
        self.log_message.emit("正在创建阶段点备份...")
        if self._create_full_backup("backup_stage_"):
            self._cleanup_backups("backup_stage_", 5)

    def create_archive_backup(self):
        today_str = datetime.now().strftime("%Y-%m-%d")
        if any(f.startswith(f"backup_archive_{today_str}") for f in os.listdir(self.base_backup_dir)):
            self.log_message.emit(f"今日已存在日终归档备份，将跳过。")
            return
            
        self.log_message.emit("正在创建日终归档备份...")
        if self._create_full_backup("backup_archive_"):
            self._cleanup_backups("backup_archive_", 15)

    def _create_full_backup(self, prefix):
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                book_root_path = os.path.join(temp_dir, 'book')
                os.makedirs(book_root_path)

                all_books = self.data_manager.get_all_books()
                book_list_data = []
                
                if all_books:
                    for book in all_books:
                        book_folder_name = str(book['id'])
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
                                volumes_structure[vol_name] = {"name": vol_name, "children": [], "createTime": None}
                            volumes_structure[vol_name]['children'].append({
                                "name": chapter['title'], "count": chapter['word_count'],
                                "createTime": chapter['createTime'], "volumeName": vol_name
                            })

                        book_data_for_json = self.data_manager.get_book_details(book['id'])
                        book_data_for_json['name'] = book_data_for_json.pop('title')
                        book_data_for_json['summary'] = book_data_for_json.pop('description')
                        book_data_for_json['children'] = list(volumes_structure.values())
                        
                        book_json_path = os.path.join(book_path, 'book.json')
                        with open(book_json_path, 'w', encoding='utf-8') as f:
                            json.dump(book_data_for_json, f, ensure_ascii=False, indent=4)
                        
                        book_list_data.append({
                            "name": book['title'], "author": "", "createTime": book['createTime'],
                            "totalCount": total_word_count, "lastEditInfo": last_edit_chapter, "id": book['id']
                        })
                
                booklist_path = os.path.join(book_root_path, 'bookList.json')
                with open(booklist_path, 'w', encoding='utf-8') as f:
                    json.dump(book_list_data, f, ensure_ascii=False, indent=4)

                # vvvvvvvvvv [修改] 备份 materials vvvvvvvvvv
                all_materials = self.data_manager.get_all_materials()
                if all_materials:
                    materials_filepath = os.path.join(temp_dir, 'materials.json')
                    with open(materials_filepath, 'w', encoding='utf-8') as f:
                        json.dump(all_materials, f, ensure_ascii=False, indent=4)
                # ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

                all_insp_items = self.data_manager.get_all_inspiration_items()
                if all_insp_items:
                    insp_items_filepath = os.path.join(temp_dir, 'inspiration_items.json')
                    with open(insp_items_filepath, 'w', encoding='utf-8') as f:
                        json.dump(all_insp_items, f, ensure_ascii=False, indent=4)
                
                all_insp_fragments = self.data_manager.get_all_inspiration_fragments()
                if all_insp_fragments:
                    insp_fragments_filepath = os.path.join(temp_dir, 'inspiration_fragments.json')
                    with open(insp_fragments_filepath, 'w', encoding='utf-8') as f:
                        json.dump(all_insp_fragments, f, ensure_ascii=False, indent=4)

                timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                zip_filename = f"{prefix}{timestamp}.zip"
                zip_filepath = os.path.join(self.base_backup_dir, zip_filename)

                with zipfile.ZipFile(zip_filepath, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for root, _, files in os.walk(temp_dir):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, temp_dir)
                            zipf.write(file_path, arcname)
                
                self.log_message.emit(f"成功创建完整备份: {zip_filename}")
                return True
        except Exception as e:
            import traceback
            self.log_message.emit(f"创建完整备份时发生错误: {e}")
            traceback.print_exc()
            return False

    def _cleanup_backups(self, prefix, keep_count):
        try:
            files = [f for f in os.listdir(self.base_backup_dir) if f.startswith(prefix)]
            files.sort(key=lambda name: os.path.getmtime(os.path.join(self.base_backup_dir, name)), reverse=True)
            
            if len(files) > keep_count:
                files_to_delete = files[keep_count:]
                for f in files_to_delete:
                    os.remove(os.path.join(self.base_backup_dir, f))
        except Exception as e:
            self.log_message.emit(f"清理 {prefix} 备份时出错: {e}")

    def list_backups(self):
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
        backup_path = os.path.join(backup_info['dir'], backup_info['file'])
        if not os.path.exists(backup_path):
            self.log_message.emit("备份文件不存在。")
            return False

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                with zipfile.ZipFile(backup_path, 'r') as zipf:
                    zipf.extractall(temp_dir)
                
                self.log_message.emit(f"正在从 {backup_info['type']} 备份 '{backup_info['file']}' 恢复...")
                
                self.data_manager.clear_all_writing_data()

                book_root_path = os.path.join(temp_dir, 'book')
                booklist_path = os.path.join(book_root_path, 'bookList.json') if os.path.exists(book_root_path) else None

                if booklist_path and os.path.exists(booklist_path):
                    with open(booklist_path, 'r', encoding='utf-8') as f:
                        book_list = json.load(f)
                    
                    for book_info_item in book_list:
                        book_folder_name = str(book_info_item.get('id') or book_info_item['createTime'])
                        book_json_path = os.path.join(book_root_path, book_folder_name, 'book.json')
                        if not os.path.exists(book_json_path): continue
                        
                        with open(book_json_path, 'r', encoding='utf-8') as f: book_data = json.load(f)
                        new_book_id = self.data_manager.add_book_from_backup(book_data)

                        for volume in book_data.get('children', []):
                            for chapter in volume.get('children', []):
                                content_filename = os.path.join(book_root_path, book_folder_name, 'content', f"{chapter['createTime']}.json")
                                if not os.path.exists(content_filename): continue
                                
                                with open(content_filename, 'r', encoding='utf-8') as f: content_data = json.load(f)
                                self.data_manager.add_chapter_from_backup(new_book_id, chapter, content_data)
                
                is_bcb_backup = backup_info.get("type") == "BCB 备份"
                if not is_bcb_backup:
                    # vvvvvvvvvv [修改] 恢复 materials，并兼容旧的 settings.json vvvvvvvvvv
                    materials_filepath = os.path.join(temp_dir, 'materials.json')
                    if not os.path.exists(materials_filepath):
                        materials_filepath = os.path.join(temp_dir, 'settings.json') # Fallback

                    if os.path.exists(materials_filepath):
                        with open(materials_filepath, 'r', encoding='utf-8') as f:
                            materials_list = json.load(f)
                        for material_data in materials_list:
                            self.data_manager.add_material_from_backup(material_data)
                    # ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

                    insp_items_filepath = os.path.join(temp_dir, 'inspiration_items.json')
                    if os.path.exists(insp_items_filepath):
                        with open(insp_items_filepath, 'r', encoding='utf-8') as f:
                            self.data_manager.add_inspiration_item_from_backup(json.load(f))
                    
                    insp_fragments_filepath = os.path.join(temp_dir, 'inspiration_fragments.json')
                    if os.path.exists(insp_fragments_filepath):
                        with open(insp_fragments_filepath, 'r', encoding='utf-8') as f:
                            self.data_manager.add_inspiration_fragment_from_backup(json.load(f))

            self.log_message.emit("数据库恢复成功。请重启应用以刷新界面。")
            return True
        except Exception as e:
            self.log_message.emit(f"恢复失败: {e}")
            import traceback
            traceback.print_exc()
            return False
            
    def delete_backup(self, backup_info):
        backup_path = os.path.join(backup_info['dir'], backup_info['file'])
        if not os.path.exists(backup_path):
            self.log_message.emit("要删除的备份文件不存在。")
            return False
        
        try:
            os.remove(backup_path)
            self.log_message.emit(f"已删除备份: {backup_info['file']}")
            return True
        except Exception as e:
            self.log_message.emit(f"删除失败: {e}")
            return False