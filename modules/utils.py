# ShiCheng_Writer/modules/utils.py
import sys
import os

def get_app_root():
    """ 
    获取应用程序运行根目录 
    用于存放/读取数据库、备份文件夹等用户数据，以及定位资源文件
    """
    if getattr(sys, 'frozen', False):
        # 如果是打包后的 exe (Nuitka/PyInstaller)，返回 exe 所在目录
        return os.path.dirname(sys.executable)
    
    # 开发环境 (假设 utils.py 在 modules/ 下，上级目录的上一级是项目根目录)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def resource_path(relative_path):
    """ 
    获取资源的绝对路径 
    修复逻辑：Nuitka standalone 模式下，资源文件夹通常拷贝在 exe 同级目录下
    """
    base_path = get_app_root()
    return os.path.join(base_path, relative_path)