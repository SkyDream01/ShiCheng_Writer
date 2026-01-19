# ShiCheng_Writer/modules/material_system.py
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QTreeView, QPushButton, QHBoxLayout,
                               QLineEdit, QComboBox, QTextEdit, QDialog, QMenu,
                               QFormLayout, QDialogButtonBox, QLabel, QMessageBox,
                               QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
                               QStyledItemDelegate, QApplication, QInputDialog, QStackedWidget)
from PySide6.QtGui import QStandardItemModel, QStandardItem, QAction
from PySide6.QtCore import Qt, Signal
import json

class MaterialSelectionDialog(QDialog):
    """一个用于选择引用的素材的对话框"""
    def __init__(self, data_manager, current_book_id, parent=None):
        super().__init__(parent)
        self.data_manager = data_manager
        self.current_book_id = current_book_id
        self.selected_material_id = None
        self.selected_material_name = None

        self.setWindowTitle("选择引用的素材")
        self.setMinimumSize(400, 300)
        layout = QVBoxLayout(self)

        self.tree_view = QTreeView()
        self.tree_view.setHeaderHidden(True)
        self.model = QStandardItemModel()
        self.tree_view.setModel(self.model)
        self.tree_view.doubleClicked.connect(self.on_double_clicked)
        layout.addWidget(self.tree_view)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        self.buttons.accepted.connect(self.on_accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self.load_materials()

    def load_materials(self):
        self.model.clear()
        materials = self.data_manager.get_materials(self.current_book_id)
        
        materials_by_type = {}
        for m in materials:
            if m['type'] not in materials_by_type:
                materials_by_type[m['type']] = []
            materials_by_type[m['type']].append(m)

        for type_name, materials_list in materials_by_type.items():
            type_item = QStandardItem(f"[{type_name}]")
            type_item.setEditable(False)
            self.model.appendRow(type_item)
            for material in materials_list:
                item = QStandardItem(material['name'])
                item.setEditable(False)
                item.setData(material['id'], Qt.UserRole)
                type_item.appendRow(item)
        self.tree_view.expandAll()

    def on_double_clicked(self, index):
        if index.parent().isValid():
            self.on_accept()

    def on_accept(self):
        index = self.tree_view.currentIndex()
        if not index.isValid() or not index.parent().isValid():
            QMessageBox.warning(self, "提示", "请选择一个具体的素材项。")
            return
        
        item = self.model.itemFromIndex(index)
        self.selected_material_id = item.data(Qt.UserRole)
        self.selected_material_name = item.text()
        self.accept()

class AttributeDelegate(QStyledItemDelegate):
    """属性表格的委托，用于创建和管理编辑器"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_dialog = parent

    def createEditor(self, parent, option, index):
        if index.column() == 1: # 类型列
            editor = QComboBox(parent)
            editor.addItems(["文本", "引用", "集合"])
            return editor
        return super().createEditor(parent, option, index)

    def setEditorData(self, editor, index):
        if index.column() == 1:
            value = index.model().data(index, Qt.EditRole)
            editor.setCurrentText(value)
        else:
            super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        if index.column() == 1:
            model.setData(index, editor.currentText(), Qt.EditRole)
        else:
            super().setModelData(editor, model, index)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)

class MaterialEditDialog(QDialog):
    """功能强大的对话框，用于添加和编辑素材"""
    def __init__(self, data_manager, material_id=None, book_id=None, parent=None):
        super().__init__(parent)
        self.data_manager = data_manager
        self.material_id = material_id
        self.current_book_id = book_id
        self.is_new = (material_id is None)

        self.setWindowTitle("编辑素材" if not self.is_new else "创建新素材")
        self.setMinimumSize(650, 550)

        self.main_layout = QVBoxLayout(self)
        
        # --- Top Form ---
        self.form_layout = QFormLayout()
        self.name_edit = QLineEdit()
        self.type_combo = QComboBox()
        self.type_combo.addItems(['文本', '对象', '模板', '列表'])
        self.scope_combo = QComboBox()
        self.scope_combo.addItems(['本书素材', '全局素材'])
        self.description_edit = QTextEdit()
        self.form_layout.addRow("名称:", self.name_edit)
        self.form_layout.addRow("类型:", self.type_combo)
        self.form_layout.addRow("范围:", self.scope_combo)
        self.form_layout.addRow("描述:", self.description_edit)
        self.main_layout.addLayout(self.form_layout)

        # --- Stacked Widget for Content ---
        self.content_stack = QStackedWidget()
        self._create_content_pages()
        self.main_layout.addWidget(self.content_stack)

        # --- Dialog Buttons ---
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        self.main_layout.addWidget(self.buttons)

        # --- Connections ---
        self.type_combo.currentTextChanged.connect(self._update_content_page)
        self.buttons.accepted.connect(self.save_material)
        self.buttons.rejected.connect(self.reject)

        self.load_material_data()

    def _create_content_pages(self):
        """一次性创建所有内容类型的UI页面"""
        # Page 0: Text
        text_page = QWidget()
        text_layout = QVBoxLayout(text_page)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.addWidget(QLabel("文本内容:"))
        self.text_content_edit = QTextEdit()
        self.text_content_edit.setPlaceholderText("在此输入素材的详细文本内容...")
        text_layout.addWidget(self.text_content_edit)
        self.content_stack.addWidget(text_page)

        # Page 1: Attributes (Object/Template)
        attr_page = QWidget()
        attr_layout = QVBoxLayout(attr_page)
        attr_layout.setContentsMargins(0, 0, 0, 0)
        self.attributes_table = QTableWidget()
        self.attributes_table.setColumnCount(3)
        self.attributes_table.setHorizontalHeaderLabels(["属性名", "类型", "值"])
        self.attributes_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.attributes_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.attributes_table.setItemDelegate(AttributeDelegate(self))
        attr_layout.addWidget(self.attributes_table)
        attr_button_layout = QHBoxLayout()
        add_attr_button = QPushButton("添加属性")
        add_attr_button.clicked.connect(self.add_attribute_row)
        remove_attr_button = QPushButton("删除选中属性")
        remove_attr_button.clicked.connect(lambda: self.attributes_table.removeRow(self.attributes_table.currentRow()))
        attr_button_layout.addWidget(add_attr_button)
        attr_button_layout.addWidget(remove_attr_button)
        attr_layout.addLayout(attr_button_layout)
        self.content_stack.addWidget(attr_page)

        # Page 2: List
        list_page = QWidget()
        list_layout = QVBoxLayout(list_page)
        list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_items_table = QTableWidget()
        self.list_items_table.setColumnCount(1)
        self.list_items_table.setHorizontalHeaderLabels(["值"])
        self.list_items_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        list_layout.addWidget(self.list_items_table)
        list_button_layout = QHBoxLayout()
        add_item_button = QPushButton("添加列表项")
        add_item_button.clicked.connect(lambda: self.list_items_table.insertRow(self.list_items_table.rowCount()))
        remove_item_button = QPushButton("删除选中项")
        remove_item_button.clicked.connect(lambda: self.list_items_table.removeRow(self.list_items_table.currentRow()))
        list_button_layout.addWidget(add_item_button)
        list_button_layout.addWidget(remove_item_button)
        list_layout.addLayout(list_button_layout)
        self.content_stack.addWidget(list_page)
        
    def _update_content_page(self, type_name):
        """根据类型切换QStackedWidget中显示的页面"""
        if type_name == '文本':
            self.content_stack.setCurrentIndex(0)
        elif type_name in ['对象', '模板']:
            self.content_stack.setCurrentIndex(1)
        elif type_name == '列表':
            self.content_stack.setCurrentIndex(2)

    def _populate_fields(self):
        """用 self.material_data 的数据填充所有UI字段"""
        if self.is_new:
            return

        # 填充顶部表单
        self.name_edit.setText(self.material_data.get('name', ''))
        self.description_edit.setText(self.material_data.get('description', ''))
        self.type_combo.setCurrentText(self.material_data.get('type', '文本'))
        self.type_combo.setEnabled(False)
        is_global = self.material_data.get('book_id') is None
        self.scope_combo.setCurrentIndex(1 if is_global else 0)
        self.scope_combo.setEnabled(False)

        # 填充内容页面
        content = self.material_data.get('content', {})
        # 文本页面
        self.text_content_edit.setText(content.get('value', ''))
        
        # 属性页面
        self.attributes_table.setRowCount(0)
        attributes = content.get('attributes', [])
        self.attributes_table.setRowCount(len(attributes))
        for i, attr in enumerate(attributes):
            self.attributes_table.setItem(i, 0, QTableWidgetItem(attr.get('name', '')))
            type_combo = QComboBox()
            type_combo.addItems(["文本", "引用", "集合"])
            type_combo.setCurrentText(attr.get('type', '文本'))
            self.attributes_table.setCellWidget(i, 1, type_combo)
            type_combo.currentTextChanged.connect(
                lambda text, row=i: self.on_attribute_type_changed(row, 1)
            )
            self.update_attribute_value_widget(i, attr.get('type', '文本'), attr.get('value'))
            
        # 列表页面
        self.list_items_table.setRowCount(0)
        items = content.get('items', [])
        self.list_items_table.setRowCount(len(items))
        for i, item_val in enumerate(items):
            self.list_items_table.setItem(i, 0, QTableWidgetItem(item_val))

    def load_material_data(self):
        """加载素材数据并填充到UI中"""
        if self.is_new:
            self._update_content_page(self.type_combo.currentText())
            return

        self.material_data = self.data_manager.get_material_details(self.material_id)
        if not self.material_data:
            QMessageBox.critical(self, "错误", "无法加载素材信息。")
            self.reject()
            return

        self._populate_fields()
        self._update_content_page(self.material_data.get('type', '文本'))
    
    def add_attribute_row(self):
        """为属性表添加一个新行"""
        row = self.attributes_table.rowCount()
        self.attributes_table.insertRow(row)
        
        # Name item
        self.attributes_table.setItem(row, 0, QTableWidgetItem(""))
        
        # Type ComboBox
        type_combo = QComboBox()
        type_combo.addItems(["文本", "引用", "集合"])
        self.attributes_table.setCellWidget(row, 1, type_combo)
        type_combo.currentTextChanged.connect(
            lambda text, r=row: self.on_attribute_type_changed(r, 1)
        )
        
        # Value Widget (defaults to text)
        self.update_attribute_value_widget(row, "文本")

    def on_attribute_type_changed(self, row, column):
        """当属性类型改变时，更新值控件"""
        if column == 1:
            combo = self.attributes_table.cellWidget(row, column)
            if combo:
                self.update_attribute_value_widget(row, combo.currentText())

    def update_attribute_value_widget(self, row, attr_type, value=None):
        """可靠地更新单元格控件：先移除并销毁旧控件，再设置新控件"""
        old_widget = self.attributes_table.cellWidget(row, 2)
        if old_widget:
            self.attributes_table.removeCellWidget(row, 2)
            old_widget.deleteLater()

        if attr_type == "文本":
            editor = QLineEdit()
            if value and isinstance(value, str):
                editor.setText(value)
            self.attributes_table.setCellWidget(row, 2, editor)
        elif attr_type == "引用":
            button = QPushButton("选择引用...")
            if value and isinstance(value, dict):
                button.setText(value.get('name', '选择引用...'))
                button.setProperty('ref_id', value.get('id'))
            button.clicked.connect(lambda *args, r=row: self.select_material_reference(r))
            self.attributes_table.setCellWidget(row, 2, button)
        elif attr_type == "集合":
            button = QPushButton("编辑集合")
            if value and isinstance(value, list):
                 button.setProperty('collection', value)
            else:
                 button.setProperty('collection', [])
            button.clicked.connect(lambda *args, r=row: self.edit_collection(r))
            self.attributes_table.setCellWidget(row, 2, button)

    def select_material_reference(self, row):
        """打开对话框以选择引用的素材"""
        dialog = MaterialSelectionDialog(self.data_manager, self.current_book_id, self)
        if dialog.exec():
            button = self.attributes_table.cellWidget(row, 2)
            button.setText(dialog.selected_material_name)
            button.setProperty('ref_id', dialog.selected_material_id)

    def edit_collection(self, row):
        """编辑一个集合类型属性的值"""
        button = self.attributes_table.cellWidget(row, 2)
        collection = button.property('collection')
        
        items_str = "\n".join([str(item) for item in collection])
        new_items_str, ok = QInputDialog.getMultiLineText(self, "编辑集合", "输入集合项（每行一项）:", text=items_str)
        
        if ok:
            new_collection = [item.strip() for item in new_items_str.split('\n') if item.strip()]
            button.setProperty('collection', new_collection)
            QMessageBox.information(self, "集合已更新", f"当前集合包含 {len(new_collection)} 项。")

    def save_material(self):
        """保存素材数据到数据库"""
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "输入错误", "素材名称不能为空。")
            return
            
        mat_type = self.type_combo.currentText()
        description = self.description_edit.toPlainText()
        is_global = self.scope_combo.currentIndex() == 1
        book_id = None if is_global else self.current_book_id
        
        content = {}
        if mat_type == '文本':
            content['value'] = self.text_content_edit.toPlainText()
        elif mat_type in ['对象', '模板']:
            attributes = []
            for i in range(self.attributes_table.rowCount()):
                name_item = self.attributes_table.item(i, 0)
                if not (name_item and name_item.text()): continue

                attr_name = name_item.text()
                type_widget = self.attributes_table.cellWidget(i, 1)
                attr_type = type_widget.currentText()
                value_widget = self.attributes_table.cellWidget(i, 2)
                attr_value = None
                
                if attr_type == "文本" and value_widget:
                    attr_value = value_widget.text()
                elif attr_type == "引用" and value_widget:
                    attr_value = {
                        "id": value_widget.property('ref_id'),
                        "name": value_widget.text()
                    }
                elif attr_type == "集合" and value_widget:
                    attr_value = value_widget.property('collection')

                attributes.append({
                    'name': attr_name,
                    'type': attr_type,
                    'value': attr_value
                })
            content['attributes'] = attributes
        elif mat_type == '列表':
            items = []
            for i in range(self.list_items_table.rowCount()):
                item = self.list_items_table.item(i, 0)
                if item and item.text():
                    items.append(item.text())
            content['items'] = items

        if self.is_new:
            if not self.data_manager.add_material(name, mat_type, description, book_id, content):
                QMessageBox.critical(self, "错误", f"创建素材失败。请确保在同一范围内没有重名的素材。")
                return
        else:
            if not self.data_manager.update_material(self.material_id, name, mat_type, description, content):
                QMessageBox.critical(self, "错误", f"更新素材失败。")
                return
        
        self.accept()

class MaterialPanel(QWidget):
    """素材面板，用于展示和管理素材"""
    materials_changed = Signal()

    def __init__(self, data_manager, parent=None):
        super().__init__(parent)
        self.data_manager = data_manager
        self.current_book_id = None

        self.setWindowTitle("素材仓库")
        self.layout = QVBoxLayout(self)

        self.tree_view = QTreeView()
        self.tree_view.setHeaderHidden(True)
        self.model = QStandardItemModel()
        self.tree_view.setModel(self.model)
        self.tree_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree_view.customContextMenuRequested.connect(self.open_context_menu)
        self.tree_view.doubleClicked.connect(self.edit_selected_material)
        
        button_layout = QHBoxLayout()
        self.add_button = QPushButton("添加新素材")
        self.edit_button = QPushButton("编辑选中")
        self.delete_button = QPushButton("删除选中")
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.edit_button)
        button_layout.addWidget(self.delete_button)
        
        self.add_button.clicked.connect(self.add_new_material)
        self.edit_button.clicked.connect(self.edit_selected_material)
        self.delete_button.clicked.connect(self.delete_selected_material)

        self.layout.addWidget(QLabel("全局素材 & 本书素材:"))
        self.layout.addWidget(self.tree_view)
        self.layout.addLayout(button_layout)
        
    def set_book(self, book_id):
        self.current_book_id = book_id
        self.load_materials()

    def load_materials(self):
        self.model.clear()
        if self.current_book_id is None:
            self.add_button.setEnabled(False)
            self.edit_button.setEnabled(False)
            self.delete_button.setEnabled(False)
            return
            
        self.add_button.setEnabled(True)
        self.edit_button.setEnabled(True)
        self.delete_button.setEnabled(True)

        materials = self.data_manager.get_materials(self.current_book_id)
        
        global_root = QStandardItem("全局素材")
        global_root.setEditable(False)
        book_root = QStandardItem("本书素材")
        book_root.setEditable(False)
        
        for material in materials:
            item = QStandardItem(f"{material['name']} ({material['type']})")
            item.setEditable(False)
            item.setData(material['id'], Qt.UserRole)
            if material['book_id'] is None:
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
        if not index.isValid() or not index.parent().isValid():
            return
        
        menu = QMenu()
        edit_action = menu.addAction("编辑")
        delete_action = menu.addAction("删除")
        
        action = menu.exec(self.tree_view.viewport().mapToGlobal(position))
        
        if action == edit_action:
            self.edit_selected_material()
        elif action == delete_action:
            self.delete_selected_material()
            
    def get_selected_material_id(self):
        index = self.tree_view.currentIndex()
        if not index.isValid() or not index.parent().isValid():
            return None
        item = self.model.itemFromIndex(index)
        return item.data(Qt.UserRole)

    def add_new_material(self):
        if self.current_book_id is None:
            QMessageBox.warning(self, "提示", "请先选择一本书籍。")
            return
            
        dialog = MaterialEditDialog(self.data_manager, book_id=self.current_book_id, parent=self)
        if dialog.exec():
            self.load_materials()
            self.materials_changed.emit()

    def edit_selected_material(self, index=None): # Can be called by signal or button
        material_id = self.get_selected_material_id()
        if material_id is None:
            if index and index.isValid() and index.parent().isValid():
                 item = self.model.itemFromIndex(index)
                 material_id = item.data(Qt.UserRole)
            else:
                QMessageBox.warning(self, "提示", "请先选择一个要编辑的素材。")
                return
        
        dialog = MaterialEditDialog(self.data_manager, material_id=material_id, book_id=self.current_book_id, parent=self)
        if dialog.exec():
            self.load_materials()
            self.materials_changed.emit()

    def delete_selected_material(self):
        material_id = self.get_selected_material_id()
        if material_id is None:
            QMessageBox.warning(self, "提示", "请先选择一个要删除的素材。")
            return

        reply = QMessageBox.question(self, "确认删除", "确定要永久删除这个素材吗？\n此操作无法撤销。",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            if self.data_manager.delete_material(material_id):
                self.load_materials()
                self.materials_changed.emit()
            else:
                QMessageBox.critical(self, "失败", "删除素材时发生错误。")