# ShiCheng_Writer/modules/settings_system.py
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QTreeView, QPushButton, QHBoxLayout,
                               QLineEdit, QComboBox, QTextEdit, QDialog, QMenu,
                               QFormLayout, QDialogButtonBox, QLabel, QMessageBox,
                               QTableWidget, QTableWidgetItem, QHeaderView)
from PySide6.QtGui import QStandardItemModel, QStandardItem, QAction
from PySide6.QtCore import Qt, Signal

class SettingEditDialog(QDialog):
    """
    一个功能强大的对话框，用于添加和编辑设定。
    根据设定的类型（文本、对象、模板、列表）动态生成不同的编辑界面。
    """
    def __init__(self, data_manager, setting_id=None, book_id=None, parent=None):
        super().__init__(parent)
        self.data_manager = data_manager
        self.setting_id = setting_id
        self.current_book_id = book_id
        self.is_new = (setting_id is None)

        self.setWindowTitle("编辑设定" if not self.is_new else "创建新设定")
        self.setMinimumSize(500, 450)

        # 主布局
        self.main_layout = QVBoxLayout(self)
        
        # 基础信息表单
        self.form_layout = QFormLayout()
        self.name_edit = QLineEdit()
        self.type_combo = QComboBox()
        self.type_combo.addItems(['文本', '对象', '模板', '列表'])
        self.scope_combo = QComboBox()
        self.scope_combo.addItems(['本书设定', '全局设定'])
        self.description_edit = QTextEdit()
        
        self.form_layout.addRow("名称:", self.name_edit)
        self.form_layout.addRow("类型:", self.type_combo)
        self.form_layout.addRow("范围:", self.scope_combo)
        self.form_layout.addRow("描述:", self.description_edit)
        
        self.main_layout.addLayout(self.form_layout)

        # 动态内容区域
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.main_layout.addWidget(self.content_widget)

        # 按钮
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        self.main_layout.addWidget(self.buttons)

        # 信号连接
        self.type_combo.currentTextChanged.connect(self.setup_content_ui)
        self.buttons.accepted.connect(self.save_setting)
        self.buttons.rejected.connect(self.reject)

        self.load_setting_data()
    
    def load_setting_data(self):
        if self.is_new:
            self.setup_content_ui(self.type_combo.currentText())
            return

        self.setting_data = self.data_manager.get_setting_details(self.setting_id)
        if not self.setting_data:
            QMessageBox.critical(self, "错误", "无法加载设定信息。")
            self.reject()
            return
            
        self.name_edit.setText(self.setting_data.get('name', ''))
        self.description_edit.setText(self.setting_data.get('description', ''))
        
        self.type_combo.setCurrentText(self.setting_data.get('type', '文本'))
        self.type_combo.setEnabled(False) 

        is_global = self.setting_data.get('book_id') is None
        self.scope_combo.setCurrentIndex(1 if is_global else 0)
        self.scope_combo.setEnabled(False)
        
        self.setup_content_ui(self.type_combo.currentText())

    def clear_layout(self, layout):
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def setup_content_ui(self, type_name):
        self.clear_layout(self.content_layout)
        
        content = self.setting_data.get('content', {}) if hasattr(self, 'setting_data') and self.setting_data else {}

        if type_name == '文本':
            self.text_content_edit = QTextEdit()
            self.text_content_edit.setPlaceholderText("在此输入设定的详细文本内容...")
            if not self.is_new:
                 self.text_content_edit.setText(content.get('value', ''))
            self.content_layout.addWidget(QLabel("文本内容:"))
            self.content_layout.addWidget(self.text_content_edit)

        elif type_name in ['对象', '模板']:
            self.attributes_table = QTableWidget()
            self.attributes_table.setColumnCount(2)
            self.attributes_table.setHorizontalHeaderLabels(["属性名", "属性值"])
            self.attributes_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            
            attributes = content.get('attributes', []) if not self.is_new else []
            self.attributes_table.setRowCount(len(attributes))
            for i, attr in enumerate(attributes):
                self.attributes_table.setItem(i, 0, QTableWidgetItem(attr.get('name', '')))
                self.attributes_table.setItem(i, 1, QTableWidgetItem(str(attr.get('value', ''))))

            self.content_layout.addWidget(self.attributes_table)
            
            button_layout = QHBoxLayout()
            add_attr_button = QPushButton("添加属性")
            add_attr_button.clicked.connect(lambda: self.attributes_table.insertRow(self.attributes_table.rowCount()))
            remove_attr_button = QPushButton("删除选中属性")
            remove_attr_button.clicked.connect(lambda: self.attributes_table.removeRow(self.attributes_table.currentRow()))
            button_layout.addWidget(add_attr_button)
            button_layout.addWidget(remove_attr_button)
            self.content_layout.addLayout(button_layout)

        elif type_name == '列表':
            self.list_items_table = QTableWidget()
            self.list_items_table.setColumnCount(1)
            self.list_items_table.setHorizontalHeaderLabels(["值"])
            self.list_items_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

            items = content.get('items', []) if not self.is_new else []
            self.list_items_table.setRowCount(len(items))
            for i, item_val in enumerate(items):
                self.list_items_table.setItem(i, 0, QTableWidgetItem(item_val))
            
            self.content_layout.addWidget(self.list_items_table)
            
            button_layout = QHBoxLayout()
            add_item_button = QPushButton("添加列表项")
            add_item_button.clicked.connect(lambda: self.list_items_table.insertRow(self.list_items_table.rowCount()))
            remove_item_button = QPushButton("删除选中项")
            remove_item_button.clicked.connect(lambda: self.list_items_table.removeRow(self.list_items_table.currentRow()))
            button_layout.addWidget(add_item_button)
            button_layout.addWidget(remove_item_button)
            self.content_layout.addLayout(button_layout)
    
    def save_setting(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "输入错误", "设定名称不能为空。")
            return
            
        type = self.type_combo.currentText()
        description = self.description_edit.toPlainText()
        is_global = self.scope_combo.currentIndex() == 1
        book_id = None if is_global else self.current_book_id
        
        content = {}
        if type == '文本':
            content['value'] = self.text_content_edit.toPlainText()
        elif type in ['对象', '模板']:
            attributes = []
            for i in range(self.attributes_table.rowCount()):
                name_item = self.attributes_table.item(i, 0)
                value_item = self.attributes_table.item(i, 1)
                if name_item and name_item.text():
                    attributes.append({
                        'name': name_item.text(),
                        'value': value_item.text() if value_item else ''
                    })
            content['attributes'] = attributes
        elif type == '列表':
            items = []
            for i in range(self.list_items_table.rowCount()):
                item = self.list_items_table.item(i, 0)
                if item and item.text():
                    items.append(item.text())
            content['items'] = items

        if self.is_new:
            if not self.data_manager.add_setting(name, type, description, book_id, content):
                QMessageBox.critical(self, "错误", f"创建设定失败。请确保在同一范围内没有重名的设定。")
                return
        else:
            if not self.data_manager.update_setting(self.setting_id, name, type, description, content):
                QMessageBox.critical(self, "错误", f"更新设定失败。")
                return
        
        self.accept()

class SettingsPanel(QWidget):
    """设定面板，用于展示和管理设定"""
    settings_changed = Signal()

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
        self.tree_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree_view.customContextMenuRequested.connect(self.open_context_menu)
        self.tree_view.doubleClicked.connect(self.edit_selected_setting)
        
        button_layout = QHBoxLayout()
        self.add_button = QPushButton("添加新设定")
        self.edit_button = QPushButton("编辑选中")
        self.delete_button = QPushButton("删除选中")
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.edit_button)
        button_layout.addWidget(self.delete_button)
        
        self.add_button.clicked.connect(self.add_new_setting)
        self.edit_button.clicked.connect(self.edit_selected_setting)
        self.delete_button.clicked.connect(self.delete_selected_setting)

        self.layout.addWidget(QLabel("全局设定 & 本书设定:"))
        self.layout.addWidget(self.tree_view)
        self.layout.addLayout(button_layout)
        
    def set_book(self, book_id):
        self.current_book_id = book_id
        self.load_settings()

    def load_settings(self):
        self.model.clear()
        if self.current_book_id is None:
            self.add_button.setEnabled(False)
            self.edit_button.setEnabled(False)
            self.delete_button.setEnabled(False)
            return
            
        self.add_button.setEnabled(True)
        self.edit_button.setEnabled(True)
        self.delete_button.setEnabled(True)

        settings = self.data_manager.get_settings(self.current_book_id)
        
        global_root = QStandardItem("全局设定")
        global_root.setEditable(False)
        book_root = QStandardItem("本书设定")
        book_root.setEditable(False)
        
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
        
        self.tree_view.expandAll()

    def open_context_menu(self, position):
        index = self.tree_view.indexAt(position)
        if not index.isValid() or not index.parent().isValid():  # 确保点击的是子项
            return
        
        menu = QMenu()
        edit_action = menu.addAction("编辑")
        delete_action = menu.addAction("删除")
        
        action = menu.exec(self.tree_view.viewport().mapToGlobal(position))
        
        if action == edit_action:
            self.edit_selected_setting()
        elif action == delete_action:
            self.delete_selected_setting()
            
    def get_selected_setting_id(self):
        index = self.tree_view.currentIndex()
        if not index.isValid() or not index.parent().isValid():
            return None
        item = self.model.itemFromIndex(index)
        return item.data(Qt.UserRole)

    def add_new_setting(self):
        if self.current_book_id is None:
            QMessageBox.warning(self, "提示", "请先选择一本书籍。")
            return
            
        dialog = SettingEditDialog(self.data_manager, book_id=self.current_book_id, parent=self)
        if dialog.exec():
            self.load_settings()
            self.settings_changed.emit()

    def edit_selected_setting(self):
        setting_id = self.get_selected_setting_id()
        if setting_id is None:
            QMessageBox.warning(self, "提示", "请先选择一个要编辑的设定。")
            return
        
        dialog = SettingEditDialog(self.data_manager, setting_id=setting_id, book_id=self.current_book_id, parent=self)
        if dialog.exec():
            self.load_settings()
            self.settings_changed.emit()

    def delete_selected_setting(self):
        setting_id = self.get_selected_setting_id()
        if setting_id is None:
            QMessageBox.warning(self, "提示", "请先选择一个要删除的设定。")
            return

        reply = QMessageBox.question(self, "确认删除", "确定要永久删除这个设定吗？\n此操作无法撤销。",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            if self.data_manager.delete_setting(setting_id):
                self.load_settings()
                self.settings_changed.emit()
            else:
                QMessageBox.critical(self, "失败", "删除设定时发生错误。")