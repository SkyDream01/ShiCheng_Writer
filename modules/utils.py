# ShiCheng_Writer/modules/utils.py
import sys
import os

def resource_path(relative_path):
    """ 获取资源的绝对路径，无论是开发环境还是打包环境 """
    try:
        # PyInstaller/Nuitka 创建一个临时文件夹，并把路径存储在 _MEIPASS 中
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

def get_app_root():
    """ 
    [新增] 获取应用程序运行根目录 
    用于存放/读取数据库、备份文件夹等用户数据
    """
    if getattr(sys, 'frozen', False):
        # 如果是打包后的 exe，返回 exe 所在目录
        return os.path.dirname(sys.executable)
    
    # 开发环境 (假设 utils.py 在 modules/ 下，上级目录的上一级可能才是项目根，
    # 或者根据你的结构，main.py 在根目录，modules 在根目录内)
    # 这里假设 utils.py 在 <root>/modules/utils.py，所以向上两级是 root
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))