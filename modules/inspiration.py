# ShiCheng_Writer/modules/inspiration.py
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QLabel, QTabWidget, 
                               QListWidget, QListWidgetItem, QInputDialog, QMessageBox,
                               QTreeView, QMenu)
from PySide6.QtGui import QStandardItemModel, QStandardItem, QAction
from PySide6.QtCore import Qt

# data_manager 将从主窗口传入
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
    """灵感锦囊（未整理的灵感）"""
    def __init__(self, data_manager, parent=None):
        super().__init__(parent)
        self.data_manager = data_manager
        
        layout = QVBoxLayout(self)
        
        add_button = QPushButton("快速记录灵感")
        add_button.clicked.connect(self.add_fragment)
        
        self.list_widget = QListWidget()
        
        layout.addWidget(add_button)
        layout.addWidget(QLabel("存放未整理的灵感碎片(文本/图片/音频)"))
        layout.addWidget(self.list_widget)
        
        self.load_fragments()

    def load_fragments(self):
        self.list_widget.clear()
        fragments = self.data_manager.get_inspiration_fragments()
        for frag in fragments:
            # 简化显示
            item = QListWidgetItem(f"[{frag['type']}] {frag['content'][:50]}...")
            item.setData(Qt.UserRole, frag['id'])
            self.list_widget.addItem(item)
            
    def add_fragment(self):
        text, ok = QInputDialog.getText(self, "记录灵感", "写下你的想法：")
        if ok and text:
            self.data_manager.add_inspiration_fragment('text', text, '快速记录')
            self.load_fragments()
            QMessageBox.information(self, "成功", "灵感已存入锦囊！")

class InspirationWarehousePanel(QWidget):
    """灵感仓库（已整理的灵感）"""
    def __init__(self, data_manager, parent=None):
        super().__init__(parent)
        self.data_manager = data_manager
        
        layout = QVBoxLayout(self)
        
        add_button = QPushButton("新建灵感/资料")
        add_button.clicked.connect(self.add_item)

        self.tree_view = QTreeView()
        self.tree_view.setHeaderHidden(True)
        self.model = QStandardItemModel()
        self.tree_view.setModel(self.model)

        layout.addWidget(add_button)
        layout.addWidget(QLabel("以文件管理的形式存放已整理的灵感资料"))
        layout.addWidget(self.tree_view)
        
        self.load_items()

    def load_items(self):
        self.model.clear()
        items = self.data_manager.get_inspiration_items()
        
        # 使用字典来快速查找父项
        item_dict = {None: self.model.invisibleRootItem()}
        
        for item_data in items:
            parent_id = item_data['parent_id']
            if parent_id not in item_dict:
                # 如果父项还没处理，先跳过（理论上排序后不会发生）
                continue
                
            parent_item = item_dict[parent_id]
            new_item = QStandardItem(item_data['title'])
            new_item.setData(item_data['id'], Qt.UserRole)
            new_item.setEditable(False)
            parent_item.appendRow(new_item)
            item_dict[item_data['id']] = new_item
            
    def add_item(self):
        title, ok = QInputDialog.getText(self, "新建灵感", "请输入标题：")
        if ok and title:
            # 简化：默认添加到根目录
            self.data_manager.add_inspiration_item(title=title)
            self.load_items()