"""Build the Windows executable from any working directory."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

if __name__ == '__main__':
    if sys.platform != 'win32':
        raise SystemExit('Build this Windows desktop application on Windows.')
    subprocess.run([
        sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
        '--onefile', '--windowed', '--name', '奶蛙快传双向版',
        '--distpath', str(ROOT / 'dist'),
        '--workpath', str(ROOT / 'build' / 'pyinstaller'),
        '--specpath', str(ROOT / 'build'),
        '--add-data', str(ROOT / 'ui.html') + ';.', str(ROOT / 'app.py'),
    ], cwd=ROOT, check=True)
    print('Built:', ROOT / 'dist' / '奶蛙快传双向版.exe')
