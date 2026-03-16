"""Tests for pylinphonc._ctypes_api (pure Python, no DLL required)."""

import pytest
from pylinphonc._ctypes_api import (
    REG_NONE, REG_PROGRESS, REG_OK, REG_CLEARED, REG_FAILED,
    CALL_INCOMING,
    get_lib_name,
    bctbx_to_list,
)


def test_reg_constants_are_distinct():
    values = [REG_NONE, REG_PROGRESS, REG_OK, REG_CLEARED, REG_FAILED]
    assert len(set(values)) == len(values)


def test_reg_ok_value():
    assert REG_OK == 2


def test_call_incoming_value():
    assert CALL_INCOMING == 1


def test_get_lib_name_windows(monkeypatch):
    monkeypatch.setattr("platform.system", lambda: "Windows")
    assert get_lib_name() == "liblinphone.dll"


def test_get_lib_name_linux(monkeypatch):
    monkeypatch.setattr("platform.system", lambda: "Linux")
    assert get_lib_name() == "liblinphone.so"


def test_get_lib_name_darwin(monkeypatch):
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    assert get_lib_name() == "liblinphone.dylib"


def test_get_lib_name_unknown_falls_back_to_so(monkeypatch):
    monkeypatch.setattr("platform.system", lambda: "FreeBSD")
    assert get_lib_name() == "liblinphone.so"


def test_bctbx_to_list_null_returns_empty():
    assert bctbx_to_list(0) == []
    assert bctbx_to_list(None) == []
