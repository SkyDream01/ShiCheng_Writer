# ShiCheng_Writer/modules/webdav_client.py
import requests
import xml.etree.ElementTree as ET
from urllib.parse import unquote, urljoin, urlparse
import os
import ssl
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

class LegacySslAdapter(HTTPAdapter):
    """适配器：允许连接使用旧版 SSL/TLS 配置的服务器"""
    def init_poolmanager(self, *args, **kwargs):
        context = create_urllib3_context()
        try:
            context.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)
        except AttributeError:
            pass # 如果 Python 版本过新或 ssl 模块不支持，忽略即可
        kwargs['ssl_context'] = context
        return super().init_poolmanager(*args, **kwargs)

class WebDAVClient:
    def __init__(self, settings):
        self.base_url = settings.get('webdav_url')
        if not self.base_url:
            raise ValueError("WebDAV URL 不能为空。")
            
        self.auth = (settings.get('webdav_user'), settings.get('webdav_pass'))
        self.root_path = settings.get('webdav_root', '/shicheng/').strip('/')
        
        self.session = requests.Session()
        self.session.auth = self.auth
        self.session.mount('https://', LegacySslAdapter())

    def _get_full_url(self, path=''):
        base = self.base_url.rstrip('/')
        full_path = "/".join(part.strip('/') for part in [self.root_path, path] if part)
        url = f"{base}/{full_path}"

        # WebDAV 规范：列出集合内容时，URL 通常应以 / 结尾
        if not path and not url.endswith('/'):
            url += '/'
        return url

    def test_connection(self):
        if not all([self.base_url, self.auth[0], self.auth[1]]):
            return False, "WebDAV 连接信息不完整。"
        
        try:
            propfind_url = self._get_full_url()
            # Depth: 0 只检查根目录本身是否存在
            res = self.session.request("PROPFIND", propfind_url, headers={"Depth": "0"}, timeout=15)

            if res.status_code == 404:
                # 尝试 MKCOL 创建
                mk_res = self.session.request("MKCOL", propfind_url.rstrip('/'), timeout=15)
                if mk_res.status_code in [201, 200, 405]: 
                    # 405 可能意味着已存在（某些服务器实现）
                    return True, "连接成功，已尝试创建云端目录。"
                else:
                    return False, f"目录不存在且创建失败 (Code: {mk_res.status_code})"
            
            elif res.ok: # 200-299
                 return True, "连接成功，云端目录已就绪。"
            else:
                 return False, f"连接响应异常 (Code: {res.status_code})"

        except requests.exceptions.RequestException as e:
            return False, f"网络请求失败: {e}"
        except Exception as e:
            return False, f"未知错误: {e}"

    def list_files(self):
        """列出目录下的文件，增强了对不同 Server XML 格式的兼容性"""
        headers = {"Depth": "1", "Content-Type": 'application/xml; charset="utf-8"'}
        # 尽量精简请求体，只请求需要的属性
        xml_body = """<?xml version="1.0" encoding="utf-8" ?>
<D:propfind xmlns:D="DAV:"><D:prop>
<D:resourcetype/><D:getlastmodified/>
</D:prop></D:propfind>"""
        
        try:
            list_url = self._get_full_url()
            response = self.session.request("PROPFIND", list_url, headers=headers, data=xml_body.encode('utf-8'), timeout=20)
            response.raise_for_status()

            # 使用 ElementTree 解析
            # 注意：WebDAV 响应通常包含命名空间，如 {DAV:}response
            try:
                root = ET.fromstring(response.content)
            except ET.ParseError:
                print("WebDAV XML 解析失败")
                return []

            files = []
            request_path = urlparse(list_url).path.rstrip('/')

            # 使用通配符查找所有 response 节点，忽略命名空间前缀差异
            # .{*}response 匹配任意命名空间下的 response 标签
            for res in root.findall('.//{*}response'):
                href_node = res.find('.//{*}href')
                if href_node is None: continue
                
                href = href_node.text
                if not href: continue

                # 解析路径并解码 (处理中文路径 %E4...)
                parsed_href = urlparse(href)
                href_path = unquote(parsed_href.path).rstrip('/')

                # 跳过自身（目录本身）
                if href_path == request_path:
                    continue

                name = os.path.basename(href_path)
                if not name: continue

                # 检查是否是集合 (文件夹)
                is_collection = False
                rtype = res.find('.//{*}resourcetype')
                if rtype is not None:
                    if rtype.find('.//{*}collection') is not None:
                        is_collection = True
                
                # 获取修改时间
                modified_text = ""
                mod_node = res.find('.//{*}getlastmodified')
                if mod_node is not None:
                    modified_text = mod_node.text

                files.append({
                    'name': name,
                    'modified': modified_text,
                    'type': 'collection' if is_collection else 'file'
                })
            return files

        except Exception as e:
            print(f"列出WebDAV文件时出错: {e}")
            return []

    def upload_file(self, local_path, remote_filename):
        remote_url = self._get_full_url(remote_filename)
        try:
            with open(local_path, 'rb') as f:
                # 使用 stream 上传，避免大文件读入内存
                response = self.session.put(remote_url, data=f, timeout=120)
            if response.status_code in [200, 201, 204]:
                return True, f"上传成功: {remote_filename}"
            else:
                return False, f"上传失败 (Code: {response.status_code})"
        except Exception as e:
            return False, f"上传异常: {e}"

    def download_file(self, remote_filename, local_path):
        remote_url = self._get_full_url(remote_filename)
        try:
            response = self.session.get(remote_url, stream=True, timeout=120)
            if response.status_code == 200:
                with open(local_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                return True, f"下载成功: {os.path.basename(local_path)}"
            else:
                return False, f"下载失败 (Code: {response.status_code})"
        except Exception as e:
            return False, f"下载异常: {e}"

    def delete_file(self, remote_filename):
        remote_url = self._get_full_url(remote_filename)
        try:
            response = self.session.delete(remote_url, timeout=30)
            if response.status_code in [204, 200, 404]: 
                return True, f"删除成功: {remote_filename}"
            else:
                return False, f"删除失败 (Code: {response.status_code})"
        except Exception as e:
            return False, f"删除异常: {e}"