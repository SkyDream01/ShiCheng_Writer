# ShiCheng_Writer/modules/utils.py
import sys
import os

def resource_path(relative_path):
    """ 获取资源的绝对路径，无论是开发环境还是打包环境 """
    try:
        # PyInstaller 创建一个临时文件夹，并把路径存储在 _MEIPASS 中
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)