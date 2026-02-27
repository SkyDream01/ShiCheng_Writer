# ShiCheng_Writer/modules/backup.py
"""
备份模块 - 实现三级备份策略（快照线、阶段点、日终归档）
"""
import os
import shutil
import json
import zipfile
import tempfile
import uuid
import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import QObject, Signal, QThread

from .database import DataManager, DB_FILE, DBRow

logger = logging.getLogger(__name__)

# 类型别名
BackupInfo = Dict[str, Any]


class BackupWorker(QThread):
    """
    后台备份工作线程

    Signals:
        finished: 备份完成信号 (success: bool, message: str)
        log: 日志输出信号 (message: str)
        backup_created: 备份创建成功信号 (backup_type: str, backup_filename: str, message: str)
    """
    finished = Signal(bool, str)  # success, message
    log = Signal(str)
    backup_created = Signal(str, str, str)  # backup_type, backup_filename, message

    def __init__(self, task_type: str, base_backup_dir: str, parent: Optional[QObject] = None) -> None:
        """
        初始化备份工作线程

        Args:
            task_type: 备份类型 ('stage', 'archive', 'snapshot')
            base_backup_dir: 备份目录基础路径
            parent: 父对象
        """
        super().__init__(parent)
        self.task_type = task_type
        self.base_backup_dir = base_backup_dir
        self.snapshot_data: Optional[Dict[str, Any]] = None  # 仅用于 snapshot

    def run(self) -> None:
        """线程入口，执行备份任务"""
        # 在线程内部实例化 DataManager，确保数据库连接线程安全
        local_data_manager = DataManager()

        try:
            if self.task_type == 'snapshot':
                self._run_snapshot(local_data_manager)
            elif self.task_type in ['stage', 'archive']:
                self._run_full_backup(local_data_manager)
        except Exception as e:
            logger.exception("备份过程中发生错误")
            self.finished.emit(False, str(e))
        finally:
            local_data_manager.close()

    def _run_snapshot(self, data_manager: DataManager) -> None:
        """执行快照备份"""
        if not self.snapshot_data:
            self.finished.emit(True, "无数据更新")
            return

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_filename = f"backup_snapshot_{timestamp}.json"
        backup_filepath = os.path.join(self.base_backup_dir, backup_filename)

        try:
            with open(backup_filepath, 'w', encoding='utf-8') as f:
                json.dump(self.snapshot_data, f, ensure_ascii=False, indent=2)

            self.log.emit(f"快照线备份本地成功：{backup_filename}")
            self.backup_created.emit('snapshot', backup_filename, "快照备份完成")
            self.finished.emit(True, "快照备份完成")
        except Exception as e:
            self.finished.emit(False, f"快照备份失败：{e}")

    def _run_full_backup(self, data_manager: DataManager) -> None:
        """执行完整备份（阶段点或日终归档）"""
        prefix = f"backup_{self.task_type}_"
        zip_filepath = self._create_zip(data_manager, prefix)

        if zip_filepath:
            backup_filename = os.path.basename(zip_filepath)
            self.backup_created.emit(self.task_type, backup_filename, f"{self.task_type} 备份完成")
            self.finished.emit(True, f"{self.task_type} 备份完成")
        else:
            self.finished.emit(False, "本地 ZIP 创建失败")

    def _create_zip(self, data_manager: DataManager, prefix: str) -> Optional[str]:
        """创建 ZIP 备份文件"""
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                book_root_path = os.path.join(temp_dir, 'book')
                os.makedirs(book_root_path)

                # 获取所有书籍
                all_books = data_manager.get_all_books()
                book_list_data: List[Dict[str, Any]] = []

                if all_books:
                    for book in all_books:
                        book_folder_name = str(book['id'])
                        book_path = os.path.join(book_root_path, book_folder_name)
                        content_path = os.path.join(book_path, 'content')
                        os.makedirs(content_path)

                        # 获取章节列表
                        chapters = data_manager.get_chapters_for_book(book['id'])
                        total_word_count = 0
                        last_edit_chapter = "无章节"
                        volumes_structure: Dict[str, Dict[str, Any]] = {}

                        for chapter in chapters:
                            # 单独获取章节内容
                            content_text, _ = data_manager.get_chapter_content(chapter['id'])

                            total_word_count += chapter['word_count']
                            last_edit_chapter = chapter['title']

                            chapter_content_data = {
                                "content": content_text,
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

                        book_data_for_json = data_manager.get_book_details(book['id'])
                        if book_data_for_json:
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

                self.log.emit(f"本地打包成功：{zip_filename}")
                return zip_filepath

        except Exception as e:
            self.log.emit(f"打包失败：{e}")
            logger.exception("创建 ZIP 备份失败")
            return None

    def _dump_table(self, fetch_func: Callable[[], List[Any]], filepath: str) -> None:
        """导出数据库表数据到 JSON 文件"""
        data = fetch_func()
        if data:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)


class BackupManager(QObject):
    """
    备份管理器，作为前端和后台线程的桥梁

    Signals:
        log_message: 日志消息信号
        backup_finished: 备份完成信号
    """
    log_message = Signal(str)
    backup_finished = Signal(bool, str)

    def __init__(self, data_manager: DataManager, base_backup_dir: str = "backups") -> None:
        """
        初始化备份管理器

        Args:
            data_manager: 数据管理器实例
            base_backup_dir: 备份目录基础路径
        """
        super().__init__()
        self.data_manager = data_manager
        self.base_backup_dir = base_backup_dir
        if not os.path.exists(self.base_backup_dir):
            os.makedirs(self.base_backup_dir)
        self.last_snapshot_check_time = datetime.now()

        self._current_worker: Optional[BackupWorker] = None
        self._latest_backup_filename: Optional[str] = None
        self._latest_backup_type: Optional[str] = None

    def _start_worker(self, task_type: str, snapshot_data: Optional[Dict[str, Any]] = None) -> None:
        """启动备份工作线程"""
        if self._current_worker and self._current_worker.isRunning():
            self.log_message.emit("后台已有备份任务在运行，本次跳过。")
            return

        # 清理之前的 worker（如果存在）
        if self._current_worker:
            self._disconnect_worker_signals(self._current_worker)
            self._current_worker = None

        self._current_worker = BackupWorker(task_type, self.base_backup_dir)
        self._current_worker.snapshot_data = snapshot_data
        self._current_worker.log.connect(self.log_message.emit)
        self._current_worker.finished.connect(self._on_worker_finished)
        self._current_worker.backup_created.connect(self._on_backup_created)
        self._current_worker.start()

    def _disconnect_worker_signals(self, worker: BackupWorker) -> None:
        """安全地断开 worker 的信号连接"""
        try:
            worker.log.disconnect()
        except (RuntimeError, TypeError):
            pass
        try:
            worker.finished.disconnect()
        except (RuntimeError, TypeError):
            pass
        try:
            worker.backup_created.disconnect()
        except (RuntimeError, TypeError):
            pass

    def _on_worker_finished(self, success: bool, message: str) -> None:
        """处理备份工作线程完成事件"""
        # 无论成功失败，都将结果转发给 backup_finished 信号
        self.backup_finished.emit(success, message)

        if not success:
            self.log_message.emit(f"备份任务结束：{message}")

        self._cleanup_local_backups()

    def _on_backup_created(self, backup_type: str, backup_filename: str, message: str) -> None:
        """处理备份创建完成事件"""
        self._latest_backup_filename = backup_filename
        self._latest_backup_type = backup_type
        self.log_message.emit(f"备份文件已创建：{backup_filename}")

    def create_stage_point_backup(self) -> None:
        """创建阶段点备份"""
        self.log_message.emit("开始阶段点备份 (后台运行)...")
        self._start_worker('stage')

    def create_archive_backup(self) -> None:
        """创建日终归档备份（每天仅一次）"""
        today_str = datetime.now().strftime("%Y-%m-%d")
        if any(f.startswith(f"backup_archive_{today_str}") for f in os.listdir(self.base_backup_dir)):
            return
        self.log_message.emit("开始日终归档备份 (后台运行)...")
        self._start_worker('archive')

    def create_snapshot_backup(self) -> None:
        """创建快照线增量备份"""
        modified_chapters = self.data_manager.get_chapters_modified_since(self.last_snapshot_check_time)
        if not modified_chapters:
            return

        snapshot_data: Dict[str, Any] = {"backup_time": datetime.now().isoformat(), "chapters": []}
        for chapter in modified_chapters:
            snapshot_data["chapters"].append({
                "id": chapter['id'], "title": chapter['title'], "book_id": chapter['book_id'],
                "content": chapter['content'], "modified_time": chapter['lastEditTime']
            })

        self.last_snapshot_check_time = datetime.now()
        self._start_worker('snapshot', snapshot_data)

    def _cleanup_local_backups(self) -> None:
        """清理过期的本地备份文件"""
        for prefix, limit in [("backup_snapshot_", 15), ("backup_stage_", 5), ("backup_archive_", 15)]:
            try:
                files = [f for f in os.listdir(self.base_backup_dir) if f.startswith(prefix)]
                files.sort(key=lambda name: os.path.getmtime(os.path.join(self.base_backup_dir, name)), reverse=True)
                if len(files) > limit:
                    for f in files[limit:]:
                        os.remove(os.path.join(self.base_backup_dir, f))
            except Exception as e:
                self.log_message.emit(f"清理 {prefix} 备份失败：{e}")

    def list_backups(self) -> List[BackupInfo]:
        """列出所有备份文件"""
        backups: List[BackupInfo] = []
        try:
            files = os.listdir(self.base_backup_dir)
            for file in files:
                backup_info: BackupInfo = {"file": file, "dir": self.base_backup_dir, "source": "local"}
                if file.startswith('backup_stage_'):
                    backup_info["type"] = "Stage"
                elif file.startswith('backup_archive_'):
                    backup_info["type"] = "Archive"
                elif file.lower().endswith('.bcb'):
                    backup_info["type"] = "BCB 备份"
                elif file.startswith('backup_snapshot_'):
                    backup_info["type"] = "Snapshot"
                else:
                    continue
                backups.append(backup_info)
        except OSError:
            pass
        backups.sort(key=lambda x: x['file'], reverse=True)
        return backups

    def restore_from_snapshot(self, backup_info: BackupInfo) -> bool:
        """从快照备份恢复数据"""
        filename = os.path.basename(backup_info['file'])
        backup_path = os.path.join(backup_info['dir'], filename)
        if not os.path.exists(backup_path):
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
            self.log_message.emit(f"从快照恢复失败：{e}")
            logger.exception("快照恢复失败")
            return False

    def restore_from_backup(self, backup_info: BackupInfo) -> bool:
        """
        从完整备份恢复数据

        Returns:
            恢复是否成功
        """
        filename = os.path.basename(backup_info['file'])
        backup_path = os.path.join(backup_info['dir'], filename)
        if not os.path.exists(backup_path):
            self.log_message.emit("备份文件不存在。")
            return False

        # 使用时间戳+UUID 生成唯一的恢复 ID，避免文件名冲突
        restore_id = f"{int(datetime.now().timestamp() * 1000)}_{uuid.uuid4().hex[:8]}"
        backed_up_files: List[Tuple[str, str]] = []

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                with zipfile.ZipFile(backup_path, 'r') as zipf:
                    zipf.extractall(temp_dir)

                self.log_message.emit(f"正在从 {backup_info['type']} 备份 '{backup_info['file']}' 恢复...")

                # 1. 备份当前数据库文件 (使用唯一文件名)
                db_files_to_backup = [DB_FILE, DB_FILE + '-shm', DB_FILE + '-wal']
                for db_file in db_files_to_backup:
                    if os.path.exists(db_file):
                        backup_file = f"{db_file}.restore_backup_{restore_id}"
                        shutil.copy2(db_file, backup_file)
                        backed_up_files.append((db_file, backup_file))
                        self.log_message.emit(f"已备份数据库文件：{os.path.basename(db_file)} -> {os.path.basename(backup_file)}")

                # 2. 清空数据库
                self.log_message.emit("正在清空本地数据库...")
                self.data_manager.clear_all_writing_data()
                self.log_message.emit("本地数据库已清空，准备写入备份数据...")

                # 3. 恢复数据
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
                            self.log_message.emit(f"正在恢复书籍：{book_data.get('name')}")

                            if 'children' in book_data:
                                for volume in book_data['children']:
                                    for chapter_meta in volume['children']:
                                        content_filename = f"{chapter_meta['createTime']}.json"
                                        content_path = os.path.join(book_root_path, str(book_id), 'content', content_filename)
                                        if os.path.exists(content_path):
                                            with open(content_path, 'r', encoding='utf-8') as f:
                                                content_data = json.load(f)
                                            self.data_manager.add_chapter_from_backup(restored_book_id, chapter_meta, content_data)

                # 恢复其他模块数据
                materials_path = os.path.join(temp_dir, 'materials.json')
                if not os.path.exists(materials_path):
                    materials_path = os.path.join(temp_dir, 'settings.json')
                if os.path.exists(materials_path):
                    with open(materials_path, 'r', encoding='utf-8') as f:
                        for m in json.load(f):
                            self.data_manager.add_material_from_backup(m)

                insp_items_path = os.path.join(temp_dir, 'inspiration_items.json')
                if os.path.exists(insp_items_path):
                    with open(insp_items_path, 'r', encoding='utf-8') as f:
                        for i in json.load(f):
                            self.data_manager.add_inspiration_item_from_backup(i)

                insp_fragments_path = os.path.join(temp_dir, 'inspiration_fragments.json')
                if os.path.exists(insp_fragments_path):
                    with open(insp_fragments_path, 'r', encoding='utf-8') as f:
                        for frag in json.load(f):
                            self.data_manager.add_inspiration_fragment_from_backup(frag)

                timelines_path = os.path.join(temp_dir, 'timelines.json')
                if os.path.exists(timelines_path):
                    with open(timelines_path, 'r', encoding='utf-8') as f:
                        for t in json.load(f):
                            self.data_manager.add_timeline_from_backup(t)

                events_path = os.path.join(temp_dir, 'timeline_events.json')
                if os.path.exists(events_path):
                    with open(events_path, 'r', encoding='utf-8') as f:
                        for e in json.load(f):
                            self.data_manager.add_timeline_event_from_backup(e)

            self.log_message.emit("数据库恢复成功。请重启应用以刷新界面。")

            # 4. 恢复成功，清理临时备份文件
            for _, backup_file in backed_up_files:
                try:
                    if os.path.exists(backup_file):
                        os.remove(backup_file)
                except OSError:
                    pass

            return True

        except Exception as e:
            # 5. 恢复失败，执行回滚
            self.log_message.emit(f"恢复失败：{e}")
            logger.exception("备份恢复失败")

            if backed_up_files:
                self.log_message.emit("正在恢复备份的数据库文件...")
                restore_success = True
                for original_file, backup_file in backed_up_files:
                    try:
                        if os.path.exists(backup_file):
                            shutil.copy2(backup_file, original_file)
                            self.log_message.emit(f"已恢复数据库文件：{os.path.basename(original_file)}")
                    except Exception as restore_error:
                        self.log_message.emit(f"恢复数据库文件 {os.path.basename(original_file)} 失败：{restore_error}")
                        restore_success = False

                if restore_success:
                    self.log_message.emit("数据库文件已恢复至恢复前的状态。")
                else:
                    self.log_message.emit("警告：部分数据库文件恢复失败，数据可能不一致。")
            else:
                self.log_message.emit("警告：没有可用的数据库备份文件，数据可能已丢失。")

            return False

    def delete_backup(self, backup_info: BackupInfo) -> bool:
        """删除备份文件"""
        filename = os.path.basename(backup_info['file'])
        backup_path = os.path.join(backup_info['dir'], filename)
        try:
            os.remove(backup_path)
            self.log_message.emit(f"已删除备份：{backup_info['file']}")
            return True
        except Exception as e:
            self.log_message.emit(f"删除失败：{e}")
            logger.exception("删除备份失败")
            return False
