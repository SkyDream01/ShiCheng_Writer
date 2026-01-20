import os
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QToolBar, 
                               QLineEdit, QTreeView, QMenu, QInputDialog, 
                               QMessageBox, QFileDialog)
from PySide6.QtGui import QStandardItemModel, QStandardItem, QAction, QIcon, QKeySequence
from PySide6.QtCore import Qt, Signal, QSortFilterProxyModel

from modules.utils import resource_path
from widgets.dialogs import EditBookDialog, ManageGroupsDialog

class BookTreeWidget(QWidget):
    """
    管理书籍树状视图、书籍搜索和书籍 CRUD 操作。
    """
    
    # 与主窗口通信的信号
    book_selected = Signal(int, str)  # book_id, book_title
    book_deleted = Signal(int)        # book_id
    status_message_requested = Signal(str) # message
    
    def __init__(self, data_manager, parent=None):
        super().__init__(parent)
        self.data_manager = data_manager
        self.current_book_id = None
        
        self.setup_ui()
        self.load_books()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 工具栏
        self.toolbar = QToolBar()
        self.add_book_action = QAction(QIcon(resource_path("resources/icons/add.png")), "新建书籍", self)
        self.add_book_action.setShortcut(QKeySequence("Ctrl+N"))
        self.add_book_action.triggered.connect(self.add_new_book)
        self.toolbar.addAction(self.add_book_action)

        # 搜索输入框
        search_layout = QHBoxLayout()
        search_layout.setContentsMargins(2, 2, 2, 2)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索书籍...")
        self.search_input.textChanged.connect(self.filter_books)
        search_layout.addWidget(self.search_input)
        
        search_widget = QWidget()
        search_widget.setLayout(search_layout)

        # 树状视图
        self.tree = QTreeView()
        self.tree.setHeaderHidden(True)
        self.model = QStandardItemModel()
        
        self.proxy_model = QSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.model)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy_model.setRecursiveFilteringEnabled(True)
        
        self.tree.setModel(self.proxy_model)
        self.tree.clicked.connect(self.on_book_selected)
        self.tree.doubleClicked.connect(self.on_book_double_clicked)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.open_menu)

        layout.addWidget(self.toolbar)
        layout.addWidget(search_widget)
        layout.addWidget(self.tree)

    def _get_source_idx(self, index):
        """辅助函数：映射代理索引到源索引"""
        return self.proxy_model.mapToSource(index)

    def load_books(self):
        self.model.clear()
        books_by_group = self.data_manager.get_books_and_groups()
        
        # 记录展开状态？暂时全部展开
        for group_name, books in books_by_group.items():
            group_item = QStandardItem(group_name)
            group_item.setEditable(False)
            group_item.setData("group", Qt.UserRole)
            self.model.appendRow(group_item)
            for book in books:
                item = QStandardItem(book['title'])
                item.setData(book['id'], Qt.UserRole)
                item.setEditable(False)
                group_item.appendRow(item)
        
        self.tree.expandAll()
        self.filter_books() # 重新应用过滤器

    def filter_books(self):
        search_text = self.search_input.text()
        self.proxy_model.setFilterRegularExpression(search_text if search_text else "")
        self.tree.expandAll()

    def on_book_selected(self, index):
        source_index = self._get_source_idx(index)
        item = self.model.itemFromIndex(source_index)
        
        if not item or item.data(Qt.UserRole) == "group":
            return
            
        book_id = item.data(Qt.UserRole)
        if isinstance(book_id, int):
            self.current_book_id = book_id
            self.book_selected.emit(book_id, item.text())

    def on_book_double_clicked(self, index):
        source_index = self._get_source_idx(index)
        item = self.model.itemFromIndex(source_index)
        if not item:
            return
        data = item.data(Qt.UserRole)
        if data == "group":
            self.add_new_book_to_group(item.text())

    def open_menu(self, position):
        index = self.tree.indexAt(position)
        if not index.isValid():
            # 点击空白处，显示通用菜单
            menu = QMenu()
            add_action = menu.addAction("新建书籍")
            manage_groups_action = menu.addAction("分组管理")
            
            action = menu.exec(self.tree.viewport().mapToGlobal(position))
            if action == add_action:
                self.add_new_book()
            elif action == manage_groups_action:
                self.open_group_manager()
            return

        source_index = self._get_source_idx(index)
        item = self.model.itemFromIndex(source_index)
        data = item.data(Qt.UserRole)
        menu = QMenu()
        
        if isinstance(data, int):  # 书籍
            edit_action = menu.addAction("编辑书籍信息")
            set_group_action = menu.addAction("设置分组")
            export_action = menu.addAction("导出为 TXT")
            delete_action = menu.addAction("删除书籍")
            
            action = menu.exec(self.tree.viewport().mapToGlobal(position))
            
            if action == edit_action: self.edit_book(data)
            elif action == delete_action: self.delete_book(data)
            elif action == set_group_action: self.set_book_group(data)
            elif action == export_action: self.export_book(data)
            
        else:  # 分组
            group_name = item.text()
            new_book_action = menu.addAction("新建书籍")
            rename_group_action = menu.addAction("重命名分组")
            delete_group_action = menu.addAction("删除分组")
            
            action = menu.exec(self.tree.viewport().mapToGlobal(position))
            
            if action == new_book_action: self.add_new_book_to_group(group_name)
            elif action == rename_group_action: self.rename_group(group_name)
            elif action == delete_group_action: self.delete_group(group_name)

    # --- 动作 ---

    def add_new_book(self):
        title, ok = QInputDialog.getText(self, "新建书籍", "请输入书名:")
        if ok:
            if title and title.strip():
                self.data_manager.add_book(title, group="未分组")
                self.load_books()
                self.status_message_requested.emit(f"书籍《{title}》已创建！")
            else:
                QMessageBox.warning(self, "警告", "书名不能为空！")

    def add_new_book_to_group(self, group_name):
        title, ok = QInputDialog.getText(self, f"在「{group_name}」中新建书籍", "请输入书名:")
        if ok:
            if title and title.strip():
                self.data_manager.add_book(title, group=group_name)
                self.load_books()
                self.status_message_requested.emit(f"书籍《{title}》已在「{group_name}」分组中创建！")
            else:
                QMessageBox.warning(self, "警告", "书名不能为空！")

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
            self.status_message_requested.emit(f"书籍《{new_details['title']}》信息已更新。")
            # 如果这是当前书籍，重新发送选择信号以更新详情页
            if self.current_book_id == book_id:
                self.book_selected.emit(book_id, new_details['title'])

    def delete_book(self, book_id):
        reply = QMessageBox.question(self, '确认删除', 
            "确定要删除这本书吗？\n该操作会将其移入回收站，您可以在“文件 > 回收站”中恢复。", 
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            book_details = self.data_manager.get_book_details(book_id)
            title = book_details['title'] if book_details else "未知"
            self.data_manager.delete_book(book_id)
            self.load_books()
            
            if self.current_book_id == book_id:
                self.current_book_id = None
                self.book_deleted.emit(book_id)
            
            self.status_message_requested.emit(f"书籍《{title}》已移入回收站。")

    def set_book_group(self, book_id):
        book_details = self.data_manager.get_book_details(book_id)
        if not book_details: return
        group, ok = QInputDialog.getText(self, "设置分组", "请输入分组名称:", text=book_details.get('group', ''))
        if ok:
            self.data_manager.update_book(book_id, book_details.get('title'), 
                                          book_details.get('description'), 
                                          book_details.get('cover_path'), group)
            self.load_books()

    def export_book(self, book_id):
        if not book_id: return
        book_details = self.data_manager.get_book_details(book_id)
        if not book_details: return
        
        file_path, _ = QFileDialog.getSaveFileName(self, "导出为 TXT", f"{book_details['title']}.txt", "文本文件 (*.txt)")
        if file_path:
            try:
                chapters = self.data_manager.get_chapters_for_book(book_id)
                with open(file_path, 'w', encoding='utf-8-sig') as f:
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

    def rename_group(self, old_name):
        new_name, ok = QInputDialog.getText(self, "重命名分组", "请输入新的分组名称:", text=old_name)
        if ok:
            if new_name and new_name.strip():
                if new_name != old_name:
                    self.data_manager.rename_group(old_name, new_name)
                    self.load_books()
                    self.status_message_requested.emit(f"分组「{old_name}」已重命名为「{new_name}」")
            else:
                QMessageBox.warning(self, "警告", "分组名称不能为空！")

    def delete_group(self, group_name):
        books_in_group = self.data_manager.get_books_by_group(group_name)
        if books_in_group:
            reply = QMessageBox.question(self, "确认删除分组", 
                f"分组「{group_name}」中有 {len(books_in_group)} 本书籍。删除分组将会把这些书籍移动到「未分组」。\n\n确定要继续吗？", 
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
        else:
            reply = QMessageBox.question(self, "确认删除", f"确定要删除空分组「{group_name}」吗？", 
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
        
        self.data_manager.delete_group(group_name)
        self.load_books()
        if books_in_group:
            self.status_message_requested.emit(f"分组「{group_name}」已删除，{len(books_in_group)} 本书籍已移动到「未分组」")
        else:
            self.status_message_requested.emit(f"空分组「{group_name}」已删除")

    def open_group_manager(self):
        dialog = ManageGroupsDialog(self.data_manager, self)
        dialog.exec()

    def select_book(self, book_id):
        """通过 ID 程序化选中书籍"""
        # 遍历模型查找项
        for row in range(self.model.rowCount()):
            item = self.model.item(row)
            if item.data(Qt.UserRole) == "group":
                # 检查子项
                for child_row in range(item.rowCount()):
                    child = item.child(child_row)
                    if child.data(Qt.UserRole) == book_id:
                        # 找到了
                        index = self.model.indexFromItem(child)
                        proxy_index = self.proxy_model.mapFromSource(index)
                        self.tree.setCurrentIndex(proxy_index)
                        self.tree.scrollTo(proxy_index)
                        return
            elif item.data(Qt.UserRole) == book_id:
                # 找到了（如果书籍在根级别，尽管当前逻辑将其放入分组）
                index = self.model.indexFromItem(item)
                proxy_index = self.proxy_model.mapFromSource(index)
                self.tree.setCurrentIndex(proxy_index)
                self.tree.scrollTo(proxy_index)
                return
