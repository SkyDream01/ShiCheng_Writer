# ShiCheng_Writer/modules/timeline_system.py
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QTreeView, QPushButton, QHBoxLayout,
                               QDialog, QMenu, QSplitter,
                               QFormLayout, QDialogButtonBox, QLabel, QMessageBox,
                               QTextEdit, QLineEdit, QListWidget, QListWidgetItem,
                               QToolBar, QProgressBar, QComboBox, QInputDialog)
from PySide6.QtGui import QStandardItemModel, QStandardItem, QAction, QIcon
from PySide6.QtCore import Qt, Signal
import json
import time

from .material_system import MaterialSelectionDialog # 复用素材选择对话框

class TimelineEditDialog(QDialog):
    """时间轴编辑对话框"""
    def __init__(self, data_manager, timeline_id, book_id, parent=None):
        super().__init__(parent)
        self.data_manager = data_manager
        self.timeline_id = timeline_id
        self.book_id = book_id
        self.current_item = None
        self.is_dirty = False # 用于追踪是否有未保存的更改

        self.setWindowTitle("编辑时间轴")
        self.setMinimumSize(1000, 700)

        main_layout = QVBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)
        
        # --- Left Panel ---
        left_panel = self._create_left_panel()
        
        # --- Right Panel ---
        right_panel = self._create_right_panel()

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([350, 650])
        
        dialog_buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel, self)
        dialog_buttons.accepted.connect(self.save_and_close)
        dialog_buttons.rejected.connect(self.reject)
        
        main_layout.addWidget(splitter)
        main_layout.addWidget(dialog_buttons)
        self.setLayout(main_layout)

        self._connect_signals()
        self.load_events()

    def _create_left_panel(self):
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        toolbar = QToolBar()
        add_event_action = QAction("添加事件", self)
        add_event_action.triggered.connect(self.add_event)
        remove_event_action = QAction("删除事件", self)
        remove_event_action.triggered.connect(self.remove_event)
        # vvvvvvvvvv [新增] 添加提升和降低层级的操作 vvvvvvvvvv
        promote_action = QAction("提升层级", self)
        promote_action.triggered.connect(self.promote_event)
        demote_action = QAction("降低层级", self)
        demote_action.triggered.connect(self.demote_event)
        # ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        toolbar.addAction(add_event_action)
        toolbar.addAction(remove_event_action)
        # vvvvvvvvvv [新增] 将操作添加到工具栏 vvvvvvvvvv
        toolbar.addSeparator()
        toolbar.addAction(promote_action)
        toolbar.addAction(demote_action)
        # ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        
        self.tree_view = QTreeView()
        self.tree_view.setHeaderHidden(True)
        self.tree_model = QStandardItemModel()
        self.tree_view.setModel(self.tree_model)
        self.tree_view.setDragDropMode(QTreeView.InternalMove)
        self.tree_view.setSelectionMode(QTreeView.SingleSelection)
        self.tree_model.rowsMoved.connect(lambda: self.set_dirty(True))

        left_layout.addWidget(toolbar)
        left_layout.addWidget(self.tree_view)
        return left_panel

    def _create_right_panel(self):
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        form_layout = QFormLayout()

        self.title_edit = QLineEdit()
        self.time_edit = QLineEdit()
        self.status_combo = QComboBox()
        self.status_combo.addItems(["未开始", "进行中", "已完成", "关键节点"])
        self.content_edit = QTextEdit()
        
        form_layout.addRow("标题:", self.title_edit)
        form_layout.addRow("时间点:", self.time_edit)
        form_layout.addRow("状态:", self.status_combo)
        form_layout.addRow("详细内容:", self.content_edit)
        
        right_layout.addLayout(form_layout)
        return right_panel

    def _connect_signals(self):
        self.tree_view.selectionModel().currentChanged.connect(self.on_event_selected)
        self.title_edit.textChanged.connect(lambda: self.set_dirty(True))
        self.time_edit.textChanged.connect(lambda: self.set_dirty(True))
        self.status_combo.currentTextChanged.connect(lambda: self.set_dirty(True))
        self.content_edit.textChanged.connect(lambda: self.set_dirty(True))

    def set_dirty(self, dirty=True):
        self.is_dirty = dirty

    def load_events(self):
        self.tree_model.clear()
        events = self.data_manager.get_timeline_events(self.timeline_id)
        
        item_map = {}
        root_item = self.tree_model.invisibleRootItem()
        
        # 先创建所有 item
        for event in events:
            # vvvvvvvvvv [修改] 显示时间点和标题 vvvvvvvvvv
            display_text = f"[{event.get('event_time', '')}] {event['title']}"
            item = QStandardItem(display_text)
            # ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
            item.setData(event, Qt.UserRole)
            item.setEditable(False)
            item_map[event['id']] = item

        # 再构建树结构
        for event in events:
            item = item_map[event['id']]
            parent_id = event.get('parent_id')
            if parent_id and parent_id in item_map:
                parent_item = item_map[parent_id]
                parent_item.appendRow(item)
            else:
                root_item.appendRow(item)

        self.tree_view.expandAll()
        self.set_dirty(False)

    def on_event_selected(self, current_index, previous_index):
        if self.is_dirty:
            self.save_current_event_details(previous_index)
        
        if not current_index.isValid():
            self.current_item = None
            self.clear_editor_fields()
            return
            
        self.current_item = self.tree_model.itemFromIndex(current_index)
        event_data = self.current_item.data(Qt.UserRole)
        
        self.title_edit.setText(event_data.get('title', ''))
        self.time_edit.setText(event_data.get('event_time', ''))
        self.status_combo.setCurrentText(event_data.get('status', '未开始'))
        self.content_edit.setText(event_data.get('content', ''))
        
        self.set_dirty(False)

    def save_current_event_details(self, index_to_save):
        if not index_to_save.isValid(): return
        
        item_to_save = self.tree_model.itemFromIndex(index_to_save)
        if not item_to_save: return

        data = item_to_save.data(Qt.UserRole)
        data['title'] = self.title_edit.text()
        data['event_time'] = self.time_edit.text()
        data['status'] = self.status_combo.currentText()
        data['content'] = self.content_edit.toPlainText()
        
        # vvvvvvvvvv [修改] 更新 item 显示文本 vvvvvvvvvv
        display_text = f"[{data.get('event_time', '')}] {data['title']}"
        item_to_save.setText(display_text)
        # ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        item_to_save.setData(data, Qt.UserRole)
        self.set_dirty(True)

    def clear_editor_fields(self):
        self.title_edit.clear()
        self.time_edit.clear()
        self.content_edit.clear()
        self.status_combo.setCurrentIndex(0)

    def add_event(self):
        parent_item = self.tree_model.invisibleRootItem()
        parent_id = None
        
        current_index = self.tree_view.currentIndex()
        if current_index.isValid():
            parent_item = self.tree_model.itemFromIndex(current_index)
            parent_id = parent_item.data(Qt.UserRole)['id']

        new_event = {
            "id": int(time.time() * 1000), # 临时唯一ID
            "timeline_id": self.timeline_id,
            "parent_id": parent_id,
            "title": "新事件",
            "content": "", "event_time": "",
            "status": "未开始", "referenced_materials": "[]"
        }
        # vvvvvvvvvv [修改] 创建 item 时也包含时间 vvvvvvvvvv
        display_text = f"[{new_event.get('event_time', '')}] {new_event['title']}"
        item = QStandardItem(display_text)
        # ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        item.setData(new_event, Qt.UserRole)
        parent_item.appendRow(item)
        self.tree_view.expandAll()
        self.set_dirty(True)

    def remove_event(self):
        index = self.tree_view.currentIndex()
        if not index.isValid(): return
        
        reply = QMessageBox.question(self, "确认删除", "确定要删除此事件及其所有子事件吗？", 
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.tree_model.removeRow(index.row(), index.parent())
            self.set_dirty(True)

    # vvvvvvvvvv [新增] 实现提升和降低层级的方法 vvvvvvvvvv
    def promote_event(self):
        index = self.tree_view.currentIndex()
        if not index.isValid(): return

        item = self.tree_model.itemFromIndex(index)
        parent = item.parent()

        if parent and parent != self.tree_model.invisibleRootItem():
            # 从原父节点移除
            taken_item = parent.takeRow(item.row())
            # 添加到祖父节点
            grandparent = parent.parent()
            if grandparent:
                grandparent.appendRow(taken_item)
            else:
                self.tree_model.invisibleRootItem().appendRow(taken_item)
            self.set_dirty(True)

    def demote_event(self):
        index = self.tree_view.currentIndex()
        if not index.isValid() or index.row() == 0: return

        item = self.tree_model.itemFromIndex(index)
        parent = item.parent()
        if not parent: parent = self.tree_model.invisibleRootItem()

        # 找到它上面的同级节点
        sibling_item = parent.child(item.row() - 1)
        if sibling_item:
            # 从原父节点移除
            taken_item = parent.takeRow(item.row())
            # 添加到新的父节点（原同级节点）
            sibling_item.appendRow(taken_item)
            self.tree_view.expand(sibling_item.index())
            self.set_dirty(True)
    # ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

    def save_and_close(self):
        self.save_current_event_details(self.tree_view.currentIndex())
        all_events = []
        
        def recurse_save(parent_item, parent_id=None):
            for row in range(parent_item.rowCount()):
                item = parent_item.child(row)
                if not item: continue
                data = item.data(Qt.UserRole)
                data['order_index'] = row
                data['parent_id'] = parent_id
                all_events.append(data)
                
                if 'id' in data and item.hasChildren():
                    recurse_save(item, data['id'])
        
        recurse_save(self.tree_model.invisibleRootItem())
        self.data_manager.update_timeline_events(self.timeline_id, all_events)
        QMessageBox.information(self, "成功", "时间轴已成功保存。")
        self.accept()
        
    def reject(self):
        if self.is_dirty:
            reply = QMessageBox.question(self, "确认退出", "有未保存的更改，您确定要退出吗？",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.No:
                return
        super().reject()


class TimelinePanel(QWidget):
    """时间轴面板，用于展示和管理书籍的时间轴"""
    def __init__(self, data_manager, parent=None):
        super().__init__(parent)
        self.data_manager = data_manager
        self.current_book_id = None
        
        self.layout = QVBoxLayout(self)
        self.list_widget = QListWidget()
        self.list_widget.doubleClicked.connect(self.edit_selected_timeline)
        
        button_layout = QHBoxLayout()
        add_button = QPushButton("新建时间轴")
        add_button.clicked.connect(self.add_timeline)
        edit_button = QPushButton("编辑选中")
        edit_button.clicked.connect(self.edit_selected_timeline)
        
        button_layout.addWidget(add_button)
        button_layout.addWidget(edit_button)
        
        self.layout.addWidget(QLabel("本书的时间轴:"))
        self.layout.addWidget(self.list_widget)
        self.layout.addLayout(button_layout)
        
    def set_book(self, book_id):
        self.current_book_id = book_id
        self.load_timelines()

    def load_timelines(self):
        self.list_widget.clear()
        if not self.current_book_id: return
        
        timelines = self.data_manager.get_timelines_for_book(self.current_book_id)
        for tl in timelines:
            item = QListWidgetItem(tl['name'])
            item.setData(Qt.UserRole, tl['id'])
            self.list_widget.addItem(item)
            
    def add_timeline(self):
        if not self.current_book_id: return
        name, ok = QInputDialog.getText(self, "新建时间轴", "请输入时间轴名称:")
        if ok and name:
            self.data_manager.add_timeline(self.current_book_id, name)
            self.load_timelines()
            
    def edit_selected_timeline(self):
        selected_item = self.list_widget.currentItem()
        if not selected_item: 
            QMessageBox.warning(self, "提示", "请先选择一个时间轴。")
            return
        
        timeline_id = selected_item.data(Qt.UserRole)
        dialog = TimelineEditDialog(self.data_manager, timeline_id, self.current_book_id, self)
        dialog.exec()
        self.load_timelines() # 刷新列表以防名称等被更改