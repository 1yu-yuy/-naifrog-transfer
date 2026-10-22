import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

class TransferTests(unittest.TestCase):
    def setUp(self):
        self.fixture = tempfile.TemporaryDirectory(prefix='.test-data-', dir=ROOT)
        self.addCleanup(self.fixture.cleanup)
        folder = Path(self.fixture.name)
        program = folder / 'program'
        program.mkdir()
        for name in ('app.py', 'ui.html'):
            shutil.copy2(ROOT / name, program / name)
        temp = folder / 'system-temp'
        temp.mkdir()
        patcher = patch.object(tempfile, 'tempdir', str(temp))
        patcher.start()
        self.addCleanup(patcher.stop)
        spec = importlib.util.spec_from_file_location('transfer_test', program / 'app.py')
        self.app = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.app)
        self.addCleanup(self.cleanup_cache)

    def cleanup_cache(self):
        if self.app.TEMP_SESSION is not None:
            self.app.TEMP_SESSION.cleanup()

    def request(self, path, body=b'', admin=False, authorized=True, get=False, length=None):
        a = self.app
        h = object.__new__(a.Handler)
        h.path = path
        h.server = type('Server', (), {'server_port': 17960})()
        h.client_address = ('127.0.0.1' if admin else '192.0.2.2', 1234)
        h.headers = {'Content-Length': str(len(body) if length is None else length), 'X-Filename': 'same.txt'}
        if authorized:
            h.headers['X-Admin' if admin else 'X-Token'] = a.ADMIN if admin else a.TOKEN
        h.rfile = io.BytesIO(body)
        h.connection = type('Connection', (), {'settimeout': lambda *_: None})()
        result = []
        h.send = lambda code, data=b'', kind=None: result.append((code, data, kind))
        (h.do_GET if get else h.do_POST)()
        return result[0]

    def test_receive_same_names_without_cache(self):
        names = []
        for data in (b'one', b'two'):
            code, result, _ = self.request('/api/file', data)
            self.assertEqual(code, 200)
            item = result['item']
            self.assertTrue(item['is_saved'])
            self.assertEqual(self.app.received_path(item['id'])[1].read_bytes(), data)
            names.append(item['saved'])
        self.assertEqual(len(set(names)), 2)
        self.assertIsNone(self.app.CACHE)

    def test_text_restore(self):
        code, result, _ = self.request('/api/text', json.dumps({'text': '你好奶蛙'}).encode())
        self.assertEqual(code, 200)
        self.app.ITEMS.clear()
        self.app.restore_items()
        self.assertEqual(len(self.app.ITEMS), 1)
        self.assertEqual(self.app.ITEMS[0]['text'], '你好奶蛙')
        self.assertTrue(self.app.ITEMS[0]['is_saved'])

    def test_cleanup_preserves_incoming(self):
        self.request('/api/file', b'keep')
        code, result, _ = self.request('/api/outbox/file', b'to-phone', admin=True)
        self.assertEqual(code, 200)
        self.assertEqual(self.app.outgoing_path(result['item']['id'])[1].read_bytes(), b'to-phone')
        cache = self.app.CACHE
        self.assertNotEqual(cache.parent, self.app.BASE)
        self.app.TEMP_SESSION.cleanup()
        self.assertFalse(cache.exists())
        self.assertEqual(len(list(self.app.DATA.iterdir())), 1)

    def test_access_control(self):
        self.assertEqual(self.request('/api/file', b'no', authorized=False)[0], 403)
        self.assertEqual(self.request('/api/outbox/file', b'no')[0], 403)
        self.assertEqual(self.request('/api/save', b'{}')[0], 403)
        self.assertEqual(self.request('/api/config', get=True)[0], 403)
        self.assertFalse(list(self.app.DATA.iterdir()))

    def test_interrupted_upload(self):
        self.assertEqual(self.request('/api/file', b'short', length=100)[0], 400)
        self.assertFalse(list(self.app.DATA.iterdir()))
        self.assertFalse(self.app.ITEMS)

    def test_invalid_id(self):
        with self.assertRaises(FileNotFoundError):
            self.app.received_path('../app.py')

    def test_version_and_qr(self):
        with patch.object(self.app, 'addresses', return_value=['192.0.2.1']):
            code, result, _ = self.request('/api/config', admin=True, get=True)
        self.assertEqual(code, 200)
        self.assertEqual(result['version'], '1.7')
        self.assertEqual(result['qr_error'], '')
        self.assertTrue(result['qrs'][0].startswith('data:image/svg+xml;base64,'))

if __name__ == '__main__':
    unittest.main()

