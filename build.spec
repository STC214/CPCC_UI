# -*- mode: python ; coding: utf-8 -*-
block_cipher = None

# 确保包含必要的数据文件
datas = [
    ('04.ico', '.'),
]

a = Analysis(
    ['main_app.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'cleaner_module',
        'old_module',
        'new_module',
        'PIL',
        'PIL.Image',
        'PIL.JpegImagePlugin',
        'logging',
        'shutil',
        'zipfile',
        're',
        'pathlib',
        'argparse',
        'json',
        'time',
        'tempfile',
        'uuid',
        'ctypes',
        'datetime',
        'typing'
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='漫画文件处理工具',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # 无控制台窗口
    icon='04.ico',
    disable_windowed_traceback=False,
    version_file=None,
    embed_manifest=True,
    onefile=True  # 添加单文件打包参数
)