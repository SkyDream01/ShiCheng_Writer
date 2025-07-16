# ShiCheng_Writer/modules/webdav_client.py
import requests
import xml.etree.ElementTree as ET
from urllib.parse import unquote, urljoin, urlparse
import os
import ssl
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

class LegacySslAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        context = create_urllib3_context()
        context.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)
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

        # 如果 path 为空, 说明操作目标是文件夹本身, 此时需确保 URL 以斜杠结尾
        # 这是许多 WebDAV 服务器在列出目录内容 (PROPFIND Depth: 1) 时所要求的
        if not path and not url.endswith('/'):
            url += '/'
        return url

    def test_connection(self):
        if not all([self.base_url, self.auth[0], self.auth[1]]):
            return False, "WebDAV 连接信息不完整。"
        
        try:
            propfind_url = self._get_full_url()
            propfind_res = self.session.request("PROPFIND", propfind_url, headers={"Depth": "0"}, timeout=10)

            if propfind_res.status_code == 404:
                # 尝试创建根目录
                mkcol_res = self.session.request("MKCOL", propfind_url.rstrip('/'), timeout=10)
                if mkcol_res.status_code in [201, 405]: # 405 Method Not Allowed 可能表示目录已存在
                    # 再次尝试 PROPFIND 验证
                    final_check = self.session.request("PROPFIND", propfind_url, headers={"Depth": "0"}, timeout=10)
                    if final_check.ok:
                        return True, "连接成功，云端目录已创建！"
                    else:
                        final_check.raise_for_status()
                else:
                    mkcol_res.raise_for_status()
            
            elif propfind_res.ok:
                 return True, "连接成功，云端目录已就绪！"
            else:
                propfind_res.raise_for_status()

        except requests.exceptions.RequestException as e:
            return False, f"连接失败: {e}"
        return False, "连接测试期间发生未知错误。"

    def list_files(self):
        headers = {"Depth": "1", "Content-Type": 'application/xml; charset="utf-8"'}
        xml_body = """<?xml version="1.0"?>
<d:propfind xmlns:d="DAV:"><d:prop><d:displayname/>
<d:resourcetype/><d:getcontentlength/><d:getlastmodified/></d:prop></d:propfind>"""
        
        try:
            list_url = self._get_full_url()
            response = self.session.request("PROPFIND", list_url, headers=headers, data=xml_body.encode('utf-8'), timeout=15)
            response.raise_for_status()

            files = []
            root = ET.fromstring(response.content)
            namespaces = {'d': 'DAV:'}
            
            # 获取请求的 URL 路径部分, 用于精确跳过自身
            request_path = urlparse(list_url).path

            for res in root.findall('d:response', namespaces):
                href = res.findtext('d:href', '', namespaces)
                href_path = unquote(urlparse(href).path)

                # 移除尾部斜杠以进行统一比较, 精确跳过目录本身
                if href_path.rstrip('/') == request_path.rstrip('/'):
                    continue

                name = os.path.basename(href_path.rstrip('/'))
                resourcetype_node = res.find('.//d:resourcetype', namespaces)
                is_collection = resourcetype_node.find('d:collection', namespaces) is not None
                
                modified_text = res.findtext('.//d:getlastmodified', None, namespaces)

                if not name:
                    continue

                files.append({
                    'name': name,
                    'modified': modified_text,
                    'type': 'collection' if is_collection else 'file'
                })
            return files

        except requests.exceptions.RequestException as e:
            print(f"列出WebDAV文件失败: {e}")
            return []

    def upload_file(self, local_path, remote_filename):
        remote_url = self._get_full_url(remote_filename)
        try:
            with open(local_path, 'rb') as f:
                response = self.session.put(remote_url, data=f, timeout=60)
            if response.status_code in [200, 201, 204]:
                return True, f"上传成功: {remote_filename}"
            else:
                response.raise_for_status()
        except requests.exceptions.RequestException as e:
            return False, f"上传失败: {e}"
        return False, "上传期间发生未知错误。"

    def download_file(self, remote_filename, local_path):
        remote_url = self._get_full_url(remote_filename)
        try:
            response = self.session.get(remote_url, timeout=60)
            response.raise_for_status()
            with open(local_path, 'wb') as f:
                f.write(response.content)
            return True, f"下载成功: {os.path.basename(local_path)}"
        except requests.exceptions.RequestException as e:
            return False, f"下载失败: {e}"
        return False, "下载期间发生未知错误。"

    def delete_file(self, remote_filename):
        remote_url = self._get_full_url(remote_filename)
        try:
            response = self.session.delete(remote_url, timeout=15)
            if response.status_code in [204, 404]: # 204 No Content (成功), 404 Not Found (可视为成功)
                return True, f"删除成功: {remote_filename}"
            else:
                response.raise_for_status()
        except requests.exceptions.RequestException as e:
            return False, f"删除失败: {e}"
        return False, "删除期间发生未知错误。"