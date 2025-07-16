# ShiCheng_Writer/main_window.py
import sys
import os
import shutil
import tempfile
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                               QListWidget, QListWidgetItem, QSplitter, QDockWidget,
                               QTreeView, QMessageBox, QInputDialog, QFileDialog,
                               QToolBar, QLabel, QMenu, QPushButton, QStatusBar, QToolButton,
                               QDialog, QDialogButtonBox, QApplication, QFormLayout, QLineEdit,
                               QTextEdit, QMenuBar, QTabWidget, QFrame, QComboBox, QCheckBox,
                               QTreeWidget, QTreeWidgetItem, QHeaderView)
from PySide6.QtGui import QStandardItemModel, QStandardItem, QAction, QKeySequence, QFont, QIcon
from PySide6.QtCore import Qt, QSize, QTimer

from modules.theme_manager import set_stylesheet
from modules.database import DataManager
from widgets.editor import Editor
from modules.material_system import MaterialPanel
from modules.inspiration import InspirationPanel
from modules.timeline_system import TimelinePanel
from modules.utils import resource_path
from modules.backup import BackupManager

class WebDAVSettingsDialog(QDialog):
    """WebDAV 设置对话框"""
    def __init__(self, data_manager, parent=None):
        super().__init__(parent)
        self.data_manager = data_manager
        # [修改] 直接从父窗口获取 BackupManager 实例
        self.backup_manager = parent.backup_manager if parent else BackupManager(data_manager)
        
        self.setWindowTitle("WebDAV 设置")
        self.setMinimumSize(400, 300)

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        self.enabled_check = QCheckBox("启用 WebDAV 同步")
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://dav.example.com/webdav/")
        self.user_edit = QLineEdit()
        self.pass_edit = QLineEdit()
        self.pass_edit.setEchoMode(QLineEdit.Password)
        self.root_dir_edit = QLineEdit()
        self.root_dir_edit.setPlaceholderText("/shicheng/")
        self.sync_freq_combo = QComboBox()
        self.sync_freq_combo.addItems(["实时", "每小时", "仅启动时"])
        
        form_layout.addRow(self.enabled_check)
        form_layout.addRow("WebDAV 地址:", self.url_edit)
        form_layout.addRow("用户名:", self.user_edit)
        form_layout.addRow("密码/Token:", self.pass_edit)
        form_layout.addRow("云端根目录:", self.root_dir_edit)
        form_layout.addRow("同步频率:", self.sync_freq_combo)

        layout.addLayout(form_layout)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel, self)
        self.test_button = QPushButton("测试连接")
        buttons.addButton(self.test_button, QDialogButtonBox.ActionRole)

        self.test_button.clicked.connect(self.test_webdav_connection)
        buttons.accepted.connect(self.save_settings)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.load_settings()

    def load_settings(self):
        settings = self.data_manager.get_webdav_settings()
        self.enabled_check.setChecked(settings.get('webdav_enabled', False))
        self.url_edit.setText(settings.get('webdav_url', ''))
        self.user_edit.setText(settings.get('webdav_user', ''))
        self.pass_edit.setText(settings.get('webdav_pass', ''))
        self.root_dir_edit.setText(settings.get('webdav_root', '/shicheng/'))
        self.sync_freq_combo.setCurrentText(settings.get('webdav_sync_freq', '实时'))

    def save_settings(self):
        settings = {
            'webdav_enabled': self.enabled_check.isChecked(),
            'webdav_url': self.url_edit.text(),
            'webdav_user': self.user_edit.text(),
            'webdav_pass': self.pass_edit.text(),
            'webdav_root': self.root_dir_edit.text(),
            'webdav_sync_freq': self.sync_freq_combo.currentText()
        }
        self.data_manager.save_webdav_settings(settings)
        QMessageBox.information(self, "成功", "WebDAV 设置已保存。")
        self.accept()
        
    def test_webdav_connection(self):
        """测试 WebDAV 连接"""
        # [修改] 将界面上的当前设置临时保存，以便 backup_manager 可以获取到最新信息
        current_settings = {
            'webdav_enabled': self.enabled_check.isChecked(),
            'webdav_url': self.url_edit.text(),
            'webdav_user': self.user_edit.text(),
            'webdav_pass': self.pass_edit.text(),
            'webdav_root': self.root_dir_edit.text(),
            'webdav_sync_freq': self.sync_freq_combo.currentText()
        }
        self.data_manager.save_webdav_settings(current_settings)
        
        self.test_button.setEnabled(False)
        self.test_button.setText("测试中...")
        QApplication.processEvents() # 刷新界面

        # [修改] 直接调用 backup_manager 的测试方法
        success, message = self.backup_manager.test_webdav_connection()

        if success:
            QMessageBox.information(self, "连接成功", message)
        else:
            QMessageBox.critical(self, "连接失败", message)
            
        self.test_button.setEnabled(True)
        self.test_button.setText("测试连接")

class BackupDialog(QDialog):
    def __init__(self, backup_manager, parent=None):
        super().__init__(parent)
        self.backup_manager = backup_manager
        self.setWindowTitle("备份与恢复")
        self.setMinimumSize(550, 450)
        
        layout = QVBoxLayout(self)
        self.backup_tree = QTreeWidget()
        self.backup_tree.setHeaderLabels(["备份文件", "类型", "来源"])
        self.backup_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)

        button_layout = QHBoxLayout()
        restore_button = QPushButton("恢复选中项")
        restore_button.clicked.connect(self.restore_backup)
        delete_button = QPushButton("删除选中项")
        delete_button.clicked.connect(self.delete_backup)
        refresh_button = QPushButton("刷新列表")
        refresh_button.clicked.connect(self.load_backups)
        
        button_layout.addWidget(restore_button)
        button_layout.addWidget(delete_button)
        button_layout.addStretch()
        button_layout.addWidget(refresh_button)

        layout.addWidget(QLabel("选择一个备份进行恢复或删除:"))
        layout.addWidget(self.backup_tree)
        layout.addLayout(button_layout)
        
        self.load_backups()

    def load_backups(self):
        self.backup_tree.clear()
        
        # Local Backups
        local_backups = self.backup_manager.list_backups()
        if local_backups:
            local_root = QTreeWidgetItem(self.backup_tree, ["本地备份"])
            for backup in local_backups:
                backup['source'] = 'local'
                child = QTreeWidgetItem(local_root, [backup['file'], backup['type'], "本地"])
                child.setData(0, Qt.UserRole, backup)
            local_root.setExpanded(True)

        # Cloud Backups
        remote_backups = self.backup_manager.list_remote_backups()
        if remote_backups:
            cloud_root = QTreeWidgetItem(self.backup_tree, ["云端备份 (WebDAV)"])
            for backup in remote_backups:
                child = QTreeWidgetItem(cloud_root, [backup['file'], backup['type'], "云端"])
                child.setData(0, Qt.UserRole, backup)
            cloud_root.setExpanded(True)
        
        if not local_backups and not remote_backups:
            self.backup_tree.addTopLevelItem(QTreeWidgetItem(["暂无任何备份文件"]))

    def restore_backup(self):
        selected_item = self.backup_tree.currentItem()
        if not selected_item or not selected_item.data(0, Qt.UserRole):
            QMessageBox.warning(self, "提示", "请先选择一个具体的备份文件。")
            return
            
        backup_info = selected_item.data(0, Qt.UserRole)
        is_cloud = backup_info.get("source") == "cloud"

        if is_cloud:
            reply = QMessageBox.question(self, "确认恢复",
                                         f"您确定要从【云端】恢复备份\n'{backup_info['file']}'\n吗？\n"
                                         "这将首先从云端下载文件，然后覆盖本地数据。",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
            
            with tempfile.TemporaryDirectory() as temp_dir:
                # [修改] remote_path 现在是完整路径，需要取文件名
                remote_filename = os.path.basename(backup_info['path'])
                downloaded_filepath = self.backup_manager.download_backup(remote_filename, temp_dir)
                if not downloaded_filepath:
                    QMessageBox.critical(self, "下载失败", "无法从云端下载备份文件，请检查网络和WebDAV设置。")
                    return
                
                temp_backup_info = {
                    "file": os.path.basename(downloaded_filepath),
                    "dir": temp_dir,
                    "type": backup_info['type']
                }
                self.proceed_with_restore(temp_backup_info)
        else:
            self.proceed_with_restore(backup_info)

    def proceed_with_restore(self, backup_info):
        backup_type_lower = backup_info.get('type', '').lower()
        if 'snapshot' in backup_type_lower or '快照线' in backup_type_lower:
            if self.backup_manager.restore_from_snapshot(backup_info):
                QMessageBox.information(self, "成功", "数据已从快照恢复。\n请检查相关章节内容。")
                if self.parent().current_book_id:
                    self.parent().load_chapters_for_book(self.parent().current_book_id)
                self.accept()
            else:
                QMessageBox.critical(self, "失败", "恢复过程中发生错误。")
        else:
            reply = QMessageBox.warning(self, "确认恢复",
                                         f"您确定要从 {backup_info['type']} 备份\n'{backup_info['file']}'\n恢复吗？\n"
                                         "【警告】此操作将完全覆盖当前所有数据！\n"
                                         "恢复后必须重启应用才能看到更改。\n"
                                         "操作无法撤销，请谨慎操作！",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                if self.backup_manager.restore_from_backup(backup_info):
                    QMessageBox.information(self, "成功", "数据已从备份恢复。\n请立即重启应用程序以应用更改。")
                    self.parent().load_books()
                    self.accept()
                else:
                    QMessageBox.critical(self, "失败", "恢复过程中发生错误，请查看状态栏或控制台输出。")

    def delete_backup(self):
        selected_item = self.backup_tree.currentItem()
        if not selected_item or not selected_item.data(0, Qt.UserRole):
            QMessageBox.warning(self, "提示", "请先选择一个具体的备份文件。")
            return

        backup_info = selected_item.data(0, Qt.UserRole)
        is_cloud = backup_info.get("source") == "cloud"
        source_text = "【云端】" if is_cloud else "【本地】"

        reply = QMessageBox.question(self, "确认删除",
                                       f"确定要永久删除此 {source_text} 备份吗？\n'{backup_info['file']}'",
                                       QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            success = False
            if is_cloud:
                # [修改] 传递文件名而不是完整路径
                remote_filename = os.path.basename(backup_info['path'])
                success = self.backup_manager.delete_remote_backup(remote_filename)
            else:
                success = self.backup_manager.delete_backup(backup_info)
            
            if success:
                QMessageBox.information(self, "成功", f"备份 '{backup_info['file']}' 已被删除。")
                self.load_backups()
            else:
                QMessageBox.critical(self, "失败", "删除过程中发生错误。")


class ManageGroupsDialog(QDialog):
    # ... (此类的内部逻辑保持不变) ...
    def __init__(self, data_manager, parent=None):
        super().__init__(parent)
        self.data_manager = data_manager
        self.setWindowTitle("分组管理")
        self.setMinimumSize(350, 250)

        layout = QVBoxLayout(self)
        self.group_list = QListWidget()
        self.load_groups()

        button_layout = QHBoxLayout()
        add_button = QPushButton("新建")
        add_button.clicked.connect(self.add_new_group)
        rename_button = QPushButton("重命名")
        rename_button.clicked.connect(self.rename_group)
        delete_button = QPushButton("删除")
        delete_button.clicked.connect(self.delete_group)

        button_layout.addWidget(add_button)
        button_layout.addWidget(rename_button)
        button_layout.addWidget(delete_button)

        layout.addWidget(QLabel("所有分组:"))
        layout.addWidget(self.group_list)
        layout.addLayout(button_layout)

    def load_groups(self):
        self.group_list.clear()
        groups = self.data_manager.get_all_groups()
        groups = [g for g in groups if g != "未分组"]
        if not groups:
            self.group_list.addItem("暂无自定义分组")
        else:
            self.group_list.addItems(groups)
        if self.parent():
            self.parent().load_books()


    def add_new_group(self):
        new_name, ok = QInputDialog.getText(self, "新建分组", "请输入新分组的名称:")
        if ok and new_name:
            self.data_manager.add_book(title="新书籍", group=new_name)
            QMessageBox.information(self, "成功", f"分组 '{new_name}' 已创建，并已添加一本“新书籍”。")
            self.load_groups()

    def rename_group(self):
        selected_item = self.group_list.currentItem()
        if not selected_item or selected_item.text() == "暂无自定义分组":
            QMessageBox.warning(self, "提示", "请选择一个要重命名的分组。")
            return

        old_name = selected_item.text()
        new_name, ok = QInputDialog.getText(self, "重命名分组", f"为分组 '{old_name}' 输入新名称:", text=old_name)

        if ok and new_name and new_name != old_name:
            if self.data_manager.rename_group(old_name, new_name):
                QMessageBox.information(self, "成功", f"分组已重命名为 '{new_name}'。")
                self.load_groups()
            else:
                QMessageBox.critical(self, "失败", "重命名失败。")

    def delete_group(self):
        selected_item = self.group_list.currentItem()
        if not selected_item or selected_item.text() == "暂无自定义分组":
            QMessageBox.warning(self, "提示", "请选择一个要删除的分组。")
            return

        group_name = selected_item.text()
        reply = QMessageBox.question(self, "确认删除",
                                       f"确定要删除分组 '{group_name}' 吗？\n该分组下的所有书籍将被移动到 '未分组'。",
                                       QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            if self.data_manager.delete_group(group_name):
                QMessageBox.information(self, "成功", f"分组 '{group_name}' 已删除。")
                self.load_groups()
            else:
                QMessageBox.critical(self, "失败", "删除失败。")

class EditBookDialog(QDialog):
    # ... (此类的内部逻辑保持不变) ...
    def __init__(self, book_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑书籍信息")

        self.layout = QFormLayout(self)

        self.title_edit = QLineEdit(book_data.get('title', ''))
        self.desc_edit = QTextEdit(book_data.get('description', ''))
        self.cover_edit = QLineEdit(book_data.get('cover_path', ''))
        self.group_edit = QLineEdit(book_data.get('group', ''))

        self.layout.addRow("书名:", self.title_edit)
        self.layout.addRow("简介:", self.desc_edit)
        self.layout.addRow("封面路径:", self.cover_edit)
        self.layout.addRow("分组:", self.group_edit)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        self.layout.addWidget(self.buttons)

    def get_details(self):
        return {
            "title": self.title_edit.text(),
            "description": self.desc_edit.toPlainText(),
            "cover_path": self.cover_edit.text(),
            "group": self.group_edit.text()
        }

class MainWindow(QMainWindow):
    # ... (此类中除了 WebDAVSettingsDialog 和 BackupDialog 的调用外，其他逻辑保持不变) ...
    def __init__(self, data_manager, backup_manager, initial_theme):
        super().__init__()
        self.data_manager = data_manager
        self.backup_manager = backup_manager
        self.current_book_id = None
        self.current_chapter_id = None
        self.is_text_changed = False
        self.current_theme = initial_theme

        self.setWindowTitle("诗成写作 PC版")
        self.setGeometry(100, 100, 1400, 900)
        self.setWindowIcon(QIcon(resource_path('resources/icons/logo.png')))

        self.backup_manager.log_message.connect(self.show_status_message)

        self.setup_ui()
        self.setup_actions()
        self.setup_menu_bar()
        self.setup_status_bar()
        self.load_and_apply_font_size()
        self.load_books()
        self.setup_snapshot_timer()
        self.setup_stage_point_timer()
        self.run_archive_backup()

        self.typing_timer = QTimer(self)
        self.typing_timer.setInterval(5000)
        self.typing_timer.timeout.connect(self.update_typing_speed)
        self.last_char_count = 0
        self.typing_speed = 0
    
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

    def setup_status_bar(self):
        status_bar = self.statusBar()
        status_bar.showMessage("欢迎使用诗成写作！")
        
        self.word_count_label = QLabel("字数: 0")
        self.typing_speed_label = QLabel("速度: 0 字/分")
        self.font_size_combobox = QComboBox()
        self.font_size_combobox.addItems(["14px", "16px", "18px", "20px"])
        self.font_size_combobox.currentIndexChanged.connect(self.on_font_size_changed)

        status_bar.addPermanentWidget(self.word_count_label)
        status_bar.addPermanentWidget(self.typing_speed_label)
        status_bar.addPermanentWidget(self.font_size_combobox)


    def create_left_panel(self):
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        book_widget = QWidget()
        book_layout = QVBoxLayout(book_widget)
        book_layout.setContentsMargins(0, 0, 0, 0)
        book_layout.setSpacing(0)

        book_toolbar = QToolBar()
        add_book_action = QAction(QIcon(resource_path("resources/icons/add.png")), "新建书籍", self)
        add_book_action.triggered.connect(self.add_new_book)
        book_toolbar.addAction(add_book_action)

        self.book_tree = QTreeView()
        self.book_tree.setHeaderHidden(True)
        self.book_model = QStandardItemModel()
        self.book_tree.setModel(self.book_model)
        self.book_tree.clicked.connect(self.on_book_selected)
        self.book_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.book_tree.customContextMenuRequested.connect(self.open_book_menu)

        book_layout.addWidget(book_toolbar)
        book_layout.addWidget(self.book_tree)
        book_widget.setLayout(book_layout)

        chapter_widget = QWidget()
        chapter_layout = QVBoxLayout(chapter_widget)
        chapter_layout.setContentsMargins(0, 0, 0, 0)
        chapter_layout.setSpacing(0)
        
        chapter_toolbar = QToolBar()
        self.add_chapter_toolbar_action = QAction(QIcon(resource_path("resources/icons/add_chapter.png")), "新建章节", self)
        self.add_chapter_toolbar_action.triggered.connect(self.add_new_chapter)
        self.add_chapter_toolbar_action.setEnabled(False) 
        chapter_toolbar.addAction(self.add_chapter_toolbar_action)

        self.chapter_tree = QTreeView()
        self.chapter_tree.setHeaderHidden(True)
        self.chapter_model = QStandardItemModel()
        self.chapter_tree.setModel(self.chapter_model)
        self.chapter_tree.clicked.connect(self.on_chapter_selected)
        self.chapter_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.chapter_tree.customContextMenuRequested.connect(self.open_chapter_menu)

        chapter_layout.addWidget(chapter_toolbar)
        chapter_layout.addWidget(self.chapter_tree)
        chapter_widget.setLayout(chapter_layout)
        
        left_splitter = QSplitter(Qt.Vertical)
        left_splitter.addWidget(book_widget)
        left_splitter.addWidget(chapter_widget)
        left_splitter.setSizes([300, 600])

        left_layout.addWidget(left_splitter)
        return left_panel


    def create_center_panel(self):
        editor_container = QWidget()
        editor_layout = QVBoxLayout(editor_container)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(0)

        self.editor = Editor()
        
        editor_layout.addWidget(self.editor)
        
        return editor_container

    def create_right_panel(self):
        self.right_tabs = QTabWidget()
        self.material_panel = MaterialPanel(self.data_manager, self)
        self.inspiration_panel = InspirationPanel(self.data_manager, self)
        self.timeline_panel = TimelinePanel(self.data_manager, self)
        self.right_tabs.addTab(self.material_panel, "素材仓库")
        self.right_tabs.addTab(self.inspiration_panel, "灵感中心")
        self.right_tabs.addTab(self.timeline_panel, "时间轴")
        return self.right_tabs


    def setup_actions(self):
        self.add_book_action = QAction("新建书籍", self)
        self.add_book_action.setShortcut(QKeySequence("Ctrl+N"))
        self.add_book_action.triggered.connect(self.add_new_book)

        self.add_chapter_action = QAction("新建章节", self)
        self.add_chapter_action.setShortcut(QKeySequence("Ctrl+Shift+N"))
        self.add_chapter_action.triggered.connect(self.add_new_chapter)
        self.add_chapter_action.setEnabled(False)

        self.save_action = QAction("保存", self)
        self.save_action.setShortcut(QKeySequence("Ctrl+S"))
        self.save_action.triggered.connect(self.save_current_chapter)

        self.export_action = QAction("导出书籍", self)
        self.export_action.setShortcut(QKeySequence("Ctrl+E"))
        self.export_action.triggered.connect(lambda: self.export_book(self.current_book_id))
        self.export_action.setEnabled(False)

        self.undo_action = QAction("撤销", self)
        self.undo_action.setShortcut(QKeySequence.Undo)
        self.undo_action.triggered.connect(self.editor.undo)
        self.editor.undoAvailable.connect(self.undo_action.setEnabled)

        self.redo_action = QAction("重做", self)
        self.redo_action.setShortcut(QKeySequence.Redo)
        self.redo_action.triggered.connect(self.editor.redo)
        self.editor.redoAvailable.connect(self.redo_action.setEnabled)
        
        self.indent_action = QAction("全文缩进", self)
        self.indent_action.setShortcut(QKeySequence("Ctrl+I"))
        self.indent_action.triggered.connect(self.auto_indent_document)

        self.unindent_action = QAction("取消缩进", self)
        self.unindent_action.setShortcut(QKeySequence("Ctrl+Shift+I"))
        self.unindent_action.triggered.connect(self.auto_unindent_document)

        self.toggle_theme_action = QAction("切换亮/暗主题", self)
        self.toggle_theme_action.setShortcut(QKeySequence("F11"))
        self.toggle_theme_action.triggered.connect(self.toggle_theme)


    def setup_menu_bar(self):
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("文件")
        file_menu.addAction(self.add_book_action)
        file_menu.addAction(self.add_chapter_action)
        file_menu.addSeparator()
        file_menu.addAction(self.save_action)
        file_menu.addSeparator()
        file_menu.addAction(self.export_action)
        file_menu.addSeparator()

        group_manage_action = QAction("分组管理", self)
        group_manage_action.triggered.connect(self.open_group_manager)
        file_menu.addAction(group_manage_action)

        backup_menu = file_menu.addMenu("备份")
        backup_now_action = QAction("立即备份", self)
        backup_now_action.triggered.connect(self.backup_manager.create_stage_point_backup)
        backup_menu.addAction(backup_now_action)

        backup_manage_action = QAction("备份管理", self)
        backup_manage_action.triggered.connect(self.open_backup_manager)
        backup_menu.addAction(backup_manage_action)

        webdav_settings_action = QAction("WebDAV 设置", self)
        webdav_settings_action.triggered.connect(self.open_webdav_settings)
        backup_menu.addAction(webdav_settings_action)

        file_menu.addSeparator()
        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        edit_menu = menu_bar.addMenu("编辑")
        edit_menu.addAction(self.undo_action)
        edit_menu.addAction(self.redo_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.indent_action)
        edit_menu.addAction(self.unindent_action)

        view_menu = menu_bar.addMenu("视图")
        view_menu.addAction(self.toggle_theme_action)

    def open_webdav_settings(self):
        dialog = WebDAVSettingsDialog(self.data_manager, self)
        dialog.exec()

    def update_theme(self, new_theme):
        self.data_manager.set_preference('theme', new_theme)
        self.current_theme = new_theme
        if hasattr(self.editor, 'highlighter'):
             self.editor.highlighter.update_highlight_color()

    def toggle_theme(self):
        new_theme = 'dark' if self.current_theme == 'light' else 'light'
        set_stylesheet(new_theme)
        self.update_theme(new_theme)
        
    def load_and_apply_font_size(self):
        font_size_str = self.data_manager.get_preference('font_size', '16px')
        
        self.editor.set_font_size(font_size_str)
        
        self.font_size_combobox.blockSignals(True)
        idx = self.font_size_combobox.findText(font_size_str)
        if idx != -1:
            self.font_size_combobox.setCurrentIndex(idx)
        else:
            self.font_size_combobox.setCurrentIndex(1) # Default to 16px
        self.font_size_combobox.blockSignals(False)


    def on_font_size_changed(self, index):
        size_str = self.font_size_combobox.itemText(index)
        self.editor.set_font_size(size_str)
        self.data_manager.set_preference('font_size', size_str)


    def auto_indent_document(self):
        if not self.current_chapter_id:
            QMessageBox.warning(self, "提示", "请先打开一个章节。")
            return
        self.editor.auto_indent_document()
        self.on_text_changed()
        QMessageBox.information(self, "成功", "全文缩进操作已完成。")

    def auto_unindent_document(self):
        if not self.current_chapter_id:
            QMessageBox.warning(self, "提示", "请先打开一个章节。")
            return
        self.editor.auto_unindent_document()
        self.on_text_changed()
        QMessageBox.information(self, "成功", "取消全文缩进操作已完成。")

    def open_group_manager(self):
        dialog = ManageGroupsDialog(self.data_manager, self)
        dialog.exec()

    def load_books(self):
        self.book_model.clear()
        books_by_group = self.data_manager.get_books_and_groups()
        for group_name, books in books_by_group.items():
            group_item = QStandardItem(group_name)
            group_item.setEditable(False)
            group_item.setData("group", Qt.UserRole)
            self.book_model.appendRow(group_item)
            for book in books:
                item = QStandardItem(book['title'])
                item.setData(book['id'], Qt.UserRole)
                item.setEditable(False)
                group_item.appendRow(item)
        self.book_tree.expandAll()

    def on_book_selected(self, index):
        item = self.book_model.itemFromIndex(index)
        if not item or item.data(Qt.UserRole) == "group":
            return
            
        book_id = item.data(Qt.UserRole)

        if isinstance(book_id, int):
            if self.is_text_changed:
                self.save_current_chapter()

            self.current_book_id = book_id
            self.load_chapters_for_book(book_id)
            self.material_panel.set_book(book_id)
            self.inspiration_panel.refresh_all()
            self.timeline_panel.set_book(book_id)
            self.refresh_editor_highlighter()
            self.setWindowTitle(f"诗成写作 - {item.text()}")
            self.add_chapter_action.setEnabled(True)
            self.add_chapter_toolbar_action.setEnabled(True)
            self.export_action.setEnabled(True)
            
            self.editor.clear()
            self.current_chapter_id = None
            self.word_count_label.setText("字数: 0")
            self.typing_speed_label.setText("速度: 0 字/分")

    def open_book_menu(self, position):
        index = self.book_tree.indexAt(position)
        if not index.isValid(): return
        item = self.book_model.itemFromIndex(index)
        book_id = item.data(Qt.UserRole)
        if not isinstance(book_id, int): return
        menu = QMenu()
        edit_action = menu.addAction("编辑书籍信息")
        set_group_action = menu.addAction("设置分组")
        export_action = menu.addAction("导出为 TXT")
        delete_action = menu.addAction("删除书籍")
        action = menu.exec_(self.book_tree.viewport().mapToGlobal(position))
        if action == edit_action: self.edit_book(book_id)
        elif action == delete_action: self.delete_book(book_id)
        elif action == set_group_action: self.set_book_group(book_id)
        elif action == export_action: self.export_book(book_id)

    def open_chapter_menu(self, position):
        index = self.chapter_tree.indexAt(position)
        if not index.isValid(): return
        item = self.chapter_model.itemFromIndex(index)
        data = item.data(Qt.UserRole)
        menu = QMenu()
        if isinstance(data, int):
            rename_chapter_action = menu.addAction("重命名章节")
            delete_chapter_action = menu.addAction("删除章节")
        else: # Is a volume
            rename_volume_action = menu.addAction("重命名卷")
        action = menu.exec_(self.chapter_tree.viewport().mapToGlobal(position))
        if isinstance(data, int):
            if action == rename_chapter_action: self.rename_chapter(data)
            elif action == delete_chapter_action: self.delete_chapter(data)
        else:
            if action == rename_volume_action: self.rename_volume(item.text())

    def add_new_book(self):
        title, ok = QInputDialog.getText(self, "新建书籍", "请输入书名:")
        if ok and title:
            self.data_manager.add_book(title, group="未分组")
            self.load_books()
            self.statusBar().showMessage(f"书籍《{title}》已创建！", 3000)

    def edit_book(self, book_id):
        book_details = self.data_manager.get_book_details(book_id)
        if not book_details:
            QMessageBox.warning(self, "错误", "找不到书籍信息。")
            return
        dialog = EditBookDialog(book_details, self)
        if dialog.exec():
            new_details = dialog.get_details()
            self.data_manager.update_book(book_id, **new_details)
            self.load_books()
            self.statusBar().showMessage(f"书籍《{new_details['title']}》信息已更新。", 3000)

    def delete_book(self, book_id):
        reply = QMessageBox.question(self, '确认删除', "确定要删除这本书吗？\n该操作会将其移入回收站。", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            book_details = self.data_manager.get_book_details(book_id)
            self.data_manager.delete_book(book_id)
            self.load_books()
            if self.current_book_id == book_id:
                self.current_book_id = None
                self.current_chapter_id = None
                self.editor.clear()
                self.chapter_model.clear()
                self.setWindowTitle("诗成写作 PC版")
                self.add_chapter_action.setEnabled(False)
                self.add_chapter_toolbar_action.setEnabled(False)
                self.export_action.setEnabled(False)
            self.statusBar().showMessage(f"书籍《{book_details['title']}》已移入回收站。", 3000)
            
    def set_book_group(self, book_id):
        book_details = self.data_manager.get_book_details(book_id)
        if not book_details: return
        group, ok = QInputDialog.getText(self, "设置分组", "请输入分组名称:", text=book_details.get('group', ''))
        if ok:
            self.data_manager.update_book(book_id, book_details.get('title'), book_details.get('description'), book_details.get('cover_path'), group)
            self.load_books()

    def export_book(self, book_id):
        if not book_id:
            QMessageBox.warning(self, "提示", "请先选择一本书籍进行导出。")
            return
        book_details = self.data_manager.get_book_details(book_id)
        if not book_details:
            QMessageBox.warning(self, "错误", "找不到书籍信息。")
            return
        file_path, _ = QFileDialog.getSaveFileName(self, "导出为 TXT", f"{book_details['title']}.txt", "文本文件 (*.txt)")
        if file_path:
            try:
                chapters = self.data_manager.get_chapters_for_book(book_id)
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(f"书名：{book_details['title']}\n")
                    f.write(f"描述：{book_details.get('description', '')}\n")
                    f.write("="*20 + "\n\n")
                    current_volume = None
                    for chapter_data in chapters:
                        if chapter_data['volume'] != current_volume:
                            current_volume = chapter_data['volume']
                            f.write(f"\n{'#'*2} {current_volume}\n\n")
                        chapter_id = chapter_data['id']
                        content, _ = self.data_manager.get_chapter_content(chapter_id)
                        f.write(f"### {chapter_data['title']}\n\n")
                        f.write(content)
                        f.write("\n\n" + "-"*15 + "\n\n")
                QMessageBox.information(self, "成功", f"书籍已成功导出到 {os.path.basename(file_path)}")
            except Exception as e:
                QMessageBox.critical(self, "导出失败", f"发生错误：\n{e}")

    def load_chapters_for_book(self, book_id):
        self.chapter_model.clear()
        chapters = self.data_manager.get_chapters_for_book(book_id)
        volumes = {}
        for chapter in chapters:
            vol = chapter['volume'] or "未分卷"
            if vol not in volumes:
                volume_item = QStandardItem(vol)
                volume_item.setEditable(False)
                volumes[vol] = volume_item
                self.chapter_model.appendRow(volume_item)
            chapter_item = QStandardItem(chapter['title'])
            chapter_item.setData(chapter['id'], Qt.UserRole)
            chapter_item.setEditable(False)
            volumes[vol].appendRow(chapter_item)
        self.chapter_tree.expandAll()

    def on_chapter_selected(self, index):
        item = self.chapter_model.itemFromIndex(index)
        if not item or not isinstance(item.data(Qt.UserRole), int):
             return
        
        chapter_id = item.data(Qt.UserRole)
        if self.is_text_changed and self.current_chapter_id != chapter_id:
            reply = QMessageBox.question(self, "保存提示", "当前章节已修改，是否保存？", QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
            if reply == QMessageBox.Save: self.save_current_chapter()
            elif reply == QMessageBox.Cancel:
                self.find_and_select_chapter(self.current_chapter_id, force_select=True)
                return
        
        self.current_chapter_id = chapter_id
        content, count = self.data_manager.get_chapter_content(chapter_id)
        self.editor.blockSignals(True)
        self.editor.setPlainText(content)
        self.editor.blockSignals(False)
        self.is_text_changed = False
        self.word_count_label.setText(f"字数: {count}")
        self.typing_speed_label.setText("速度: 0 字/分")
        self.statusBar().showMessage(f"已打开章节: {item.text()}", 3000)
        self.last_char_count = count
        if not self.typing_timer.isActive(): self.typing_timer.start()

    def add_new_chapter(self):
        if self.current_book_id is None:
            QMessageBox.warning(self, "提示", "请先选择一本书籍！")
            return
        chapters = self.data_manager.get_chapters_for_book(self.current_book_id)
        current_volumes = sorted(list({c['volume'] for c in chapters if c['volume']}))
        volume, ok_vol = QInputDialog.getItem(self, "分卷", "请选择或输入分卷名：", current_volumes, 0, True)
        if not ok_vol: return
        if not volume: volume = "未分卷"
        title, ok_title = QInputDialog.getText(self, "新建章节", "请输入章节名:")
        if ok_title and title:
            new_chapter_id = self.data_manager.add_chapter(self.current_book_id, volume, title)
            self.load_chapters_for_book(self.current_book_id)
            self.find_and_select_chapter(new_chapter_id, force_select=True)

    def rename_chapter(self, chapter_id):
        chapter_details = self.data_manager.get_chapter_details(chapter_id)
        if not chapter_details: return
        new_title, ok = QInputDialog.getText(self, "重命名章节", "请输入新的章节名:", text=chapter_details['title'])
        if ok and new_title:
            self.data_manager.update_chapter_title(chapter_id, new_title)
            self.load_chapters_for_book(self.current_book_id)
            self.statusBar().showMessage(f"章节已重命名为《{new_title}》", 3000)

    def delete_chapter(self, chapter_id):
        reply = QMessageBox.question(self, '确认删除', "确定要删除这个章节吗？\n该操作无法撤销。", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            chapter_details = self.data_manager.get_chapter_details(chapter_id)
            self.data_manager.delete_chapter(chapter_id)
            self.load_chapters_for_book(self.current_book_id)
            if self.current_chapter_id == chapter_id:
                self.current_chapter_id = None
                self.editor.clear()
            self.statusBar().showMessage(f"章节《{chapter_details['title']}》已删除。", 3000)

    def rename_volume(self, old_volume_name):
        new_volume_name, ok = QInputDialog.getText(self, "重命名卷", "请输入新的卷名:", text=old_volume_name)
        if ok and new_volume_name and new_volume_name != old_volume_name:
            self.data_manager.update_volume_name(self.current_book_id, old_volume_name, new_volume_name)
            self.load_chapters_for_book(self.current_book_id)
            self.statusBar().showMessage(f"卷《{old_volume_name}》已重命名为《{new_volume_name}》", 3000)

    def find_and_select_chapter(self, chapter_id, force_select=False):
        if chapter_id is None: return
        for row in range(self.chapter_model.rowCount()):
            parent_item = self.chapter_model.item(row)
            if not parent_item: continue
            for child_row in range(parent_item.rowCount()):
                child_item = parent_item.child(child_row)
                if child_item and child_item.data(Qt.UserRole) == chapter_id:
                    index = self.chapter_model.indexFromItem(child_item)
                    self.chapter_tree.setCurrentIndex(index)
                    if force_select: self.on_chapter_selected(index)
                    return
                    
    def save_current_chapter(self):
        if self.current_chapter_id and self.is_text_changed:
            content = self.editor.toPlainText()
            self.data_manager.update_chapter_content(self.current_chapter_id, content)
            self.is_text_changed = False
            self.word_count_label.setText(f"字数: {len(content.strip())}")
            self.statusBar().showMessage(f"章节已保存！", 2000)
            return True
        elif not self.is_text_changed and self.current_chapter_id:
            self.statusBar().showMessage(f"内容未修改，无需保存。", 2000)
        elif not self.current_chapter_id:
            self.statusBar().showMessage(f"当前没有打开的章节可供保存。", 2000)
        return False
        
    def refresh_editor_highlighter(self):
        if self.current_book_id:
            materials_names = self.data_manager.get_all_materials_names(self.current_book_id)
            self.editor.update_highlighter(materials_names)
        else:
            self.editor.update_highlighter([])
            
    def on_text_changed(self):
        if not self.editor.signalsBlocked():
            self.is_text_changed = True
            content = self.editor.toPlainText()
            count = len(content.strip())
            self.word_count_label.setText(f"字数: {count}*")

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

    def closeEvent(self, event):
        if self.is_text_changed:
            reply = QMessageBox.question(self, "退出提示", "当前章节有未保存的修改，是否保存？", QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
            if reply == QMessageBox.Save: self.save_current_chapter()
            elif reply == QMessageBox.Cancel:
                event.ignore()
                return

        self.show_status_message("正在执行关闭前的阶段点备份...")
        self.backup_manager.create_stage_point_backup()

        self.typing_timer.stop()
        self.data_manager.close()
        event.accept()

    def setup_snapshot_timer(self):
        self.snapshot_timer = QTimer(self)
        self.snapshot_timer.timeout.connect(self.run_snapshot_backup)
        self.update_timer_interval('snapshot_timer', 1 * 60 * 1000) # 1 minute default
        self.show_status_message("快照线(Snapshot Line)增量备份已启动。")

    def setup_stage_point_timer(self):
        self.stage_point_timer = QTimer(self)
        self.stage_point_timer.timeout.connect(self.run_stage_backup)
        self.update_timer_interval('stage_point_timer', 30 * 60 * 1000) # 30 minutes default
        self.show_status_message("阶段点(Stage Point)定时备份已启动。")

    def update_timer_interval(self, timer_name, default_interval):
        freq = self.data_manager.get_webdav_settings().get('webdav_sync_freq', '实时')
        timer = getattr(self, timer_name)
        if freq == '每小时':
            timer.setInterval(60 * 60 * 1000)
        elif freq == '仅启动时':
            timer.stop()
        else: # 实时
            timer.setInterval(default_interval)
            if not timer.isActive():
                timer.start()

    def run_snapshot_backup(self):
        self.backup_manager.create_snapshot_backup()
        self.update_timer_interval('snapshot_timer', 1 * 60 * 1000)
        
    def run_stage_backup(self):
        self.backup_manager.create_stage_point_backup()
        self.update_timer_interval('stage_point_timer', 30 * 60 * 1000)

    def run_archive_backup(self):
        self.show_status_message("正在检查并创建日终归档备份...")
        self.backup_manager.create_archive_backup()
        freq = self.data_manager.get_webdav_settings().get('webdav_sync_freq', '实时')
        if freq == '仅启动时':
            self.backup_manager.create_stage_point_backup() # Also trigger a stage backup on start
            
    def open_backup_manager(self):
        if self.is_text_changed: self.save_current_chapter()
        dialog = BackupDialog(self.backup_manager, self)
        dialog.exec()
        if dialog.result() == QDialog.Accepted:
            self.load_books()
            self.chapter_model.clear()
            self.editor.clear()
            self.current_book_id = None
            self.current_chapter_id = None