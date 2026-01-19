from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QToolBar, 
                               QLineEdit, QTreeView, QMenu, QInputDialog, 
                               QMessageBox, QHeaderView)
from PySide6.QtGui import QStandardItemModel, QStandardItem, QAction, QIcon, QKeySequence
from PySide6.QtCore import Qt, Signal, QSortFilterProxyModel

from modules.utils import resource_path

class ChapterTreeWidget(QWidget):
    """
    Manages the Chapter Tree View, Chapter Search, and Chapter CRUD operations.
    """
    
    # Signals
    chapter_selected = Signal(int)  # chapter_id
    chapter_deleted = Signal(int)   # chapter_id
    status_message_requested = Signal(str)
    
    def __init__(self, data_manager, parent=None):
        super().__init__(parent)
        self.data_manager = data_manager
        self.current_book_id = None
        
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Toolbar
        self.toolbar = QToolBar()
        self.add_chapter_action = QAction(QIcon(resource_path("resources/icons/add_chapter.png")), "新建章节", self)
        self.add_chapter_action.triggered.connect(self.add_new_chapter)
        self.add_chapter_action.setEnabled(False) 
        self.toolbar.addAction(self.add_chapter_action)

        # Search Input
        search_layout = QHBoxLayout()
        search_layout.setContentsMargins(2, 2, 2, 2)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索章节...")
        self.search_input.textChanged.connect(self.filter_chapters)
        search_layout.addWidget(self.search_input)
        
        search_widget = QWidget()
        search_widget.setLayout(search_layout)

        # Tree View
        self.tree = QTreeView()
        self.tree.setHeaderHidden(True)
        self.model = QStandardItemModel()
        
        self.proxy_model = QSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.model)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy_model.setRecursiveFilteringEnabled(True)
        
        self.tree.setModel(self.proxy_model)
        self.tree.clicked.connect(self.on_chapter_selected)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.open_menu)

        layout.addWidget(self.toolbar)
        layout.addWidget(search_widget)
        layout.addWidget(self.tree)

    def _get_source_idx(self, index):
        """Helper: Map proxy index to source index"""
        return self.proxy_model.mapToSource(index)

    def _get_proxy_idx(self, source_index):
        """Helper: Map source index to proxy index"""
        return self.proxy_model.mapFromSource(source_index)

    def set_book_id(self, book_id):
        """Sets the current book context and enables controls"""
        self.current_book_id = book_id
        if book_id is not None:
            self.add_chapter_action.setEnabled(True)
            self.load_chapters_for_book(book_id)
        else:
            self.add_chapter_action.setEnabled(False)
            self.model.clear()

    def load_chapters_for_book(self, book_id):
        self.model.clear()
        if not book_id: return
        
        chapters = self.data_manager.get_chapters_for_book(book_id)
        volumes = {}
        for chapter in chapters:
            vol = chapter['volume'] or "未分卷"
            if vol not in volumes:
                volume_item = QStandardItem(vol)
                volume_item.setEditable(False)
                volumes[vol] = volume_item
                self.model.appendRow(volume_item)
            chapter_item = QStandardItem(chapter['title'])
            chapter_item.setData(chapter['id'], Qt.UserRole)
            chapter_item.setEditable(False)
            volumes[vol].appendRow(chapter_item)
        self.tree.expandAll()
        self.filter_chapters()

    def filter_chapters(self):
        search_text = self.search_input.text()
        self.proxy_model.setFilterRegularExpression(search_text if search_text else "")
        self.tree.expandAll()

    def on_chapter_selected(self, index):
        source_index = self._get_source_idx(index)
        item = self.model.itemFromIndex(source_index)
        if not item or not isinstance(item.data(Qt.UserRole), int):
            return
        
        chapter_id = item.data(Qt.UserRole)
        self.chapter_selected.emit(chapter_id)

    def open_menu(self, position):
        index = self.tree.indexAt(position)
        if not index.isValid(): return
        
        source_index = self._get_source_idx(index)
        item = self.model.itemFromIndex(source_index)
        data = item.data(Qt.UserRole)
        menu = QMenu()
        
        if isinstance(data, int): # Chapter
            rename_chapter_action = menu.addAction("重命名章节")
            delete_chapter_action = menu.addAction("删除章节")
            
            action = menu.exec(self.tree.viewport().mapToGlobal(position))
            
            if action == rename_chapter_action: self.rename_chapter(data)
            elif action == delete_chapter_action: self.delete_chapter(data)
            
        else: # Volume
            rename_volume_action = menu.addAction("重命名卷")
            action = menu.exec(self.tree.viewport().mapToGlobal(position))
            if action == rename_volume_action: self.rename_volume(item.text())

    # --- Actions ---

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
        if ok_title:
            if title and title.strip():
                new_chapter_id = self.data_manager.add_chapter(self.current_book_id, volume, title)
                self.load_chapters_for_book(self.current_book_id)
                self.find_and_select_chapter(new_chapter_id, force_select=True)
            else:
                QMessageBox.warning(self, "警告", "章节名不能为空！")

    def rename_chapter(self, chapter_id):
        chapter_details = self.data_manager.get_chapter_details(chapter_id)
        if not chapter_details: return
        new_title, ok = QInputDialog.getText(self, "重命名章节", "请输入新的章节名:", text=chapter_details['title'])
        if ok:
            if new_title and new_title.strip():
                self.data_manager.update_chapter_title(chapter_id, new_title)
                self.load_chapters_for_book(self.current_book_id)
                self.status_message_requested.emit(f"章节已重命名为《{new_title}》")
            else:
                QMessageBox.warning(self, "警告", "章节名不能为空！")
            # Reselect/restore view state if needed

    def delete_chapter(self, chapter_id):
        reply = QMessageBox.question(self, '确认删除', 
            "确定要删除这个章节吗？\n该操作会将其移入回收站，您可以在“文件 > 回收站”中恢复。", 
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            chapter_details = self.data_manager.get_chapter_details(chapter_id)
            self.data_manager.delete_chapter(chapter_id)
            self.load_chapters_for_book(self.current_book_id)
            self.chapter_deleted.emit(chapter_id)
            
            title = chapter_details['title'] if chapter_details else "未知"
            self.status_message_requested.emit(f"章节《{title}》已移入回收站。")

    def rename_volume(self, old_volume_name):
        new_volume_name, ok = QInputDialog.getText(self, "重命名卷", "请输入新的卷名:", text=old_volume_name)
        if ok:
            if new_volume_name and new_volume_name.strip():
                if new_volume_name != old_volume_name:
                    self.data_manager.update_volume_name(self.current_book_id, old_volume_name, new_volume_name)
                    self.load_chapters_for_book(self.current_book_id)
                    self.status_message_requested.emit(f"卷《{old_volume_name}》已重命名为《{new_volume_name}》")
            else:
                QMessageBox.warning(self, "警告", "卷名不能为空！")

    def find_and_select_chapter(self, chapter_id, force_select=False):
        if chapter_id is None: 
            self.tree.clearSelection()
            return
            
        for row in range(self.model.rowCount()):
            parent_item = self.model.item(row)
            if not parent_item: continue
            for child_row in range(parent_item.rowCount()):
                child_item = parent_item.child(child_row)
                if child_item and child_item.data(Qt.UserRole) == chapter_id:
                    source_index = self.model.indexFromItem(child_item)
                    proxy_index = self._get_proxy_idx(source_index)
                        
                    self.tree.setCurrentIndex(proxy_index)
                    self.tree.scrollTo(proxy_index)
                    if force_select: 
                        # This triggers on_chapter_selected
                        self.on_chapter_selected(proxy_index)
                    return
