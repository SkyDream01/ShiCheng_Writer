# shicheng_writer/modules/theme_manager.py
import os
from PySide6.QtWidgets import QApplication

def set_stylesheet(theme):
    """加载并应用QSS样式表"""
    app = QApplication.instance()
    if not app:
        return

    light_style_file = os.path.join("resources", "styles", "style.qss")
    dark_style_file = os.path.join("resources", "styles", "dark_style.qss")

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