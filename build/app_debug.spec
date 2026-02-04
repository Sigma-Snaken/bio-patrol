# -*- mode: python ; coding: utf-8 -*-
# Debug version with console output

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('settings/', 'settings/'),
        ('public/', 'public/'),
    ],
    hiddenimports=[
        'pydantic_settings',
        'python_dotenv',
        'uvicorn.lifespan.on',
        'uvicorn.lifespan.off',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets.wsproto_impl',
        'uvicorn.protocols.http.httptools_impl',
        'uvicorn.protocols.http.h11_impl',
        'uvicorn.loops.auto',
        'uvicorn.loops.asyncio',
        'uvicorn.logging',
        'kachaka_api',
        'fastapi',
        'starlette',
        'asyncio',
        'json',
        'sqlite3',
        'aiohttp',
        'grpcio',
        'protobuf',
        'paho.mqtt',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='kachaka_cmd_center_debug',
    debug=True,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # Disable UPX for debugging
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Force console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    onefile=True,
)