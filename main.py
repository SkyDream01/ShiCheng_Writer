# ShiCheng_Writer/main.py
import sys
import os
import logging
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication, Qt

# 导入模块
from modules.database import initialize_database, DataManager
from modules.backup import BackupManager
from modules.theme_manager import set_stylesheet
from modules.utils import resource_path, get_app_root

def main():
    # 将 MainWindow 的导入移至函数内部，确保所有依赖都已加载
    from main_window import MainWindow

    # 配置日志系统
    log_dir = os.path.join(get_app_root(), "logs")
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    log_file = os.path.join(log_dir, "shicheng_writer.log")
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    logger = logging.getLogger(__name__)

    # 1. 初始化数据库
    initialize_database()

    # 2. 创建数据管理器实例
    data_manager = DataManager()

    # 3. 创建备份管理器实例
    # [修改] 获取绝对路径，并在初始化前确保目录存在
    backup_dir = os.path.join(get_app_root(), "backups")
    
    # [新增] 关键修复：如果备份文件夹不存在，手动创建，防止报错
    if not os.path.exists(backup_dir):
        try:
            os.makedirs(backup_dir)
            logger.info(f"已自动创建备份目录: {backup_dir}")
        except Exception as e:
            logger.error(f"无法创建备份目录 '{backup_dir}': {e}")

    # 显式传入 base_backup_dir
    backup_manager = BackupManager(data_manager, base_backup_dir=backup_dir)

    # 4. 启动Qt应用
    app = QApplication(sys.argv)

    # 优先从数据库加载主题，若无则匹配系统
    saved_theme = data_manager.get_preference('theme')
    if saved_theme in ['light', 'dark']:
        initial_theme = saved_theme
    else:
        # 检测系统主题并加载初始样式
        initial_theme = 'dark' if app.styleHints().colorScheme() == Qt.ColorScheme.Dark else 'light'
    
    # 加载样式表
    set_stylesheet(initial_theme)

    # 将 backup_manager 和初始主题传递给主窗口
    window = MainWindow(data_manager, backup_manager, initial_theme)

    # 监听系统颜色方案的变化 (自动切换)
    def on_color_scheme_changed(scheme):
        # 仅当用户未明确设置主题时才自动切换
        if data_manager.get_preference('theme') is None:
            new_theme = 'dark' if scheme == Qt.ColorScheme.Dark else 'light'
            logger.info(f"系统主题已更改为: {new_theme.capitalize()}")
            set_stylesheet(new_theme)
            window.update_theme(new_theme)

    app.styleHints().colorSchemeChanged.connect(on_color_scheme_changed)

    window.show()

    sys.exit(app.exec())

if __name__ == '__main__':
    main()