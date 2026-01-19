# ShiCheng_Writer/modules/utils.py
import sys
import os

def get_app_root():
    """ 
    获取应用程序运行根目录 
    用于存放/读取数据库、备份文件夹等用户数据，以及定位资源文件
    """
    if getattr(sys, 'frozen', False):
        # 打包后的环境
        exe_dir = os.path.dirname(sys.executable)
        # 检查是否是PyInstaller/Nuitka单文件模式
        if os.path.exists(os.path.join(exe_dir, 'resources')):
            return exe_dir
        return exe_dir
    
    # 开发环境：从当前文件向上查找项目根目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # 向上查找包含特定文件/目录的目录作为项目根
    markers = ['main.py', 'modules', 'resources']
    search_dir = current_dir
    
    while search_dir and search_dir != os.path.dirname(search_dir):
        if all(os.path.exists(os.path.join(search_dir, m)) for m in markers):
            return search_dir
        search_dir = os.path.dirname(search_dir)
    
    # 回退到原始逻辑
    return os.path.dirname(current_dir)

def resource_path(relative_path):
    """ 
    获取资源的绝对路径 
    修复逻辑：Nuitka standalone 模式下，资源文件夹通常拷贝在 exe 同级目录下
    """
    base_path = get_app_root()
    return os.path.join(base_path, relative_path)