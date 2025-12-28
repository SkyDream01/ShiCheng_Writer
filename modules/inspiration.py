# ShiCheng_Writer/modules/inspiration.py
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QLabel, QTabWidget, 
                               QListWidget, QListWidgetItem, QInputDialog, QMessageBox,
                               QTreeView, QMenu, QAbstractItemView, QDialog, QTextEdit,
                               QDialogButtonBox, QApplication)
from PySide6.QtGui import QStandardItemModel, QStandardItem, QAction, QCursor
from PySide6.QtCore import Qt

class InspirationPanel(QWidget):
    """灵感面板，包含灵感锦囊和灵感仓库"""
    def __init__(self, data_manager, parent=None):
        super().__init__(parent)
        self.data_manager = data_manager
        self.setWindowTitle("灵感中心")
        
        self.layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.layout.addWidget(self.tabs)
        
        # 创建两个子面板
        self.kit_panel = InspirationKitPanel(self.data_manager)
        self.warehouse_panel = InspirationWarehousePanel(self.data_manager)
        
        self.tabs.addTab(self.kit_panel, "灵感锦囊")
        self.tabs.addTab(self.warehouse_panel, "灵感仓库")

    def refresh_all(self):
        """刷新所有数据"""
        self.kit_panel.load_fragments()
        self.warehouse_panel.load_items()

class InspirationKitPanel(QWidget):
    """灵感锦囊（未整理的灵感 - 增加右键菜单和双击编辑）"""
    def __init__(self, data_manager, parent=None):
        super().__init__(parent)
        self.data_manager = data_manager
        
        layout = QVBoxLayout(self)
        
        add_button = QPushButton("快速记录灵感 (+)")
        add_button.clicked.connect(self.add_fragment)
        
        self.list_widget = QListWidget()
        self.list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self.show_context_menu)
        self.list_widget.itemDoubleClicked.connect(self.edit_fragment)
        
        layout.addWidget(add_button)
        layout.addWidget(QLabel("灵感碎片 (双击编辑，右键菜单)"))
        layout.addWidget(self.list_widget)
        
        self.load_fragments()

    def load_fragments(self):
        self.list_widget.clear()
        fragments = self.data_manager.get_inspiration_fragments()
        for frag in fragments:
            # 显示前50个字符
            content_preview = frag['content'].replace('\n', ' ')
            if len(content_preview) > 50:
                content_preview = content_preview[:50] + "..."
            
            item = QListWidgetItem(f"[{frag['type']}] {content_preview}")
            item.setToolTip(frag['content']) # 悬浮显示全文
            item.setData(Qt.UserRole, frag)  # 存储完整数据对象
            self.list_widget.addItem(item)
            
    def add_fragment(self):
        text, ok = QInputDialog.getMultiLineText(self, "记录灵感", "写下你的想法：")
        if ok and text:
            self.data_manager.add_inspiration_fragment('text', text, '快速记录')
            self.load_fragments()

    def show_context_menu(self, pos):
        item = self.list_widget.itemAt(pos)
        if not item: return

        menu = QMenu()
        edit_action = menu.addAction("编辑")
        copy_action = menu.addAction("复制内容")
        menu.addSeparator()
        delete_action = menu.addAction("删除")

        action = menu.exec(self.list_widget.mapToGlobal(pos))

        if action == edit_action:
            self.edit_fragment(item)
        elif action == copy_action:
            frag = item.data(Qt.UserRole)
            QApplication.clipboard().setText(frag['content'])
        elif action == delete_action:
            self.delete_fragment(item)

    def edit_fragment(self, item):
        frag = item.data(Qt.UserRole)
        text, ok = QInputDialog.getMultiLineText(self, "编辑灵感", "修改你的想法：", text=frag['content'])
        if ok and text and text != frag['content']:
            # 需要在 database.py 中实现 update_inspiration_fragment
            if hasattr(self.data_manager, 'update_inspiration_fragment'):
                self.data_manager.update_inspiration_fragment(frag['id'], text)
                self.load_fragments()
            else:
                QMessageBox.warning(self, "未实现", "数据库缺少更新功能 (update_inspiration_fragment)。")

    def delete_fragment(self, item):
        frag = item.data(Qt.UserRole)
        if QMessageBox.question(self, "删除", "确定删除这条灵感吗？") == QMessageBox.Yes:
            # 需要在 database.py 中实现 delete_inspiration_fragment
            if hasattr(self.data_manager, 'delete_inspiration_fragment'):
                self.data_manager.delete_inspiration_fragment(frag['id'])
                self.load_fragments()
            else:
                # 兼容性回退：如果没这个方法，提示用户
                QMessageBox.warning(self, "未实现", "数据库缺少删除功能 (delete_inspiration_fragment)。")

class InspirationWarehousePanel(QWidget):
    """灵感仓库（增加右键菜单：删除、重命名）"""
    def __init__(self, data_manager, parent=None):
        super().__init__(parent)
        self.data_manager = data_manager
        
        layout = QVBoxLayout(self)
        
        add_button = QPushButton("新建灵感条目 (+)")
        add_button.clicked.connect(self.add_item)

        self.tree_view = QTreeView()
        self.tree_view.setHeaderHidden(True)
        self.model = QStandardItemModel()
        self.tree_view.setModel(self.model)
        self.tree_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree_view.customContextMenuRequested.connect(self.show_context_menu)
        self.tree_view.doubleClicked.connect(self.on_double_click)

        layout.addWidget(add_button)
        layout.addWidget(QLabel("灵感资料库 (右键管理)"))
        layout.addWidget(self.tree_view)
        
        self.load_items()

    def load_items(self):
        self.model.clear()
        items = self.data_manager.get_inspiration_items()
        
        item_dict = {None: self.model.invisibleRootItem()}
        
        # 简单的按 parent_id 排序确保父节点先创建
        items.sort(key=lambda x: (x['parent_id'] if x['parent_id'] is not None else -1))

        for item_data in items:
            parent_id = item_data['parent_id']
            if parent_id not in item_dict:
                # 如果父节点还没加载（可能是乱序），暂时挂在根节点或忽略
                parent_id = None
                
            parent_item = item_dict[parent_id]
            new_item = QStandardItem(item_data['title'])
            new_item.setData(item_data, Qt.UserRole)
            new_item.setEditable(False)
            parent_item.appendRow(new_item)
            item_dict[item_data['id']] = new_item
            
        self.tree_view.expandAll()

    def add_item(self):
        title, ok = QInputDialog.getText(self, "新建灵感", "请输入标题：")
        if ok and title:
            self.data_manager.add_inspiration_item(title=title)
            self.load_items()

    def show_context_menu(self, pos):
        index = self.tree_view.indexAt(pos)
        menu = QMenu()
        
        if index.isValid():
            rename_action = menu.addAction("重命名")
            edit_content_action = menu.addAction("编辑详情")
            menu.addSeparator()
            delete_action = menu.addAction("删除")
            
            action = menu.exec(self.tree_view.viewport().mapToGlobal(pos))
            
            if action == rename_action:
                self.rename_item(index)
            elif action == edit_content_action:
                self.edit_item_content(index)
            elif action == delete_action:
                self.delete_item(index)
        else:
            # 空白处右键
            add_action = menu.addAction("新建根条目")
            action = menu.exec(self.tree_view.viewport().mapToGlobal(pos))
            if action == add_action:
                self.add_item()

    def on_double_click(self, index):
        self.edit_item_content(index)

    def rename_item(self, index):
        item = self.model.itemFromIndex(index)
        data = item.data(Qt.UserRole)
        new_title, ok = QInputDialog.getText(self, "重命名", "新标题:", text=data['title'])
        if ok and new_title:
             if hasattr(self.data_manager, 'update_inspiration_item'):
                # 假设 update 接口: id, title=..., content=...
                self.data_manager.update_inspiration_item(data['id'], title=new_title)
                self.load_items()
             else:
                QMessageBox.warning(self, "提示", "请在 Database 中实现 update_inspiration_item。")

    def edit_item_content(self, index):
        item = self.model.itemFromIndex(index)
        data = item.data(Qt.UserRole)
        
        dialog = QDialog(self)
        dialog.setWindowTitle(f"编辑: {data['title']}")
        dialog.resize(500, 400)
        layout = QVBoxLayout(dialog)
        
        text_edit = QTextEdit()
        text_edit.setPlainText(data.get('content', ''))
        layout.addWidget(text_edit)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        
        if dialog.exec():
            new_content = text_edit.toPlainText()
            if hasattr(self.data_manager, 'update_inspiration_item'):
                self.data_manager.update_inspiration_item(data['id'], content=new_content)
                self.load_items()

    def delete_item(self, index):
        item = self.model.itemFromIndex(index)
        data = item.data(Qt.UserRole)
        if QMessageBox.question(self, "删除", f"确定删除 '{data['title']}' 吗？") == QMessageBox.Yes:
            if hasattr(self.data_manager, 'delete_inspiration_item'):
                self.data_manager.delete_inspiration_item(data['id'])
                self.load_items()
            else:
                QMessageBox.warning(self, "提示", "请在 Database 中实现 delete_inspiration_item。")