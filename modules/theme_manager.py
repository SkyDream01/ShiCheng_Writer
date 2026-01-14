# ShiCheng_Writer/modules/theme_manager.py
import os
import logging
from PySide6.QtWidgets import QApplication
from .utils import resource_path # [修改] 从 utils 导入

logger = logging.getLogger(__name__)

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
        logger.warning(f"默认样式文件 '{light_style_file}' 未找到。")
        return

    try:
        if os.path.exists(style_file_to_load):
            with open(style_file_to_load, "r", encoding='utf-8') as f:
                app.setStyleSheet(f.read())
                logger.info(f"成功加载样式: {style_file_to_load}")
    except Exception as e:
        logger.error(f"无法加载样式表: {e}")