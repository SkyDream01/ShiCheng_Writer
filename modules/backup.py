# ShiCheng_Writer/modules/backup.py
import os
import shutil
import json
import zipfile
import tempfile
from datetime import datetime
from PySide6.QtCore import QObject, Signal, QThread

from .webdav_client import WebDAVClient
# [优化] 引入 DataManager 类以便在线程中新建连接
from .database import DataManager

class BackupWorker(QThread):
    """
    [优化] 后台备份工作线程
    """
    finished = Signal(bool, str) # success, message
    log = Signal(str)

    def __init__(self, task_type, base_backup_dir, parent=None):
        super().__init__(parent)
        self.task_type = task_type # 'stage', 'archive', 'snapshot'
        self.base_backup_dir = base_backup_dir
        self.snapshot_data = None # 仅用于 snapshot

    def run(self):
        # [优化] 在线程内部实例化 DataManager，确保数据库连接线程安全
        local_data_manager = DataManager()
        
        try:
            if self.task_type == 'snapshot':
                self._run_snapshot(local_data_manager)
            elif self.task_type in ['stage', 'archive']:
                self._run_full_backup(local_data_manager)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.finished.emit(False, str(e))
        finally:
            local_data_manager.close()

    def _get_webdav_client(self, data_manager):
        settings = data_manager.get_webdav_settings()
        if not settings.get('webdav_enabled'):
            return None
        return WebDAVClient(settings)

    def _run_snapshot(self, data_manager):
        if not self.snapshot_data:
            self.finished.emit(True, "无数据更新")
            return

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_filename = f"backup_snapshot_{timestamp}.json"
        backup_filepath = os.path.join(self.base_backup_dir, backup_filename)
        
        try:
            with open(backup_filepath, 'w', encoding='utf-8') as f:
                json.dump(self.snapshot_data, f, ensure_ascii=False, indent=2)
            
            self.log.emit(f"快照线备份本地成功: {backup_filename}")
            
            # 上传
            client = self._get_webdav_client(data_manager)
            if client:
                self.log.emit(f"WebDAV: 开始上传快照 {backup_filename}...")
                success, msg = client.upload_file(backup_filepath, backup_filename)
                self.log.emit(f"WebDAV: {msg}")
                if success:
                    self._cleanup_webdav(client, "snapshot")
            
            self.finished.emit(True, "快照备份完成")
        except Exception as e:
            self.finished.emit(False, f"快照备份失败: {e}")

    def _run_full_backup(self, data_manager):
        prefix = f"backup_{self.task_type}_"
        zip_filepath = self._create_zip(data_manager, prefix)
        
        if zip_filepath:
            client = self._get_webdav_client(data_manager)
            if client:
                filename = os.path.basename(zip_filepath)
                self.log.emit(f"WebDAV: 开始上传 {filename}...")
                success, msg = client.upload_file(zip_filepath, filename)
                self.log.emit(f"WebDAV: {msg}")
                if success:
                    self._cleanup_webdav(client, self.task_type)
            self.finished.emit(True, f"{self.task_type} 备份完成")
        else:
            self.finished.emit(False, "本地 ZIP 创建失败")

    def _create_zip(self, data_manager, prefix):
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                book_root_path = os.path.join(temp_dir, 'book')
                os.makedirs(book_root_path)
                
                # --- 获取数据 (使用线程内的 database 连接) ---
                all_books = data_manager.get_all_books()
                book_list_data = []
                
                if all_books:
                    for book in all_books:
                        book_folder_name = str(book['id'])
                        book_path = os.path.join(book_root_path, book_folder_name)
                        content_path = os.path.join(book_path, 'content')
                        os.makedirs(content_path)
                        
                        chapters = data_manager.get_chapters_for_book(book['id'])
                        total_word_count = 0
                        last_edit_chapter = "无章节"
                        volumes_structure = {}
                        
                        for chapter in chapters:
                            total_word_count += chapter['word_count']
                            last_edit_chapter = chapter['title']
                            
                            chapter_content_data = {
                                "content": chapter['content'], "count": chapter['word_count'],
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

                        book_data_for_json = data_manager.get_book_details(book['id'])
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
                
                # 导出其他模块数据
                self._dump_table(data_manager.get_all_materials, os.path.join(temp_dir, 'materials.json'))
                self._dump_table(data_manager.get_all_inspiration_items, os.path.join(temp_dir, 'inspiration_items.json'))
                self._dump_table(data_manager.get_all_inspiration_fragments, os.path.join(temp_dir, 'inspiration_fragments.json'))
                self._dump_table(data_manager.get_all_timelines, os.path.join(temp_dir, 'timelines.json'))
                self._dump_table(data_manager.get_all_timeline_events, os.path.join(temp_dir, 'timeline_events.json'))

                timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                zip_filename = f"{prefix}{timestamp}.zip"
                zip_filepath = os.path.join(self.base_backup_dir, zip_filename)

                with zipfile.ZipFile(zip_filepath, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for root, _, files in os.walk(temp_dir):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, temp_dir)
                            zipf.write(file_path, arcname)
                
                self.log.emit(f"本地打包成功: {zip_filename}")
                return zip_filepath
        except Exception as e:
            self.log.emit(f"打包失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _dump_table(self, fetch_func, filepath):
        data = fetch_func()
        if data:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)

    def _cleanup_webdav(self, client, backup_type):
        retention_map = {"snapshot": 100, "stage": 5, "archive": 15}
        keep_count = retention_map.get(backup_type)
        prefix_map = {
            "snapshot": "backup_snapshot_",
            "stage": "backup_stage_",
            "archive": "backup_archive_"
        }
        file_prefix = prefix_map.get(backup_type)
        if not file_prefix: return

        try:
            all_files = client.list_files()
            backup_files = [info for info in all_files if os.path.basename(info['name']).startswith(file_prefix)]
            if len(backup_files) > keep_count:
                backup_files.sort(key=lambda x: x['modified'], reverse=True)
                for f_info in backup_files[keep_count:]:
                    client.delete_file(os.path.basename(f_info['name']))
        except Exception:
            pass

class BackupManager(QObject):
    """
    [优化] 备份管理器，作为前端和后台线程的桥梁
    """
    log_message = Signal(str)

    def __init__(self, data_manager, base_backup_dir="backups"):
        super().__init__()
        self.data_manager = data_manager
        self.base_backup_dir = base_backup_dir
        if not os.path.exists(self.base_backup_dir):
            os.makedirs(self.base_backup_dir)
        self.last_snapshot_check_time = datetime.now()
        
        self._current_worker = None

    def test_webdav_connection(self):
        settings = self.data_manager.get_webdav_settings()
        if not settings.get('webdav_enabled'):
            return False, "WebDAV未启用。"
        client = WebDAVClient(settings)
        return client.test_connection()

    def _start_worker(self, task_type, snapshot_data=None):
        if self._current_worker and self._current_worker.isRunning():
            self.log_message.emit("后台已有备份任务在运行，本次跳过。")
            return

        self._current_worker = BackupWorker(task_type, self.base_backup_dir)
        self._current_worker.snapshot_data = snapshot_data
        self._current_worker.log.connect(self.log_message.emit)
        self._current_worker.finished.connect(self._on_worker_finished)
        self._current_worker.start()

    def _on_worker_finished(self, success, message):
        if not success:
            self.log_message.emit(f"备份任务结束: {message}")
        self._cleanup_local_backups()

    def create_stage_point_backup(self):
        self.log_message.emit("开始阶段点备份 (后台运行)...")
        self._start_worker('stage')

    def create_archive_backup(self):
        today_str = datetime.now().strftime("%Y-%m-%d")
        if any(f.startswith(f"backup_archive_{today_str}") for f in os.listdir(self.base_backup_dir)):
            return 
        self.log_message.emit("开始日终归档备份 (后台运行)...")
        self._start_worker('archive')

    def create_snapshot_backup(self):
        modified_chapters = self.data_manager.get_chapters_modified_since(self.last_snapshot_check_time)
        if not modified_chapters:
            return

        snapshot_data = { "backup_time": datetime.now().isoformat(), "chapters": [] }
        for chapter in modified_chapters:
            snapshot_data["chapters"].append({
                "id": chapter['id'], "title": chapter['title'], "book_id": chapter['book_id'],
                "content": chapter['content'], "modified_time": chapter['lastEditTime'] 
            })
        
        self.last_snapshot_check_time = datetime.now()
        self._start_worker('snapshot', snapshot_data)

    def _cleanup_local_backups(self):
        for prefix, limit in [("backup_snapshot_", 15), ("backup_stage_", 5), ("backup_archive_", 15)]:
             try:
                files = [f for f in os.listdir(self.base_backup_dir) if f.startswith(prefix)]
                files.sort(key=lambda name: os.path.getmtime(os.path.join(self.base_backup_dir, name)), reverse=True)
                if len(files) > limit:
                    for f in files[limit:]:
                        os.remove(os.path.join(self.base_backup_dir, f))
             except: pass

    def list_backups(self):
        backups = []
        try:
            files = os.listdir(self.base_backup_dir)
            for file in files:
                backup_info = {"file": file, "dir": self.base_backup_dir, "source": "local"}
                if file.startswith('backup_stage_'): backup_info["type"] = "Stage"
                elif file.startswith('backup_archive_'): backup_info["type"] = "Archive"
                elif file.lower().endswith('.bcb'): backup_info["type"] = "BCB 备份"
                elif file.startswith('backup_snapshot_'): backup_info["type"] = "Snapshot"
                else: continue
                backups.append(backup_info)
        except OSError: pass
        backups.sort(key=lambda x: x['file'], reverse=True)
        return backups

    def list_remote_backups(self):
        client = self._get_webdav_client_direct()
        if not client: return []
        all_remote_backups = []
        try:
            files = client.list_files()
            for f_info in files:
                file_name = os.path.basename(f_info['name'])
                if not (file_name.endswith(('.zip', '.json')) and file_name.startswith('backup_')): continue
                backup_info = {"file": file_name, "dir": client.root_path, "path": f_info['name'], "source": "cloud"}
                if file_name.startswith('backup_snapshot_'): backup_info["type"] = "Snapshot"
                elif file_name.startswith('backup_stage_'): backup_info["type"] = "Stage"
                elif file_name.startswith('backup_archive_'): backup_info["type"] = "Archive"
                else: continue
                all_remote_backups.append(backup_info)
        except Exception: pass
        all_remote_backups.sort(key=lambda x: x['file'], reverse=True)
        return all_remote_backups

    def _get_webdav_client_direct(self):
        settings = self.data_manager.get_webdav_settings()
        if not settings.get('webdav_enabled'): return None
        return WebDAVClient(settings)

    def download_backup(self, remote_filename, local_dir):
        client = self._get_webdav_client_direct()
        if not client: return None
        local_filepath = os.path.join(local_dir, remote_filename)
        self.log_message.emit(f"正在下载 {remote_filename}...")
        success, msg = client.download_file(remote_filename, local_filepath)
        self.log_message.emit(f"下载结束: {msg}")
        return local_filepath if success else None
    
    def restore_from_snapshot(self, backup_info):
        backup_path = os.path.join(backup_info['dir'], backup_info['file'])
        if not os.path.exists(backup_path): return False
        try:
            with open(backup_path, 'r', encoding='utf-8') as f:
                snapshot_data = json.load(f)
            chapters_to_restore = snapshot_data.get("chapters", [])
            for chapter_data in chapters_to_restore:
                self.data_manager.update_chapter_content(chapter_data['id'], chapter_data['content'])
            self.log_message.emit(f"成功从快照恢复 {len(chapters_to_restore)} 个章节。")
            return True
        except Exception as e:
            self.log_message.emit(f"从快照恢复失败: {e}")
            return False

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
                self.log_message.emit("本地数据库已清空，准备写入备份数据...")

                book_root_path = os.path.join(temp_dir, 'book')
                booklist_path = os.path.join(book_root_path, 'bookList.json')
                if os.path.exists(booklist_path):
                    with open(booklist_path, 'r', encoding='utf-8') as f:
                        book_list = json.load(f)
                    
                    for book_item in book_list:
                        book_id = book_item['id']
                        book_json_path = os.path.join(book_root_path, str(book_id), 'book.json')
                        if os.path.exists(book_json_path):
                            with open(book_json_path, 'r', encoding='utf-8') as f:
                                book_data = json.load(f)
                            
                            restored_book_id = self.data_manager.add_book_from_backup(book_data)
                            self.log_message.emit(f"正在恢复书籍: {book_data.get('name')}")
                            
                            if 'children' in book_data:
                                for volume in book_data['children']:
                                    for chapter_meta in volume['children']:
                                        content_filename = f"{chapter_meta['createTime']}.json"
                                        content_path = os.path.join(book_root_path, str(book_id), 'content', content_filename)
                                        if os.path.exists(content_path):
                                            with open(content_path, 'r', encoding='utf-8') as f:
                                                content_data = json.load(f)
                                            self.data_manager.add_chapter_from_backup(restored_book_id, chapter_meta, content_data)
                
                # 恢复其他数据
                materials_path = os.path.join(temp_dir, 'materials.json')
                if not os.path.exists(materials_path): materials_path = os.path.join(temp_dir, 'settings.json')
                if os.path.exists(materials_path):
                    with open(materials_path, 'r', encoding='utf-8') as f:
                        for m in json.load(f): self.data_manager.add_material_from_backup(m)

                insp_items_path = os.path.join(temp_dir, 'inspiration_items.json')
                if os.path.exists(insp_items_path):
                    with open(insp_items_path, 'r', encoding='utf-8') as f:
                        for i in json.load(f): self.data_manager.add_inspiration_item_from_backup(i)

                insp_fragments_path = os.path.join(temp_dir, 'inspiration_fragments.json')
                if os.path.exists(insp_fragments_path):
                    with open(insp_fragments_path, 'r', encoding='utf-8') as f:
                        for frag in json.load(f): self.data_manager.add_inspiration_fragment_from_backup(frag)

                timelines_path = os.path.join(temp_dir, 'timelines.json')
                if os.path.exists(timelines_path):
                    with open(timelines_path, 'r', encoding='utf-8') as f:
                        for t in json.load(f): self.data_manager.add_timeline_from_backup(t)

                events_path = os.path.join(temp_dir, 'timeline_events.json')
                if os.path.exists(events_path):
                    with open(events_path, 'r', encoding='utf-8') as f:
                        for e in json.load(f): self.data_manager.add_timeline_event_from_backup(e)

            self.log_message.emit("数据库恢复成功。请重启应用以刷新界面。")
            return True
        except Exception as e:
            self.log_message.emit(f"恢复失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def delete_backup(self, backup_info):
        backup_path = os.path.join(backup_info['dir'], backup_info['file'])
        try:
            os.remove(backup_path)
            self.log_message.emit(f"已删除备份: {backup_info['file']}")
            return True
        except Exception as e:
            self.log_message.emit(f"删除失败: {e}")
            return False
            
    def delete_remote_backup(self, remote_filename):
        client = self._get_webdav_client_direct()
        if not client: return False
        success, message = client.delete_file(remote_filename)
        self.log_message.emit(f"WebDAV: {message}")
        return success