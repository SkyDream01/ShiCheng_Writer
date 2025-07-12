# ShiCheng_Writer/modules/settings_system.py
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QTreeView, QPushButton, 
                               QLineEdit, QComboBox, QTextEdit, QDialog, 
                               QFormLayout, QDialogButtonBox, QLabel)
from PySide6.QtGui import QStandardItemModel, QStandardItem
from PySide6.QtCore import Qt

class SettingsPanel(QWidget):
    """设定面板，用于展示和管理设定"""
    def __init__(self, data_manager, parent=None):
        super().__init__(parent)
        self.data_manager = data_manager
        self.current_book_id = None

        self.setWindowTitle("设定仓库")
        self.layout = QVBoxLayout(self)

        self.tree_view = QTreeView()
        self.tree_view.setHeaderHidden(True)
        self.model = QStandardItemModel()
        self.tree_view.setModel(self.model)
        
        self.add_button = QPushButton("添加新设定")
        self.add_button.clicked.connect(self.open_add_setting_dialog)
        
        self.layout.addWidget(QLabel("全局设定 & 本书设定:"))
        self.layout.addWidget(self.tree_view)
        self.layout.addWidget(self.add_button)
        
    def set_book(self, book_id):
        self.current_book_id = book_id
        self.load_settings()

    def load_settings(self):
        self.model.clear()
        if self.current_book_id is None:
            return
            
        settings = self.data_manager.get_settings(self.current_book_id)
        
        global_root = QStandardItem("全局设定")
        book_root = QStandardItem("本书设定")
        
        for setting in settings:
            item = QStandardItem(f"{setting['name']} ({setting['type']})")
            item.setEditable(False)
            item.setData(setting['id'], Qt.UserRole)
            if setting['book_id'] is None:
                global_root.appendRow(item)
            else:
                book_root.appendRow(item)
        
        if global_root.rowCount() > 0:
            self.model.appendRow(global_root)
        if book_root.rowCount() > 0:
            self.model.appendRow(book_root)

    def open_add_setting_dialog(self):
        if self.current_book_id is None:
            return
            
        dialog = AddSettingDialog(self)
        if dialog.exec():
            details = dialog.get_details()
            # 决定是全局还是本书设定
            is_global = details.pop('is_global')
            book_id = None if is_global else self.current_book_id
            
            self.data_manager.add_setting(**details, book_id=book_id)
            self.load_settings() # 重新加载

class AddSettingDialog(QDialog):
    """添加设定的对话框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("创建新设定")
        
        self.form_layout = QFormLayout(self)
        
        self.name_edit = QLineEdit()
        self.type_combo = QComboBox()
        self.type_combo.addItems(['文本', '对象', '模板', '列表'])
        self.description_edit = QTextEdit()
        self.scope_combo = QComboBox()
        self.scope_combo.addItems(['本书设定', '全局设定'])
        
        self.form_layout.addRow("名称:", self.name_edit)
        self.form_layout.addRow("类型:", self.type_combo)
        self.form_layout.addRow("范围:", self.scope_combo)
        self.form_layout.addRow("描述:", self.description_edit)
        
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        
        self.form_layout.addWidget(self.buttons)

    def get_details(self):
        return {
            "name": self.name_edit.text(),
            "type": self.type_combo.currentText().lower(),
            "description": self.description_edit.toPlainText(),
            "is_global": self.scope_combo.currentIndex() == 1
        }