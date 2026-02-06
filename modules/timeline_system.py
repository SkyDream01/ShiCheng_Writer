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
        promote_action = QAction("提升层级", self)
        promote_action.triggered.connect(self.promote_event)
        demote_action = QAction("降低层级", self)
        demote_action.triggered.connect(self.demote_event)
        toolbar.addAction(add_event_action)
        toolbar.addAction(remove_event_action)
        toolbar.addSeparator()
        toolbar.addAction(promote_action)
        toolbar.addAction(demote_action)
        
        self.tree_view = QTreeView()
        self.tree_view.setHeaderHidden(True)
        self.tree_model = QStandardItemModel()
        self.tree_view.setModel(self.tree_model)
        self.tree_view.setDragDropMode(QTreeView.InternalMove)
        self.tree_view.setSelectionMode(QTreeView.SingleSelection)
        # 核心功能：当行移动（拖拽完成）后，连接到 on_rows_moved 函数
        self.tree_model.rowsMoved.connect(self.on_rows_moved)

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
        self.title_edit.textChanged.connect(self.on_title_or_time_changed)
        self.time_edit.textChanged.connect(self.on_title_or_time_changed)
        self.status_combo.currentTextChanged.connect(lambda: self.set_dirty(True))
        self.content_edit.textChanged.connect(lambda: self.set_dirty(True))

    def set_dirty(self, dirty=True):
        self.is_dirty = dirty

    def _generate_unique_id(self):
        """生成唯一的数字ID，使用计数器确保唯一性"""
        import itertools
        if not hasattr(self, '_id_counter'):
            self._id_counter = itertools.count(int(time.time() * 1000))
        
        # 获取当前所有ID
        existing_ids = set()
        root = self.tree_model.invisibleRootItem()
        
        def traverse(parent_item):
            for i in range(parent_item.rowCount()):
                item = parent_item.child(i)
                data = item.data(Qt.UserRole)
                if data and 'id' in data:
                    existing_ids.add(data['id'])
                if item.hasChildren():
                    traverse(item)
        
        traverse(root)
        
        # 确保ID唯一
        while True:
            new_id = next(self._id_counter)
            if new_id not in existing_ids:
                return new_id

    def on_rows_moved(self, parent, start, end, destination, dest_row):
        """当行被拖拽移动后触发，实现编号实时更新"""
        self.update_item_numbers()
        self.set_dirty(True)

    def update_item_numbers(self):
        """遍历整个树，更新所有项目的层级编号和显示文本"""
        root = self.tree_model.invisibleRootItem()
        
        def traverse(parent_item, prefix=""):
            for i in range(parent_item.rowCount()):
                item = parent_item.child(i)
                if not item: continue
                event_data = item.data(Qt.UserRole)
                if not event_data: continue
                
                # 构建新的编号和显示文本
                number = f"{prefix}{i + 1}"
                display_text = f"{number}. [{event_data.get('event_time', '')}] {event_data.get('title', '无标题')}"
                item.setText(display_text)

                # 递归处理子节点
                if item.hasChildren():
                    traverse(item, prefix=f"{number}.")
        
        traverse(root)

    def load_events(self):
        """从数据库加载事件并构建树"""
        self.tree_model.clear()
        events = self.data_manager.get_timeline_events(self.timeline_id)
        
        item_map = {}
        root_item = self.tree_model.invisibleRootItem()
        
        # 第一次遍历：创建所有item
        for event in events:
            item = QStandardItem(event['title']) # 临时标题
            item.setData(event, Qt.UserRole)
            item.setEditable(False)
            item_map[event['id']] = item

        # 第二次遍历：构建父子关系
        for event in events:
            item = item_map[event['id']]
            parent_id = event.get('parent_id')
            if parent_id and parent_id in item_map:
                parent_item = item_map[parent_id]
                parent_item.appendRow(item)
            else:
                root_item.appendRow(item)

        self.tree_view.expandAll()
        self.update_item_numbers() # 初始化编号
        self.set_dirty(False)

    def on_event_selected(self, current_index, previous_index):
        """当选择的事件变化时触发"""
        if self.is_dirty and previous_index.isValid():
            self.save_current_event_details(previous_index)
        
        if not current_index.isValid():
            self.current_item = None
            self.clear_editor_fields()
            return
            
        self.current_item = self.tree_model.itemFromIndex(current_index)
        event_data = self.current_item.data(Qt.UserRole)
        
        # 暂时禁用信号，避免填充数据时触发不必要的操作
        self.title_edit.blockSignals(True)
        self.time_edit.blockSignals(True)

        self.title_edit.setText(event_data.get('title', ''))
        self.time_edit.setText(event_data.get('event_time', ''))
        self.status_combo.setCurrentText(event_data.get('status', '未开始'))
        self.content_edit.setText(event_data.get('content', ''))
        
        self.title_edit.blockSignals(False)
        self.time_edit.blockSignals(False)

        self.set_dirty(False)

    def on_title_or_time_changed(self):
        """当标题或时间点文本框变化时，实时更新树视图中的项目文本"""
        if not self.current_item: return
        self.set_dirty(True)

        # 更新数据模型中的数据
        data = self.current_item.data(Qt.UserRole)
        data['title'] = self.title_edit.text()
        data['event_time'] = self.time_edit.text()
        self.current_item.setData(data, Qt.UserRole)
        
        # 刷新整个树的编号和显示
        self.update_item_numbers()

    def save_current_event_details(self, index_to_save):
        """保存当前编辑区的内容到对应的Item中"""
        if not index_to_save.isValid(): return
        
        item_to_save = self.tree_model.itemFromIndex(index_to_save)
        if not item_to_save: return

        data = item_to_save.data(Qt.UserRole)
        data['status'] = self.status_combo.currentText()
        data['content'] = self.content_edit.toPlainText()
        # 标题和时间点已在 on_title_or_time_changed 中实时保存
        
        item_to_save.setData(data, Qt.UserRole)

    def clear_editor_fields(self):
        """清空右侧编辑面板"""
        self.title_edit.clear()
        self.time_edit.clear()
        self.content_edit.clear()
        self.status_combo.setCurrentIndex(0)

    def add_event(self):
        """添加新事件"""
        parent_item = self.tree_model.invisibleRootItem()
        parent_id = None
        
        current_index = self.tree_view.currentIndex()
        if current_index.isValid():
            selected_item = self.tree_model.itemFromIndex(current_index)
            # 智能判断：如果选中项是叶子节点，则作为兄弟节点添加，否则作为子节点
            if selected_item.hasChildren():
                parent_item = selected_item
                parent_id = parent_item.data(Qt.UserRole)['id']
            else:
                parent_item = selected_item.parent() or self.tree_model.invisibleRootItem()
                if selected_item.parent():
                    parent_id = selected_item.parent().data(Qt.UserRole)['id']

        new_event = {
            "id": self._generate_unique_id(),
            "timeline_id": self.timeline_id,
            "parent_id": parent_id,
            "title": "新事件",
            "content": "", "event_time": "",
            "status": "未开始", "referenced_materials": "[]"
        }
        item = QStandardItem()
        item.setData(new_event, Qt.UserRole)
        parent_item.appendRow(item)

        self.tree_view.expandAll()
        self.update_item_numbers()
        self.set_dirty(True)

    def remove_event(self):
        """删除选中事件"""
        index = self.tree_view.currentIndex()
        if not index.isValid(): return
        
        reply = QMessageBox.question(self, "确认删除", "确定要删除此事件及其所有子事件吗？", 
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.tree_model.removeRow(index.row(), index.parent())
            self.update_item_numbers()
            self.set_dirty(True)

    def promote_event(self):
        """提升层级"""
        index = self.tree_view.currentIndex()
        if not index.isValid(): return

        item = self.tree_model.itemFromIndex(index)
        parent = item.parent()

        if parent and parent != self.tree_model.invisibleRootItem():
            taken_item = parent.takeRow(item.row())[0] # takeRow returns a list
            grandparent = parent.parent() or self.tree_model.invisibleRootItem()
            grandparent.appendRow(taken_item)
            
            self.update_item_numbers()
            self.set_dirty(True)

    def demote_event(self):
        """降低层级"""
        index = self.tree_view.currentIndex()
        if not index.isValid() or index.row() == 0: return # 根节点或第一个子节点不能降级

        item = self.tree_model.itemFromIndex(index)
        parent = item.parent() or self.tree_model.invisibleRootItem()

        # 成为前一个兄弟节点的子节点
        sibling_item = parent.child(item.row() - 1)
        if sibling_item:
            taken_item = parent.takeRow(item.row())[0]
            sibling_item.appendRow(taken_item)
            self.tree_view.expand(sibling_item.index())
            self.update_item_numbers()
            self.set_dirty(True)

    def save_and_close(self):
        """保存所有更改并关闭对话框"""
        current_index = self.tree_view.currentIndex()
        if self.is_dirty and current_index.isValid():
            self.save_current_event_details(current_index)

        all_events = []
        
        def recurse_save(parent_item, parent_id=None):
            for row in range(parent_item.rowCount()):
                item = parent_item.child(row, 0)
                if not item: continue
                
                data = item.data(Qt.UserRole)
                data['order_index'] = row
                data['parent_id'] = parent_id
                all_events.append(data)
                
                if item.hasChildren():
                    recurse_save(item, data['id'])
        
        recurse_save(self.tree_model.invisibleRootItem())
        self.data_manager.update_timeline_events(self.timeline_id, all_events)
        QMessageBox.information(self, "成功", "时间轴已成功保存。")
        self.accept()
        
    def reject(self):
        """关闭对话框，若有未保存更改则提示"""
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
            
    def edit_selected_timeline(self, item=None):
        selected_item = self.list_widget.currentItem()
        if not selected_item: 
            QMessageBox.warning(self, "提示", "请先选择一个时间轴。")
            return
        
        timeline_id = selected_item.data(Qt.UserRole)
        dialog = TimelineEditDialog(self.data_manager, timeline_id, self.current_book_id, self)
        dialog.exec()
        self.load_timelines() # 刷新列表