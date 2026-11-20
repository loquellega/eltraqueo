# SPDX-License-Identifier: GPL-3.0-or-later
"""Entrada para PyInstaller y para correr desde el código: python run_eltraqueo.py"""
import multiprocessing
import sys

from eltraqueo.app import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
