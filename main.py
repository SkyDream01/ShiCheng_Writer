# ShiCheng_Writer/main.py
import sys
import os
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication, Qt

# 修正导入顺序，将共享函数从新模块导入
from modules.database import initialize_database, DataManager
from modules.backup import BackupManager
from modules.theme_manager import set_stylesheet

def main():
    # 将 MainWindow 的导入移至函数内部，确保所有依赖都已加载
    from main_window import MainWindow

    # 1. 初始化数据库
    initialize_database()

    # 2. 创建数据管理器实例
    data_manager = DataManager()

    # 3. 创建备份管理器实例, 并传入 data_manager
    backup_manager = BackupManager(data_manager)

    # 4. 启动Qt应用
    app = QApplication(sys.argv)

    # 优先从数据库加载主题，若无则匹配系统
    saved_theme = data_manager.get_preference('theme')
    if saved_theme in ['light', 'dark']:
        initial_theme = saved_theme
    else:
        # 检测系统主题并加载初始样式
        initial_theme = 'dark' if app.styleHints().colorScheme() == Qt.ColorScheme.Dark else 'light'
    
    set_stylesheet(initial_theme)


    # 将 backup_manager 和初始主题传递给主窗口
    window = MainWindow(data_manager, backup_manager, initial_theme)

    # 监听系统颜色方案的变化 (自动切换)
    def on_color_scheme_changed(scheme):
        # 仅当用户未明确设置主题时才自动切换
        if data_manager.get_preference('theme') is None:
            new_theme = 'dark' if scheme == Qt.ColorScheme.Dark else 'light'
            print(f"系统主题已更改为: {new_theme.capitalize()}")
            set_stylesheet(new_theme)
            # 通知窗口更新其状态和组件
            window.update_theme(new_theme)

    app.styleHints().colorSchemeChanged.connect(on_color_scheme_changed)

    window.show()

    sys.exit(app.exec())

if __name__ == '__main__':
    main()