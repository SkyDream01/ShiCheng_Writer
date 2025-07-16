# ShiCheng_Writer/modules/backup.py
import os
import shutil
import json
import zipfile
import tempfile
from datetime import datetime
from PySide6.QtCore import QObject, Signal

# 确保 webdav_client.py 已经创建好并放在 modules 目录下
from .webdav_client import WebDAVClient

class BackupManager(QObject):
    """
    备份管理器，支持三层备份策略和WebDAV同步。
    """
    log_message = Signal(str)

    def __init__(self, data_manager, base_backup_dir="backups"):
        super().__init__()
        self.data_manager = data_manager
        self.base_backup_dir = base_backup_dir
        
        if not os.path.exists(self.base_backup_dir):
            os.makedirs(self.base_backup_dir)

        self.last_snapshot_check_time = datetime.now()

    def _get_webdav_client(self):
        """
        获取一个配置好的 WebDAV 客户端实例。
        如果不启用或配置不完整，则返回 None。
        """
        settings = self.data_manager.get_webdav_settings()
        if not settings.get('webdav_enabled'):
            return None
        if not all([settings.get('webdav_url'), settings.get('webdav_user'), settings.get('webdav_pass')]):
            self.log_message.emit("WebDAV 信息不完整，无法连接。")
            return None
        return WebDAVClient(settings)

    def test_webdav_connection(self):
        """
        使用WebDAV客户端进行连接测试。
        """
        client = self._get_webdav_client()
        if not client:
            return False, "WebDAV未启用或配置不完整。"
        return client.test_connection()

    def _upload_to_webdav(self, file_path, backup_type):
        """
        将已存在的本地备份文件上传到 WebDAV。
        """
        client = self._get_webdav_client()
        if not client:
            return

        filename = os.path.basename(file_path)
        self.log_message.emit(f"WebDAV: 开始上传 {filename}...")
        success, message = client.upload_file(file_path, filename)
        self.log_message.emit(f"WebDAV: {message}")

        if success:
            # 上传成功后，执行远程清理
            self._cleanup_webdav_backups(client, backup_type)

    def _cleanup_webdav_backups(self, client, backup_type):
        """
        清理远程的旧备份文件。
        """
        retention_map = {"snapshot": 100, "stage": 5, "archive": 15}
        keep_count = retention_map.get(backup_type)
        if not keep_count or keep_count == -1: 
            return

        prefix_map = {
            "snapshot": "backup_snapshot_",
            "stage": "backup_stage_",
            "archive": "backup_archive_"
        }
        file_prefix = prefix_map.get(backup_type)
        if not file_prefix: 
            return

        try:
            all_files_info = client.list_files()
            # webdav4 returns a list of dicts, and path is in 'name'
            backup_files = [info for info in all_files_info if os.path.basename(info['name']).startswith(file_prefix)]
            
            if len(backup_files) > keep_count:
                backup_files.sort(key=lambda x: x['modified'], reverse=True)
                files_to_delete = backup_files[keep_count:]
                
                for f_info in files_to_delete:
                    filename_to_delete = os.path.basename(f_info['name'])
                    success, message = client.delete_file(filename_to_delete)
                    self.log_message.emit(f"WebDAV 清理: {message}")
        except Exception as e:
             self.log_message.emit(f"WebDAV 清理远程备份时出错: {e}")

    def create_snapshot_backup(self):
        """
        创建快照备份。先在本地创建，成功后再上传。
        """
        modified_chapters = self.data_manager.get_chapters_modified_since(self.last_snapshot_check_time)
        if not modified_chapters:
            return

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_data = { "backup_time": datetime.now().isoformat(), "chapters": [] }
        for chapter in modified_chapters:
            backup_data["chapters"].append({
                "id": chapter['id'], "title": chapter['title'], "book_id": chapter['book_id'],
                "content": chapter['content'], "modified_time": chapter['lastEditTime'] 
            })
        
        backup_filename_path = os.path.join(self.base_backup_dir, f"backup_snapshot_{timestamp}.json")
        try:
            # 1. 先创建本地备份
            with open(backup_filename_path, 'w', encoding='utf-8') as f:
                json.dump(backup_data, f, ensure_ascii=False, indent=2)
            self.log_message.emit(f"快照线备份成功: {os.path.basename(backup_filename_path)}")
            
            # 2. 本地备份成功后，再上传到 WebDAV
            self._upload_to_webdav(backup_filename_path, "snapshot")

        except Exception as e:
            self.log_message.emit(f"创建快照线备份失败: {e}")

        self.last_snapshot_check_time = datetime.now()
        self._cleanup_backups("backup_snapshot_", 15)

    def create_stage_point_backup(self):
        """
        创建阶段点备份。先在本地创建，成功后再上传。
        """
        self.log_message.emit("正在创建阶段点备份...")
        # 1. 先创建本地完整备份
        backup_filepath = self._create_full_backup("backup_stage_")
        
        # 2. 如果本地备份成功，则上传
        if backup_filepath:
            self._upload_to_webdav(backup_filepath, "stage")
            self._cleanup_backups("backup_stage_", 5)

    def create_archive_backup(self):
        """
        创建日终归档备份。先在本地创建，成功后再上传。
        """
        today_str = datetime.now().strftime("%Y-%m-%d")
        if any(f.startswith(f"backup_archive_{today_str}") for f in os.listdir(self.base_backup_dir)):
            self.log_message.emit(f"今日已存在日终归档备份，将跳过。")
            return
            
        self.log_message.emit("正在创建日终归档备份...")
        # 1. 先创建本地完整备份
        backup_filepath = self._create_full_backup("backup_archive_")

        # 2. 如果本地备份成功，则上传
        if backup_filepath:
            self._upload_to_webdav(backup_filepath, "archive")
            self._cleanup_backups("backup_archive_", 15)

    def _create_full_backup(self, prefix):
        # 此函数的内部逻辑负责创建并返回本地备份文件的路径
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
                
                all_materials = self.data_manager.get_all_materials()
                if all_materials:
                    materials_filepath = os.path.join(temp_dir, 'materials.json')
                    with open(materials_filepath, 'w', encoding='utf-8') as f:
                        json.dump(all_materials, f, ensure_ascii=False, indent=4)

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

                all_timelines = self.data_manager.get_all_timelines()
                if all_timelines:
                    timelines_filepath = os.path.join(temp_dir, 'timelines.json')
                    with open(timelines_filepath, 'w', encoding='utf-8') as f:
                        json.dump(all_timelines, f, ensure_ascii=False, indent=4)
                
                all_timeline_events = self.data_manager.get_all_timeline_events()
                if all_timeline_events:
                    events_filepath = os.path.join(temp_dir, 'timeline_events.json')
                    with open(events_filepath, 'w', encoding='utf-8') as f:
                        json.dump(all_timeline_events, f, ensure_ascii=False, indent=4)

                timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                zip_filename = f"{prefix}{timestamp}.zip"
                zip_filepath = os.path.join(self.base_backup_dir, zip_filename)

                with zipfile.ZipFile(zip_filepath, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for root, _, files in os.walk(temp_dir):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, temp_dir)
                            zipf.write(file_path, arcname)
                
                self.log_message.emit(f"成功创建本地备份: {zip_filename}")
                return zip_filepath
        except Exception as e:
            import traceback
            self.log_message.emit(f"创建完整备份时发生错误: {e}")
            traceback.print_exc()
            return None

    def _cleanup_backups(self, prefix, keep_count):
        # 此函数只负责清理本地备份
        try:
            files = [f for f in os.listdir(self.base_backup_dir) if f.startswith(prefix)]
            files.sort(key=lambda name: os.path.getmtime(os.path.join(self.base_backup_dir, name)), reverse=True)
            
            if len(files) > keep_count:
                files_to_delete = files[keep_count:]
                for f in files_to_delete:
                    os.remove(os.path.join(self.base_backup_dir, f))
                    self.log_message.emit(f"已清理本地备份: {f}")
        except Exception as e:
            self.log_message.emit(f"清理 {prefix} 备份时出错: {e}")

    def list_backups(self):
        backups = []
        try:
            files = os.listdir(self.base_backup_dir)
            for file in files:
                backup_info = {"file": file, "dir": self.base_backup_dir, "source": "local"}
                if file.startswith('backup_stage_'):
                    backup_info["type"] = "Stage"
                    backups.append(backup_info)
                elif file.startswith('backup_archive_'):
                    backup_info["type"] = "Archive"
                    backups.append(backup_info)
                elif file.lower().endswith('.bcb'):
                    backup_info["type"] = "BCB 备份"
                    backups.append(backup_info)
                elif file.startswith('backup_snapshot_') and file.endswith('.json'):
                    backup_info["type"] = "Snapshot"
                    backups.append(backup_info)
        except OSError:
            pass
        
        backups.sort(key=lambda x: x['file'], reverse=True)
        return backups

    def list_remote_backups(self):
        client = self._get_webdav_client()
        if not client:
            return []
        
        all_remote_backups = []
        try:
            files = client.list_files()
            for f_info in files:
                file_name = os.path.basename(f_info['name'])
                
                if not (file_name.endswith(('.zip', '.json')) and file_name.startswith('backup_')):
                    continue

                backup_info = {
                    "file": file_name,
                    "dir": client.root_path,
                    "path": f_info['name'],
                    "source": "cloud"
                }
                if file_name.startswith('backup_snapshot_'):
                    backup_info["type"] = "Snapshot"
                elif file_name.startswith('backup_stage_'):
                    backup_info["type"] = "Stage"
                elif file_name.startswith('backup_archive_'):
                    backup_info["type"] = "Archive"
                else:
                    continue
                all_remote_backups.append(backup_info)
        except Exception as e:
            self.log_message.emit(f"WebDAV: 列出远程备份时出错 - {e}")
            
        all_remote_backups.sort(key=lambda x: x['file'], reverse=True)
        return all_remote_backups

    def download_backup(self, remote_filename, local_dir):
        client = self._get_webdav_client()
        if not client:
            return None

        local_filepath = os.path.join(local_dir, remote_filename)
        self.log_message.emit(f"正在从云端下载 {remote_filename}...")
        success, message = client.download_file(remote_filename, local_filepath)
        self.log_message.emit(f"WebDAV: {message}")
        return local_filepath if success else None

    def restore_from_snapshot(self, backup_info):
        backup_path = os.path.join(backup_info['dir'], backup_info['file'])
        if not os.path.exists(backup_path):
            self.log_message.emit("快照备份文件不存在。")
            return False

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
        """
        从完整的备份文件 (.zip 或 .bcb) 中恢复所有数据。
        【关键修改】增加了完整的恢复逻辑。
        """
        backup_path = os.path.join(backup_info['dir'], backup_info['file'])
        if not os.path.exists(backup_path):
            self.log_message.emit("备份文件不存在。")
            return False

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                with zipfile.ZipFile(backup_path, 'r') as zipf:
                    zipf.extractall(temp_dir)
                
                self.log_message.emit(f"正在从 {backup_info['type']} 备份 '{backup_info['file']}' 恢复...")
                
                # 1. 清空当前所有写作相关数据
                self.data_manager.clear_all_writing_data()
                self.log_message.emit("本地数据库已清空，准备写入备份数据...")

                # 2. 恢复书籍和章节
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
                            
                            # 添加书籍
                            restored_book_id = self.data_manager.add_book_from_backup(book_data)
                            self.log_message.emit(f"正在恢复书籍: {book_data.get('name')}")
                            
                            # 添加章节
                            if 'children' in book_data:
                                for volume in book_data['children']:
                                    for chapter_meta in volume['children']:
                                        content_filename = f"{chapter_meta['createTime']}.json"
                                        content_path = os.path.join(book_root_path, str(book_id), 'content', content_filename)
                                        if os.path.exists(content_path):
                                            with open(content_path, 'r', encoding='utf-8') as f:
                                                content_data = json.load(f)
                                            self.data_manager.add_chapter_from_backup(restored_book_id, chapter_meta, content_data)
                
                # 3. 恢复素材 (materials.json, settings.json 是旧版名称)
                materials_path = os.path.join(temp_dir, 'materials.json')
                if not os.path.exists(materials_path):
                     materials_path = os.path.join(temp_dir, 'settings.json') # 兼容旧版
                if os.path.exists(materials_path):
                    with open(materials_path, 'r', encoding='utf-8') as f:
                        materials_data = json.load(f)
                    for material in materials_data:
                        self.data_manager.add_material_from_backup(material)
                    self.log_message.emit(f"已恢复 {len(materials_data)} 条素材。")

                # 4. 恢复灵感条目
                insp_items_path = os.path.join(temp_dir, 'inspiration_items.json')
                if os.path.exists(insp_items_path):
                    with open(insp_items_path, 'r', encoding='utf-8') as f:
                        items_data = json.load(f)
                    for item in items_data:
                        self.data_manager.add_inspiration_item_from_backup(item)
                    self.log_message.emit(f"已恢复 {len(items_data)} 条灵感条目。")

                # 5. 恢复灵感碎片
                insp_fragments_path = os.path.join(temp_dir, 'inspiration_fragments.json')
                if os.path.exists(insp_fragments_path):
                    with open(insp_fragments_path, 'r', encoding='utf-8') as f:
                        fragments_data = json.load(f)
                    for fragment in fragments_data:
                        self.data_manager.add_inspiration_fragment_from_backup(fragment)
                    self.log_message.emit(f"已恢复 {len(fragments_data)} 条灵感碎片。")

                # 6. 恢复时间轴
                timelines_path = os.path.join(temp_dir, 'timelines.json')
                if os.path.exists(timelines_path):
                    with open(timelines_path, 'r', encoding='utf-8') as f:
                        timelines_data = json.load(f)
                    for timeline in timelines_data:
                        self.data_manager.add_timeline_from_backup(timeline)
                    self.log_message.emit(f"已恢复 {len(timelines_data)} 条时间轴。")

                # 7. 恢复时间轴事件
                events_path = os.path.join(temp_dir, 'timeline_events.json')
                if os.path.exists(events_path):
                    with open(events_path, 'r', encoding='utf-8') as f:
                        events_data = json.load(f)
                    for event in events_data:
                        self.data_manager.add_timeline_event_from_backup(event)
                    self.log_message.emit(f"已恢复 {len(events_data)} 个时间轴事件。")

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
            
    def delete_remote_backup(self, remote_filename):
        client = self._get_webdav_client()
        if not client:
            return False

        success, message = client.delete_file(remote_filename)
        self.log_message.emit(f"WebDAV: {message}")
        return success