import sys
import subprocess
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                            QHBoxLayout, QLabel, QLineEdit, QPushButton,
                            QTextEdit, QProgressBar, QFileDialog,
                            QStackedWidget, QComboBox, QListWidget,
                            QScrollArea, QMessageBox, QTextBrowser, QDialog)
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer, QUrl, QIODevice
from PyQt5.QtGui import QIcon, QPixmap, QDesktopServices
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from DrissionPage import ChromiumPage
import requests
import re
import os
import time

class DownloadThread(QThread):
    update_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal()

    def __init__(self, url, save_path, max_count=0, parent=None):
        super().__init__(parent)
        self.url = url
        self.save_path = save_path
        self.max_count = max_count  # 0表示无限制
        self.running = True
        self.downloaded_count = 0
        self.start_page = 1  # 新增：起始页码
        self.current_page = 1  # 新增：当前页码

    def run(self):
        try:
            # 解析输入格式（如"1_2"表示从第1页开始下载2个）
            if isinstance(self.max_count, str) and '_' in self.max_count:
                parts = self.max_count.split('_')
                if len(parts) == 2:
                    self.start_page = max(1, int(parts[0]))
                    self.max_count = max(0, int(parts[1]))
            
            # 确保视频保存目录存在
            if not os.path.exists(self.save_path):
                os.makedirs(self.save_path)

            dp = ChromiumPage()
            dp.listen.start('aweme/v1/web/aweme/post/')
            dp.get(self.url)

            for page in range(self.start_page, 11):  # 从start_page开始
                self.current_page = page
                if not self.running or (self.max_count > 0 and self.downloaded_count >= self.max_count):
                    break
                    
                self.update_signal.emit(f'正在采集第{page}页数据内容...')

                try:
                    resp = dp.listen.wait()
                    json_data = resp.response.body
                    video_info_list = json_data.get('aweme_list', [])

                    for index in video_info_list:
                        if not self.running or (self.max_count > 0 and self.downloaded_count >= self.max_count):
                            break
                            
                        old_title = index.get('desc', '')
                        title = re.sub(r'[\\/:*?"<>|\n]', '', old_title) or f"无标题视频_{int(time.time())}"
                        video_url = index.get('video', {}).get('play_addr', {}).get('url_list', [])[0]

                        if not video_url:
                            continue

                        self.update_signal.emit(f"发现视频: {title}\n准备下载...")

                        headers = {
                            'user-agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
                            'referer': self.url
                        }

                        try:
                            # 使用流式下载提高速度
                            response = requests.get(url=video_url, headers=headers, timeout=30, stream=True)
                            total_size = int(response.headers.get('content-length', 0))
                            downloaded_size = 0
                            chunk_size = 8192  # 8KB缓冲区
                            
                            file_path = os.path.join(self.save_path, f'{title}.mp4')
                            
                            with open(file_path, mode='wb') as f:
                                for chunk in response.iter_content(chunk_size=chunk_size):
                                    if chunk:
                                        f.write(chunk)
                                        downloaded_size += len(chunk)
                                        
                            self.update_signal.emit(f"视频保存成功: {file_path}")
                            self.downloaded_count += 1  # 增加已下载计数
                            self.progress_signal.emit(int((self.downloaded_count / max(self.max_count, 1)) * 100))  # 更新进度

                        except Exception as e:
                            self.update_signal.emit(f"下载失败: {str(e)}")

                    # 翻页
                    if self.running and (self.max_count == 0 or self.downloaded_count < self.max_count):
                        dp.scroll.to_bottom()
                        time.sleep(0.5)  # 减少等待时间到0.5秒

                except Exception as e:
                    self.update_signal.emit(f"第{page}页数据加载失败: {str(e)}")

            dp.quit()
            self.update_signal.emit("所有视频下载完成!")
            self.finished_signal.emit()

        except Exception as e:
            self.update_signal.emit(f"发生错误: {str(e)}")
            self.finished_signal.emit()

    def stop(self):
        self.running = False

class SingleVideoDownloadThread(QThread):
    """单视频下载线程"""
    update_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal()

    def __init__(self, url, save_path, parent=None):
        super().__init__(parent)
        self.url = url
        self.save_path = save_path
        self.running = True

    def run(self):
        try:
            self.update_signal.emit('单视频下载线程开始运行')
            
            if not os.path.exists(self.save_path):
                os.makedirs(self.save_path)
                self.update_signal.emit(f'创建保存目录: {self.save_path}')

            self.update_signal.emit('正在初始化浏览器...')
            
            try:
                dp = ChromiumPage()
                self.update_signal.emit('浏览器初始化成功')
            except Exception as e:
                self.update_signal.emit(f'浏览器初始化失败: {str(e)}')
                self.finished_signal.emit()
                return
            
            # 存储捕获的视频URL
            captured_video_url = None

            self.update_signal.emit(f'正在打开页面: {self.url}')
            
            try:
                dp.get(self.url)
                self.update_signal.emit('页面加载成功，等待5秒...')
                time.sleep(5)  # 增加等待时间
                            
            except Exception as e:
                self.update_signal.emit(f'页面加载失败: {str(e)}')
                dp.quit()
                self.finished_signal.emit()
                return
            
            # 如果是jingxuan页面，可能需要点击视频
            if '/jingxuan/' in self.url:
                self.update_signal.emit('检测到精选页面，尝试点击视频...')
                try:
                    # 尝试点击第一个视频
                    video_card = dp.ele('xpath://div[contains(@class,"card")]//a', timeout=5)
                    if video_card:
                        video_card.click()
                        self.update_signal.emit('点击视频成功，等待3秒...')
                        time.sleep(3)
                except Exception as e:
                    self.update_signal.emit(f'点击视频失败: {str(e)}，继续尝试直接获取')

            # 获取视频信息
            self.update_signal.emit('正在获取视频标题...')
            video_title = None
            
            # 尝试多种方式获取标题
            title_selectors = [
                'xpath://div[@class="video-desc"]//span[@class="text"]',
                'xpath://h1[@class="title"]',
                'xpath://div[contains(@class,"title")]//span',
                'xpath://meta[@name="description"]',
                'xpath://title'
            ]
            
            for selector in title_selectors:
                try:
                    if 'meta' in selector:
                        video_title = dp.ele(selector, timeout=3).attr('content')
                    elif 'title' in selector:
                        video_title = dp.ele(selector, timeout=3).text
                    else:
                        video_title = dp.ele(selector, timeout=3).text
                    
                    if video_title:
                        video_title = re.sub(r'[\\/:*?"<>|\n]', '', video_title)[:50]
                        self.update_signal.emit(f'获取到标题: {video_title}')
                        break
                except:
                    continue
            
            if not video_title:
                self.update_signal.emit('获取标题失败，使用默认标题')
                video_title = f"无标题视频_{int(time.time())}"

            self.update_signal.emit(f'发现视频: {video_title}\n准备下载...')

            # 获取视频URL
            self.update_signal.emit('正在获取视频链接...')
            video_url = None
            
            # 方法0: 使用网络监听捕获的URL
            if captured_video_url:
                video_url = captured_video_url
                self.update_signal.emit(f'使用网络监听捕获的URL: {video_url[:50]}...')
            
            # 方法1: 优先从页面源码提取（避免blob URL）
            if not video_url:
                self.update_signal.emit('尝试从页面源码提取视频链接...')
            try:
                page_source = dp.html
                self.update_signal.emit(f'页面源码长度: {len(page_source)}')
                
                # 尝试多种正则表达式
                patterns = [
                    r'"playAddr":\[{"uri":"([^"]+)"',
                    r'"playAddr":\[{"url":"([^"]+)"',
                    r'"playUrl":"([^"]+)"',
                    r'"video":\{"playAddr":\[{"url":"([^"]+)"',
                    r'"renderCommon":"([^"]+)"',
                    r'"content":"([^"]+\.mp4[^"]*)"',
                    r'"url_list":\["([^"]+)"',
                    r'"download_addr":\{"url_list":\["([^"]+)"',
                    r'"origin_cover":\{"url_list":\["([^"]+)"',
                    r'"video":\{"play_addr":\{"uri":"([^"]+)"',
                    r'"play_addr":\{"uri":"([^"]+)"',
                    r'"video":\{"download_addr":\{"uri":"([^"]+)"'
                ]
                
                for pattern in patterns:
                    video_match = re.search(pattern, page_source)
                    if video_match:
                        video_url = video_match.group(1)
                        if not video_url.startswith('http'):
                            video_url = 'https:' + video_url.replace('\\/', '/')
                        self.update_signal.emit(f'从页面源码提取到链接: {video_url[:50]}...')
                        break
                
                # 如果找到了url_list但没有HTTP前缀，尝试提取完整的URL
                if not video_url:
                    # 查找url_list数组中的完整URL
                    url_list_match = re.search(r'"url_list":\s*\[\s*"([^"]+)"', page_source)
                    if url_list_match:
                        potential_url = url_list_match.group(1)
                        # 如果是相对路径或缺少协议，尝试构建完整URL
                        if potential_url.startswith('/'):
                            # 尝试从页面中查找基础URL
                            base_url_match = re.search(r'https://[^/]+', self.url)
                            if base_url_match:
                                video_url = base_url_match.group(0) + potential_url
                                self.update_signal.emit(f'构建完整URL: {video_url[:50]}...')
                        elif not potential_url.startswith('http'):
                            # 检查是否是包含douyinvod.com的路径
                            if 'douyinvod.com' in potential_url:
                                video_url = potential_url
                                self.update_signal.emit(f'从url_list找到视频链接: {video_url[:50]}...')
                        else:
                            video_url = potential_url
                            self.update_signal.emit(f'从url_list提取到链接: {video_url[:50]}...')
                
                if not video_url:
                    # 尝试查找所有包含.mp4的URL，但排除客户端下载链接
                    mp4_matches = re.findall(r'https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*', page_source)
                    for match in mp4_matches:
                        # 只排除真正的客户端下载链接
                        if ('client' in match.lower() and 'download' in match.lower()) or 'douyin_pc_client' in match.lower():
                            self.update_signal.emit(f'跳过客户端下载链接: {match[:50]}...')
                            continue
                        video_url = match.replace('\\/', '/')
                        self.update_signal.emit(f'从页面源码找到mp4链接: {video_url[:50]}...')
                        break
                
                # 如果仍然没找到，尝试查找抖音视频域名的URL
                if not video_url:
                    # 查找包含douyinvod.com的URL，这通常是真实的视频URL
                    douyin_video_pattern = r'https://[a-z0-9.-]*douyinvod\.com/[^"\'<>\s]+' 
                    douyin_video_matches = re.findall(douyin_video_pattern, page_source)
                    if douyin_video_matches:
                        for match in douyin_video_matches:
                            # 排除静态资源链接，寻找包含/tos/或/video/路径的链接
                            if ('/tos/' in match or '/video/' in match) and 'client' not in match.lower() and 'download' not in match.lower():
                                video_url = match
                                self.update_signal.emit(f'从页面源码找到抖音视频链接: {video_url[:50]}...')
                                break
                        
            except Exception as e:
                self.update_signal.emit(f'从页面源码提取失败: {str(e)}')
                import traceback
                self.update_signal.emit(f'错误详情: {traceback.format_exc()}')
            
            # 方法2: 从video标签获取（检查是否为blob URL）
            if not video_url or video_url.startswith('blob:'):
                try:
                    temp_url = dp.ele('xpath://video').attr('src')
                    if temp_url and not temp_url.startswith('blob:'):
                        video_url = temp_url
                        self.update_signal.emit(f'从video标签获取到链接: {video_url[:50]}...')
                    elif temp_url and temp_url.startswith('blob:'):
                        self.update_signal.emit('检测到blob URL，跳过此方法')
                except Exception as e:
                    self.update_signal.emit(f'从video标签获取失败: {str(e)}')
            
            # 方法3: 从play-btn获取
            if not video_url:
                try:
                    video_url = dp.ele('xpath://*[@class="play-btn"]').attr('data-src')
                    if video_url:
                        self.update_signal.emit(f'从play-btn获取到链接: {video_url[:50]}...')
                except Exception as e:
                    self.update_signal.emit(f'从play-btn获取失败: {str(e)}')
            
            # 方法4: 从xg-video-container获取
            if not video_url:
                try:
                    temp_url = dp.ele('xpath://xg-video-container//video').attr('src')
                    if temp_url and not temp_url.startswith('blob:'):
                        video_url = temp_url
                        self.update_signal.emit(f'从xg-video-container获取到链接: {video_url[:50]}...')
                except Exception as e:
                    self.update_signal.emit(f'从xg-video-container获取失败: {str(e)}')
            
            # 方法5: 通过JavaScript获取视频URL
            if not video_url:
                self.update_signal.emit('尝试通过JavaScript获取视频URL...')
                try:
                    # 尝试从各种全局变量获取
                    js_codes = [
                        "window._SSR_HYDRATED_DATA ? JSON.stringify(window._SSR_HYDRATED_DATA) : ''",
                        "window.microData ? JSON.stringify(window.microData) : ''",
                        "window.__INIT_PROPS__ ? JSON.stringify(window.__INIT_PROPS__) : ''",
                        "window.byted_hydrated_data ? JSON.stringify(window.byted_hydrated_data) : ''"
                    ]
                    
                    for js_code in js_codes:
                        try:
                            result = dp.run_js(js_code)
                            if result and result.strip():
                                # 在结果中查找视频URL，包括url_list结构
                                # 先查找url_list数组中的链接
                                try:
                                    import json
                                    # 尝试解析JSON并查找url_list
                                    json_data = json.loads(result)
                                    # 递归查找url_list
                                    def find_url_list(obj):
                                        if isinstance(obj, dict):
                                            for key, value in obj.items():
                                                if key == 'url_list' and isinstance(value, list) and len(value) > 0:
                                                    return value[0]
                                                result = find_url_list(value)
                                                if result:
                                                    return result
                                        elif isinstance(obj, list):
                                            for item in obj:
                                                result = find_url_list(item)
                                                if result:
                                                    return result
                                        return None
                                    
                                    found_url = find_url_list(json_data)
                                    if found_url and 'client' not in found_url.lower() and 'download' not in found_url.lower():
                                        video_url = found_url
                                        self.update_signal.emit(f'从JS数据url_list获取到链接: {video_url[:50]}...')
                                        break
                                except:
                                    # 如果不是JSON格式，使用正则表达式
                                    video_matches = re.findall(r'https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*', result)
                                    for match in video_matches:
                                        # 排除客户端下载链接
                                        if 'douyin_pc_client' in match.lower():
                                            continue
                                        video_url = match.replace('\\/', '/')
                                        self.update_signal.emit(f'从JS数据获取到链接: {video_url[:50]}...')
                                        break
                                    
                                    # 也尝试查找douyinvod.com的链接
                                    if not video_url:
                                        douyin_matches = re.findall(r'https://[a-z0-9.-]*douyinvod\.com/[^"\'<>\s]+', result)
                                        for match in douyin_matches:
                                            if ('/tos/' in match or '/video/' in match) and 'client' not in match.lower() and 'download' not in match.lower():
                                                video_url = match
                                                self.update_signal.emit(f'从JS数据获取到抖音视频链接: {video_url[:50]}...')
                                                break
                                if video_url:
                                    break
                        except:
                            continue
                except Exception as e:
                    self.update_signal.emit(f'通过JavaScript获取失败: {str(e)}')
            
            # 方法6: 尝试从video元素的source获取
            if not video_url:
                try:
                    sources = dp.eles('xpath://video/source')
                    for source in sources:
                        src = source.attr('src')
                        if src and not src.startswith('blob:'):
                            video_url = src
                            self.update_signal.emit(f'从video source获取到链接: {video_url[:50]}...')
                            break
                except Exception as e:
                    self.update_signal.emit(f'从video source获取失败: {str(e)}')

            # 清理和验证视频URL
            if video_url:
                # 解码URL
                from urllib.parse import unquote
                video_url = unquote(video_url)
                # 移除转义的反斜杠
                video_url = video_url.replace('\\', '')
                self.update_signal.emit(f'清理后的URL: {video_url[:50]}...')
            
            if not video_url or ('client' in video_url.lower() and 'download' in video_url.lower()):
                self.update_signal.emit('错误: 无法获取有效的视频链接')
                dp.quit()
                self.finished_signal.emit()
                return

            # 下载视频
            self.update_signal.emit(f'开始下载视频，URL长度: {len(video_url)}')
            headers = {
                'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36',
                'referer': self.url
            }

            try:
                self.update_signal.emit('发送下载请求...')
                response = requests.get(url=video_url, headers=headers, timeout=30, stream=True)
                response.raise_for_status()
                self.update_signal.emit(f'请求成功，状态码: {response.status_code}')

                file_path = os.path.join(self.save_path, f'{video_title}.mp4')
                self.update_signal.emit(f'保存到: {file_path}')

                # 获取文件大小
                total_size = int(response.headers.get('content-length', 0))
                if total_size > 0:
                    self.update_signal.emit(f'文件大小: {total_size/1024/1024:.2f} MB')
                else:
                    self.update_signal.emit('文件大小未知，开始下载...')

                downloaded_size = 0
                unknown_size_progress = 0  # 用于未知大小时的进度动画
                chunk_count = 0

                with open(file_path, mode='wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded_size += len(chunk)
                            chunk_count += 1

                            # 如果知道总大小，计算百分比进度
                            if total_size > 0:
                                progress = int((downloaded_size / total_size) * 100)
                                self.progress_signal.emit(progress)
                            else:
                                # 未知大小时，使用动画进度（0-100来回循环）
                                unknown_size_progress = (unknown_size_progress + 5) % 101
                                # 每下载50个chunk更新一次进度
                                if chunk_count % 50 == 0:
                                    self.progress_signal.emit(unknown_size_progress)
                                    mb_downloaded = downloaded_size / (1024 * 1024)
                                    self.update_signal.emit(f'已下载: {mb_downloaded:.2f} MB')

                self.update_signal.emit(f'视频保存成功: {file_path} ({downloaded_size/1024/1024:.2f} MB)')
                self.progress_signal.emit(100)

            except Exception as e:
                self.update_signal.emit(f'下载失败: {str(e)}')
                # 即使下载失败，也重置进度条
                self.progress_signal.emit(0)

            dp.quit()
            self.update_signal.emit('单视频下载完成!')
            self.finished_signal.emit()

        except Exception as e:
            self.update_signal.emit(f'发生错误: {str(e)}')
            import traceback
            self.update_signal.emit(f'错误详情: {traceback.format_exc()}')
            self.finished_signal.emit()

    def stop(self):
        """停止下载线程"""
        self.running = False

class DouyinDownloader(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setStyleSheet("""
            QMainWindow {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #2d3436, stop:1 #636e72);
            }
            QWidget {
                background: transparent;
                color: #dfe6e9;
            }
            QLabel {
                color: #ffffff;
                font-size: 14px;
                font-weight: 600;
                background: transparent;
            }
            QLineEdit {
                background: rgba(255, 255, 255, 0.1);
                border: 2px solid rgba(255, 255, 255, 0.2);
                border-radius: 8px;
                padding: 10px;
                color: #ffffff;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 2px solid #00b894;
                background: rgba(255, 255, 255, 0.15);
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00b894, stop:1 #00cec9);
                color: #ffffff;
                border: none;
                border-radius: 8px;
                padding: 14px 28px;
                font-size: 14px;
                font-weight: bold;
                min-height: 40px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00cec9, stop:1 #81ecec);
            }
            QPushButton:pressed {
                background: #0984e3;
            }
            QPushButton:disabled {
                background: rgba(255, 255, 255, 0.2);
                color: rgba(255, 255, 255, 0.5);
            }
            QTextEdit {
                background: rgba(0, 0, 0, 0.3);
                border: 2px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                color: #00ff88;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 12px;
                padding: 10px;
            }
            QProgressBar {
                border: none;
                border-radius: 10px;
                background: rgba(255, 255, 255, 0.1);
                text-align: center;
                color: #ffffff;
                height: 25px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00b894, stop:1 #fd79a8);
                border-radius: 10px;
            }
            QComboBox {
                background: rgba(255, 255, 255, 0.1);
                border: 2px solid rgba(255, 255, 255, 0.2);
                border-radius: 8px;
                padding: 10px;
                color: #ffffff;
                font-size: 13px;
                min-width: 80px;
            }
            QComboBox:hover {
                border: 2px solid #00b894;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
                border: 5px solid transparent;
                border-top: 8px solid #ffffff;
                margin-right: 5px;
            }
            QComboBox QAbstractItemView {
                background: rgba(45, 52, 54, 0.95);
                border: 2px solid rgba(255, 255, 255, 0.2);
                border-radius: 8px;
                selection-background-color: #00b894;
                color: #ffffff;
            }
        """)
        self.download_thread = None
        self.single_download_thread = None  # 单视频下载线程
        self.sidebar_buttons = []  # 存储侧边栏按钮
        self.progress_value = 0  # 进度值
        self.progress_direction = 1  # 进度方向 1=前进, -1=后退
        self.default_save_path = os.path.join(os.path.dirname(__file__), '视频下载')  # 默认保存路径
        
        # 创建默认下载文件夹
        if not os.path.exists(self.default_save_path):
            os.makedirs(self.default_save_path)
        
        # 进度条动画计时器
        self.progress_timer = QTimer()
        self.progress_timer.timeout.connect(self.update_progress_animation)
        self.progress_timer.start(50)  # 每50ms更新一次
        
        self.initUI()

    def initUI(self):
        # 设置窗口图标
        icon_path = os.path.join(os.path.dirname(__file__), '2.png')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        self.setWindowTitle('抖音视频下载器 - 红丽科技')
        self.setGeometry(100, 100, 700, 650)
        
        # 主容器
        main_widget = QWidget()
        main_layout = QVBoxLayout()
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # ============ 顶部导航栏 ============
        nav_bar = QWidget()
        nav_bar.setFixedHeight(60)
        nav_bar.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #667eea, stop:1 #764ba2);
                border-bottom: 2px solid rgba(255, 255, 255, 0.1);
            }
        """)
        nav_layout = QHBoxLayout()
        nav_layout.setContentsMargins(20, 0, 20, 0)
        
        # Logo和应用名称
        logo_label = QLabel('🎥 抖音视频下载器 Pro')
        logo_label.setStyleSheet("""
            QLabel {
                font-size: 22px;
                font-weight: bold;
                color: #ffffff;
                padding: 5px 15px;
            }
        """)
        nav_layout.addWidget(logo_label)
        
        nav_layout.addStretch()
        
        # 导航按钮
        nav_btn_style = """
            QPushButton {
                background: transparent;
                border: none;
                color: rgba(255, 255, 255, 0.8);
                font-size: 14px;
                padding: 10px 22px;
                border-radius: 6px;
                min-height: 40px;
                height: 40px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.2);
                color: #ffffff;
            }
            QPushButton:pressed {
                background: rgba(255, 255, 255, 0.1);
            }
        """

        home_btn = QPushButton('🏠 首页')
        home_btn.setStyleSheet(nav_btn_style)
        home_btn.setFixedHeight(40)
        home_btn.clicked.connect(lambda: self.switch_page(0))  # 导航到批量下载页面
        nav_layout.addWidget(home_btn)

        settings_btn = QPushButton('⚙️ 设置')
        settings_btn.setStyleSheet(nav_btn_style)
        settings_btn.setFixedHeight(40)
        settings_btn.clicked.connect(lambda: self.switch_page(4))  # 导航到偏好设置页面
        nav_layout.addWidget(settings_btn)

        about_btn = QPushButton('ℹ️ 关于')
        about_btn.setStyleSheet(nav_btn_style)
        about_btn.setFixedHeight(40)
        about_btn.clicked.connect(lambda: self.switch_page(8))  # 导航到关于页面
        nav_layout.addWidget(about_btn)
        
        nav_bar.setLayout(nav_layout)
        main_layout.addWidget(nav_bar)
        
        # ============ 中间区域（左右布局） ============
        content_area = QWidget()
        content_layout = QHBoxLayout()
        content_layout.setSpacing(0)
        content_layout.setContentsMargins(0, 0, 0, 0)
        
        # ============ 左侧边栏 ============
        sidebar = QWidget()
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet("""
            QWidget {
                background: #1e1e1e;
                border-right: 2px solid rgba(255, 255, 255, 0.1);
            }
        """)
        sidebar_layout = QVBoxLayout()
        sidebar_layout.setSpacing(5)
        sidebar_layout.setContentsMargins(10, 15, 10, 15)
        
        # 边栏标题
        sidebar_title = QLabel('功能菜单')
        sidebar_title.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: #00cec9;
                padding: 5px;
                border-bottom: 2px solid rgba(0, 206, 201, 0.3);
            }
        """)
        sidebar_layout.addWidget(sidebar_title)
        sidebar_layout.addSpacing(15)
        
        # 边栏菜单按钮样式 - 紧凑设计，带背景色
        sidebar_btn_style = """
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.1);
                color: rgba(255, 255, 255, 0.8);
                font-size: 13px;
                padding: 6px 10px;
                text-align: left;
                border-radius: 5px;
                min-height: 32px;
                max-height: 32px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(102, 126, 234, 0.6), stop:1 rgba(118, 75, 162, 0.6));
                border: 1px solid rgba(102, 126, 234, 0.5);
                color: #ffffff;
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(102, 126, 234, 0.8), stop:1 rgba(118, 75, 162, 0.8));
            }
        """
        
        # 侧边栏菜单项
        menu_items = [
            ('📥 批量下载', 0),
            ('🎬 视频管理', 1),
            ('📂 文件夹浏览', 2),
            ('📊 下载统计', 3),
            ('⚙️ 偏好设置', 4),
            ('💬 软件交流区', 5),
            ('📝 运行日志', 6),
            ('❓ 帮助中心', 7)
        ]
        
        for item_text, page_index in menu_items:
            btn = QPushButton(item_text)
            btn.setStyleSheet(sidebar_btn_style)
            btn.setProperty('page_index', page_index)
            btn.setFixedHeight(34)
            btn.clicked.connect(lambda checked, idx=page_index: self.switch_page(idx))
            sidebar_layout.addWidget(btn)
            self.sidebar_buttons.append(btn)
        
        sidebar_layout.addStretch()
        
        # 边栏底部信息
        info_label = QLabel('📌 v2.0.1')
        info_label.setStyleSheet("""
            QLabel {
                font-size: 12px;
                color: rgba(255, 255, 255, 0.4);
            }
        """)
        sidebar_layout.addWidget(info_label)
        
        sidebar.setLayout(sidebar_layout)
        content_layout.addWidget(sidebar)
        
        # ============ 右侧内容区 ============
        # 创建页面切换器
        self.page_stack = QStackedWidget()
        
        # 创建各个页面
        self.create_batch_download_page()  # 页面0: 批量下载
        self.create_video_manage_page()     # 页面1: 视频管理
        self.create_folder_browse_page()    # 页面2: 文件夹浏览
        self.create_download_stats_page()   # 页面3: 下载统计
        self.create_settings_page()         # 页面4: 偏好设置
        self.create_community_page()        # 页面5: 软件交流区
        self.create_log_page()             # 页面6: 运行日志
        self.create_help_page()             # 页面7: 帮助中心
        self.create_about_page()            # 页面8: 关于我们
        
        content_layout.addWidget(self.page_stack)
        
        content_area.setLayout(content_layout)
        main_layout.addWidget(content_area)
        
        # ============ 底部状态栏 ============
        status_bar = QWidget()
        status_bar.setFixedHeight(35)
        status_bar.setStyleSheet("""
            QWidget {
                background: #1a1a1a;
                border-top: 2px solid rgba(255, 255, 255, 0.1);
            }
        """)
        status_layout = QHBoxLayout()
        status_layout.setContentsMargins(20, 0, 20, 0)
        
        self.status_label = QLabel('📊 状态: 就绪')
        self.status_label.setStyleSheet("""
            QLabel {
                font-size: 13px;
                color: rgba(255, 255, 255, 0.6);
            }
        """)
        status_layout.addWidget(self.status_label)
        
        status_layout.addStretch()
        
        time_label = QLabel('⏰')
        time_label.setStyleSheet("""
            QLabel {
                font-size: 13px;
                color: rgba(255, 255, 255, 0.6);
            }
        """)
        status_layout.addWidget(time_label)
        
        status_bar.setLayout(status_layout)
        main_layout.addWidget(status_bar)
        
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

    # 修改start_download方法
    def start_download(self):
        url = self.url_input.text().strip()
        save_path = self.default_save_path  # 直接使用默认保存路径

        if not url:
            self.log_output.append('错误: 请输入有效的抖音用户主页URL')
            return

        # 获取选择的值
        start_page = int(self.start_page_combo.currentText().split()[1])
        max_count = self.count_combo.currentData()

        self.log_output.clear()
        self.progress_bar.setValue(0)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        self.download_thread = DownloadThread(url, save_path, f"{start_page}_{max_count}")
        self.download_thread.update_signal.connect(self.update_log)
        self.download_thread.progress_signal.connect(self.update_progress)
        self.download_thread.finished_signal.connect(self.download_finished)
        self.download_thread.start()

    def download_single_video(self):
        """下载单个视频"""
        url = self.single_video_input.text().strip()
        save_path = self.default_save_path

        self.log_output.append(f'开始单视频下载，URL: {url[:50]}...')

        if not url:
            self.log_output.append('错误: 请输入有效的抖音视频URL')
            return

        # 检查是否是有效的视频链接（支持多种格式）
        is_video_url = '/video/' in url or '/jingxuan/' in url or 'modal_id=' in url or 'aweme_id=' in url
        if not is_video_url:
            self.log_output.append('错误: 请输入有效的视频链接')
            return

        self.log_output.clear()
        self.progress_bar.setValue(0)
        self.start_btn.setEnabled(False)
        self.single_download_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        try:
            self.single_download_thread = SingleVideoDownloadThread(url, save_path)
            self.single_download_thread.update_signal.connect(self.update_log)
            self.single_download_thread.progress_signal.connect(self.update_progress)
            self.single_download_thread.finished_signal.connect(self.download_finished)
            self.single_download_thread.start()
            self.log_output.append('单视频下载线程已启动')
        except Exception as e:
            self.log_output.append(f'启动下载线程失败: {str(e)}')
            self.start_btn.setEnabled(True)
            self.single_download_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)

    def stop_download(self):
        if self.download_thread:
            self.download_thread.stop()
            self.log_output.append('正在停止下载...')
            self.stop_btn.setEnabled(False)
        if self.single_download_thread:
            self.single_download_thread.stop()
            self.log_output.append('正在停止下载...')
            self.stop_btn.setEnabled(False)

    def update_log(self, message):
        self.log_output.append(message)
        
        # 更新状态栏
        if '发现视频:' in message:
            # 提取视频标题
            video_title = message.split('发现视频:')[1].strip()
            self.status_label.setText(f'📊 正在下载: {video_title}')
        elif '视频保存成功' in message:
            # 视频下载成功
            self.status_label.setText('📊 状态: 下载成功')
        elif '所有视频下载完成' in message or '发生错误' in message:
            # 下载完成或出错
            self.status_label.setText('📊 状态: 就绪')

    def update_progress(self, value):
        self.progress_bar.setValue(value)
    
    def update_progress_animation(self):
        """更新进度条动画效果"""
        if self.download_thread and self.download_thread.running:
            # 下载中显示无限循环绿色动画
            self.progress_value += 2 * self.progress_direction
            if self.progress_value >= 100:
                self.progress_direction = -1
            elif self.progress_value <= 0:
                self.progress_direction = 1
            self.progress_bar.setValue(self.progress_value)
        else:
            self.progress_bar.setValue(0)

    def download_finished(self):
        self.start_btn.setEnabled(True)
        self.single_download_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setValue(100)

    def refresh_video_list(self):
        """刷新视频列表"""
        try:
            self.video_list.clear()

            if not os.path.exists(self.default_save_path):
                self.video_count_label.setText('📊 总共: 0 个视频')
                return

            # 获取所有mp4文件
            files = [f for f in os.listdir(self.default_save_path) if f.endswith('.mp4')]
            files.sort(key=lambda x: os.path.getmtime(os.path.join(self.default_save_path, x)), reverse=True)

            # 添加到列表
            for file in files:
                file_path = os.path.join(self.default_save_path, file)
                file_size = os.path.getsize(file_path)
                file_mtime = os.path.getmtime(file_path)

                # 格式化文件大小
                if file_size < 1024 * 1024:
                    size_str = f'{file_size / 1024:.1f} KB'
                elif file_size < 1024 * 1024 * 1024:
                    size_str = f'{file_size / (1024 * 1024):.1f} MB'
                else:
                    size_str = f'{file_size / (1024 * 1024 * 1024):.1f} GB'

                # 格式化时间
                import datetime
                mtime_str = datetime.datetime.fromtimestamp(file_mtime).strftime('%Y-%m-%d %H:%M')

                # 创建列表项
                item_text = f'🎬 {file}\n📏 {size_str}  🕒 {mtime_str}'
                self.video_list.addItem(item_text)
                # 存储完整路径
                self.video_list.item(self.video_list.count() - 1).setData(256, file_path)

            self.video_count_label.setText(f'📊 总共: {len(files)} 个视频')
            self.log_output.append(f'✅ 已刷新视频列表，共 {len(files)} 个文件')

        except Exception as e:
            self.log_output.append(f'❌ 刷新视频列表失败: {str(e)}')

    def delete_selected_video(self):
        """删除选中的视频"""
        try:
            selected_items = self.video_list.selectedItems()

            if not selected_items:
                self.log_output.append('⚠️ 请先选择要删除的视频')
                return

            from PyQt5.QtWidgets import QMessageBox

            reply = QMessageBox.question(
                self,
                '确认删除',
                f'确定要删除选中的 {len(selected_items)} 个视频吗？',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                deleted_count = 0
                for item in selected_items:
                    file_path = item.data(256)  # 获取文件路径
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        deleted_count += 1

                self.refresh_video_list()
                self.log_output.append(f'✅ 已删除 {deleted_count} 个视频')

        except Exception as e:
            self.log_output.append(f'❌ 删除视频失败: {str(e)}')

    def open_selected_video(self):
        """打开选中的视频"""
        try:
            selected_items = self.video_list.selectedItems()

            if not selected_items:
                self.log_output.append('⚠️ 请先选择要打开的视频')
                return

            file_path = selected_items[0].data(256)  # 获取文件路径

            if os.path.exists(file_path):
                # 打开视频文件
                import subprocess
                if os.name == 'nt':  # Windows系统
                    os.startfile(file_path)
                elif os.name == 'posix':  # Linux/Mac系统
                    subprocess.run(['xdg-open', file_path])

                self.log_output.append(f'✅ 已打开视频: {os.path.basename(file_path)}')
            else:
                self.log_output.append(f'❌ 文件不存在: {file_path}')

        except Exception as e:
            self.log_output.append(f'❌ 打开视频失败: {str(e)}')

    def refresh_all(self):
        """重置所有输入参数"""
        # 保留网址不清空
        self.start_page_combo.setCurrentIndex(0)  # 重置为第一页
        self.count_combo.setCurrentIndex(0)      # 重置为"全部"
        self.progress_bar.setValue(0)
        self.log_output.clear()

        # 如果正在下载则停止
        if self.download_thread and self.download_thread.isRunning():
            self.download_thread.stop()
            self.download_thread.wait()

        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setValue(100)  # 修正缩进
    
    def switch_page(self, page_index):
        """切换页面"""
        self.page_stack.setCurrentIndex(page_index)

        # 切换到下载统计页面时自动更新统计
        if page_index == 3:  # 下载统计页面
            self.update_download_stats()

        # 切换到文件夹浏览页面时自动更新统计
        if page_index == 2:  # 文件夹浏览页面
            self.update_download_stats()

        # 切换到视频管理页面时自动刷新视频列表
        if page_index == 1:  # 视频管理页面
            self.refresh_video_list()

        # 更新侧边栏按钮样式 - 选中状态
        for i, btn in enumerate(self.sidebar_buttons):
            if i == page_index:
                btn.setStyleSheet("""
                    QPushButton {
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                            stop:0 rgba(102, 126, 234, 0.7), stop:1 rgba(118, 75, 162, 0.7));
                        border: 1px solid rgba(0, 206, 201, 0.6);
                        color: #ffffff;
                        font-size: 13px;
                        padding: 6px 10px;
                        text-align: left;
                        border-radius: 5px;
                        min-height: 32px;
                        max-height: 32px;
                        font-weight: bold;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background: rgba(255, 255, 255, 0.08);
                        border: 1px solid rgba(255, 255, 255, 0.1);
                        color: rgba(255, 255, 255, 0.8);
                        font-size: 13px;
                        padding: 6px 10px;
                        text-align: left;
                        border-radius: 5px;
                        min-height: 32px;
                        max-height: 32px;
                    }
                    QPushButton:hover {
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                            stop:0 rgba(102, 126, 234, 0.6), stop:1 rgba(118, 75, 162, 0.6));
                        border: 1px solid rgba(102, 126, 234, 0.5);
                        color: #ffffff;
                    }
                    QPushButton:pressed {
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                            stop:0 rgba(102, 126, 234, 0.8), stop:1 rgba(118, 75, 162, 0.8));
                    }
                """)
    
    def create_batch_download_page(self):
        """创建批量下载页面"""
        page = QWidget()
        page.setStyleSheet("""
            QWidget {
                background: #2d2d2d;
            }
        """)
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(25, 25, 25, 25)
        
        # 页面标题
        page_title = QLabel('批量下载设置')
        page_title.setStyleSheet("""
            QLabel {
                font-size: 24px;
                font-weight: bold;
                color: #ffffff;
                padding: 10px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(0, 206, 201, 0.2), stop:1 rgba(253, 121, 168, 0.2));
                border-radius: 10px;
                border-left: 4px solid #00cec9;
            }
        """)
        layout.addWidget(page_title)
        
        # ==================== 第1区：基础配置 ====================
        config_group = QWidget()
        config_group.setStyleSheet("""
            QWidget {
                background: rgba(255, 255, 255, 0.05);
                border-radius: 12px;
                padding: 18px;
                border: 1px solid rgba(0, 206, 201, 0.15);
            }
        """)
        config_layout = QVBoxLayout()
        config_layout.setSpacing(12)
        
        # 区块标题
        config_title = QLabel('🔗 基础配置')
        config_title.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: #00cec9;
                padding: 5px 0;
                border-bottom: 2px solid rgba(0, 206, 201, 0.3);
                margin-bottom: 8px;
            }
        """)
        config_layout.addWidget(config_title)
        
        # URL配置
        url_row = QHBoxLayout()
        url_label = QLabel('📌 抖音主页URL:')
        url_label.setStyleSheet("font-size: 13px; color: #dfe6e9; min-width: 120px;")
        url_row.addWidget(url_label)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText('https://www.douyin.com/user/...')
        url_row.addWidget(self.url_input)
        config_layout.addLayout(url_row)

        # 单视频下载配置
        single_video_row = QHBoxLayout()
        single_video_label = QLabel('🎬 单视频URL:')
        single_video_label.setStyleSheet("font-size: 13px; color: #dfe6e9; min-width: 120px;")
        single_video_row.addWidget(single_video_label)
        self.single_video_input = QLineEdit()
        self.single_video_input.setPlaceholderText('https://www.douyin.com/video/...')
        single_video_row.addWidget(self.single_video_input)
        config_layout.addLayout(single_video_row)

        config_group.setLayout(config_layout)
        layout.addWidget(config_group)
        
        # ==================== 第2区：下载参数 ====================
        params_group = QWidget()
        params_group.setStyleSheet("""
            QWidget {
                background: rgba(255, 255, 255, 0.05);
                border-radius: 12px;
                padding: 18px;
                border: 1px solid rgba(255, 234, 167, 0.15);
            }
        """)
        params_layout = QHBoxLayout()
        params_layout.setSpacing(30)
        
        # 起始页码
        page_config = QWidget()
        page_config_layout = QVBoxLayout()
        page_config_layout.setSpacing(8)
        
        page_title_lbl = QLabel('📄 起始页码')
        page_title_lbl.setStyleSheet("font-size: 14px; color: #ffeaa7; font-weight: bold;")
        page_config_layout.addWidget(page_title_lbl)
        
        self.start_page_combo = QComboBox()
        for i in range(1, 11):
            self.start_page_combo.addItem(f'第 {i} 页')
        page_config_layout.addWidget(self.start_page_combo)
        page_config.setLayout(page_config_layout)
        params_layout.addWidget(page_config)
        
        # 下载数量
        count_config = QWidget()
        count_config_layout = QVBoxLayout()
        count_config_layout.setSpacing(8)
        
        count_title_lbl = QLabel('📊 下载数量')
        count_title_lbl.setStyleSheet("font-size: 14px; color: #81ecec; font-weight: bold;")
        count_config_layout.addWidget(count_title_lbl)
        
        self.count_combo = QComboBox()
        self.count_combo.addItem('🔄 全部', 0)
        for i in range(1, 21):
            self.count_combo.addItem(f'📥 {i} 个', i)
        count_config_layout.addWidget(self.count_combo)
        count_config.setLayout(count_config_layout)
        params_layout.addWidget(count_config)
        
        params_group.setLayout(params_layout)
        layout.addWidget(params_group)
        
        # ==================== 第3区：操作控制 ====================
        control_group = QWidget()
        control_group.setStyleSheet("""
            QWidget {
                background: rgba(255, 255, 255, 0.05);
                border-radius: 12px;
                padding: 18px;
                border: 1px solid rgba(162, 155, 254, 0.15);
            }
        """)
        control_layout = QVBoxLayout()
        control_layout.setSpacing(12)
        
        # 区块标题
        control_title = QLabel('🎮 操作控制')
        control_title.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: #a29bfe;
                padding: 5px 0;
                border-bottom: 2px solid rgba(162, 155, 254, 0.3);
                margin-bottom: 8px;
            }
        """)
        control_layout.addWidget(control_title)
        
        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.setSpacing(15)
        
        self.start_btn = QPushButton('▶ 开始下载')
        self.start_btn.setFixedHeight(42)
        self.start_btn.setMinimumWidth(150)
        self.start_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00b894, stop:1 #00cec9);
                font-size: 15px;
                font-weight: bold;
                border-radius: 8px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00cec9, stop:1 #55efc4);
            }
        """)
        self.start_btn.clicked.connect(self.start_download)
        btn_row.addWidget(self.start_btn)

        self.single_download_btn = QPushButton('🎥 下载单视频')
        self.single_download_btn.setFixedHeight(42)
        self.single_download_btn.setMinimumWidth(150)
        self.single_download_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #fd79a8, stop:1 #e84393);
                font-size: 15px;
                font-weight: bold;
                border-radius: 8px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #e84393, stop:1 #d63031);
            }
        """)
        self.single_download_btn.clicked.connect(self.download_single_video)
        btn_row.addWidget(self.single_download_btn)
        
        self.stop_btn = QPushButton('⏹ 停止下载')
        self.stop_btn.setFixedHeight(42)
        self.stop_btn.setMinimumWidth(150)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #e17055, stop:1 #d63031);
                font-size: 15px;
                font-weight: bold;
                border-radius: 8px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #d63031, stop:1 #e17055);
            }
        """)
        self.stop_btn.clicked.connect(self.stop_download)
        btn_row.addWidget(self.stop_btn)
        
        self.refresh_btn = QPushButton('🔄 刷新重置')
        self.refresh_btn.setFixedHeight(42)
        self.refresh_btn.setMinimumWidth(150)
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #6c5ce7, stop:1 #a29bfe);
                font-size: 15px;
                font-weight: bold;
                border-radius: 8px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #a29bfe, stop:1 #74b9ff);
            }
        """)
        self.refresh_btn.clicked.connect(self.refresh_all)
        btn_row.addWidget(self.refresh_btn)
        
        btn_row.addStretch()
        control_layout.addLayout(btn_row)
        
        control_group.setLayout(control_layout)
        layout.addWidget(control_group)
        
        # ==================== 第4区：进度显示 ====================
        progress_group = QWidget()
        progress_group.setStyleSheet("""
            QWidget {
                background: rgba(255, 255, 255, 0.05);
                border-radius: 12px;
                padding: 18px;
                border: 1px solid rgba(253, 121, 168, 0.15);
            }
        """)
        progress_layout = QVBoxLayout()
        progress_layout.setSpacing(12)
        
        # 区块标题
        progress_title = QLabel('📊 下载进度')
        progress_title.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: #fd79a8;
                padding: 5px 0;
                border-bottom: 2px solid rgba(253, 121, 168, 0.3);
                margin-bottom: 8px;
            }
        """)
        progress_layout.addWidget(progress_title)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(26)
        self.progress_bar.setValue(0)
        self.progress_bar.setRange(0, 100)
        # 绿色无限循环进度条样式
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                border-radius: 13px;
                background: rgba(0, 0, 0, 0.3);
                text-align: center;
                color: #ffffff;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00b894, stop:0.5 #55efc4, stop:1 #00b894);
                border-radius: 13px;
            }
        """)
        progress_layout.addWidget(self.progress_bar)
        
        progress_group.setLayout(progress_layout)
        layout.addWidget(progress_group)
        
        layout.addStretch()
        page.setLayout(layout)
        self.page_stack.addWidget(page)
    
    def create_video_manage_page(self):
        """创建视频管理页面"""
        page = QWidget()
        page.setStyleSheet("background: #2d2d2d;")
        layout = QVBoxLayout()
        layout.setSpacing(20)
        layout.setContentsMargins(25, 25, 25, 25)

        page_title = QLabel('视频管理')
        page_title.setStyleSheet("""
            QLabel {
                font-size: 24px;
                font-weight: bold;
                color: #ffffff;
                padding: 10px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(253, 121, 168, 0.2), stop:1 rgba(102, 126, 234, 0.2));
                border-radius: 10px;
                border-left: 4px solid #fd79a8;
            }
        """)
        layout.addWidget(page_title)

        # 工具栏
        toolbar = QWidget()
        toolbar.setStyleSheet("background: rgba(255, 255, 255, 0.05); border-radius: 10px; padding: 15px;")
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setSpacing(15)

        refresh_btn = QPushButton('🔄 刷新列表')
        refresh_btn.setFixedHeight(40)
        refresh_btn.setMinimumWidth(120)
        refresh_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00b894, stop:1 #00cec9);
                font-size: 14px;
                font-weight: bold;
                border-radius: 8px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00cec9, stop:1 #55efc4);
            }
        """)
        refresh_btn.clicked.connect(lambda: self.refresh_video_list())
        toolbar_layout.addWidget(refresh_btn)

        delete_btn = QPushButton('🗑️ 删除选中')
        delete_btn.setFixedHeight(40)
        delete_btn.setMinimumWidth(120)
        delete_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #e17055, stop:1 #d63031);
                font-size: 14px;
                font-weight: bold;
                border-radius: 8px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #d63031, stop:1 #e17055);
            }
        """)
        delete_btn.clicked.connect(lambda: self.delete_selected_video())
        toolbar_layout.addWidget(delete_btn)

        open_btn = QPushButton('📂 打开文件')
        open_btn.setFixedHeight(40)
        open_btn.setMinimumWidth(120)
        open_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #6c5ce7, stop:1 #a29bfe);
                font-size: 14px;
                font-weight: bold;
                border-radius: 8px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #a29bfe, stop:1 #74b9ff);
            }
        """)
        open_btn.clicked.connect(lambda: self.open_selected_video())
        toolbar_layout.addWidget(open_btn)

        toolbar_layout.addStretch()

        # 统计信息
        self.video_count_label = QLabel('📊 总共: 0 个视频')
        self.video_count_label.setStyleSheet("font-size: 14px; color: #dfe6e9; font-weight: bold;")
        toolbar_layout.addWidget(self.video_count_label)

        toolbar.setLayout(toolbar_layout)
        layout.addWidget(toolbar)

        # 视频列表
        self.video_list = QListWidget()
        self.video_list.setStyleSheet("""
            QListWidget {
                background: rgba(0, 0, 0, 0.3);
                border: 2px solid rgba(253, 121, 168, 0.3);
                border-radius: 10px;
                padding: 10px;
                color: #ffffff;
                font-size: 13px;
            }
            QListWidget::item {
                padding: 12px;
                border-radius: 6px;
                margin: 3px;
            }
            QListWidget::item:hover {
                background: rgba(253, 121, 168, 0.2);
            }
            QListWidget::item:selected {
                background: rgba(253, 121, 168, 0.4);
                border: 1px solid #fd79a8;
            }
        """)
        self.video_list.setMinimumHeight(400)
        self.video_list.itemDoubleClicked.connect(self.open_selected_video)
        layout.addWidget(self.video_list)

        # 提示信息
        tip_label = QLabel('💡 提示：选中视频后可以删除或打开文件，双击可以直接播放')
        tip_label.setStyleSheet("""
            QLabel {
                font-size: 12px;
                color: rgba(255, 255, 255, 0.5);
                padding: 10px;
                background: rgba(253, 121, 168, 0.1);
                border-radius: 6px;
            }
        """)
        layout.addWidget(tip_label)

        layout.addStretch()
        page.setLayout(layout)
        self.page_stack.addWidget(page)
    
    def create_folder_browse_page(self):
        """创建文件夹浏览页面"""
        page = QWidget()
        page.setStyleSheet("background: #2d2d2d;")
        layout = QVBoxLayout()
        layout.setSpacing(20)
        layout.setContentsMargins(25, 25, 25, 25)
        
        # 页面标题
        page_title = QLabel('文件夹浏览')
        page_title.setStyleSheet("""
            QLabel {
                font-size: 24px;
                font-weight: bold;
                color: #ffffff;
                padding: 10px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(0, 206, 201, 0.2), stop:1 rgba(162, 155, 254, 0.2));
                border-radius: 10px;
                border-left: 4px solid #81ecec;
            }
        """)
        layout.addWidget(page_title)
        
        # 视频文件夹打开区域
        video_folder_widget = QWidget()
        video_folder_widget.setStyleSheet("""
            QWidget {
                background: rgba(255, 255, 255, 0.05);
                border-radius: 12px;
                padding: 25px;
                border: 1px solid rgba(255, 234, 167, 0.15);
            }
        """)
        video_folder_layout = QVBoxLayout()
        video_folder_layout.setSpacing(20)
        
        # 标题
        folder_title = QLabel('📁 视频文件夹')
        folder_title.setStyleSheet("""
            QLabel {
                font-size: 20px;
                font-weight: bold;
                color: #ffeaa7;
                padding: 5px 0;
                border-bottom: 2px solid rgba(255, 234, 167, 0.3);
                margin-bottom: 10px;
            }
        """)
        video_folder_layout.addWidget(folder_title)
        
        # 当前路径显示
        path_info = QWidget()
        path_info.setStyleSheet("background: rgba(0, 0, 0, 0.2); border-radius: 8px; padding: 15px;")
        path_info_layout = QVBoxLayout()
        path_info_layout.setSpacing(8)
        
        path_label = QLabel('📍 当前保存路径:')
        path_label.setStyleSheet("font-size: 14px; color: #dfe6e9; font-weight: bold;")
        path_info_layout.addWidget(path_label)
        
        self.current_path_label = QLabel(self.default_save_path)
        self.current_path_label.setStyleSheet("""
            QLabel {
                font-size: 13px;
                color: #00cec9;
                font-family: 'Consolas', 'Monaco', monospace;
                padding: 8px;
                background: rgba(0, 0, 0, 0.3);
                border-radius: 5px;
                border: 1px solid rgba(0, 206, 201, 0.3);
            }
        """)
        self.current_path_label.setWordWrap(True)
        path_info_layout.addWidget(self.current_path_label)
        path_info.setLayout(path_info_layout)
        video_folder_layout.addWidget(path_info)
        
        # 统计信息
        stats_widget = QWidget()
        stats_widget.setStyleSheet("background: rgba(0, 0, 0, 0.2); border-radius: 8px; padding: 15px;")
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(20)

        self.folder_count_label = QLabel('📊 视频数量: 0')
        self.folder_count_label.setStyleSheet("font-size: 14px; color: #a29bfe; font-weight: bold;")
        stats_layout.addWidget(self.folder_count_label)

        self.folder_size_label = QLabel('💾 占用空间: 0 MB')
        self.folder_size_label.setStyleSheet("font-size: 14px; color: #fd79a8; font-weight: bold;")
        stats_layout.addWidget(self.folder_size_label)

        stats_layout.addStretch()
        stats_widget.setLayout(stats_layout)
        video_folder_layout.addWidget(stats_widget)
        
        # 按钮区域
        btn_row = QHBoxLayout()
        btn_row.setSpacing(15)
        
        open_folder_btn = QPushButton('📂 打开文件夹')
        open_folder_btn.setFixedHeight(45)
        open_folder_btn.setMinimumWidth(180)
        open_folder_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00b894, stop:1 #00cec9);
                font-size: 15px;
                font-weight: bold;
                border-radius: 10px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00cec9, stop:1 #55efc4);
            }
        """)
        open_folder_btn.clicked.connect(self.open_video_folder)
        btn_row.addWidget(open_folder_btn)
        
        refresh_btn = QPushButton('🔄 刷新统计')
        refresh_btn.setFixedHeight(45)
        refresh_btn.setMinimumWidth(180)
        refresh_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #6c5ce7, stop:1 #a29bfe);
                font-size: 15px;
                font-weight: bold;
                border-radius: 10px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #a29bfe, stop:1 #74b9ff);
            }
        """)
        refresh_btn.clicked.connect(lambda: self.refresh_folder_stats())
        btn_row.addWidget(refresh_btn)
        
        btn_row.addStretch()
        video_folder_layout.addLayout(btn_row)
        
        video_folder_widget.setLayout(video_folder_layout)
        layout.addWidget(video_folder_widget)
        
        layout.addStretch()
        page.setLayout(layout)
        self.page_stack.addWidget(page)
    
    def open_video_folder(self):
        """打开视频文件夹"""
        try:
            if not os.path.exists(self.default_save_path):
                self.log_output.append('文件夹不存在，正在创建...')
                os.makedirs(self.default_save_path)
            
            # 打开文件夹
            import subprocess
            if os.name == 'nt':  # Windows系统
                os.startfile(self.default_save_path)
            elif os.name == 'posix':  # Linux/Mac系统
                subprocess.run(['xdg-open', self.default_save_path])
            
            self.log_output.append(f'✅ 已打开文件夹: {self.default_save_path}')
        except Exception as e:
            self.log_output.append(f'❌ 打开文件夹失败: {str(e)}')
    
    def refresh_folder_stats(self):
        """刷新文件夹统计信息"""
        self.update_download_stats()

    def update_download_stats(self):
        """更新下载统计信息"""
        try:
            # 统计视频文件
            if os.path.exists(self.default_save_path):
                files = [f for f in os.listdir(self.default_save_path) if f.endswith('.mp4')]
                file_count = len(files)
                total_size = sum(os.path.getsize(os.path.join(self.default_save_path, f)) for f in files)

                # 转换大小单位
                if total_size < 1024 * 1024:
                    total_size_str = f'{total_size / 1024:.2f} KB'
                    folder_size_str = total_size_str
                elif total_size < 1024 * 1024 * 1024:
                    total_size_str = f'{total_size / (1024 * 1024):.2f} MB'
                    folder_size_str = total_size_str
                else:
                    total_size_str = f'{total_size / (1024 * 1024 * 1024):.2f} GB'
                    folder_size_str = total_size_str

                # 更新下载统计页面的标签
                self.stats_total_label.setText(str(file_count))
                self.stats_size_label.setText(total_size_str)
                self.stats_path_label.setText(f'📁 保存路径: {self.default_save_path}')

                # 显示文件列表
                if file_count > 0:
                    files_info = '\n'.join([f'• {f}' for f in sorted(files)[:10]])
                    if file_count > 10:
                        files_info += f'\n... 还有 {file_count - 10} 个文件'
                    self.stats_files_label.setText(f'📄 文件列表:\n{files_info}')
                else:
                    self.stats_files_label.setText('📄 暂无视频文件')

                # 从日志中统计成功和失败次数
                log_text = self.log_output.toPlainText()
                success_count = log_text.count('视频保存成功')
                fail_count = log_text.count('下载失败')

                # 计算成功率
                total_attempts = success_count + fail_count
                if total_attempts > 0:
                    success_rate = (success_count / total_attempts) * 100
                    self.stats_success_label.setText(f'{success_rate:.1f}%')
                else:
                    self.stats_success_label.setText('100%')

                # 下载次数（统计开始下载的次数）
                download_count = log_text.count('开始下载')
                self.stats_count_label.setText(f'{download_count} 次')

                # 更新文件夹浏览页面的标签
                self.folder_count_label.setText(f'📊 视频数量: {file_count}')
                self.folder_size_label.setText(f'💾 占用空间: {folder_size_str}')
                self.current_path_label.setText(self.default_save_path)

            else:
                self.stats_total_label.setText('0')
                self.stats_size_label.setText('0 MB')
                self.stats_success_label.setText('N/A')
                self.stats_count_label.setText('0 次')
                self.stats_path_label.setText(f'📁 保存路径: {self.default_save_path} (不存在)')
                self.stats_files_label.setText('📄 文件夹不存在')

                self.folder_count_label.setText('📊 视频数量: 0')
                self.folder_size_label.setText('💾 占用空间: 0 MB')
                self.current_path_label.setText(self.default_save_path)

            self.log_output.append('✅ 统计信息已更新')

        except Exception as e:
            self.log_output.append(f'❌ 更新统计信息失败: {str(e)}')
    
    def create_download_stats_page(self):
        """创建下载统计页面"""
        page = QWidget()
        page.setStyleSheet("background: #2d2d2d;")
        layout = QVBoxLayout()
        layout.setSpacing(20)
        layout.setContentsMargins(25, 25, 25, 25)

        page_title = QLabel('下载统计')
        page_title.setStyleSheet("""
            QLabel {
                font-size: 24px;
                font-weight: bold;
                color: #ffffff;
                padding: 10px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(162, 155, 254, 0.2), stop:1 rgba(253, 121, 168, 0.2));
                border-radius: 10px;
                border-left: 4px solid #a29bfe;
            }
        """)
        layout.addWidget(page_title)

        # 统计信息区域
        stats_container = QWidget()
        stats_container.setStyleSheet("""
            QWidget {
                background: rgba(255, 255, 255, 0.05);
                border-radius: 12px;
                padding: 25px;
                border: 1px solid rgba(162, 155, 254, 0.15);
            }
        """)
        stats_layout = QVBoxLayout()
        stats_layout.setSpacing(20)

        # 概览统计卡片
        overview_widget = QWidget()
        overview_widget.setStyleSheet("background: rgba(0, 0, 0, 0.2); border-radius: 10px; padding: 20px;")
        overview_layout = QHBoxLayout()
        overview_layout.setSpacing(30)

        # 总视频数
        total_card = QWidget()
        total_layout = QVBoxLayout()
        total_title = QLabel('📹 总视频数')
        total_title.setStyleSheet("font-size: 14px; color: rgba(255, 255, 255, 0.7);")
        self.stats_total_label = QLabel('0')
        self.stats_total_label.setStyleSheet("font-size: 36px; font-weight: bold; color: #00cec9;")
        total_layout.addWidget(total_title)
        total_layout.addWidget(self.stats_total_label)
        total_card.setLayout(total_layout)
        overview_layout.addWidget(total_card)

        # 总文件大小
        size_card = QWidget()
        size_layout = QVBoxLayout()
        size_title = QLabel('💾 总大小')
        size_title.setStyleSheet("font-size: 14px; color: rgba(255, 255, 255, 0.7);")
        self.stats_size_label = QLabel('0 MB')
        self.stats_size_label.setStyleSheet("font-size: 36px; font-weight: bold; color: #fd79a8;")
        size_layout.addWidget(size_title)
        size_layout.addWidget(self.stats_size_label)
        size_card.setLayout(size_layout)
        overview_layout.addWidget(size_card)

        # 下载成功率
        success_card = QWidget()
        success_layout = QVBoxLayout()
        success_title = QLabel('✅ 成功率')
        success_title.setStyleSheet("font-size: 14px; color: rgba(255, 255, 255, 0.7);")
        self.stats_success_label = QLabel('100%')
        self.stats_success_label.setStyleSheet("font-size: 36px; font-weight: bold; color: #00b894;")
        success_layout.addWidget(success_title)
        success_layout.addWidget(self.stats_success_label)
        success_card.setLayout(success_layout)
        overview_layout.addWidget(success_card)

        # 下载次数
        count_card = QWidget()
        count_layout = QVBoxLayout()
        count_title = QLabel('🔄 下载次数')
        count_title.setStyleSheet("font-size: 14px; color: rgba(255, 255, 255, 0.7);")
        self.stats_count_label = QLabel('0 次')
        self.stats_count_label.setStyleSheet("font-size: 36px; font-weight: bold; color: #a29bfe;")
        count_layout.addWidget(count_title)
        count_layout.addWidget(self.stats_count_label)
        count_card.setLayout(count_layout)
        overview_layout.addWidget(count_card)

        overview_layout.addStretch()
        overview_widget.setLayout(overview_layout)
        stats_layout.addWidget(overview_widget)

        # 详细统计信息
        detail_widget = QWidget()
        detail_widget.setStyleSheet("background: rgba(0, 0, 0, 0.2); border-radius: 10px; padding: 20px;")
        detail_layout = QVBoxLayout()
        detail_layout.setSpacing(15)

        detail_title = QLabel('📋 详细信息')
        detail_title.setStyleSheet("""
            QLabel {
                font-size: 18px;
                font-weight: bold;
                color: #dfe6e9;
                padding: 8px 0;
                border-bottom: 2px solid rgba(162, 155, 254, 0.3);
            }
        """)
        detail_layout.addWidget(detail_title)

        # 路径信息
        self.stats_path_label = QLabel(f'📁 保存路径: {self.default_save_path}')
        self.stats_path_label.setStyleSheet("""
            QLabel {
                font-size: 13px;
                color: rgba(255, 255, 255, 0.8);
                padding: 10px;
                background: rgba(162, 155, 254, 0.1);
                border-radius: 6px;
                border-left: 3px solid #a29bfe;
            }
        """)
        self.stats_path_label.setWordWrap(True)
        detail_layout.addWidget(self.stats_path_label)

        # 文件列表信息
        self.stats_files_label = QLabel('')
        self.stats_files_label.setStyleSheet("""
            QLabel {
                font-size: 13px;
                color: rgba(255, 255, 255, 0.8);
                padding: 10px;
                background: rgba(0, 0, 0, 0.3);
                border-radius: 6px;
            }
        """)
        self.stats_files_label.setWordWrap(True)
        detail_layout.addWidget(self.stats_files_label)

        detail_widget.setLayout(detail_layout)
        stats_layout.addWidget(detail_widget)

        # 刷新按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        refresh_stats_btn = QPushButton('🔄 刷新统计')
        refresh_stats_btn.setFixedHeight(45)
        refresh_stats_btn.setMinimumWidth(200)
        refresh_stats_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #6c5ce7, stop:1 #a29bfe);
                font-size: 15px;
                font-weight: bold;
                border-radius: 10px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #a29bfe, stop:1 #74b9ff);
            }
        """)
        refresh_stats_btn.clicked.connect(self.update_download_stats)
        btn_row.addWidget(refresh_stats_btn)

        stats_layout.addLayout(btn_row)

        stats_container.setLayout(stats_layout)
        layout.addWidget(stats_container)

        layout.addStretch()
        page.setLayout(layout)
        self.page_stack.addWidget(page)
    
    def create_settings_page(self):
        """创建偏好设置页面"""
        page = QWidget()
        page.setObjectName('settingsPage')
        page.setStyleSheet("background: #2d2d2d;")
        layout = QVBoxLayout()
        layout.setSpacing(20)
        layout.setContentsMargins(25, 25, 25, 25)
        
        page_title = QLabel('偏好设置')
        page_title.setStyleSheet("""
            QLabel {
                font-size: 24px;
                font-weight: bold;
                color: #ffffff;
                padding: 10px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(108, 92, 231, 0.2), stop:1 rgba(162, 155, 254, 0.2));
                border-radius: 10px;
                border-left: 4px solid #6c5ce7;
            }
        """)
        layout.addWidget(page_title)
        
        # 保存路径设置区域
        save_path_widget = QWidget()
        save_path_widget.setObjectName('savePathWidget')
        save_path_widget.setStyleSheet("""
            QWidget {
                background: rgba(255, 255, 255, 0.05);
                border-radius: 12px;
                padding: 25px;
                border: 1px solid rgba(108, 92, 231, 0.15);
            }
        """)
        save_path_layout = QVBoxLayout()
        save_path_layout.setSpacing(20)
        
        # 标题
        path_title = QLabel('💾 默认保存路径设置')
        path_title.setStyleSheet("""
            QLabel {
                font-size: 18px;
                font-weight: bold;
                color: #6c5ce7;
                padding: 8px 0;
                border-bottom: 2px solid rgba(108, 92, 231, 0.3);
                margin-bottom: 12px;
            }
        """)
        save_path_layout.addWidget(path_title)
        
        # 当前路径显示
        current_path_box = QWidget()
        current_path_box.setStyleSheet("background: rgba(0, 0, 0, 0.2); border-radius: 8px; padding: 15px;")
        current_path_box_layout = QVBoxLayout()
        current_path_box_layout.setSpacing(10)
        
        current_path_label = QLabel('📍 当前默认保存路径:')
        current_path_label.setObjectName('pathLabel')
        current_path_label.setStyleSheet("font-size: 14px; color: #dfe6e9; font-weight: bold;")
        current_path_box_layout.addWidget(current_path_label)
        
        self.settings_path_label = QLabel(self.default_save_path)
        self.settings_path_label.setStyleSheet("""
            QLabel {
                font-size: 13px;
                color: #00cec9;
                font-family: 'Consolas', 'Monaco', monospace;
                padding: 10px;
                background: rgba(0, 0, 0, 0.3);
                border-radius: 6px;
                border: 1px solid rgba(0, 206, 201, 0.3);
            }
        """)
        self.settings_path_label.setWordWrap(True)
        current_path_box_layout.addWidget(self.settings_path_label)
        current_path_box.setLayout(current_path_box_layout)
        save_path_layout.addWidget(current_path_box)
        
        # 修改路径按钮区域
        btn_row = QHBoxLayout()
        btn_row.setSpacing(15)
        
        change_path_btn = QPushButton('📂 修改默认路径')
        change_path_btn.setFixedHeight(45)
        change_path_btn.setMinimumWidth(180)
        change_path_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #6c5ce7, stop:1 #a29bfe);
                font-size: 15px;
                font-weight: bold;
                border-radius: 10px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #a29bfe, stop:1 #74b9ff);
            }
        """)
        change_path_btn.clicked.connect(self.change_default_path)
        btn_row.addWidget(change_path_btn)
        
        reset_path_btn = QPushButton('🔄 重置为默认')
        reset_path_btn.setFixedHeight(45)
        reset_path_btn.setMinimumWidth(180)
        reset_path_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #e17055, stop:1 #d63031);
                font-size: 15px;
                font-weight: bold;
                border-radius: 10px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #d63031, stop:1 #e17055);
            }
        """)
        reset_path_btn.clicked.connect(self.reset_default_path)
        btn_row.addWidget(reset_path_btn)
        
        btn_row.addStretch()
        save_path_layout.addLayout(btn_row)
        
        # 提示信息
        tip_label = QLabel('💡 提示：修改默认路径后，批量下载时如果未指定路径将自动使用此路径')
        tip_label.setStyleSheet("""
            QLabel {
                font-size: 13px;
                color: rgba(255, 255, 255, 0.6);
                padding: 12px;
                background: rgba(108, 92, 231, 0.1);
                border-radius: 8px;
                border-left: 3px solid #6c5ce7;
            }
        """)
        tip_label.setWordWrap(True)
        save_path_layout.addWidget(tip_label)
        
        save_path_widget.setLayout(save_path_layout)
        layout.addWidget(save_path_widget)
        
        layout.addStretch()
        page.setLayout(layout)
        self.page_stack.addWidget(page)
    
    def change_default_path(self):
        """修改默认保存路径"""
        folder = QFileDialog.getExistingDirectory(self, '选择默认保存目录', self.default_save_path)
        if folder:
            self.default_save_path = folder
            self.settings_path_label.setText(folder)
            self.log_output.append(f'默认保存路径已修改为: {folder}')
    
    def reset_default_path(self):
        """重置为默认路径"""
        script_dir = os.path.dirname(__file__)
        self.default_save_path = os.path.join(script_dir, '视频下载')
        self.settings_path_label.setText(self.default_save_path)
        self.log_output.append(f'默认保存路径已重置为: {self.default_save_path}')

    def create_community_page(self):
        """创建软件交流区页面"""
        page = QWidget()
        page.setStyleSheet("background: #2d2d2d;")
        layout = QVBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # 使用requests获取图片URL（因为Gitee页面需要解析HTML）
        # 图片显示标签
        self.community_image_label = QLabel()
        self.community_image_label.setAlignment(Qt.AlignCenter)
        self.community_image_label.setStyleSheet("""
            QLabel {
                background: rgba(0, 0, 0, 0.3);
                padding: 20px;
                border-radius: 10px;
                color: rgba(255, 255, 255, 0.7);
                font-size: 14px;
            }
        """)
        self.community_image_label.setText('正在加载图片...')
        layout.addWidget(self.community_image_label)

        # 添加刷新按钮
        refresh_image_btn = QPushButton('🔄 重新加载图片')
        refresh_image_btn.setStyleSheet("""
            QPushButton {
                background: rgba(102, 126, 234, 0.3);
                border: 1px solid rgba(102, 126, 234, 0.5);
                color: #ffffff;
                padding: 8px 20px;
                border-radius: 5px;
                font-size: 13px;
            }
            QPushButton:hover {
                background: rgba(102, 126, 234, 0.5);
            }
        """)
        refresh_image_btn.clicked.connect(self.load_community_image_from_gitee)
        layout.addWidget(refresh_image_btn, alignment=Qt.AlignCenter)

        # 延迟加载图片（确保UI先显示）
        QTimer.singleShot(500, self.load_community_image_from_gitee)

        page.setLayout(layout)
        self.page_stack.addWidget(page)

    def load_community_image_from_gitee(self):
        """从Gitee raw文件获取图片URL并显示"""
        self.community_image_label.setText('正在加载图片...')
        
        # 使用QThread避免阻塞UI
        class ImageLoadThread(QThread):
            finished = pyqtSignal(object, str)  # pixmap, error_msg
            
            def run(self):
                try:
                    import requests
                    import re
                    
                    # 直接访问raw文件内容
                    raw_url = "https://gitee.com/du_honggang/activation-codes/raw/master/xiexiaoshuo_tupianjiaoliuqun"
                    
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }
                    
                    # 获取文件原始内容
                    response = requests.get(raw_url, headers=headers, timeout=10)
                    response.raise_for_status()
                    
                    # 文件内容应该是图片URL
                    content = response.text.strip()
                    
                    # 尝试从内容中提取图片URL
                    # 可能是直接的URL，或者是Markdown格式 ![alt](url)
                    img_url = None
                    
                    # 方法1: 直接就是URL
                    if content.startswith('http') and ('.jpg' in content or '.jpeg' in content or '.png' in content or '.gif' in content or '.webp' in content):
                        img_url = content.split('\n')[0].strip()
                    
                    # 方法2: Markdown格式 ![alt](url)
                    if not img_url:
                        markdown_match = re.search(r'!\[.*?\]\((.*?)\)', content)
                        if markdown_match:
                            img_url = markdown_match.group(1)
                    
                    # 方法3: 纯URL（任何http链接）
                    if not img_url:
                        url_match = re.search(r'(https?://\S+)', content)
                        if url_match:
                            img_url = url_match.group(1)
                    
                    if not img_url:
                        self.finished.emit(None, f'无法从文件内容中提取图片URL\n文件内容: {content[:200]}')
                        return
                    
                    # 清理URL（去除可能的尾随字符）
                    img_url = img_url.strip(')">\'')
                    
                    # 下载图片
                    img_response = requests.get(img_url, headers=headers, timeout=15)
                    img_response.raise_for_status()
                    
                    # 创建pixmap
                    pixmap = QPixmap()
                    if pixmap.loadFromData(img_response.content):
                        self.finished.emit(pixmap, '')
                    else:
                        self.finished.emit(None, f'图片格式不支持或已损坏\nURL: {img_url}')
                        
                except requests.exceptions.RequestException as e:
                    self.finished.emit(None, f'网络请求失败: {str(e)}')
                except Exception as e:
                    self.finished.emit(None, f'加载失败: {str(e)}')
        
        # 创建并启动线程
        self.image_thread = ImageLoadThread()
        self.image_thread.finished.connect(self.on_image_loaded)
        self.image_thread.start()
    
    def on_image_loaded(self, pixmap, error_msg):
        """图片加载完成后的回调"""
        if pixmap:
            # 计算合适的显示尺寸
            label_width = min(800, self.community_image_label.parent().width() - 100 if self.community_image_label.parent() else 800)
            label_height = min(600, self.community_image_label.parent().height() - 200 if self.community_image_label.parent() else 600)
            
            self.community_image_label.setPixmap(pixmap.scaled(
                label_width,
                label_height,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            ))
            self.community_image_label.setText('')
            self.community_image_label.setStyleSheet("""
                QLabel {
                    background: rgba(0, 0, 0, 0.3);
                    padding: 0px;
                    border-radius: 10px;
                }
            """)
        else:
            self.community_image_label.setText(f'图片加载失败\n\n{error_msg}\n\n请点击下方按钮重试')
            self.community_image_label.setStyleSheet("""
                QLabel {
                    background: rgba(0, 0, 0, 0.3);
                    padding: 30px;
                    border-radius: 10px;
                    color: rgba(255, 255, 255, 0.7);
                    font-size: 14px;
                }
            """)

    def create_help_page(self):
        """创建帮助中心页面（带右侧垂直滚动条的文本框）"""
        page = QWidget()
        page.setStyleSheet("background: #2d2d2d;")
        
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        page_title = QLabel('帮助中心')
        page_title.setStyleSheet("""
            QLabel {
                font-size: 22px;
                font-weight: bold;
                color: #ffffff;
                padding: 8px 12px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(0, 206, 201, 0.2), stop:1 rgba(108, 92, 231, 0.2));
                border-radius: 6px;
                border-left: 4px solid #00cec9;
            }
        """)
        layout.addWidget(page_title)
        
        help_text = QTextBrowser()
        help_text.setHtml('''
<!DOCTYPE html>
<html>
<head>
<style>
    body {
        font-family: "Microsoft YaHei", "微软雅黑", Arial, sans-serif;
        font-size: 13px;
        color: #dfe6e9;
        line-height: 1.8;
        margin: 0;
        padding: 10px;
    }
    h1 {
        font-size: 20px;
        color: #00cec9;
        border-bottom: 2px solid rgba(0, 206, 201, 0.4);
        padding-bottom: 8px;
        margin-bottom: 15px;
    }
    h2 {
        font-size: 17px;
        color: #fd79a8;
        margin-top: 15px;
        margin-bottom: 10px;
    }
    h3 {
        font-size: 15px;
        color: #ffeaa7;
        margin-top: 12px;
        margin-bottom: 8px;
    }
    .step {
        margin: 8px 0;
        padding-left: 15px;
    }
    .tip {
        background: rgba(108, 92, 231, 0.15);
        border-left: 3px solid #6c5ce7;
        padding: 10px 15px;
        margin: 10px 0;
        border-radius: 0 6px 6px 0;
    }
    .highlight {
        color: #00cec9;
        font-weight: bold;
    }
    .warn {
        color: #fd79a8;
        font-weight: bold;
    }
    ul, ol {
        margin: 8px 0;
        padding-left: 25px;
    }
    li {
        margin: 5px 0;
    }
    a {
        color: #74b9ff;
        text-decoration: none;
    }
    a:hover {
        text-decoration: underline;
    }
</style>
</head>
<body>
    <h1>📖 抖音视频下载器 - 帮助中心</h1>
    
    <h2>📌 软件简介</h2>
    <p>抖音视频下载器是一款免费的桌面应用程序，用于批量下载抖音用户主页视频和单个视频。</p>
    <p><span class="highlight">主要功能：</span></p>
    <ul>
        <li>批量下载用户主页所有公开视频</li>
        <li>支持单个视频链接下载</li>
        <li>自定义下载数量和起始页码</li>
        <li>自动保存到指定文件夹</li>
        <li>实时显示下载进度和日志</li>
        <li>支持视频文件管理</li>
    </ul>
    
    <h2>📥 批量下载使用说明</h2>
    
    <h3>步骤 1：进入批量下载页面</h3>
    <p class="step">点击左侧边栏的「📥 批量下载」按钮，进入批量下载设置页面。</p>
    
    <h3>步骤 2：设置保存路径</h3>
    <p class="step">在「💾 保存路径」输入框中选择视频保存位置，或在「⚙️ 偏好设置」中设置默认路径。</p>
    <p class="step"><span class="tip">💡 默认保存路径：程序所在目录下的「视频下载」文件夹</span></p>
    
    <h3>步骤 3：输入抖音主页URL</h3>
    <p class="step">1. 打开抖音网站，找到要下载视频的用户主页</p>
    <p class="step">2. 复制用户主页的完整URL</p>
    <p class="step">3. 示例：<span class="highlight">https://www.douyin.com/user/MS4wLjABAAA...</span></p>
    <p class="step">4. 将URL粘贴到「📌 抖音主页URL」输入框中</p>
    
    <h3>步骤 4：选择下载参数</h3>
    <p class="step"><span class="warn">起始页码：</span>选择从第几页开始下载（1-10页）</p>
    <p class="step"><span class="warn">下载数量：</span>选择要下载的视频数量（1-20个）或选择「全部」</p>
    
    <h3>步骤 5：开始下载</h3>
    <p class="step">点击「▶ 开始下载」按钮开始批量下载</p>
    <p class="step">进度条会显示当前下载进度</p>
    <p class="step">日志区域会实时显示下载状态</p>
    
    <h3>步骤 6：查看下载结果</h3>
    <p class="step">下载完成后，可在「📂 文件夹浏览」中查看已下载的视频</p>
    <p class="step">点击「📂 打开文件夹」可直接打开视频保存目录</p>
    <p class="step">「📝 运行日志」页面会记录所有下载操作历史</p>
    
    <h2>🎬 单视频下载说明</h2>
    
    <h3>方法 1：从抖音APP分享</h3>
    <ol>
        <li>打开抖音APP，找到想要下载的视频</li>
        <li>点击视频右侧的「分享按钮」（箭头图标）</li>
        <li>选择「复制链接」选项</li>
        <li>将链接粘贴到「🎬 单视频URL」输入框中</li>
        <li>点击「🎥 下载单视频」按钮</li>
    </ol>
    
    <h3>方法 2：从抖音网页版分享</h3>
    <ol>
        <li>在浏览器中打开抖音网站</li>
        <li>找到想要下载的视频</li>
        <li>点击视频下方的「分享」按钮</li>
        <li>选择「复制链接」</li>
        <li>将链接粘贴到「🎬 单视频URL」输入框中</li>
        <li>点击「🎥 下载单视频」按钮</li>
    </ol>
    
    <h3>方法 3：从浏览器地址栏</h3>
    <ol>
        <li>在浏览器中打开想要下载的视频页面</li>
        <li>复制浏览器地址栏中的完整URL</li>
        <li>确保URL中包含 <span class="highlight">/video/</span></li>
        <li>示例：<span class="highlight">https://www.douyin.com/video/7301234567890123456</span></li>
        <li>将URL粘贴到「🎬 单视频URL」输入框中</li>
        <li>点击「🎥 下载单视频」按钮</li>
    </ol>
    
    <h3>⚠️ 注意事项</h3>
    <ul>
        <li>单视频链接必须包含 <span class="warn">/video/</span>，不是用户主页链接</li>
        <li>用户主页链接用于批量下载，单视频链接用于下载单个视频</li>
        <li>如果链接无效，请检查是否复制完整</li>
        <li>下载速度取决于网络环境和视频大小</li>
    </ul>
    
    <h2>💡 使用提示</h2>
    <div class="tip">
        • 确保网络连接稳定，下载速度会更快<br>
        • 如需下载大量视频，建议分批次下载<br>
        • 可以在「⚙️ 偏好设置」中修改默认保存路径<br>
        • 「📝 运行日志」页面会记录所有下载历史<br>
        • 下载过程中可随时点击「⏹ 停止下载」中断<br>
        • 支持下载用户主页所有公开视频
    </div>
    
    <h2>📞 联系我们</h2>
    <p>如有任何问题或建议，欢迎加入我们的交流群：</p>
    <p>QQ交流群：<span class="highlight">1035396790</span></p>
    <p>官方网站：<a href="https://hongni.lovestoblog.com/" target="_blank">https://hongni.lovestoblog.com/</a></p>
    
    <br>
    <p style="text-align: center; color: rgba(255,255,255,0.5); font-size: 12px;">--- 使用滚动条上下拖动查看更多内容 ---</p>
</body>
</html>
        ''')
        help_text.setStyleSheet("""
            QTextBrowser {
                background: rgba(255, 255, 255, 0.03);
                border: 2px solid rgba(0, 206, 201, 0.4);
                border-radius: 10px;
                padding: 10px;
                font-size: 13px;
                color: #dfe6e9;
            }
            QTextBrowser:focus {
                border: 2px solid rgba(0, 206, 201, 0.6);
            }
        """)
        help_text.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        help_text.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        help_text.setOpenExternalLinks(True)
        
        help_text.verticalScrollBar().setStyleSheet("""
            QScrollBar:vertical {
                background: rgba(255, 255, 255, 0.08);
                width: 10px;
                border-radius: 5px;
                margin: 3px;
            }
            QScrollBar::handle:vertical {
                background: rgba(102, 126, 234, 0.7);
                border-radius: 4px;
                min-height: 40px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(102, 126, 234, 0.9);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
            }
        """)
        
        help_text.horizontalScrollBar().setStyleSheet("""
            QScrollBar:horizontal {
                background: rgba(255, 255, 255, 0.08);
                height: 10px;
                border-radius: 5px;
                margin: 3px;
            }
            QScrollBar::handle:horizontal {
                background: rgba(102, 126, 234, 0.7);
                border-radius: 4px;
                min-width: 40px;
            }
            QScrollBar::handle:horizontal:hover {
                background: rgba(102, 126, 234, 0.9);
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: transparent;
            }
        """)
        
        layout.addWidget(help_text)
        page.setLayout(layout)
        self.page_stack.addWidget(page)

    def create_about_page(self):
        """创建关于页面"""
        page = QWidget()
        page.setStyleSheet("background: #2d2d2d;")
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(25, 25, 25, 25)

        # 页面标题
        page_title = QLabel('关于我们')
        page_title.setStyleSheet("""
            QLabel {
                font-size: 24px;
                font-weight: bold;
                color: #ffffff;
                padding: 10px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(253, 121, 168, 0.2), stop:1 rgba(162, 155, 254, 0.2));
                border-radius: 10px;
                border-left: 4px solid #fd79a8;
            }
        """)
        layout.addWidget(page_title)

        # 公司信息 - 直接文本显示
        company_title = QLabel('🏢 红丽科技公司')
        company_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #fd79a9; margin-top: 10px;")
        layout.addWidget(company_title)

        company_desc = QLabel('红丽科技公司致力于为广大用户提供优质的软件下载服务。我们专注于小说相关工具的开发与分享，让用户能够更便捷地享受阅读和创作的乐趣。\n\n我们的软件下载平台汇集了多种实用工具，包括小说搜索下载、智能写作、格式化工具等，满足不同用户的需求。')
        company_desc.setStyleSheet("font-size: 13px; color: #dfe6e9; line-height: 1.8;")
        company_desc.setWordWrap(True)
        layout.addWidget(company_desc)

        # 软件信息 - 直接文本显示
        software_title = QLabel('📋 软件信息')
        software_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #00cec9; margin-top: 15px;")
        layout.addWidget(software_title)

        software_info = QLabel('''
<b>软件版本:</b>v2.0.1<br>
<b>软件性质:</b>免费开源<br>
<b>开发公司:</b>红丽科技公司<br>
<b>官方网站:</b><a href="https://hongni.lovestoblog.com/" style="color: #74b9ff;">https://hongni.lovestoblog.com/</a>
        ''')
        software_info.setStyleSheet("font-size: 13px; color: #dfe6e9; line-height: 1.8;")
        software_info.setWordWrap(True)
        software_info.setTextFormat(1)
        software_info.setOpenExternalLinks(True)
        layout.addWidget(software_info)

        # 交流群信息 - 直接文本显示
        group_title = QLabel('💬 用户交流群')
        group_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #ffeaa7; margin-top: 15px;")
        layout.addWidget(group_title)

        group_info = QLabel('''
<b>QQ交流群:</b>1035396790<br><br>
欢迎加入我们的QQ交流群,与其他用户一起交流使用心得,反馈问题建议,获取最新更新信息.<br><br>
<b>扫码进群:</b><br>
点击左侧边栏的"软件交流区",扫描页面中的二维码即可快速加入群聊.
        ''')
        group_info.setStyleSheet("font-size: 13px; color: #dfe6e9; line-height: 1.8;")
        group_info.setWordWrap(True)
        group_info.setTextFormat(1)
        layout.addWidget(group_info)

        # 开源声明 - 直接文本显示
        open_source_title = QLabel('开源声明')
        open_source_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #a29bfe; margin-top: 15px;")
        layout.addWidget(open_source_title)

        open_source_text = QLabel('本软件为免费开源软件,遵循开源协议发布.我们坚持开源免费的理念,让更多人能够享受到优质的软件服务.欢迎广大开发者参与贡献,共同完善软件功能.')
        open_source_text.setStyleSheet("font-size: 13px; color: rgba(255, 255, 255, 0.8); line-height: 1.6;")
        open_source_text.setWordWrap(True)
        layout.addWidget(open_source_text)

        # 使用声明 - 直接文本显示
        disclaimer_title = QLabel('使用声明')
        disclaimer_title.setStyleSheet("font-size: 8px; font-weight: bold; color: #ff7675; margin-top: 15px;")
        layout.addWidget(disclaimer_title)

        disclaimer_text = QLabel('本软件仅供学习交流使用,不得用于商业用途.用户下载的内容版权归原著作权人所有,请遵守相关法律法规,尊重知识产权.因用户使用本软件产生的任何法律责任,均由用户自行承担,与本软件作者无关.')
        disclaimer_text.setStyleSheet("font-size: 8px; color: rgba(255, 255, 255, 0.8); line-height: 1.6;")
        disclaimer_text.setWordWrap(True)
        layout.addWidget(disclaimer_text)

        layout.addStretch()
        page.setLayout(layout)
        self.page_stack.addWidget(page)

    def create_log_page(self):
        """创建运行日志页面"""
        page = QWidget()
        page.setStyleSheet("""
            QWidget {
                background: #2d2d2d;
            }
        """)
        layout = QVBoxLayout()
        layout.setSpacing(20)
        layout.setContentsMargins(25, 25, 25, 25)
        
        # 页面标题
        page_title = QLabel('运行日志')
        page_title.setStyleSheet("""
            QLabel {
                font-size: 24px;
                font-weight: bold;
                color: #ffffff;
                padding: 10px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(0, 206, 201, 0.2), stop:1 rgba(253, 121, 168, 0.2));
                border-radius: 10px;
                border-left: 4px solid #00cec9;
            }
        """)
        layout.addWidget(page_title)
        
        # 日志显示区域
        log_display = QWidget()
        log_display.setStyleSheet("""
            QWidget {
                background: rgba(255, 255, 255, 0.05);
                border-radius: 12px;
                padding: 18px;
                border: 1px solid rgba(0, 184, 148, 0.15);
            }
        """)
        log_display_layout = QVBoxLayout()
        log_display_layout.setSpacing(12)
        
        # 区块标题和操作按钮
        header_row = QHBoxLayout()
        log_title = QLabel('📝 运行日志')
        log_title.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: #00cec9;
                padding: 5px 0;
                border-bottom: 2px solid rgba(0, 206, 201, 0.3);
                margin-bottom: 8px;
            }
        """)
        header_row.addWidget(log_title)
        header_row.addStretch()
        
        # 清空日志按钮
        clear_log_btn = QPushButton('🗑️ 清空日志')
        clear_log_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #e17055, stop:1 #d63031);
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #d63031, stop:1 #e17055);
            }
        """)
        clear_log_btn.clicked.connect(lambda: self.log_output.clear())
        header_row.addWidget(clear_log_btn)
        
        log_display_layout.addLayout(header_row)
        
        # 日志输出框
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMinimumHeight(500)
        self.log_output.setStyleSheet("""
            QTextEdit {
                background: rgba(0, 0, 0, 0.6);
                border: 2px solid rgba(0, 184, 148, 0.4);
                border-radius: 10px;
                font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                font-size: 13px;
                color: #00ff88;
                padding: 15px;
            }
            QTextEdit:hover {
                border: 2px solid rgba(0, 184, 148, 0.6);
            }
        """)
        log_display_layout.addWidget(self.log_output)
        
        # 日志统计信息
        stats_row = QHBoxLayout()
        stats_label = QLabel('💡 提示：日志会自动保存所有下载记录')
        stats_label.setStyleSheet("""
            QLabel {
                font-size: 12px;
                color: rgba(255, 255, 255, 0.5);
                padding: 8px;
            }
        """)
        stats_row.addWidget(stats_label)
        stats_row.addStretch()
        
        log_display_layout.addLayout(stats_row)
        
        log_display.setLayout(log_display_layout)
        layout.addWidget(log_display)
        
        layout.addStretch()
        page.setLayout(layout)
        self.page_stack.addWidget(page)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = DouyinDownloader()
    ex.show()
    sys.exit(app.exec_())
