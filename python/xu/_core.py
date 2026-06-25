"""Rust _core — all commands are implemented in Rust via maturin/pyo3.

This module is the compiled extension (xu/_core.*.pyd). The xu package
re-exports from here. No Python fallback — if the extension is not
built, import will fail.
"""
from xu._core import *