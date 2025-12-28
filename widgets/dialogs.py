# ShiCheng_Writer/widgets/dialogs.py
import os
import tempfile
import json
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, 
                               QLabel, QLineEdit, QCheckBox, QComboBox, 
                               QDialogButtonBox, QPushButton, QMessageBox, 
                               QTreeWidget, QTreeWidgetItem, QHeaderView, 
                               QListWidget, QInputDialog, QTextEdit, QApplication)
from PySide6.QtCore import Qt

class RecycleBinDialog(QDialog):
    """[新增] 回收站管理对话框"""
    def __init__(self, data_manager, parent=None):
        super().__init__(parent)
        self.data_manager = data_manager
        self.setWindowTitle("回收站")
        self.resize(750, 450) # 稍微加宽以容纳书籍名称
        
        layout = QVBoxLayout(self)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["名称", "类型", "删除时间", "所属书籍/原位置"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tree.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        layout.addWidget(self.tree)
        
        btn_layout = QHBoxLayout()
        self.restore_btn = QPushButton("还原")
        self.restore_btn.clicked.connect(self.restore_item)
        self.del_btn = QPushButton("彻底删除")
        self.del_btn.setStyleSheet("background-color: #e74c3c; color: white;")
        self.del_btn.clicked.connect(self.delete_item)
        self.empty_btn = QPushButton("清空回收站")
        self.empty_btn.clicked.connect(self.empty_bin)
        
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        
        btn_layout.addWidget(self.restore_btn)
        btn_layout.addWidget(self.del_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.empty_btn)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)
        
        self.load_data()
        
    def load_data(self):
        self.tree.clear()
        items = self.data_manager.get_recycle_bin_items()
        for item in items:
            try:
                item_data = json.loads(item['item_data'])
                name = item_data.get('title', '未知')
                type_str = "书籍" if item['item_type'] == 'book' else "章节"
                
                origin = "-"
                if item['item_type'] == 'chapter':
                    book_id = item_data.get('book_id')
                    # [修改] 尝试获取书籍名称，提供更好的上下文
                    if book_id:
                        book_info = self.data_manager.get_book_details(book_id)
                        if book_info:
                            origin = f"《{book_info['title']}》"
                        else:
                            origin = f"<书籍已删除 ID:{book_id}>"
                
                tree_item = QTreeWidgetItem(self.tree)
                tree_item.setText(0, name)
                tree_item.setText(1, type_str)
                tree_item.setText(2, item['deleted_at'])
                tree_item.setText(3, origin)
                tree_item.setData(0, Qt.UserRole, item['id']) # Recycle Bin ID
            except Exception as e:
                print(f"加载回收站项目失败: {e}")
                continue
            
    def restore_item(self):
        item = self.tree.currentItem()
        if not item: return
        
        recycle_id = item.data(0, Qt.UserRole)
        res = self.data_manager.restore_recycle_item(recycle_id)
        
        if res == True:
            QMessageBox.information(self, "成功", "项目已还原。")
            self.load_data()
            # 刷新父窗口视图
            parent = self.parent()
            if parent:
                if hasattr(parent, 'load_books'):
                    parent.load_books()
                if hasattr(parent, 'current_book_id') and parent.current_book_id:
                    parent.load_chapters_for_book(parent.current_book_id)
                    
        elif res == "parent_missing":
             QMessageBox.warning(self, "无法还原", "该章节所属的书籍已不存在，无法直接还原。\n请先检查回收站并还原对应的书籍。")
        else:
            QMessageBox.warning(self, "失败", "还原失败，可能发生数据库错误。")

    def delete_item(self):
        item = self.tree.currentItem()
        if not item: return
        if QMessageBox.question(self, "确认", "确定要彻底删除该项目吗？此操作无法撤销。") == QMessageBox.Yes:
            recycle_id = item.data(0, Qt.UserRole)
            self.data_manager.delete_recycle_item(recycle_id)
            self.load_data()
            
    def empty_bin(self):
        if self.tree.topLevelItemCount() == 0:
            return
        if QMessageBox.question(self, "确认", "确定要清空回收站吗？所有项目将永久丢失。") == QMessageBox.Yes:
            self.data_manager.empty_recycle_bin()
            self.load_data()

class WebDAVSettingsDialog(QDialog):
    """WebDAV 设置对话框"""
    # [修改] 参数顺序调整以兼容旧代码调用 (parent=self)，同时允许可选传入 backup_manager
    def __init__(self, data_manager, parent=None, backup_manager=None):
        super().__init__(parent)
        self.data_manager = data_manager
        
        # [修改] 优先使用传入的实例，否则尝试从 parent 获取 (兼容性处理)
        self.backup_manager = backup_manager
        if not self.backup_manager and hasattr(parent, 'backup_manager'):
             self.backup_manager = parent.backup_manager
        
        self.setWindowTitle("WebDAV 设置")
        self.setMinimumSize(400, 300)

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        self.enabled_check = QCheckBox("启用 WebDAV 同步")
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://dav.example.com/webdav/")
        self.user_edit = QLineEdit()
        self.pass_edit = QLineEdit()
        self.pass_edit.setEchoMode(QLineEdit.Password)
        self.root_dir_edit = QLineEdit()
        self.root_dir_edit.setPlaceholderText("/shicheng/")
        self.sync_freq_combo = QComboBox()
        self.sync_freq_combo.addItems(["实时", "每小时", "仅启动时"])
        
        form_layout.addRow(self.enabled_check)
        form_layout.addRow("WebDAV 地址:", self.url_edit)
        form_layout.addRow("用户名:", self.user_edit)
        form_layout.addRow("密码/Token:", self.pass_edit)
        form_layout.addRow("云端根目录:", self.root_dir_edit)
        form_layout.addRow("同步频率:", self.sync_freq_combo)

        layout.addLayout(form_layout)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel, self)
        self.test_button = QPushButton("测试连接")
        buttons.addButton(self.test_button, QDialogButtonBox.ActionRole)

        self.test_button.clicked.connect(self.test_webdav_connection)
        buttons.accepted.connect(self.save_settings)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.load_settings()

    def load_settings(self):
        settings = self.data_manager.get_webdav_settings()
        self.enabled_check.setChecked(settings.get('webdav_enabled', False))
        self.url_edit.setText(settings.get('webdav_url', ''))
        self.user_edit.setText(settings.get('webdav_user', ''))
        self.pass_edit.setText(settings.get('webdav_pass', ''))
        self.root_dir_edit.setText(settings.get('webdav_root', '/shicheng/'))
        self.sync_freq_combo.setCurrentText(settings.get('webdav_sync_freq', '实时'))

    def save_settings(self):
        settings = {
            'webdav_enabled': self.enabled_check.isChecked(),
            'webdav_url': self.url_edit.text(),
            'webdav_user': self.user_edit.text(),
            'webdav_pass': self.pass_edit.text(),
            'webdav_root': self.root_dir_edit.text(),
            'webdav_sync_freq': self.sync_freq_combo.currentText()
        }
        self.data_manager.save_webdav_settings(settings)
        QMessageBox.information(self, "成功", "WebDAV 设置已保存。")
        self.accept()
        
    def test_webdav_connection(self):
        if not self.backup_manager:
            QMessageBox.warning(self, "错误", "无法获取备份管理器实例，请检查程序初始化。")
            return

        # 临时保存当前UI上的设置用于测试
        current_settings = {
            'webdav_enabled': self.enabled_check.isChecked(),
            'webdav_url': self.url_edit.text(),
            'webdav_user': self.user_edit.text(),
            'webdav_pass': self.pass_edit.text(),
            'webdav_root': self.root_dir_edit.text(),
            'webdav_sync_freq': self.sync_freq_combo.currentText()
        }
        self.data_manager.save_webdav_settings(current_settings)
        
        self.test_button.setEnabled(False)
        self.test_button.setText("测试中...")
        
        # 强制刷新UI以免卡顿感
        QApplication.processEvents()
        
        try:
            success, message = self.backup_manager.test_webdav_connection()
            if success:
                QMessageBox.information(self, "连接成功", message)
            else:
                QMessageBox.critical(self, "连接失败", message)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"测试过程中发生异常: {str(e)}")
        finally:
            self.test_button.setEnabled(True)
            self.test_button.setText("测试连接")

class BackupDialog(QDialog):
    def __init__(self, backup_manager, parent=None):
        super().__init__(parent)
        self.backup_manager = backup_manager
        self.setWindowTitle("备份与恢复")
        self.setMinimumSize(550, 450)
        
        layout = QVBoxLayout(self)
        self.backup_tree = QTreeWidget()
        self.backup_tree.setHeaderLabels(["备份文件", "类型", "来源"])
        self.backup_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)

        button_layout = QHBoxLayout()
        restore_button = QPushButton("恢复选中项")
        restore_button.clicked.connect(self.restore_backup)
        delete_button = QPushButton("删除选中项")
        delete_button.clicked.connect(self.delete_backup)
        refresh_button = QPushButton("刷新列表")
        refresh_button.clicked.connect(self.load_backups)
        
        button_layout.addWidget(restore_button)
        button_layout.addWidget(delete_button)
        button_layout.addStretch()
        button_layout.addWidget(refresh_button)

        layout.addWidget(QLabel("选择一个备份进行恢复或删除:"))
        layout.addWidget(self.backup_tree)
        layout.addLayout(button_layout)
        
        self.load_backups()

    def load_backups(self):
        self.backup_tree.clear()
        
        # Local Backups
        local_backups = self.backup_manager.list_backups()
        if local_backups:
            local_root = QTreeWidgetItem(self.backup_tree, ["本地备份"])
            for backup in local_backups:
                backup['source'] = 'local'
                child = QTreeWidgetItem(local_root, [backup['file'], backup['type'], "本地"])
                child.setData(0, Qt.UserRole, backup)
            local_root.setExpanded(True)

        # Cloud Backups
        remote_backups = self.backup_manager.list_remote_backups()
        if remote_backups:
            cloud_root = QTreeWidgetItem(self.backup_tree, ["云端备份 (WebDAV)"])
            for backup in remote_backups:
                child = QTreeWidgetItem(cloud_root, [backup['file'], backup['type'], "云端"])
                child.setData(0, Qt.UserRole, backup)
            cloud_root.setExpanded(True)
        
        if not local_backups and not remote_backups:
            self.backup_tree.addTopLevelItem(QTreeWidgetItem(["暂无任何备份文件"]))

    def restore_backup(self):
        selected_item = self.backup_tree.currentItem()
        if not selected_item or not selected_item.data(0, Qt.UserRole):
            QMessageBox.warning(self, "提示", "请先选择一个具体的备份文件。")
            return
            
        backup_info = selected_item.data(0, Qt.UserRole)
        is_cloud = backup_info.get("source") == "cloud"

        if is_cloud:
            reply = QMessageBox.question(self, "确认恢复",
                                         f"您确定要从【云端】恢复备份\n'{backup_info['file']}'\n吗？\n"
                                         "这将首先从云端下载文件，然后覆盖本地数据。",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
            
            with tempfile.TemporaryDirectory() as temp_dir:
                remote_filename = os.path.basename(backup_info['path'])
                downloaded_filepath = self.backup_manager.download_backup(remote_filename, temp_dir)
                if not downloaded_filepath:
                    QMessageBox.critical(self, "下载失败", "无法从云端下载备份文件，请检查网络和WebDAV设置。")
                    return
                
                temp_backup_info = {
                    "file": os.path.basename(downloaded_filepath),
                    "dir": temp_dir,
                    "type": backup_info['type']
                }
                self.proceed_with_restore(temp_backup_info)
        else:
            self.proceed_with_restore(backup_info)

    def proceed_with_restore(self, backup_info):
        backup_type_lower = backup_info.get('type', '').lower()
        if 'snapshot' in backup_type_lower or '快照线' in backup_type_lower:
            if self.backup_manager.restore_from_snapshot(backup_info):
                QMessageBox.information(self, "成功", "数据已从快照恢复。\n请检查相关章节内容。")
                if self.parent() and hasattr(self.parent(), 'current_book_id'):
                    if self.parent().current_book_id:
                        self.parent().load_chapters_for_book(self.parent().current_book_id)
                self.accept()
            else:
                QMessageBox.critical(self, "失败", "恢复过程中发生错误。")
        else:
            reply = QMessageBox.warning(self, "确认恢复",
                                         f"您确定要从 {backup_info['type']} 备份\n'{backup_info['file']}'\n恢复吗？\n"
                                         "【警告】此操作将完全覆盖当前所有数据！\n"
                                         "恢复后必须重启应用才能看到更改。\n"
                                         "操作无法撤销，请谨慎操作！",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                if self.backup_manager.restore_from_backup(backup_info):
                    QMessageBox.information(self, "成功", "数据已从备份恢复。\n请立即重启应用程序以应用更改。")
                    if self.parent() and hasattr(self.parent(), 'load_books'):
                        self.parent().load_books()
                    self.accept()
                else:
                    QMessageBox.critical(self, "失败", "恢复过程中发生错误，请查看状态栏或控制台输出。")

    def delete_backup(self):
        selected_item = self.backup_tree.currentItem()
        if not selected_item or not selected_item.data(0, Qt.UserRole):
            QMessageBox.warning(self, "提示", "请先选择一个具体的备份文件。")
            return

        backup_info = selected_item.data(0, Qt.UserRole)
        is_cloud = backup_info.get("source") == "cloud"
        source_text = "【云端】" if is_cloud else "【本地】"

        reply = QMessageBox.question(self, "确认删除",
                                       f"确定要永久删除此 {source_text} 备份吗？\n'{backup_info['file']}'",
                                       QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            success = False
            if is_cloud:
                remote_filename = os.path.basename(backup_info['path'])
                success = self.backup_manager.delete_remote_backup(remote_filename)
            else:
                success = self.backup_manager.delete_backup(backup_info)
            
            if success:
                QMessageBox.information(self, "成功", f"备份 '{backup_info['file']}' 已被删除。")
                self.load_backups()
            else:
                QMessageBox.critical(self, "失败", "删除过程中发生错误。")


class ManageGroupsDialog(QDialog):
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
        groups = [g for g in groups if g != "未分组"]
        if not groups:
            self.group_list.addItem("暂无自定义分组")
        else:
            self.group_list.addItems(groups)
        if self.parent() and hasattr(self.parent(), 'load_books'):
            self.parent().load_books()

    def add_new_group(self):
        new_name, ok = QInputDialog.getText(self, "新建分组", "请输入新分组的名称:")
        if ok and new_name:
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