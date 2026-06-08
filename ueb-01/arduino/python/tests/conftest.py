"""Pytest bootstrap for the Arduino App's audience tests.

Ensures ``arduino/python/`` is importable so the audience modules resolve the
same way they do on-board (where this dir is on ``sys.path``). These tests
exercise the audience strategy modules in isolation — they must NOT import
``main.py``, since ``arduino.app_utils`` / ``arduino.app_bricks`` are only
available on the board.
"""
from __future__ import annotations

import os
import sys

_PYTHON_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PYTHON_ROOT not in sys.path:
    sys.path.insert(0, _PYTHON_ROOT)
