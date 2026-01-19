from PySide6.QtGui import QAction, QKeySequence, QIcon
from PySide6.QtWidgets import (QMenu, QMessageBox, QLabel, QComboBox, QSplitter)
from PySide6.QtCore import Qt

from modules.utils import resource_path
from modules.theme_manager import set_stylesheet
from widgets.dialogs import RecycleBinDialog, SearchReplaceDialog, ManageGroupsDialog

class UIManager:
    """
    Manages UI actions, menus, toolbars, and layout state (panels, theme, font size).
    """
    def __init__(self, main_window):
        self.mw = main_window
        self.data_manager = main_window.data_manager
        
        # State
        self.left_panel_visible = True
        self.right_panel_visible = True
        self.focus_mode = False
        self.original_splitter_sizes = [280, 770, 350]
        self.saved_left_panel_size = 280
        self.saved_right_panel_size = 350
        self.pre_focus_state = None
        
        self.search_dialog = None

    def setup_ui_components(self):
        """Initializes actions, menus, and status bar"""
        self.setup_actions()
        self.setup_menu_bar()
        self.setup_status_bar()
        self.load_and_apply_font_size()

    def setup_actions(self):
        # File Actions
        self.mw.add_book_action = QAction("新建书籍", self.mw)
        self.mw.add_book_action.setShortcut(QKeySequence("Ctrl+N"))
        self.mw.add_book_action.triggered.connect(self.mw.book_tree_widget.add_new_book)

        self.mw.add_chapter_action = QAction("新建章节", self.mw)
        self.mw.add_chapter_action.setShortcut(QKeySequence("Ctrl+Shift+N"))
        self.mw.add_chapter_action.triggered.connect(self.mw.chapter_tree_widget.add_new_chapter)
        self.mw.add_chapter_action.setEnabled(False)

        self.mw.save_action = QAction("保存", self.mw)
        self.mw.save_action.setShortcut(QKeySequence("Ctrl+S"))
        self.mw.save_action.triggered.connect(self.mw.save_current_chapter)

        self.mw.export_action = QAction("导出书籍", self.mw)
        self.mw.export_action.setShortcut(QKeySequence("Ctrl+E"))
        self.mw.export_action.triggered.connect(lambda: self.mw.book_tree_widget.export_book(self.mw.current_book_id))
        self.mw.export_action.setEnabled(False)

        # Edit Actions
        self.mw.undo_action = QAction("撤销", self.mw)
        self.mw.undo_action.setShortcut(QKeySequence.Undo)
        self.mw.undo_action.triggered.connect(self.mw.editor.undo)
        self.mw.editor.undoAvailable.connect(self.mw.undo_action.setEnabled)

        self.mw.redo_action = QAction("重做", self.mw)
        self.mw.redo_action.setShortcut(QKeySequence.Redo)
        self.mw.redo_action.triggered.connect(self.mw.editor.redo)
        self.mw.editor.redoAvailable.connect(self.mw.redo_action.setEnabled)
        
        self.mw.indent_action = QAction("全文缩进", self.mw)
        self.mw.indent_action.setShortcut(QKeySequence("Ctrl+I"))
        self.mw.indent_action.triggered.connect(self.auto_indent_document)

        self.mw.unindent_action = QAction("取消缩进", self.mw)
        self.mw.unindent_action.setShortcut(QKeySequence("Ctrl+Shift+I"))
        self.mw.unindent_action.triggered.connect(self.auto_unindent_document)

        self.mw.find_action = QAction("查找与替换", self.mw)
        self.mw.find_action.setShortcut(QKeySequence("Ctrl+F"))
        self.mw.find_action.triggered.connect(self.open_find_dialog)

        # View Actions
        self.mw.toggle_theme_action = QAction("切换亮/暗主题", self.mw)
        self.mw.toggle_theme_action.setShortcut(QKeySequence("F11"))
        self.mw.toggle_theme_action.triggered.connect(self.toggle_theme)

        self.mw.toggle_left_panel_action = QAction("显示/隐藏左侧面板", self.mw)
        self.mw.toggle_left_panel_action.setShortcut(QKeySequence("Ctrl+1"))
        self.mw.toggle_left_panel_action.triggered.connect(self.toggle_left_panel)

        self.mw.toggle_right_panel_action = QAction("显示/隐藏右侧面板", self.mw)
        self.mw.toggle_right_panel_action.setShortcut(QKeySequence("Ctrl+2"))
        self.mw.toggle_right_panel_action.triggered.connect(self.toggle_right_panel)

        self.mw.toggle_focus_mode_action = QAction("切换专注模式", self.mw)
        self.mw.toggle_focus_mode_action.setShortcut(QKeySequence("Ctrl+3"))
        self.mw.toggle_focus_mode_action.triggered.connect(self.toggle_focus_mode)

    def setup_menu_bar(self):
        menu_bar = self.mw.menuBar()

        # File Menu
        file_menu = menu_bar.addMenu("文件")
        file_menu.addAction(self.mw.add_book_action)
        file_menu.addAction(self.mw.add_chapter_action)
        file_menu.addSeparator()
        file_menu.addAction(self.mw.save_action)
        file_menu.addSeparator()
        file_menu.addAction(self.mw.export_action)
        file_menu.addSeparator()

        group_manage_action = QAction("分组管理", self.mw)
        group_manage_action.triggered.connect(self.mw.book_tree_widget.open_group_manager)
        file_menu.addAction(group_manage_action)
        
        recycle_bin_action = QAction("回收站", self.mw)
        recycle_bin_action.triggered.connect(self.open_recycle_bin)
        file_menu.addAction(recycle_bin_action)

        backup_menu = file_menu.addMenu("备份")
        backup_now_action = QAction("立即备份 (阶段点)", self.mw)
        backup_now_action.triggered.connect(lambda: self.mw.run_stage_backup(manual=True))
        backup_menu.addAction(backup_now_action)

        backup_manage_action = QAction("备份管理", self.mw)
        backup_manage_action.triggered.connect(self.mw.open_backup_manager)
        backup_menu.addAction(backup_manage_action)

        # Recent Chapters
        recent_menu = file_menu.addMenu("最近编辑的章节")
        self.recent_menu = recent_menu
        recent_menu.aboutToShow.connect(self.update_recent_chapters_menu)

        file_menu.addSeparator()
        exit_action = QAction("退出", self.mw)
        exit_action.triggered.connect(self.mw.close)
        file_menu.addAction(exit_action)

        # Edit Menu
        edit_menu = menu_bar.addMenu("编辑")
        edit_menu.addAction(self.mw.undo_action)
        edit_menu.addAction(self.mw.redo_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.mw.find_action) 
        edit_menu.addSeparator()
        edit_menu.addAction(self.mw.indent_action)
        edit_menu.addAction(self.mw.unindent_action)

        # View Menu
        view_menu = menu_bar.addMenu("视图")
        view_menu.addAction(self.mw.toggle_theme_action)
        view_menu.addSeparator()
        view_menu.addAction(self.mw.toggle_left_panel_action)
        view_menu.addAction(self.mw.toggle_right_panel_action)
        view_menu.addAction(self.mw.toggle_focus_mode_action)

    def setup_status_bar(self):
        status_bar = self.mw.statusBar()
        status_bar.showMessage("欢迎使用诗成写作！")
        
        self.mw.current_book_chapter_label = QLabel("未选择书籍")
        self.mw.word_count_label = QLabel("字数: 0")
        self.mw.typing_speed_label = QLabel("速度: 0 字/分")
        self.mw.font_size_combobox = QComboBox()
        self.mw.font_size_combobox.addItems(["14px", "16px", "18px", "20px"])
        self.mw.font_size_combobox.currentIndexChanged.connect(self.on_font_size_changed)

        status_bar.addPermanentWidget(self.mw.current_book_chapter_label)
        status_bar.addPermanentWidget(self.mw.word_count_label)
        status_bar.addPermanentWidget(self.mw.typing_speed_label)
        status_bar.addPermanentWidget(self.mw.font_size_combobox)

    # --- Feature Methods ---

    def toggle_theme(self):
        new_theme = 'dark' if self.mw.current_theme == 'light' else 'light'
        set_stylesheet(new_theme)
        self.update_theme_preference(new_theme)

    def update_theme_preference(self, new_theme):
        self.data_manager.set_preference('theme', new_theme)
        self.mw.current_theme = new_theme
        if hasattr(self.mw.editor, 'highlighter'):
             self.mw.editor.highlighter.update_highlight_color()

    def toggle_left_panel(self):
        splitter = self.mw.splitter
        if not splitter or splitter.count() < 3: return
        
        if self.left_panel_visible:
            self.saved_left_panel_size = splitter.sizes()[0] if splitter.sizes()[0] > 0 else 280
            splitter.widget(0).setVisible(False)
            self.left_panel_visible = False
        else:
            splitter.widget(0).setVisible(True)
            self.left_panel_visible = True
            current_sizes = splitter.sizes()
            left_size = self.saved_left_panel_size
            total_width = splitter.width()
            
            # Simple redistribution logic
            if total_width > left_size + 50:
                middle_ratio = current_sizes[1] / (current_sizes[1] + current_sizes[2]) if (current_sizes[1] + current_sizes[2]) > 0 else 0.7
                remaining = total_width - left_size
                middle_size = max(100, int(remaining * middle_ratio))
                right_size = max(100, remaining - middle_size)
                splitter.setSizes([left_size, middle_size, right_size])
            else:
                splitter.setSizes([left_size, 770, 350])
        
        splitter.update()

    def toggle_right_panel(self):
        splitter = self.mw.splitter
        if not splitter or splitter.count() < 3: return
        
        if self.right_panel_visible:
            self.saved_right_panel_size = splitter.sizes()[2] if splitter.sizes()[2] > 0 else 350
            splitter.widget(2).setVisible(False)
            self.right_panel_visible = False
        else:
            splitter.widget(2).setVisible(True)
            self.right_panel_visible = True
            current_sizes = splitter.sizes()
            right_size = self.saved_right_panel_size
            total_width = splitter.width()
            
            if total_width > right_size + 50:
                left_ratio = current_sizes[0] / (current_sizes[0] + current_sizes[1]) if (current_sizes[0] + current_sizes[1]) > 0 else 0.3
                remaining = total_width - right_size
                left_size = max(100, int(remaining * left_ratio))
                middle_size = max(100, remaining - left_size)
                splitter.setSizes([left_size, middle_size, right_size])
            else:
                splitter.setSizes([280, 770, right_size])
        
        splitter.update()

    def toggle_focus_mode(self):
        splitter = self.mw.splitter
        if not self.focus_mode:
            self.pre_focus_state = {
                'left_visible': self.left_panel_visible,
                'right_visible': self.right_panel_visible,
                'sizes': splitter.sizes()
            }
            splitter.widget(0).setVisible(False)
            splitter.widget(2).setVisible(False)
            self.left_panel_visible = False
            self.right_panel_visible = False
            
            sizes = splitter.sizes()
            total = sum(sizes)
            if total > 0: splitter.setSizes([0, total, 0])
            self.focus_mode = True
        else:
            if self.pre_focus_state:
                splitter.widget(0).setVisible(self.pre_focus_state['left_visible'])
                splitter.widget(2).setVisible(self.pre_focus_state['right_visible'])
                self.left_panel_visible = self.pre_focus_state['left_visible']
                self.right_panel_visible = self.pre_focus_state['right_visible']
                splitter.setSizes(self.pre_focus_state['sizes'])
            else:
                splitter.widget(0).setVisible(True)
                splitter.widget(2).setVisible(True)
                self.left_panel_visible = True
                self.right_panel_visible = True
                splitter.setSizes(self.original_splitter_sizes)
            self.focus_mode = False
        splitter.update()

    def open_recycle_bin(self):
        dialog = RecycleBinDialog(self.data_manager, self.mw)
        dialog.exec()

    def open_find_dialog(self):
        if not self.mw.current_chapter_id:
             QMessageBox.warning(self.mw, "提示", "请先打开一个章节。")
             return
        if self.search_dialog and self.search_dialog.isVisible():
            self.search_dialog.raise_()
            self.search_dialog.activateWindow()
            return
        self.search_dialog = SearchReplaceDialog(self.mw.editor, self.mw)
        self.search_dialog.show()

    def auto_indent_document(self):
        if not self.mw.current_chapter_id:
            QMessageBox.warning(self.mw, "提示", "请先打开一个章节。")
            return
        self.mw.editor.auto_indent_document()
        self.mw.on_text_changed()
        QMessageBox.information(self.mw, "成功", "全文缩进操作已完成。")

    def auto_unindent_document(self):
        if not self.mw.current_chapter_id:
            QMessageBox.warning(self.mw, "提示", "请先打开一个章节。")
            return
        self.mw.editor.auto_unindent_document()
        self.mw.on_text_changed()
        QMessageBox.information(self.mw, "成功", "取消全文缩进操作已完成。")

    def load_and_apply_font_size(self):
        font_size_str = self.data_manager.get_preference('font_size', '16px')
        self.mw.editor.set_font_size(font_size_str)
        
        self.mw.font_size_combobox.blockSignals(True)
        idx = self.mw.font_size_combobox.findText(font_size_str)
        if idx != -1:
            self.mw.font_size_combobox.setCurrentIndex(idx)
        else:
            self.mw.font_size_combobox.setCurrentIndex(1)
        self.mw.font_size_combobox.blockSignals(False)

    def on_font_size_changed(self, index):
        size_str = self.mw.font_size_combobox.itemText(index)
        self.mw.editor.set_font_size(size_str)
        self.data_manager.set_preference('font_size', size_str)

    def update_recent_chapters_menu(self):
        self.recent_menu.clear()
        recent_chapters = self.data_manager.get_recent_chapters(limit=10)
        if not recent_chapters:
            no_item = QAction("无最近编辑的章节", self.mw)
            no_item.setEnabled(False)
            self.recent_menu.addAction(no_item)
            return
        
        for chapter in recent_chapters:
            title = f"{chapter['title']} ({chapter['book_title']})"
            action = QAction(title, self.mw)
            action.setData(chapter['id'])
            action.triggered.connect(lambda checked, ch_id=chapter['id']: self.mw.open_recent_chapter(ch_id))
            self.recent_menu.addAction(action)
