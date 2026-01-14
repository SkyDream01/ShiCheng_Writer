# ShiCheng_Writer/modules/theme_manager.py
import os
import logging
from PySide6.QtWidgets import QApplication
from .utils import resource_path

logger = logging.getLogger(__name__)

def set_stylesheet(theme):
    """
    加载并应用QSS样式表 (简化版)
    直接读取标准QSS文件，不再进行变量替换，提高稳定性和速度。
    """
    app = QApplication.instance()
    if not app:
        return

    # 确定文件名
    filename = "dark_style.qss" if theme == 'dark' else "style.qss"
    style_file = resource_path(os.path.join("resources", "styles", filename))

    # 如果暗色主题文件不存在，回退到默认亮色主题
    if theme == 'dark' and not os.path.exists(style_file):
        logger.warning(f"暗色主题文件未找到: {style_file}，尝试加载默认主题")
        style_file = resource_path(os.path.join("resources", "styles", "style.qss"))

    if not os.path.exists(style_file):
        logger.error(f"样式文件未找到: {style_file}")
        return

    try:
        with open(style_file, "r", encoding='utf-8') as f:
            style_content = f.read()
            # 直接应用样式，不进行任何预处理
            app.setStyleSheet(style_content)
            logger.info(f"成功加载样式: {filename}")
    except Exception as e:
        logger.error(f"无法加载样式表 {filename}: {e}")