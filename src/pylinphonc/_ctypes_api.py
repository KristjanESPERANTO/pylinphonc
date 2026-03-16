"""
Low-level ctypes bindings for liblinphone.

Provides function signature setup, enum constants, and a helper to
traverse bctbx linked lists.
"""

import ctypes
import platform

# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

_LIB_NAMES = {
    "Windows": "liblinphone.dll",
    "Linux":   "liblinphone.so",
    "Darwin":  "liblinphone.dylib",
}


def get_lib_name() -> str:
    """Return the platform-appropriate shared library filename."""
    return _LIB_NAMES.get(platform.system(), "liblinphone.so")


# ---------------------------------------------------------------------------
# LinphoneRegistrationState enum
# ---------------------------------------------------------------------------

REG_NONE     = 0
REG_PROGRESS = 1
REG_OK       = 2
REG_CLEARED  = 3
REG_FAILED   = 4

# ---------------------------------------------------------------------------
# LinphoneCallState enum (call-enums.h)
# ---------------------------------------------------------------------------

CALL_INCOMING = 1  # LinphoneCallStateIncomingReceived


# ---------------------------------------------------------------------------
# Function signature setup
# ---------------------------------------------------------------------------

def setup_lib(lib: ctypes.CDLL) -> type:
    """
    Assign return types and argument types to all used library functions.

    Returns the CFUNCTYPE class for the call-state-changed callback so the
    caller can create a properly typed callback without importing ctypes.
    """
    vp = ctypes.c_void_p
    cp = ctypes.c_char_p
    ci = ctypes.c_int

    # Factory
    lib.linphone_factory_get.restype  = vp
    lib.linphone_factory_get.argtypes = []

    lib.linphone_factory_create_core_3.restype  = vp
    lib.linphone_factory_create_core_3.argtypes = [vp, cp, cp, vp]

    lib.linphone_factory_create_core_cbs.restype  = vp
    lib.linphone_factory_create_core_cbs.argtypes = [vp]

    # Core lifecycle
    lib.linphone_core_start.restype  = ci
    lib.linphone_core_start.argtypes = [vp]

    lib.linphone_core_stop.restype  = ci
    lib.linphone_core_stop.argtypes = [vp]

    lib.linphone_core_iterate.restype  = None
    lib.linphone_core_iterate.argtypes = [vp]

    lib.linphone_core_add_callbacks.restype  = None
    lib.linphone_core_add_callbacks.argtypes = [vp, vp]

    # Account / registration
    lib.linphone_core_get_default_account.restype  = vp
    lib.linphone_core_get_default_account.argtypes = [vp]

    lib.linphone_account_get_state.restype  = ci
    lib.linphone_account_get_state.argtypes = [vp]

    lib.linphone_account_refresh_register.restype  = None
    lib.linphone_account_refresh_register.argtypes = [vp]

    # Call control
    lib.linphone_call_accept.restype  = ci
    lib.linphone_call_accept.argtypes = [vp]

    lib.linphone_call_get_state.restype  = ci
    lib.linphone_call_get_state.argtypes = [vp]

    lib.linphone_core_get_calls_nb.restype  = ci
    lib.linphone_core_get_calls_nb.argtypes = [vp]

    lib.linphone_core_get_calls.restype  = vp   # bctbx_list_t*
    lib.linphone_core_get_calls.argtypes = [vp]

    # Core callbacks – setter for call_state_changed
    CallStateCbType = ctypes.CFUNCTYPE(None, vp, vp, ci, cp)
    lib.linphone_core_cbs_set_call_state_changed.restype  = None
    lib.linphone_core_cbs_set_call_state_changed.argtypes = [vp, CallStateCbType]

    return CallStateCbType


# ---------------------------------------------------------------------------
# bctbx_list_t traversal  (node layout: prev*, next*, data*)
# ---------------------------------------------------------------------------

class _BctbxNode(ctypes.Structure):
    pass

_BctbxNode._fields_ = [
    ("next", ctypes.POINTER(_BctbxNode)),
    ("prev", ctypes.POINTER(_BctbxNode)),
    ("data", ctypes.c_void_p),
]


def bctbx_to_list(ptr: int) -> list:
    """Convert a bctbx_list_t* pointer into a Python list of c_void_p values."""
    items = []
    if not ptr:
        return items
    node = ctypes.cast(ptr, ctypes.POINTER(_BctbxNode))
    while node:
        items.append(node.contents.data)
        nxt = node.contents.next
        node = nxt if (nxt and ctypes.cast(nxt, ctypes.c_void_p).value) else None
    return items
