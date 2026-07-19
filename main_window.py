# ShiCheng_Writer/main_window.py
import sys
import os
import shutil
import tempfile
import logging
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                               QListWidget, QListWidgetItem, QSplitter, QDockWidget,
                               QTreeView, QMessageBox, QInputDialog, QFileDialog,
                               QToolBar, QLabel, QMenu, QPushButton, QStatusBar, QToolButton,
                               QDialog, QDialogButtonBox, QApplication, QFormLayout, QLineEdit,
                               QTextEdit, QMenuBar, QTabWidget, QFrame, QComboBox, QCheckBox,
                               QTreeWidget, QTreeWidgetItem, QHeaderView, QStackedWidget, QSizePolicy)
from PySide6.QtGui import QStandardItemModel, QStandardItem, QAction, QKeySequence, QFont, QIcon
# 引入 QThread 和 Signal 用于异步备份
from PySide6.QtCore import Qt, QSize, QTimer, QThread, Signal, QSortFilterProxyModel

from modules.theme_manager import set_stylesheet
from modules.database import DataManager, calculate_hash
from modules.async_workers import LoadChapterWorker, SaveChapterWorker
from widgets.editor import Editor
# [新增] 导入分离出去的书籍详情页
from widgets.book_info_page import BookInfoPage
# [新增] 导入书籍树组件
from widgets.book_tree_widget import BookTreeWidget
# [新增] 导入章节树组件
from widgets.chapter_tree_widget import ChapterTreeWidget
from modules.material_system import MaterialPanel
from modules.inspiration import InspirationPanel
from modules.timeline_system import TimelinePanel
from modules.utils import resource_path
from modules.backup import BackupManager
# [移除] WebDAVSettingsDialog 导入
from widgets.dialogs import (BackupDialog, ManageGroupsDialog, 
                             EditBookDialog, RecycleBinDialog, SearchReplaceDialog)

from modules.ui_manager import UIManager

class MainWindow(QMainWindow):
    def __init__(self, data_manager, backup_manager, initial_theme):
        super().__init__()
        self.data_manager = data_manager
        self.backup_manager = backup_manager
        self.current_book_id = None
        self.current_chapter_id = None
        self.is_text_changed = False
        self.current_theme = initial_theme
        
        # 状态现由 UIManager 管理，保留部分引用以备需
        # UIManager 现持有面板状态逻辑。
        
        self.setWindowTitle("诗成写作 PC版")
        self.setGeometry(100, 100, 1400, 900)
        self.setWindowIcon(QIcon(resource_path('resources/icons/logo.png')))

        # 日志信号由主线程处理
        self.backup_manager.log_message.connect(self.show_status_message)
        # 连接备份完成信号，显示最终状态
        self.backup_manager.backup_finished.connect(self.on_backup_finished)

        # 异步工作线程
        self.load_chapter_worker = None
        self._load_workers = set()
        self.save_chapter_worker = None
        self._pending_save_requests = []

        # 定时器初始化（在UI设置之前，避免信号触发时定时器不存在）
        self.typing_timer = QTimer(self)
        self.typing_timer.setInterval(5000)
        self.typing_timer.timeout.connect(self.update_typing_speed)
        self.last_char_count = 0
        self.typing_speed = 0
        
        # 字数统计节流定时器
        self.wordcount_timer = QTimer(self)
        self.wordcount_timer.setSingleShot(True)
        self.wordcount_timer.setInterval(300)  # 300毫秒延迟
        self.wordcount_timer.timeout.connect(self._update_word_count_deferred)

        self.setup_ui()
        
        # 初始化 UI 管理器并设置动作/菜单
        self.ui_manager = UIManager(self)
        self.ui_manager.setup_ui_components()
        
        # [优化] 使用懒加载，提升软件启动速度感
        # 将耗时操作放入事件循环的下一次执行
        QTimer.singleShot(0, self.load_books)
        QTimer.singleShot(100, self.run_archive_backup)
        
        self.setup_snapshot_timer()
        self.setup_stage_point_timer()
        
        # 初始化时启动自动保存
        self.setup_autosave()

    # 兼容性存根属性，供外部模块访问
    # 这些属性代理到 UIManager，保持向后兼容性
    @property
    def left_panel_visible(self):
        """左侧面板可见性状态（兼容性属性）"""
        return self.ui_manager.left_panel_visible

    @left_panel_visible.setter
    def left_panel_visible(self, value):
        self.ui_manager.left_panel_visible = value

    @property
    def right_panel_visible(self):
        """右侧面板可见性状态（兼容性属性）"""
        return self.ui_manager.right_panel_visible

    @right_panel_visible.setter
    def right_panel_visible(self, value):
        self.ui_manager.right_panel_visible = value


    def _get_source_idx(self, index, proxy_model_attr):
        """辅助函数：映射代理索引到源索引"""
        if hasattr(self, proxy_model_attr):
            return getattr(self, proxy_model_attr).mapToSource(index)
        return index

    def _get_proxy_idx(self, source_index, proxy_model_attr):
        """辅助函数：映射源索引到代理索引"""
        if hasattr(self, proxy_model_attr):
            return getattr(self, proxy_model_attr).mapFromSource(source_index)
        return source_index
    
    def show_status_message(self, message):
        self.statusBar().showMessage(message, 5000)

    def setup_ui(self):
        main_widget = QWidget()
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0,0,0,0)
        main_layout.setSpacing(1)

        left_panel = self.create_left_panel()
        center_panel = self.create_center_panel()
        right_panel = self.create_right_panel()

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(left_panel)
        self.splitter.addWidget(center_panel)
        self.splitter.addWidget(right_panel)
        self.splitter.setSizes([280, 770, 350])

        main_layout.addWidget(self.splitter)
        self.setCentralWidget(main_widget)

        self.editor.textChanged.connect(self.on_text_changed)
        self.material_panel.materials_changed.connect(self.refresh_editor_highlighter)


        
    def update_recent_chapters_menu(self):
        # [重构] 已移动至 UIManager
        self.ui_manager.update_recent_chapters_menu()
    
    def create_left_panel(self):
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        # --- 1. 书籍树组件 (已重构) ---
        self.book_tree_widget = BookTreeWidget(self.data_manager, self)
        # 连接信号
        self.book_tree_widget.book_selected.connect(self.on_book_selected_from_widget)
        self.book_tree_widget.book_deleted.connect(self.on_book_deleted_from_widget)
        self.book_tree_widget.status_message_requested.connect(self.show_status_message)
        
        # --- 2. 章节树组件 (已重构) ---
        self.chapter_tree_widget = ChapterTreeWidget(self.data_manager, self)
        self.chapter_tree_widget.chapter_selected.connect(self.on_chapter_selected_from_widget)
        self.chapter_tree_widget.chapter_deleted.connect(self.on_chapter_deleted_from_widget)
        self.chapter_tree_widget.status_message_requested.connect(self.show_status_message)

        left_splitter = QSplitter(Qt.Vertical)
        left_splitter.addWidget(self.book_tree_widget)
        left_splitter.addWidget(self.chapter_tree_widget)
        left_splitter.setSizes([300, 600])

        left_layout.addWidget(left_splitter)
        return left_panel


    def create_center_panel(self):
        self.central_stack = QStackedWidget()
        
        # --- 1. 书籍信息展示页 (重构：使用独立的类) ---
        self.book_info_page = BookInfoPage()
        self.central_stack.addWidget(self.book_info_page)

        # --- 2. 编辑器页 ---
        editor_container = QWidget()
        editor_layout = QVBoxLayout(editor_container)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        
        self.editor = Editor()
        editor_layout.addWidget(self.editor)
        self.central_stack.addWidget(editor_container)
        
        return self.central_stack

    def create_right_panel(self):
        self.right_tabs = QTabWidget()
        self.right_tabs.setObjectName("RightPanelTabs")
        self.material_panel = MaterialPanel(self.data_manager, self)
        self.inspiration_panel = InspirationPanel(self.data_manager, self)
        self.timeline_panel = TimelinePanel(self.data_manager, self)
        self.right_tabs.addTab(self.material_panel, "素材仓库")
        self.right_tabs.addTab(self.inspiration_panel, "灵感中心")
        self.right_tabs.addTab(self.timeline_panel, "时间轴")
        return self.right_tabs

    def open_recent_chapter(self, chapter_id):
        # 获取章节详情并打开
        chapter_info = self.data_manager.get_chapter_info(chapter_id)
        if not chapter_info:
            QMessageBox.warning(self, "错误", "找不到该章节。")
            return
        
        # 切换到对应书籍
        book_id = chapter_info['book_id']
        # 如果当前书籍不是该章节所属书籍，切换到该书籍
        if self.current_book_id != book_id:
            # 找到书籍项并选中
            self.book_tree_widget.select_book(book_id) # 同步 UI
            
            # 手动触发更新，因为 select_book 若在模型中已选中但逻辑不同步时可能不会触发信号
            # 实际上 select_book 仅更新 UI 选择。我们需要触发加载逻辑。
            # 但是，on_book_selected_from_widget 处理逻辑。
            # 如果我调用 select_book，它会触发 clicked/selectionChanged 吗？
            # QTreeView 选择改变触发选择模型信号，但我的代码连接的是 `clicked`。
            # 所以程序化选择不会触发 `clicked`。
            # 因此必须手动调用逻辑。
            
            self.on_book_selected_from_widget(book_id, chapter_info['book_title'])
            if self.current_book_id != book_id:
                return
        
        # 找到章节项并选中
        self.find_and_select_chapter(chapter_id, force=True)
    
    def toggle_left_panel(self):
        self.ui_manager.toggle_left_panel()
    
    def toggle_right_panel(self):
        self.ui_manager.toggle_right_panel()
    
    def toggle_focus_mode(self):
        self.ui_manager.toggle_focus_mode()
    
    # [新增] 打开回收站
    def open_recycle_bin(self):
        # [重构] 已移动至 UIManager
        self.ui_manager.open_recycle_bin()
    
    def open_find_dialog(self):
        # [重构] 已移动至 UIManager
        self.ui_manager.open_find_dialog()

    def update_theme(self, new_theme):
        # [重构] 逻辑移至 UIManager，但为兼容性保留（若外部调用）
        self.ui_manager.update_theme_preference(new_theme)

    def toggle_theme(self):
        self.ui_manager.toggle_theme()
        
    def load_and_apply_font_size(self):
        # [重构] 已移动至 UIManager
        self.ui_manager.load_and_apply_font_size()

    def on_font_size_changed(self, index):
        # [重构] 已移动至 UIManager
        self.ui_manager.on_font_size_changed(index)

    def auto_indent_document(self):
        # [重构] 已移动至 UIManager
        self.ui_manager.auto_indent_document()

    def auto_unindent_document(self):
        # [重构] 已移动至 UIManager
        self.ui_manager.auto_unindent_document()

    def open_group_manager(self):
        # [重构] 已移动至 BookTreeWidget
        # 如果从菜单访问，可能仍需要此包装器
        self.book_tree_widget.open_group_manager()

    def load_books(self):
        # [重构] 已移动至 BookTreeWidget
        self.book_tree_widget.load_books()

    def on_book_selected_from_widget(self, book_id, book_title):
        """处理来自 BookTreeWidget 的书籍选择信号"""
        previous_book_id = self.current_book_id
        if self.is_text_changed and self.current_chapter_id:
            if not self.save_current_chapter(force_sync=True):
                self.book_tree_widget.current_book_id = previous_book_id
                self.book_tree_widget.select_book(previous_book_id)
                return

        self.current_book_id = book_id
        
        # [重构] 使用 ChapterTreeWidget 加载章节
        self.chapter_tree_widget.set_book_id(book_id)
        
        self.material_panel.set_book(book_id)
        self.inspiration_panel.refresh_all()
        self.timeline_panel.set_book(book_id)
        self.refresh_editor_highlighter()
        self.setWindowTitle(f"诗成写作 PC版 - {book_title}")
        self.current_book_chapter_label.setText(f"书籍: {book_title}")
        self.add_chapter_action.setEnabled(True)
        self.add_volume_action.setEnabled(True)
        # self.add_chapter_toolbar_action.setEnabled(True) # 工具栏现位于组件内部
        self.export_action.setEnabled(True)
        
        # 更新书籍信息页
        book_details = self.data_manager.get_book_details(book_id)
        if book_details:
            chapters = self.data_manager.get_chapters_for_book(book_id)
            self.book_info_page.update_info(
                book_details['title'],
                book_details.get('group', '未分组'),
                len(chapters),
                book_details.get('description', '')
            )
        
        # 切换到信息视图
        self.central_stack.setCurrentIndex(0)
        
        # 清除编辑器状态
        self.current_chapter_id = None
        self._clear_editor_content()
        self.word_count_label.setText("字数: -")
        self.typing_speed_label.setText("速度: -")

    def on_book_deleted_from_widget(self, book_id):
        """处理来自 BookTreeWidget 的书籍删除信号"""
        if self.current_book_id == book_id:
            self.current_book_id = None
            self.current_chapter_id = None
            self._clear_editor_content()
            
            # [重构] 清空章节树
            self.chapter_tree_widget.set_book_id(None)
            
            self.setWindowTitle("诗成写作 PC版")
            self.add_chapter_action.setEnabled(False)
            self.add_volume_action.setEnabled(False)
            # self.add_chapter_toolbar_action.setEnabled(False)
            self.export_action.setEnabled(False)
            
            self.book_info_page.reset()
            self.central_stack.setCurrentIndex(0)

    def on_chapter_selected_from_widget(self, chapter_id):
        """处理来自 ChapterTreeWidget 的章节选择信号"""
        if self.is_text_changed and self.current_chapter_id != chapter_id:
            reply = QMessageBox.question(self, "保存提示", "当前章节已修改，是否保存？", QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
            if reply == QMessageBox.Save: 
                if not self.save_current_chapter(force_sync=True): # 如果保存失败
                    # 将组件中的选择恢复为上一个章节
                    self.chapter_tree_widget.find_and_select_chapter(self.current_chapter_id, force_select=False)
                    return
            elif reply == QMessageBox.Cancel:
                # 恢复组件中的选择
                self.chapter_tree_widget.find_and_select_chapter(self.current_chapter_id, force_select=False)
                return
            else:
                # 用户明确丢弃旧章节的修改。
                self.is_text_changed = False
        
        # 切换到编辑器视图
        self.central_stack.setCurrentIndex(1)
        
        self.current_chapter_id = chapter_id
        
        # [异步加载]
        self.editor.setDisabled(True) # 加载时禁止输入
        self.statusBar().showMessage("正在加载章节...", 0)
        
        worker = LoadChapterWorker(self.data_manager, chapter_id)
        self.load_chapter_worker = worker
        self._load_workers.add(worker)
        worker.completed.connect(
            lambda content, count, cid=chapter_id: self.on_chapter_loaded(
                cid,
                content,
                count,
            )
        )
        worker.error.connect(
            lambda message, cid=chapter_id: self.on_chapter_load_failed(cid, message)
        )
        worker.finished.connect(lambda w=worker: self._cleanup_load_worker(w))
        worker.start()

    def _cleanup_load_worker(self, worker):
        self._load_workers.discard(worker)
        if self.load_chapter_worker is worker:
            self.load_chapter_worker = None

    def on_chapter_load_failed(self, chapter_id, message):
        if chapter_id != self.current_chapter_id:
            return
        self.current_chapter_id = None
        self._clear_editor_content()
        self.central_stack.setCurrentIndex(0)
        self.statusBar().showMessage(f"加载失败: {message}", 5000)

    def on_chapter_loaded(self, chapter_id, content, count):
        # 较早的加载任务可以自然结束，但不得覆盖用户后来选择的章节。
        if chapter_id != self.current_chapter_id:
            return
        self.editor.setDisabled(False)
        self.editor.blockSignals(True)
        self.editor.setPlainText(content)
        self.editor.blockSignals(False)
        self.is_text_changed = False
        self.update_word_count_label(count)
        self.typing_speed_label.setText("速度: 0 字/分")
        
        # 获取章节标题详情（仍为同步，但仅查询元数据，速度快）
        chapter_details = self.data_manager.get_chapter_details(chapter_id)
        chapter_title = chapter_details['title'] if chapter_details else "未知章节"
        
        self.statusBar().showMessage(f"已打开章节: {chapter_title}", 3000)
        self.last_char_count = count
        if not self.typing_timer.isActive(): self.typing_timer.start()
        
        # 刷新素材高亮
        self.refresh_editor_highlighter()

    def on_chapter_deleted_from_widget(self, chapter_id):
        if self.current_chapter_id == chapter_id:
            self.current_chapter_id = None
            self._clear_editor_content()
            # 章节删除后，如果没选中其他章节，可以切回书籍信息页
            self.central_stack.setCurrentIndex(0)

    # 存根方法，待移除或保留为 pass

    def find_and_select_chapter(self, chapter_id, force=False):
        self.chapter_tree_widget.find_and_select_chapter(chapter_id, force)

                    
    def _clear_editor_content(self):
        """清空编辑器而不制造一个没有章节归属的脏状态。"""
        self.wordcount_timer.stop()
        self.editor.blockSignals(True)
        try:
            self.editor.clear()
        finally:
            self.editor.blockSignals(False)
        self.editor.setDisabled(False)
        self.is_text_changed = False

    def save_current_chapter(self, force_sync=False):
        if self.current_chapter_id and self.is_text_changed:
            chapter_id = self.current_chapter_id
            content = self.editor.toPlainText()
            
            if force_sync:
                # 如果有正在进行的后台保存，等待其完成以防止数据覆盖
                if self.save_chapter_worker and self.save_chapter_worker.isRunning():
                    self.save_chapter_worker.wait()

                # 同步保存的是此刻的最新正文，不能在稍后重放同章节的旧队列项。
                self._pending_save_requests = [
                    request
                    for request in self._pending_save_requests
                    if request[0] != chapter_id
                ]
                    
                try:
                    if not self.data_manager.update_chapter_content(chapter_id, content):
                        raise RuntimeError("章节不存在，无法保存")
                    self.is_text_changed = False
                    self.update_word_count_label(len(content.strip()))
                    self.statusBar().showMessage(f"章节已保存！", 2000)
                    # 移除未保存标志
                    current_text = self.word_count_label.text()
                    if current_text.endswith('*'):
                        self.word_count_label.setText(current_text[:-1])
                    return True
                except Exception as e:
                    logging.getLogger(__name__).error(f"Failed to save chapter: {e}")
                    QMessageBox.critical(self, "保存失败", f"无法保存章节内容：\n{e}")
                    return False
            else:
                # 异步保存
                return self._trigger_async_save(
                    content,
                    is_manual=True,
                    chapter_id=chapter_id,
                )

        elif not self.is_text_changed and self.current_chapter_id:
            # 自动保存时静默处理，只有手动保存提示
            pass
        return bool(self.current_chapter_id)

    def _queue_save_request(self, chapter_id, content, is_manual):
        """按章节合并排队请求，同时保留章节身份。"""
        for index, request in enumerate(self._pending_save_requests):
            if request[0] == chapter_id:
                self._pending_save_requests[index] = (
                    chapter_id,
                    content,
                    request[2] or is_manual,
                )
                return
        self._pending_save_requests.append((chapter_id, content, is_manual))

    def _trigger_async_save(
        self,
        content,
        is_manual=False,
        chapter_id=None,
    ):
        """触发异步保存，如果有正在进行的保存则排队"""
        target_chapter_id = chapter_id if chapter_id is not None else self.current_chapter_id
        if target_chapter_id is None:
            return False

        if self.save_chapter_worker and self.save_chapter_worker.isRunning():
            self._queue_save_request(target_chapter_id, content, is_manual)
            if is_manual:
                self.statusBar().showMessage("正在等待后台保存完成...", 0)
            return True

        content_hash = calculate_hash(content)
        worker = SaveChapterWorker(self.data_manager, target_chapter_id, content)
        self.save_chapter_worker = worker
        worker.completed.connect(
            lambda success, cid=target_chapter_id, saved_hash=content_hash, manual=is_manual: self.on_save_finished(
                success,
                manual,
                cid,
                saved_hash,
            )
        )
        worker.error.connect(
            lambda message, cid=target_chapter_id: logging.getLogger(__name__).error(
                "Failed to save chapter %s: %s",
                cid,
                message,
            )
        )
        worker.finished.connect(lambda w=worker: self._on_save_worker_thread_finished(w))
        worker.start()
        
        if is_manual:
             self.statusBar().showMessage("正在保存...", 0)
        return True

    def on_save_finished(
        self,
        success,
        is_manual=False,
        chapter_id=None,
        saved_hash=None,
    ):
        if success:
             # 只有仍在显示同一章节且正文未再次变化时才清除脏标志。
             if chapter_id == self.current_chapter_id:
                 current_hash = calculate_hash(self.editor.toPlainText())
                 if current_hash == saved_hash:
                     self.is_text_changed = False
                     current_text = self.word_count_label.text()
                     if current_text.endswith('*'):
                         self.word_count_label.setText(current_text[:-1])
             
             if is_manual or self.is_text_changed: # 如果手动保存，或状态仍为脏（说明有新变动但此次保存成功），显示消息
                self.statusBar().showMessage("保存成功", 2000)
        else:
             self.statusBar().showMessage("保存失败", 3000)

    def _on_save_worker_thread_finished(self, worker):
        if self.save_chapter_worker is not worker:
            return
        self.save_chapter_worker = None
        if self._pending_save_requests:
            chapter_id, content, is_manual = self._pending_save_requests.pop(0)
            self._trigger_async_save(
                content,
                is_manual=is_manual,
                chapter_id=chapter_id,
            )
            
    def refresh_editor_highlighter(self):
        if self.current_book_id:
            materials_names = self.data_manager.get_all_materials_names(self.current_book_id)
            self.editor.update_highlighter(materials_names)
        else:
            self.editor.update_highlighter([])
            
    def _format_word_count_text(self, chapter_word_count, total_word_count=None):
        """格式化字数统计文本
        
        Args:
            chapter_word_count: 当前章节字数
            total_word_count: 书籍总字数（可选）
            
        Returns:
            格式化后的字数统计字符串
        """
        if total_word_count is not None and total_word_count > 0:
            percentage = (chapter_word_count / total_word_count) * 100
            return f"字数: {chapter_word_count}/{total_word_count} ({percentage:.1f}%)"
        return f"字数: {chapter_word_count}"

    def update_word_count_label(self, chapter_word_count=None):
        """更新字数统计标签"""
        if chapter_word_count is None:
            chapter_word_count = len(self.editor.toPlainText().strip())
        
        total_word_count = None
        if self.current_book_id:
            total_word_count = self.data_manager.get_book_word_count(self.current_book_id)
        
        self.word_count_label.setText(
            self._format_word_count_text(chapter_word_count, total_word_count)
        )

    def on_text_changed(self):
        if not self.editor.signalsBlocked():
            self.is_text_changed = True
            # 添加星号表示未保存（立即反馈）
            current_text = self.word_count_label.text()
            if not current_text.endswith('*'):
                self.word_count_label.setText(current_text + '*')
            # 延迟字数统计计算（节流）
            # 确保wordcount_timer存在
            if not hasattr(self, 'wordcount_timer'):
                self.wordcount_timer = QTimer(self)
                self.wordcount_timer.setSingleShot(True)
                self.wordcount_timer.setInterval(300)
                self.wordcount_timer.timeout.connect(self._update_word_count_deferred)
            self.wordcount_timer.start()

    def _update_word_count_deferred(self):
        """延迟更新字数统计（节流优化）"""
        if self.editor.signalsBlocked():
            return
        
        content = self.editor.toPlainText()
        count = len(content.strip())
        
        # 获取当前标签文本，检查是否包含星号
        current_text = self.word_count_label.text()
        has_asterisk = current_text.endswith('*')
        
        # 更新字数统计
        total_word_count = None
        if self.current_book_id:
            total_word_count = self.data_manager.get_book_word_count(self.current_book_id)
        
        new_text = self._format_word_count_text(count, total_word_count)
        
        # 如果原来有星号，保留星号
        if has_asterisk and not new_text.endswith('*'):
            new_text += '*'
        
        self.word_count_label.setText(new_text)

    def update_typing_speed(self):
        if not self.current_chapter_id:
            self.typing_speed = 0
            self.typing_timer.stop()
            self.typing_speed_label.setText("速度: 0 字/分")
            return

        current_char_count = len(self.editor.toPlainText().strip())
        chars_typed = current_char_count - self.last_char_count
        
        self.typing_speed = chars_typed * (60 / (self.typing_timer.interval() / 1000))
        self.typing_speed_label.setText(f"速度: {int(self.typing_speed)} 字/分")
        self.last_char_count = current_char_count

    def _flush_pending_saves_sync(self):
        """在关闭数据库前同步完成所有已经排队的章节保存。"""
        if self.save_chapter_worker and self.save_chapter_worker.isRunning():
            self.save_chapter_worker.wait()
        self.save_chapter_worker = None

        pending_requests = self._pending_save_requests
        self._pending_save_requests = []
        try:
            for chapter_id, content, _ in pending_requests:
                if not self.data_manager.update_chapter_content(chapter_id, content):
                    raise RuntimeError(f"章节 {chapter_id} 不存在")
            return True
        except Exception as error:
            logging.getLogger(__name__).exception("Failed to flush pending saves")
            QMessageBox.critical(self, "保存失败", f"无法完成排队保存：\n{error}")
            return False

    def closeEvent(self, event):
        if self.is_text_changed:
            reply = QMessageBox.question(self, "退出提示", "当前章节有未保存的修改，是否保存？", QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
            if reply == QMessageBox.Save:
                if not self.save_current_chapter(force_sync=True):
                    event.ignore()
                    return
            elif reply == QMessageBox.Cancel:
                event.ignore()
                return
            else:
                self._pending_save_requests = [
                    request
                    for request in self._pending_save_requests
                    if request[0] != self.current_chapter_id
                ]
                self.is_text_changed = False

        if not self._flush_pending_saves_sync():
            event.ignore()
            return

        # 加载线程使用独立连接；关闭 DataManager 前必须让它们自然结束。
        for worker in list(self._load_workers):
            worker.wait()

        # 关闭时的备份
        self.show_status_message("正在执行关闭前的阶段点备份...")
        self.backup_manager.wait_for_current_backup()
        if self.backup_manager.create_stage_point_backup():
            self.backup_manager.wait_for_current_backup()

        self.typing_timer.stop()
        self.data_manager.close()
        event.accept()

    def setup_snapshot_timer(self):
        self.snapshot_timer = QTimer(self)
        self.snapshot_timer.timeout.connect(self.run_snapshot_backup)
        self.update_timer_interval('snapshot_timer', 1 * 60 * 1000) 
        self.show_status_message("快照线(Snapshot Line)增量备份已启动。")

    def setup_stage_point_timer(self):
        self.stage_point_timer = QTimer(self)
        self.stage_point_timer.timeout.connect(self.run_stage_backup)
        self.update_timer_interval('stage_point_timer', 30 * 60 * 1000) 
        self.show_status_message("阶段点(Stage Point)定时备份已启动。")
        
    def setup_autosave(self):
        # 自动保存定时器，每60秒检查一次
        self.autosave_timer = QTimer(self)
        self.autosave_timer.setInterval(60000) 
        self.autosave_timer.timeout.connect(self.auto_save_check)
        self.autosave_timer.start()

    def auto_save_check(self):
        if self.current_chapter_id and self.is_text_changed:
            content = self.editor.toPlainText()
            self._trigger_async_save(content, is_manual=False)

    def update_timer_interval(self, timer_name, default_interval):
        # WebDAV 功能已移除，直接使用默认间隔
        timer = getattr(self, timer_name)
        timer.setInterval(default_interval)
        if not timer.isActive():
            timer.start()

    def run_snapshot_backup(self):
        # 快照备份轻量级，依然走同步，或者也可以改为异步
        self.backup_manager.create_snapshot_backup()
        self.update_timer_interval('snapshot_timer', 1 * 60 * 1000)
        
    def run_stage_backup(self, manual=False):
        if manual:
             self.show_status_message("正在后台执行手动备份...")
        
        # 直接调用 BackupManager，其内部已封装线程
        self.backup_manager.create_stage_point_backup()
        
        self.update_timer_interval('stage_point_timer', 30 * 60 * 1000)

    def run_archive_backup(self):
        self.show_status_message("正在后台检查并创建日终归档备份...")
        # 直接调用
        self.backup_manager.create_archive_backup()
    
    def on_backup_finished(self, success, message):
        self.show_status_message(message)

    def open_backup_manager(self):
        if self.is_text_changed and not self.save_current_chapter(force_sync=True):
            return
        dialog = BackupDialog(self.backup_manager, self)
        dialog.exec()
        if dialog.result() == QDialog.Accepted:
            self.load_books()
            self.current_book_id = None
            self.current_chapter_id = None
            self.chapter_tree_widget.set_book_id(None)
            self._clear_editor_content()
            self.book_info_page.reset()
            self.central_stack.setCurrentIndex(0)
            self.add_chapter_action.setEnabled(False)
            self.add_volume_action.setEnabled(False)
            self.export_action.setEnabled(False)
    
