import ctypes
import base64
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import tempfile
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
DATA = BASE / '收到的文件'
DATA.mkdir(exist_ok=True)
TOKEN, ADMIN = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
LOCK = threading.Lock()
ITEMS = []
OUTBOX = []
CACHE = None
TEMP_SESSION = None
PAGE = (Path(getattr(sys, '_MEIPASS', BASE)) / 'ui.html').read_text(encoding='utf-8')

def startup_log(message):
    try:
        with (BASE / '奶蛙快传启动日志.txt').open('a', encoding='utf-8') as log:
            log.write(time.strftime('%Y-%m-%d %H:%M:%S') + ' v1.7 ' + message + '\n')
    except OSError:
        pass

def restore_items():
    files = sorted(DATA.iterdir(), key=lambda p: p.name, reverse=True)
    restored = []
    for path in files:
        match = re.match(r'^(\d{8})_(\d{6})_[0-9a-f]{6}_(.+)$', path.name)
        if not match or path.is_symlink() or not path.is_file():
            continue
        try:
            info = path.stat()
            text = None
            if re.fullmatch(r'文字_\d{8}_\d{6}\.txt', match[3]) and info.st_size <= 1024**2:
                text = path.read_text(encoding='utf-8')
            restored.append({'id': secrets.token_hex(8), 'name': match[3], 'size': info.st_size,
                             'time': time.strftime('%m-%d %H:%M:%S', time.localtime(info.st_mtime)),
                             'text': text, 'saved': path.name, 'is_saved': True})
        except (OSError, UnicodeError):
            continue
        if len(restored) >= 300:
            break
    ITEMS[:] = list(reversed(restored))

def cache_dir():
    global CACHE, TEMP_SESSION
    with LOCK:
        if CACHE is None:
            TEMP_SESSION = tempfile.TemporaryDirectory(prefix='naifrog-send-', ignore_cleanup_errors=True)
            CACHE = Path(TEMP_SESSION.name)
    return CACHE

def received_path(item_id):
    with LOCK:
        item = next((i for i in ITEMS if i['id'] == item_id), None)
    if item is None:
        raise FileNotFoundError('未找到这份文件，请刷新接收列表')
    folder = DATA if item.get('is_saved', True) else cache_dir()
    path = (folder / item['saved']).resolve()
    if path.parent != folder.resolve() or not path.is_file():
        raise FileNotFoundError('内容已失效或文件已移动，请重新发送或检查接收文件夹')
    return item, path

def open_received(item_id):
    _, path = received_path(item_id)
    os.startfile(str(path))

def save_received(item_id):
    item, path = received_path(item_id)
    with LOCK:
        if not item.get('is_saved', True):
            path.replace(DATA / item['saved'])
            item['is_saved'] = True
    return item

def addresses():
    found = []
    candidates = []
    try:
        candidates.extend(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError:
        pass
    if sys.platform == 'win32':
        try:
            output = subprocess.check_output(['ipconfig'], timeout=5, creationflags=0x08000000)
            candidates.extend(re.findall(r'IPv4[^\r\n:：]*[:：]\s*((?:\d{1,3}\.){3}\d{1,3})', output.decode(errors='ignore')))
        except (OSError, subprocess.SubprocessError):
            pass
    for value in candidates:
        try:
            ip = ipaddress.ip_address(value)
            if any(ip in ipaddress.ip_network(n) for n in ['10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16']):
                if value not in found:
                    found.append(value)
        except ValueError:
            pass
    return list(dict.fromkeys(found)) or ['127.0.0.1']

def qr_data(url):
    import qrcode
    qr = qrcode.QRCode(border=4, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(url)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    size = len(matrix)
    path = ''.join(f'M{x},{y}h1v1h-1z' for y, row in enumerate(matrix) for x, dark in enumerate(row) if dark)
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" shape-rendering="crispEdges"><rect width="{size}" height="{size}" fill="white"/><path d="{path}" fill="black"/></svg>'
    return 'data:image/svg+xml;base64,' + base64.b64encode(svg.encode()).decode()

def outgoing_path(uid):
    with LOCK:
        item = next((i for i in OUTBOX if i['id'] == uid), None)
    if item is None:
        raise FileNotFoundError('这份内容已失效，请让电脑重新发送')
    folder = cache_dir()
    path = (folder / item['saved']).resolve()
    if path.parent != folder.resolve() or not path.is_file():
        raise FileNotFoundError('文件已失效，请让电脑重新发送')
    return item, path

def public_outbox():
    with LOCK:
        return [{key: item[key] for key in ['id', 'name', 'size', 'time', 'text', 'ticket']} for item in reversed(OUTBOX)]

class Server(ThreadingHTTPServer):
    daemon_threads = False
    allow_reuse_address = False

    def server_bind(self):
        if sys.platform == 'win32':
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def send(self, code, body=b'', kind='application/json; charset=utf-8'):
        if isinstance(body, dict):
            body = json.dumps(body, ensure_ascii=False).encode()
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def admin(self):
        return self.client_address[0] == '127.0.0.1' and secrets.compare_digest(self.headers.get('X-Admin', ''), ADMIN)

    def allowed(self):
        return self.admin() or secrets.compare_digest(self.headers.get('X-Token', ''), TOKEN)

    def do_GET(self):
        path = urllib.parse.urlsplit(self.path).path
        if path == '/':
            return self.send(200, PAGE, 'text/html; charset=utf-8')
        if path == '/favicon.ico':
            return self.send(204)
        if path == '/api/download':
            params = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            try:
                item, file = outgoing_path(params.get('id', [''])[0])
                ticket = params.get('ticket', [''])[0]
                if not ticket or not secrets.compare_digest(ticket, item['ticket']):
                    return self.send(403, {'error': '下载连接无效，请重新扫码'})
                # Stream directly to the browser download manager, without buffering large files.
                with file.open('rb') as source:
                    self.connection.settimeout(120)
                    total = os.fstat(source.fileno()).st_size
                    start, end = 0, total - 1
                    partial = self.headers.get('Range')
                    if partial:
                        match = re.fullmatch(r'bytes=(\d{1,20})-(\d{0,20})', partial)
                        if not match:
                            return self.send(416, {'error': '不支持此下载范围'})
                        start = int(match[1]); end = min(int(match[2]) if match[2] else end, end)
                        if start > end or start >= total:
                            return self.send(416, {'error': '下载范围无效'})
                    self.send_response(206 if partial else 200)
                    self.send_header('Content-Type', 'application/octet-stream')
                    self.send_header('Content-Length', str(max(0, end - start + 1)))
                    self.send_header('Content-Disposition', "attachment; filename=download; filename*=UTF-8''" + urllib.parse.quote(item['name'], safe=''))
                    self.send_header('Cache-Control', 'no-store')
                    self.send_header('Referrer-Policy', 'no-referrer')
                    self.send_header('X-Content-Type-Options', 'nosniff')
                    self.send_header('Accept-Ranges', 'bytes')
                    if partial:
                        self.send_header('Content-Range', f'bytes {start}-{end}/{total}')
                    self.end_headers()
                    source.seek(start)
                    remaining = end - start + 1
                    while remaining > 0:
                        data = source.read(min(1024**2, remaining))
                        if not data:
                            break
                        self.wfile.write(data); remaining -= len(data)
                return
            except FileNotFoundError as exc:
                return self.send(404, {'error': str(exc)})
            except OSError:
                return
        if not self.allowed():
            return self.send(403, {'error': '连接已失效，请重新扫描电脑上的二维码'})
        if path == '/api/ping':
            return self.send(200, {'ok': True})
        if path == '/api/outbox':
            return self.send(200, {'items': public_outbox()})
        if path == '/api/outbox/preview':
            uid = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get('id', [''])[0]
            try:
                item, file = outgoing_path(uid)
                kind = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif', '.webp': 'image/webp', '.bmp': 'image/bmp', '.avif': 'image/avif'}.get(file.suffix.lower())
                if kind is None or item['size'] > 100 * 1024**2:
                    return self.send(415, {'error': '此文件请下载后打开'})
                return self.send(200, file.read_bytes(), kind)
            except OSError as exc:
                return self.send(404, {'error': str(exc)[:160]})
        if not self.admin():
            return self.send(403, {'error': '仅电脑端可操作'})
        if path == '/api/config':
            urls = [f'http://{ip}:{self.server.server_port}/#{TOKEN}' for ip in addresses()]
            try:
                codes = [qr_data(url) for url in urls]
                error = ''
            except Exception:
                codes = []
                error = '二维码生成失败，请复制下方地址在手机浏览器打开，或重新启动程序'
            return self.send(200, {'urls': urls, 'qrs': codes, 'qr_error': error, 'folder': str(DATA), 'computer': socket.gethostname(), 'version': '1.7'})
        if path == '/api/items':
            with LOCK:
                items = list(reversed(ITEMS))
            return self.send(200, {'items': items})
        if path == '/api/preview':
            uid = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get('id', [''])[0]
            try:
                item, file = received_path(uid)
                types = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif', '.webp': 'image/webp', '.bmp': 'image/bmp', '.avif': 'image/avif'}
                kind = types.get(file.suffix.lower())
                if kind is None or item['size'] > 100 * 1024**2:
                    return self.send(415, {'error': '请使用系统应用预览此格式或大图片'})
                return self.send(200, file.read_bytes(), kind)
            except (FileNotFoundError, OSError) as exc:
                return self.send(404, {'error': str(exc)[:160]})
        if path == '/api/qr':
            import qrcode
            from qrcode.image.pil import PilImage
            import io
            ip = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get('ip', [''])[0]
            if ip not in addresses():
                return self.send(400, {'error': '无效地址'})
            qr = qrcode.make(f'http://{ip}:{self.server.server_port}/#{TOKEN}', image_factory=PilImage)
            buffer = io.BytesIO()
            qr.save(buffer, format='PNG')
            return self.send(200, buffer.getvalue(), 'image/png')
        return self.send(404, {'error': '不存在'})

    def do_POST(self):
        path = urllib.parse.urlsplit(self.path).path
        if not self.allowed():
            return self.send(403, {'error': '连接已失效，请重新扫码'})
        outgoing = path in ['/api/outbox/file', '/api/outbox/text']
        if outgoing and not self.admin():
            return self.send(403, {'error': '只能在电脑端选择要发到手机的内容'})
        if path in ['/api/open', '/api/save']:
            if not self.admin():
                return self.send(403, {'error': '请在电脑接收页面打开文件'})
            try:
                length = int(self.headers.get('Content-Length', '-1'))
                if not 0 < length <= 1024:
                    raise ValueError('无效请求')
                item_id = json.loads(self.rfile.read(length)).get('id')
                if not isinstance(item_id, str):
                    raise ValueError('无效文件编号')
                if path == '/api/save':
                    return self.send(200, {'ok': True, 'item': save_received(item_id)})
                open_received(item_id)
                return self.send(200, {'ok': True})
            except FileNotFoundError as exc:
                return self.send(404, {'error': str(exc)})
            except (ValueError, AttributeError):
                return self.send(400, {'error': '无效请求，请刷新页面后再试'})
            except OSError:
                return self.send(400, {'error': '操作失败，请检查文件占用、磁盘空间或默认应用设置'})
        if path == '/api/folder' and self.admin():
            os.startfile(str(DATA))
            return self.send(200, {'ok': True})
        if path == '/api/cast-settings' and self.admin():
            os.startfile('ms-settings:project')
            return self.send(200, {'ok': True})
        if path == '/api/cast-features' and self.admin():
            os.startfile('ms-settings:optionalfeatures')
            return self.send(200, {'ok': True})
        if path == '/api/stop' and self.admin():
            self.send(200, {'ok': True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        if path not in ['/api/file', '/api/text', '/api/outbox/file', '/api/outbox/text']:
            return self.send(404, {'error': '不存在'})
        try:
            length = int(self.headers.get('Content-Length', '-1'))
        except ValueError:
            length = -1
        is_text = path in ['/api/text', '/api/outbox/text']
        limit = 1024**2 if is_text else 2 * 1024**3
        if length < 0 or length > limit:
            return self.send(413, {'error': '单个文件最多 2 GB，文字最多 1 MB'})
        pending = cache_dir() if outgoing else DATA
        if shutil.disk_usage(pending).free < length + 10 * 1024**2:
            return self.send(507, {'error': '电脑磁盘空间不足'})
        uid = secrets.token_hex(8)
        temp = pending / ('.' + uid + '.part')
        self.connection.settimeout(120)
        try:
            if is_text:
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ValueError('连接中断，请重新发送')
                body = json.loads(raw)
                if not isinstance(body, dict):
                    raise ValueError('文字请求格式无效')
                message = body.get('text', '')
                if not isinstance(message, str) or not message.strip():
                    raise ValueError('请先输入文字')
                name = '文字_' + time.strftime('%Y%m%d_%H%M%S') + '.txt'
                temp.write_text(message, encoding='utf-8')
                size = temp.stat().st_size
            else:
                name = urllib.parse.unquote(self.headers.get('X-Filename', '文件'))
                name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).strip(' .')[:150] or '文件'
                if name.split('.')[0].upper() in ['CON', 'PRN', 'AUX', 'NUL'] + [f'{p}{n}' for p in ['COM', 'LPT'] for n in range(1,10)]:
                    name = '_' + name
                remaining = length
                with temp.open('wb') as out:
                    while remaining:
                        chunk = self.rfile.read(min(1024 * 1024, remaining))
                        if not chunk:
                            raise ValueError('连接中断，请重新发送')
                        out.write(chunk)
                        remaining -= len(chunk)
                size = length
                message = None
            dest = pending / (time.strftime('%Y%m%d_%H%M%S_') + uid[:6] + '_' + name)
            temp.replace(dest)
            item = {'id': uid, 'name': name, 'size': size, 'time': time.strftime('%H:%M:%S'), 'text': message, 'saved': dest.name, 'is_saved': not outgoing}
            if outgoing:
                item['ticket'] = secrets.token_urlsafe(24)
            with LOCK:
                target = OUTBOX if outgoing else ITEMS
                target.append(item)
                del target[:-300]
            return self.send(200, {'ok': True, 'item': item})
        except (ValueError, OSError, UnicodeError) as exc:
            temp.unlink(missing_ok=True)
            return self.send(400, {'error': str(exc)[:160]})

def main():
    startup_log('开始启动')
    restore_items()
    server = None
    for port in range(17960, 17980):
        try:
            server = Server(('0.0.0.0', port), Handler)
            break
        except OSError:
            continue
    if server is None:
        raise RuntimeError('启动失败，端口已被占用')
    url = f'http://127.0.0.1:{server.server_port}/?admin={ADMIN}&v=1.7'
    service = threading.Thread(target=server.serve_forever, daemon=True)
    service.start()
    startup_log('接收服务已启动，端口 ' + str(server.server_port))
    try:
        if '--headless' not in sys.argv:
            opened = webbrowser.open(url, new=1)
            startup_log('已请求打开欢迎页，浏览器返回 ' + str(opened))
            if not opened and sys.platform == 'win32':
                ctypes.windll.user32.MessageBoxW(0, '默认浏览器未能打开。请复制下面地址到浏览器：\n\n' + url, '奶蛙快传 v1.7', 64)
        else:
            print(url, flush=True)
        service.join()
    except KeyboardInterrupt:
        pass
    finally:
        if service.is_alive():
            server.shutdown()
        server.server_close()
        if TEMP_SESSION is not None:
            TEMP_SESSION.cleanup()
        startup_log('接收服务已结束')

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        startup_log('启动失败：' + type(exc).__name__ + ' ' + str(exc))
        if sys.platform == 'win32':
            ctypes.windll.user32.MessageBoxW(0, str(exc), '奶蛙快传 · 启动失败', 16)
        else:
            raise
