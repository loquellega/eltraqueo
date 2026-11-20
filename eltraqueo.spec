# -*- mode: python ; coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# Compilar en cada sistema:  pyinstaller eltraqueo.spec --noconfirm
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

datas = [("eltraqueo/ui", "eltraqueo/ui")] + collect_data_files("rtmlib")
binaries = collect_dynamic_libs("onnxruntime")
hidden = (collect_submodules("eltraqueo") + collect_submodules("rtmlib")
          + ["serial", "cv2_enumerate_cameras", "onnxruntime", "onnxruntime.capi._pybind_state"])

a = Analysis(["run_eltraqueo.py"], pathex=["."], binaries=binaries, datas=datas,
             hiddenimports=hidden, excludes=["tkinter", "matplotlib", "PyQt5", "PySide6", "pandas", "scipy", "sympy",
                       "torch", "pkg_resources", "setuptools", "IPython",
                       "onnxruntime.transformers", "onnxruntime.quantization", "onnxruntime.tools"],
             noarchive=False)
pyz = PYZ(a.pure)

is_mac = sys.platform == "darwin"
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="eltraqueo",
          console=not is_mac,            # en Windows la consola muestra la dirección y cerrarla sale
          icon=None, argv_emulation=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="eltraqueo")

if is_mac:
    app = BUNDLE(coll, name="eltraqueo.app", icon=None, bundle_identifier="mx.hectorcruz.eltraqueo",
                 info_plist={
                     "NSCameraUsageDescription": "eltraqueo usa la cámara para seguir cuerpos en escena.",
                     "NSLocalNetworkUsageDescription": "eltraqueo envía datos OSC a la red local.",
                     "CFBundleShortVersionString": "0.1.0",
                     "LSMinimumSystemVersion": "12.0",
                 })
