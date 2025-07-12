# ShiCheng_Writer/main_window.py
import sys
import os
import shutil
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                               QListWidget, QListWidgetItem, QSplitter, QDockWidget,
                               QTreeView, QMessageBox, QInputDialog, QFileDialog,
                               QToolBar, QLabel, QMenu, QPushButton, QStatusBar, QToolButton,
                               QDialog, QDialogButtonBox, QApplication, QFormLayout, QLineEdit, QTextEdit)
from PySide6.QtGui import QStandardItemModel, QStandardItem, QAction
from PySide6.QtCore import Qt, QSize, QTimer

# 从新的模块导入，打破循环依赖
from modules.theme_manager import set_stylesheet

from modules.database import DataManager
from widgets.editor import Editor
from modules.settings_system import SettingsPanel
from modules.inspiration import InspirationPanel


class BackupDialog(QDialog):
    # ... (此类无须修改，保持原样)
    def __init__(self, backup_manager, parent=None):
        super().__init__(parent)
        self.backup_manager = backup_manager
        self.setWindowTitle("备份管理")
        self.setMinimumSize(400, 300)
        layout = QVBoxLayout(self)
        self.backup_list = QListWidget()
        self.load_backups()
        button_layout = QHBoxLayout()
        restore_button = QPushButton("恢复选中项")
        restore_button.clicked.connect(self.restore_backup)
        delete_button = QPushButton("删除选中项")
        delete_button.clicked.connect(self.delete_backup)
        button_layout.addWidget(restore_button)
        button_layout.addWidget(delete_button)
        layout.addWidget(QLabel("所有可用的本地备份 (按时间倒序):"))
        layout.addWidget(self.backup_list)
        layout.addLayout(button_layout)
    def load_backups(self):
        self.backup_list.clear()
        backups = self.backup_manager.list_backups()
        if not backups:
            self.backup_list.addItem("暂无备份文件")
        else:
            self.backup_list.addItems(backups)
    def restore_backup(self):
        selected_item = self.backup_list.currentItem()
        if not selected_item or selected_item.text() == "暂无备份文件":
            QMessageBox.warning(self, "提示", "请先选择一个备份文件。")
            return
        backup_file = selected_item.text()
        reply = QMessageBox.warning(self, "确认恢复",
                                     f"您确定要从备份 '{backup_file}' 恢复吗？\n"
                                     "【警告】此操作将完全覆盖当前所有数据！\n"
                                     "恢复后必须重启应用才能看到更改。\n"
                                     "操作无法撤销，请谨慎操作！",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            if self.backup_manager.restore_from_backup(backup_file):
                QMessageBox.information(self, "成功", "数据已从备份恢复。\n请立即重启应用程序以应用更改。")
                self.accept()
            else:
                QMessageBox.critical(self, "失败", "恢复过程中发生错误，请查看控制台输出。")
    def delete_backup(self):
        selected_item = self.backup_list.currentItem()
        if not selected_item or selected_item.text() == "暂无备份文件":
            QMessageBox.warning(self, "提示", "请先选择一个要删除的备份文件。")
            return
        backup_file = selected_item.text()
        reply = QMessageBox.question(self, "确认删除",
                                       f"确定要永久删除备份 '{backup_file}' 吗？",
                                       QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            if self.backup_manager.delete_backup(backup_file):
                QMessageBox.information(self, "成功", f"备份 '{backup_file}' 已被删除。")
                self.load_backups()
            else:
                QMessageBox.critical(self, "失败", "删除过程中发生错误。")

class ManageGroupsDialog(QDialog):
    """管理分组的对话框"""
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
        # "未分组" is a special case and shouldn't be managed here
        groups = [g for g in groups if g != "未分组"]
        if not groups:
            self.group_list.addItem("暂无自定义分组")
        else:
            self.group_list.addItems(groups)
        # Refresh main window book list when dialog is shown or updated
        if self.parent():
            self.parent().load_books()


    def add_new_group(self):
        new_name, ok = QInputDialog.getText(self, "新建分组", "请输入新分组的名称:")
        if ok and new_name:
            # A group exists if a book is assigned to it.
            # So we create a placeholder book.
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
    """编辑书籍信息的对话框"""
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
    # 接收一个初始主题参数
    def __init__(self, data_manager, backup_manager, initial_theme):
        super().__init__()
        self.data_manager = data_manager
        self.backup_manager = backup_manager
        self.current_book_id = None
        self.current_chapter_id = None
        self.is_text_changed = False
        # 从 main.py 接收初始主题状态
        self.current_theme = initial_theme

        self.setWindowTitle("诗成写作 PC版")
        self.setGeometry(100, 100, 1400, 900)

        self.setup_ui()
        self.load_books()
        self.setup_auto_backup()

    def setup_ui(self):
        # ... (此函数无需修改，保持原样)
        self.splitter = QSplitter(Qt.Horizontal)
        self.editor = Editor()
        self.editor.textChanged.connect(self.on_text_changed)
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        self.word_count_label = QLabel("字数: 0")
        right_layout.addWidget(self.word_count_label)
        right_layout.addStretch()
        self.splitter.addWidget(self.editor)
        self.splitter.addWidget(right_panel)
        self.splitter.setSizes([900, 300]) 
        self.setCentralWidget(self.splitter)
        self.setup_docks()
        self.setup_toolbar()
        self.setStatusBar(QStatusBar(self))
        self.statusBar().showMessage("欢迎使用诗成写作！")

    def setup_toolbar(self):
        toolbar = QToolBar("主工具栏")
        self.addToolBar(toolbar)

        # --- 1. 文件菜单 ---
        file_button = QToolButton()
        file_button.setText("文件")
        file_button.setPopupMode(QToolButton.InstantPopup)
        file_menu = QMenu(file_button)

        add_book_action = QAction("新建书籍", self)
        add_book_action.triggered.connect(self.add_new_book)
        file_menu.addAction(add_book_action)

        self.add_chapter_action = QAction("新建章节", self)
        self.add_chapter_action.triggered.connect(self.add_new_chapter)
        self.add_chapter_action.setEnabled(False)
        file_menu.addAction(self.add_chapter_action)
        
        file_menu.addSeparator()

        save_action = QAction("保存", self)
        save_action.triggered.connect(self.save_current_chapter)
        file_menu.addAction(save_action)

        file_menu.addSeparator()
        
        self.export_action = QAction("导出书籍", self)
        self.export_action.triggered.connect(lambda: self.export_book(self.current_book_id))
        self.export_action.setEnabled(False)
        file_menu.addAction(self.export_action)
        
        file_menu.addSeparator()

        backup_now_action = QAction("立即备份", self)
        backup_now_action.triggered.connect(lambda: self.run_scheduled_backup(force=True))
        file_menu.addAction(backup_now_action)
        
        backup_manage_action = QAction("备份管理", self)
        backup_manage_action.triggered.connect(self.open_backup_manager)
        file_menu.addAction(backup_manage_action)
        
        file_button.setMenu(file_menu)
        toolbar.addWidget(file_button)

        # --- 2. 编辑菜单 ---
        edit_button = QToolButton()
        edit_button.setText("编辑")
        edit_button.setPopupMode(QToolButton.InstantPopup)
        edit_menu = QMenu(edit_button)

        indent_action = QAction("全文缩进", self)
        indent_action.triggered.connect(self.auto_indent_document)
        edit_menu.addAction(indent_action)

        unindent_action = QAction("取消缩进", self)
        unindent_action.triggered.connect(self.auto_unindent_document)
        edit_menu.addAction(unindent_action)

        edit_button.setMenu(edit_menu)
        toolbar.addWidget(edit_button)

        # --- 3. 视图菜单 ---
        view_button = QToolButton()
        view_button.setText("视图")
        view_button.setPopupMode(QToolButton.InstantPopup)
        view_menu = QMenu(view_button)
        
        book_dock_action = self.book_dock.toggleViewAction()
        book_dock_action.setText("书籍列表")
        view_menu.addAction(book_dock_action)
        
        chapter_dock_action = self.chapter_dock.toggleViewAction()
        chapter_dock_action.setText("章节结构")
        view_menu.addAction(chapter_dock_action)
        
        view_menu.addSeparator()
        
        settings_dock_action = self.settings_dock.toggleViewAction()
        settings_dock_action.setText("设定仓库")
        view_menu.addAction(settings_dock_action)
        
        inspiration_dock_action = self.inspiration_dock.toggleViewAction()
        inspiration_dock_action.setText("灵感中心")
        view_menu.addAction(inspiration_dock_action)
        
        view_menu.addSeparator()
        
        toggle_theme_action = QAction("切换亮/暗主题", self)
        toggle_theme_action.triggered.connect(self.toggle_theme)
        view_menu.addAction(toggle_theme_action)

        view_button.setMenu(view_menu)
        toolbar.addWidget(view_button)
        
        # --- 4. 工具菜单 ---
        tools_button = QToolButton()
        tools_button.setText("工具")
        tools_button.setPopupMode(QToolButton.InstantPopup)
        tools_menu = QMenu(tools_button)
        
        group_manage_action = QAction("分组管理", self)
        group_manage_action.triggered.connect(self.open_group_manager)
        tools_menu.addAction(group_manage_action)

        tools_button.setMenu(tools_menu)
        toolbar.addWidget(tools_button)

    def update_theme(self, new_theme):
        """接收来自main的自动主题变更信号，并更新内部组件"""
        self.current_theme = new_theme
        self.editor.highlighter.update_highlight_color()

    def toggle_theme(self):
        """手动切换主题"""
        new_theme = 'dark' if self.current_theme == 'light' else 'light'
        set_stylesheet(new_theme)
        # 手动切换后，也调用update_theme来更新所有组件
        self.update_theme(new_theme)
        
    def auto_indent_document(self):
        """触发编辑器全文缩进并显示消息"""
        if not self.current_chapter_id:
            QMessageBox.warning(self, "提示", "请先打开一个章节。")
            return
        self.editor.auto_indent_document()
        self.on_text_changed() # 标记为已修改
        QMessageBox.information(self, "成功", "全文缩进操作已完成。")

    def auto_unindent_document(self):
        """触发编辑器取消全文缩进并显示消息"""
        if not self.current_chapter_id:
            QMessageBox.warning(self, "提示", "请先打开一个章节。")
            return
        self.editor.auto_unindent_document()
        self.on_text_changed() # 标记为已修改
        QMessageBox.information(self, "成功", "取消全文缩进操作已完成。")

    def open_group_manager(self):
        """打开分组管理对话框"""
        dialog = ManageGroupsDialog(self.data_manager, self)
        dialog.exec()

    # --- MainWindow的其余方法保持不变 ---
    # ... (setup_docks, load_books, on_book_selected, 等)
    def setup_docks(self):
        self.book_dock = QDockWidget("书籍列表", self)
        self.book_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        book_widget = QWidget()
        book_layout = QVBoxLayout(book_widget)
        book_layout.setContentsMargins(5, 5, 5, 5)
        action_layout = QHBoxLayout()
        add_book_btn = QPushButton("新建书籍")
        add_book_btn.clicked.connect(self.add_new_book)
        import_btn = QPushButton("导入书籍")
        import_btn.clicked.connect(self.import_book)
        action_layout.addWidget(add_book_btn)
        action_layout.addWidget(import_btn)
        self.book_tree = QTreeView()
        self.book_tree.setHeaderHidden(True)
        self.book_model = QStandardItemModel()
        self.book_tree.setModel(self.book_model)
        self.book_tree.clicked.connect(self.on_book_selected)
        self.book_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.book_tree.customContextMenuRequested.connect(self.open_book_menu)
        book_layout.addLayout(action_layout)
        book_layout.addWidget(self.book_tree)
        self.book_dock.setWidget(book_widget)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.book_dock)
        self.chapter_dock = QDockWidget("章节结构", self)
        self.chapter_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        chapter_widget = QWidget()
        chapter_layout = QVBoxLayout(chapter_widget)
        chapter_layout.setContentsMargins(0, 5, 0, 5)
        self.chapter_tree = QTreeView()
        self.chapter_tree.setHeaderHidden(True)
        self.chapter_model = QStandardItemModel()
        self.chapter_tree.setModel(self.chapter_model)
        self.chapter_tree.clicked.connect(self.on_chapter_selected)
        self.chapter_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.chapter_tree.customContextMenuRequested.connect(self.open_chapter_menu)
        add_chapter_btn = QPushButton("新建章节")
        add_chapter_btn.clicked.connect(self.add_new_chapter)
        chapter_layout.addWidget(add_chapter_btn)
        chapter_layout.addWidget(self.chapter_tree)
        self.chapter_dock.setWidget(chapter_widget)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.chapter_dock)
        self.settings_dock = QDockWidget("设定仓库", self)
        self.settings_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.settings_panel = SettingsPanel(self.data_manager)
        self.settings_dock.setWidget(self.settings_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, self.settings_dock)
        self.inspiration_dock = QDockWidget("灵感中心", self)
        self.inspiration_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.inspiration_panel = InspirationPanel(self.data_manager)
        self.inspiration_dock.setWidget(self.inspiration_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, self.inspiration_dock)
        self.tabifyDockWidget(self.settings_dock, self.inspiration_dock)
        self.settings_dock.raise_()
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
        if not item: return
        book_id = item.data(Qt.UserRole)
        if isinstance(book_id, int):
            if self.is_text_changed:
                self.save_current_chapter() # 自动保存切换前的内容
            self.current_book_id = book_id
            self.load_chapters_for_book(book_id)
            self.settings_panel.set_book(book_id)
            self.update_editor_highlighter()
            self.setWindowTitle(f"诗成写作 - {item.text()}")
            self.add_chapter_action.setEnabled(True)
            self.export_action.setEnabled(True)
            # 清空编辑器和章节ID，等待用户选择章节
            self.editor.clear()
            self.current_chapter_id = None
            self.word_count_label.setText("字数: 0")
    def open_book_menu(self, position):
        index = self.book_tree.indexAt(position)
        if not index.isValid():
            return
        item = self.book_model.itemFromIndex(index)
        book_id = item.data(Qt.UserRole)
        if not isinstance(book_id, int):
            return
        menu = QMenu()
        edit_action = menu.addAction("编辑书籍信息")
        set_group_action = menu.addAction("设置分组")
        export_action = menu.addAction("导出为 TXT")
        delete_action = menu.addAction("删除书籍")
        action = menu.exec_(self.book_tree.viewport().mapToGlobal(position))
        if action == edit_action:
            self.edit_book(book_id)
        elif action == delete_action:
            self.delete_book(book_id)
        elif action == set_group_action:
            self.set_book_group(book_id)
        elif action == export_action:
            self.export_book(book_id)

    def open_chapter_menu(self, position):
        index = self.chapter_tree.indexAt(position)
        if not index.isValid():
            return
            
        item = self.chapter_model.itemFromIndex(index)
        data = item.data(Qt.UserRole)
        
        menu = QMenu()
        if isinstance(data, int): # 是章节
            rename_chapter_action = menu.addAction("重命名章节")
        else: # 是卷
            rename_volume_action = menu.addAction("重命名卷")

        action = menu.exec_(self.chapter_tree.viewport().mapToGlobal(position))

        if isinstance(data, int):
            if action == rename_chapter_action:
                self.rename_chapter(data)
        else:
            if action == rename_volume_action:
                self.rename_volume(item.text())


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
            self.load_books() # 刷新书籍列表
            self.statusBar().showMessage(f"书籍《{new_details['title']}》信息已更新。", 3000)

    def delete_book(self, book_id):
        reply = QMessageBox.question(self, '确认删除',
                                     "确定要删除这本书吗？\n该操作会将其移入回收站。",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
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
                self.export_action.setEnabled(False)
            self.statusBar().showMessage(f"书籍《{book_details['title']}》已移入回收站。", 3000)
    def set_book_group(self, book_id):
        book_details = self.data_manager.get_book_details(book_id)
        if not book_details:
            return
        group, ok = QInputDialog.getText(self, "设置分组", "请输入分组名称:", text=book_details.get('group', ''))
        if ok:
            self.data_manager.update_book(book_id, book_details.get('title'), book_details.get('description'), book_details.get('cover_path'), group)
            self.load_books()
    def import_book(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "导入书籍", "", "文本文件 (*.txt);;Word文档 (*.docx)")
        if file_path:
            QMessageBox.information(self, "提示", f"从 {os.path.basename(file_path)} 导入书籍的功能待实现。")
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
                        clean_content = content.strip()
                        expected_title = f"# {chapter_data['title']}"
                        if not clean_content.startswith(expected_title):
                             f.write(f"### {chapter_data['title']}\n\n")
                        f.write(clean_content)
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
        if not item: return
        data = item.data(Qt.UserRole)
        if isinstance(data, int):
            if self.is_text_changed and self.current_chapter_id != data:
                reply = QMessageBox.question(self, "保存提示", "当前章节已修改，是否保存？",
                                             QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                                             QMessageBox.Save)
                if reply == QMessageBox.Save:
                    self.save_current_chapter()
                elif reply == QMessageBox.Cancel:
                    self.find_and_select_chapter(self.current_chapter_id, force_select=True)
                    return
            self.current_chapter_id = data
            content, count = self.data_manager.get_chapter_content(data)
            self.editor.blockSignals(True)
            self.editor.setText(content)
            self.editor.blockSignals(False)
            self.is_text_changed = False
            self.word_count_label.setText(f"字数: {count}")
            self.statusBar().showMessage(f"已打开章节: {item.text()}", 3000)
    def add_new_chapter(self):
        if self.current_book_id is None:
            QMessageBox.warning(self, "提示", "请先选择一本书籍！")
            return
        chapters = self.data_manager.get_chapters_for_book(self.current_book_id)
        current_volumes = sorted(list({c['volume'] for c in chapters if c['volume']}))
        volume, ok_vol = QInputDialog.getItem(self, "分卷", "请选择或输入分卷名：", current_volumes, 0, True)
        if not ok_vol:
            return
        if not volume:
            volume = "未分卷"
        title, ok_title = QInputDialog.getText(self, "新建章节", "请输入章节名:")
        if ok_title and title:
            new_chapter_id = self.data_manager.add_chapter(self.current_book_id, volume, title)
            self.load_chapters_for_book(self.current_book_id)
            self.find_and_select_chapter(new_chapter_id)

    def rename_chapter(self, chapter_id):
        chapter_details = self.data_manager.get_chapter_details(chapter_id)
        if not chapter_details:
            return
        
        new_title, ok = QInputDialog.getText(self, "重命名章节", "请输入新的章节名:", text=chapter_details['title'])
        if ok and new_title:
            self.data_manager.update_chapter_title(chapter_id, new_title)
            self.load_chapters_for_book(self.current_book_id)
            self.statusBar().showMessage(f"章节已重命名为《{new_title}》", 3000)

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
                    if force_select:
                        self.on_chapter_selected(index)
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
    def update_editor_highlighter(self):
        if self.current_book_id:
            settings_names = self.data_manager.get_all_settings_names(self.current_book_id)
            self.editor.update_highlighter(settings_names)
    def on_text_changed(self):
        if not self.editor.signalsBlocked():
            self.is_text_changed = True
            content = self.editor.toPlainText()
            count = len(content.strip())
            self.word_count_label.setText(f"字数: {count}*")
    def closeEvent(self, event):
        if self.is_text_changed:
            reply = QMessageBox.question(self, "退出提示", "当前章节有未保存的修改，是否保存？",
                                         QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                                         QMessageBox.Save)
            if reply == QMessageBox.Save:
                self.save_current_chapter()
            elif reply == QMessageBox.Cancel:
                event.ignore()
                return
        self.data_manager.close()
        event.accept()
    def setup_auto_backup(self):
        self.backup_timer = QTimer(self)
        self.backup_timer.timeout.connect(self.run_scheduled_backup)
        self.backup_timer.start(1800 * 1000) 
        self.run_scheduled_backup()
        print("自动备份任务已启动，每30分钟检查一次。")
    def run_scheduled_backup(self, force=False):
        if force:
            self.statusBar().showMessage("正在执行手动备份...", 3000)
            if self.backup_manager.create_backup(force=True):
                self.statusBar().showMessage("手动备份成功！", 3000)
            else:
                 self.statusBar().showMessage("手动备份失败，请查看日志。", 3000)
        else:
            print("正在执行例行备份...")
            self.statusBar().showMessage("正在执行自动备份...", 2000)
            self.backup_manager.create_backup()
            self.statusBar().showMessage("自动备份完成。", 2000)
    def open_backup_manager(self):
        if self.is_text_changed:
            self.save_current_chapter()
        dialog = BackupDialog(self.backup_manager, self)
        dialog.exec()