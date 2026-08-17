# ShiCheng_Writer/modules/backup.py
"""
备份模块 - 实现三级备份策略（快照线、阶段点、日终归档）
"""
import os
import json
import zipfile
import tempfile
import logging
import sqlite3
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import QObject, Signal, QThread, Slot

from .database import DataManager

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

        backup_filepath = self._get_unique_backup_path(
            "backup_snapshot_",
            ".json",
        )
        backup_filename = os.path.basename(backup_filepath)

        try:
            self._write_json_atomically(backup_filepath, self.snapshot_data)

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
                        chapters = data_manager.get_chapters_for_book(
                            book['id'],
                            include_content=True,
                        )
                        total_word_count = 0
                        last_edit_chapter = "无章节"
                        volumes_structure: Dict[str, Dict[str, Any]] = {}

                        for chapter in chapters:
                            content_text = chapter.get('content') or ''

                            total_word_count += chapter['word_count']
                            last_edit_chapter = chapter['title']

                            chapter_content_data = {
                                "content": content_text,
                                "count": chapter['word_count'],
                                "hash": chapter.get('hash', '')
                            }
                            # 章节 ID 在数据库内稳定且唯一；时间戳可能为空或重复，
                            # 不能作为正文文件的身份标识。
                            content_file = f"chapter_{chapter['id']}.json"
                            chapter_filename = os.path.join(content_path, content_file)
                            with open(chapter_filename, 'w', encoding='utf-8') as f:
                                json.dump(chapter_content_data, f, ensure_ascii=False, indent=4)

                            vol_name = chapter['volume'] or "未分卷"
                            if vol_name not in volumes_structure:
                                volumes_structure[vol_name] = {"name": vol_name, "children": [], "createTime": None}
                            volumes_structure[vol_name]['children'].append({
                                "id": chapter['id'],
                                "name": chapter['title'],
                                "count": chapter['word_count'],
                                "createTime": chapter['createTime'],
                                "lastEditTime": chapter.get('lastEditTime'),
                                "volumeName": vol_name,
                                "contentFile": f"content/{content_file}",
                            })

                        book_data_for_json = dict(book)
                        book_data_for_json['name'] = book_data_for_json.pop('title')
                        book_data_for_json['summary'] = book_data_for_json.pop(
                            'description'
                        )
                        book_data_for_json['children'] = list(
                            volumes_structure.values()
                        )

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

                zip_filepath = self._get_unique_backup_path(prefix, '.zip')
                temporary_zip_filepath = f"{zip_filepath}.tmp"

                try:
                    with zipfile.ZipFile(
                        temporary_zip_filepath,
                        'w',
                        zipfile.ZIP_DEFLATED,
                    ) as zipf:
                        for root, _, files in os.walk(temp_dir):
                            for file in files:
                                file_path = os.path.join(root, file)
                                arcname = os.path.relpath(file_path, temp_dir)
                                zipf.write(file_path, arcname)
                    os.replace(temporary_zip_filepath, zip_filepath)
                except Exception:
                    if os.path.exists(temporary_zip_filepath):
                        os.remove(temporary_zip_filepath)
                    raise

                self.log.emit(f"本地打包成功：{os.path.basename(zip_filepath)}")
                return zip_filepath

        except Exception as e:
            self.log.emit(f"打包失败：{e}")
            logger.exception("创建 ZIP 备份失败")
            return None

    def _dump_table(self, fetch_func: Callable[[], List[Any]], filepath: str) -> None:
        """导出数据库表数据到 JSON 文件"""
        data = fetch_func()
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def _get_unique_backup_path(self, prefix: str, extension: str) -> str:
        """返回不会覆盖已有备份的文件路径。"""
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
        path = os.path.join(self.base_backup_dir, f"{prefix}{timestamp}{extension}")
        suffix = 1
        while os.path.exists(path):
            path = os.path.join(
                self.base_backup_dir,
                f"{prefix}{timestamp}_{suffix}{extension}",
            )
            suffix += 1
        return path

    @staticmethod
    def _write_json_atomically(path: str, data: Dict[str, Any]) -> None:
        """将 JSON 完整写入临时文件后再替换目标文件。"""
        temporary_path = f"{path}.tmp"
        try:
            with open(temporary_path, 'w', encoding='utf-8') as file:
                json.dump(data, file, ensure_ascii=False, indent=2)
            os.replace(temporary_path, path)
        except Exception:
            if os.path.exists(temporary_path):
                os.remove(temporary_path)
            raise


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
        self._pending_snapshot_check_time: Optional[datetime] = None

    def _start_worker(
        self,
        task_type: str,
        snapshot_data: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """启动备份工作线程"""
        if self._current_worker and self._current_worker.isRunning():
            self.log_message.emit("后台已有备份任务在运行，本次跳过。")
            return False

        # 清理之前的 worker（如果存在）
        if self._current_worker:
            self._disconnect_worker_signals(self._current_worker)
            self._current_worker = None

        worker = BackupWorker(task_type, self.base_backup_dir)
        worker.snapshot_data = snapshot_data
        worker.log.connect(self.log_message.emit)
        worker.finished.connect(self._on_worker_finished)
        worker.backup_created.connect(self._on_backup_created)
        self._current_worker = worker
        worker.start()
        return True

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

    @Slot(bool, str)
    def _on_worker_finished(
        self,
        success: bool,
        message: str,
        worker: Optional[BackupWorker] = None,
    ) -> None:
        """处理备份工作线程完成事件"""
        if worker is None:
            sender = self.sender()
            worker = sender if isinstance(sender, BackupWorker) else None
        if worker is None:
            return
        # A queued signal from a just-finished worker can arrive after another
        # task has begun.  Never let that stale result alter the new task's
        # snapshot cursor or status.
        if worker is not self._current_worker:
            return

        if (
            success
            and worker.task_type == 'snapshot'
            and self._pending_snapshot_check_time is not None
        ):
            self.last_snapshot_check_time = self._pending_snapshot_check_time
        if worker.task_type == 'snapshot':
            self._pending_snapshot_check_time = None

        # 无论成功失败，都将结果转发给 backup_finished 信号
        self.backup_finished.emit(success, message)

        if not success:
            self.log_message.emit(f"备份任务结束：{message}")

        self._cleanup_local_backups()

    @Slot(str, str, str)
    def _on_backup_created(
        self,
        backup_type: str,
        backup_filename: str,
        message: str,
        worker: Optional[BackupWorker] = None,
    ) -> None:
        """处理备份创建完成事件"""
        if worker is None:
            sender = self.sender()
            worker = sender if isinstance(sender, BackupWorker) else None
        if worker is None:
            return
        if worker is not self._current_worker:
            return
        self._latest_backup_filename = backup_filename
        self._latest_backup_type = backup_type
        self.log_message.emit(f"备份文件已创建：{backup_filename}")

    def create_stage_point_backup(self) -> bool:
        """创建阶段点备份"""
        self.log_message.emit("开始阶段点备份 (后台运行)...")
        return self._start_worker('stage')

    def create_archive_backup(self) -> bool:
        """创建日终归档备份（每天仅一次）"""
        today_str = datetime.now().strftime("%Y-%m-%d")
        if any(f.startswith(f"backup_archive_{today_str}") for f in os.listdir(self.base_backup_dir)):
            return False
        self.log_message.emit("开始日终归档备份 (后台运行)...")
        return self._start_worker('archive')

    def create_snapshot_backup(self) -> bool:
        """创建快照线增量备份"""
        snapshot_upper_bound = datetime.now()
        modified_chapters = self.data_manager.get_chapters_modified_since(
            self.last_snapshot_check_time,
            snapshot_upper_bound,
        )
        if not modified_chapters:
            # 查询使用了闭区间上界；即使此刻有其他备份在运行，之后的修改也会
            # 由下一窗口捕获，因此空窗口可以安全推进游标。
            self.last_snapshot_check_time = snapshot_upper_bound
            return True

        snapshot_data: Dict[str, Any] = {
            "backup_time": snapshot_upper_bound.isoformat(),
            "chapters": [],
        }
        for chapter in modified_chapters:
            snapshot_data["chapters"].append({
                "id": chapter['id'], "title": chapter['title'], "book_id": chapter['book_id'],
                "content": chapter['content'], "modified_time": chapter['lastEditTime']
            })

        self._pending_snapshot_check_time = snapshot_upper_bound
        if not self._start_worker('snapshot', snapshot_data):
            self._pending_snapshot_check_time = None
            return False
        return True

    def wait_for_current_backup(self, timeout_ms: Optional[int] = None) -> bool:
        """等待当前后台备份结束，供应用安全关闭时使用。"""
        worker = self._current_worker
        if not worker or not worker.isRunning():
            return True
        if timeout_ms is None:
            return worker.wait()
        return worker.wait(timeout_ms)

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
            if not isinstance(chapters_to_restore, list):
                raise ValueError("快照中的 chapters 字段格式无效")

            missing_ids = [
                chapter_data.get('id')
                for chapter_data in chapters_to_restore
                if not isinstance(chapter_data, dict)
                or chapter_data.get('id') is None
                or self.data_manager.get_chapter_details(chapter_data['id']) is None
            ]
            if missing_ids:
                raise ValueError(f"快照引用了不存在的章节 ID：{missing_ids}")

            for chapter_data in chapters_to_restore:
                if not self.data_manager.update_chapter_content(
                    chapter_data['id'],
                    chapter_data.get('content', ''),
                ):
                    raise ValueError(f"无法恢复章节 ID：{chapter_data['id']}")
            self.log_message.emit(f"成功从快照恢复 {len(chapters_to_restore)} 个章节。")
            return True
        except Exception as e:
            self.log_message.emit(f"从快照恢复失败：{e}")
            logger.exception("快照恢复失败")
            return False

    @staticmethod
    def _safe_extract_zip(zip_file: zipfile.ZipFile, destination: str) -> None:
        """只允许 ZIP 成员解压到指定临时目录内。"""
        destination_root = os.path.realpath(destination)
        for member in zip_file.infolist():
            target_path = os.path.realpath(os.path.join(destination_root, member.filename))
            try:
                is_inside = os.path.commonpath([destination_root, target_path]) == destination_root
            except ValueError:
                is_inside = False
            if not is_inside:
                raise ValueError(f"备份包含不安全路径：{member.filename}")
        zip_file.extractall(destination_root)

    @staticmethod
    def _load_json(path: str, expected_type: type) -> Any:
        if not os.path.isfile(path):
            raise ValueError(f"备份缺少必要文件：{os.path.basename(path)}")
        with open(path, 'r', encoding='utf-8') as file:
            data = json.load(file)
        if not isinstance(data, expected_type):
            raise ValueError(f"备份文件格式无效：{os.path.basename(path)}")
        return data

    def _build_restore_plan(self, temp_dir: str) -> Dict[str, Any]:
        """在触碰当前数据库前完整解析并校验恢复内容。"""
        book_root_path = os.path.join(temp_dir, 'book')
        book_list = self._load_json(
            os.path.join(book_root_path, 'bookList.json'),
            list,
        )
        plan: Dict[str, Any] = {"books": []}

        for book_item in book_list:
            if not isinstance(book_item, dict) or book_item.get('id') is None:
                raise ValueError("bookList.json 包含无效书籍记录")
            book_id = book_item['id']
            book_path = os.path.join(book_root_path, str(book_id))
            book_data = self._load_json(os.path.join(book_path, 'book.json'), dict)
            if book_data.get('id') is None:
                book_data['id'] = book_id

            chapter_entries = []
            volumes = book_data.get('children', [])
            if not isinstance(volumes, list):
                raise ValueError(f"书籍 {book_id} 的卷结构无效")
            for volume in volumes:
                if not isinstance(volume, dict) or not isinstance(volume.get('children', []), list):
                    raise ValueError(f"书籍 {book_id} 的章节结构无效")
                for chapter_meta in volume.get('children', []):
                    if not isinstance(chapter_meta, dict):
                        raise ValueError(f"书籍 {book_id} 包含无效章节记录")

                    relative_content_path = chapter_meta.get('contentFile')
                    if relative_content_path:
                        content_path = os.path.realpath(
                            os.path.join(book_path, relative_content_path)
                        )
                    else:
                        # 兼容旧版备份格式。
                        legacy_filename = f"{chapter_meta.get('createTime')}.json"
                        content_path = os.path.realpath(
                            os.path.join(book_path, 'content', legacy_filename)
                        )

                    book_path_root = os.path.realpath(book_path)
                    try:
                        is_inside_book = (
                            os.path.commonpath([book_path_root, content_path]) == book_path_root
                        )
                    except ValueError:
                        is_inside_book = False
                    if not is_inside_book:
                        raise ValueError(f"章节正文路径无效：{relative_content_path}")

                    content_data = self._load_json(content_path, dict)
                    chapter_entries.append((chapter_meta, content_data))

            plan["books"].append((book_data, chapter_entries))

        optional_tables = {
            "materials": ('materials.json', 'settings.json'),
            "inspiration_items": ('inspiration_items.json',),
            "inspiration_fragments": ('inspiration_fragments.json',),
            "timelines": ('timelines.json',),
            "timeline_events": ('timeline_events.json',),
        }
        for key, filenames in optional_tables.items():
            table_data: List[Any] = []
            for filename in filenames:
                path = os.path.join(temp_dir, filename)
                if os.path.isfile(path):
                    table_data = self._load_json(path, list)
                    break
            plan[key] = table_data

        return plan

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
        if not zipfile.is_zipfile(backup_path):
            self.log_message.emit("备份文件不是有效的 ZIP 文件。")
            return False

        safety_connection: Optional[sqlite3.Connection] = None
        safety_path: Optional[str] = None
        database_was_modified = False
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                with zipfile.ZipFile(backup_path, 'r') as zipf:
                    self._safe_extract_zip(zipf, temp_dir)

                # 所有引用文件和 JSON 必须在清空现有数据前验证完成。
                restore_plan = self._build_restore_plan(temp_dir)

                self.log_message.emit(
                    f"正在从 {backup_info.get('type', '完整')} 备份 "
                    f"'{backup_info['file']}' 恢复..."
                )

                # 使用 SQLite 在线备份 API 获取一致的安全副本；不要复制仍打开的
                # db/wal/shm 文件组合。
                safety_fd, safety_path = tempfile.mkstemp(
                    prefix='shicheng_restore_',
                    suffix='.sqlite',
                )
                os.close(safety_fd)
                safety_connection = sqlite3.connect(safety_path)
                with self.data_manager.lock:
                    self.data_manager.conn.backup(safety_connection)

                self.log_message.emit("正在清空本地数据库...")
                self.data_manager.clear_all_writing_data()
                database_was_modified = True
                self.log_message.emit("本地数据库已清空，准备写入备份数据...")

                for book_data, chapter_entries in restore_plan["books"]:
                    restored_book_id = self.data_manager.add_book_from_backup(book_data)
                    self.log_message.emit(f"正在恢复书籍：{book_data.get('name')}")
                    for chapter_meta, content_data in chapter_entries:
                        self.data_manager.add_chapter_from_backup(
                            restored_book_id,
                            chapter_meta,
                            content_data,
                        )

                for material in restore_plan["materials"]:
                    self.data_manager.add_material_from_backup(material)
                for item in restore_plan["inspiration_items"]:
                    self.data_manager.add_inspiration_item_from_backup(item)
                for fragment in restore_plan["inspiration_fragments"]:
                    self.data_manager.add_inspiration_fragment_from_backup(fragment)
                for timeline in restore_plan["timelines"]:
                    self.data_manager.add_timeline_from_backup(timeline)
                for event in restore_plan["timeline_events"]:
                    self.data_manager.add_timeline_event_from_backup(event)

            self.log_message.emit("数据库恢复成功。请重启应用以刷新界面。")
            return True

        except Exception as e:
            self.log_message.emit(f"恢复失败：{e}")
            if database_was_modified:
                logger.exception("备份恢复失败，正在回滚")
            else:
                logger.warning("备份校验失败：%s", e)
            if database_was_modified and safety_connection is not None:
                try:
                    with self.data_manager.lock:
                        self.data_manager.conn.rollback()
                        safety_connection.backup(self.data_manager.conn)
                    self.log_message.emit("数据库已恢复至操作前状态。")
                except Exception as restore_error:
                    self.log_message.emit(f"安全回滚失败：{restore_error}")
                    logger.exception("恢复失败后的安全回滚失败")
            return False
        finally:
            if safety_connection is not None:
                safety_connection.close()
            if safety_path and os.path.exists(safety_path):
                try:
                    os.remove(safety_path)
                except OSError:
                    logger.warning("无法删除恢复安全副本：%s", safety_path)

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
