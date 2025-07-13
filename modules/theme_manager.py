# ShiCheng_Writer/modules/theme_manager.py
import os
import sys  # [新增] 导入 sys
from PySide6.QtWidgets import QApplication

# vvvvvvvvvvvvvv [新增] 资源路径辅助函数 vvvvvvvvvvvvvv
def resource_path(relative_path):
    """ 获取资源的绝对路径，无论是开发环境还是打包环境 """
    try:
        # PyInstaller 创建一个临时文件夹，并把路径存储在 _MEIPASS 中
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)
# ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

def set_stylesheet(theme):
    """加载并应用QSS样式表"""
    app = QApplication.instance()
    if not app:
        return

    # vvvvvvvvvvvvvv [修改] 使用 resource_path 函数来定位文件 vvvvvvvvvvvvvv
    light_style_file = resource_path(os.path.join("resources", "styles", "style.qss"))
    dark_style_file = resource_path(os.path.join("resources", "styles", "dark_style.qss"))
    # ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

    style_file_to_load = light_style_file
    if theme == 'dark' and os.path.exists(dark_style_file):
        style_file_to_load = dark_style_file
    elif not os.path.exists(light_style_file):
        print(f"警告: 默认样式文件 '{light_style_file}' 未找到。")
        return

    try:
        if os.path.exists(style_file_to_load):
            with open(style_file_to_load, "r", encoding='utf-8') as f:
                app.setStyleSheet(f.read())
                print(f"成功加载样式: {style_file_to_load}")
    except Exception as e:
        print(f"无法加载样式表: {e}")