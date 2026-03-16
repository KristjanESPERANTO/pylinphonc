"""
pylinphonc – Python replacement for linphonc.exe (Linphone CLI client).

Drop-in replacement for the discontinued linphonc.exe 3.x binary, using
liblinphone 5.x via ctypes. Provides the same stdin/stdout interface for
compatibility with existing watchdog scripts (e.g. PowerShell service monitors).

License: GNU Affero General Public License v3.0 or later (AGPL-3.0-or-later)
The Linphone SDK itself is also AGPLv3: https://gitlab.linphone.org/BC/public/linphone-sdk
"""

from pylinphonc._ctypes_api import (
    REG_NONE,
    REG_PROGRESS,
    REG_OK,
    REG_CLEARED,
    REG_FAILED,
    CALL_INCOMING,
)

__version__ = "0.1.0"
__all__ = [
    "REG_NONE",
    "REG_PROGRESS",
    "REG_OK",
    "REG_CLEARED",
    "REG_FAILED",
    "CALL_INCOMING",
]
