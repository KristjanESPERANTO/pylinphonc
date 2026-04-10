"""
Command-line interface: stdin/stdout dispatcher compatible with linphonc.exe 3.x.

Supported stdin commands (CLI mode):
  status register   → prints "registered=1" (ok) or "registered=-1" (error/not registered)
  register          → triggers re-registration
  quit / exit       → shuts down cleanly

Auto-reregister: when registration is lost (REG_FAILED), pylinphonc retries
automatically every --reregister-interval seconds (default: 30).

Windows Service subcommands (requires pywin32):
  pylinphonc install [-a] [-d N] [-l FILE] [-c FILE]
                        Install as Windows service 'PyLinphonc' and start it.
  pylinphonc start      Start the service.
  pylinphonc stop       Stop the service.
  pylinphonc uninstall  Remove the service.
"""

import argparse
import ctypes
import json
import logging
import os
import pathlib
import sys
import threading
import time

from pylinphonc._ctypes_api import (
    REG_OK,
    REG_FAILED,
    CALL_INCOMING,
    get_lib_name,
    setup_lib,
)

# ── Optional Windows service support (requires pywin32) ───────────────────────
try:
    import win32service
    import win32serviceutil
    import servicemanager
    _HAS_WIN32 = True
except ImportError:
    _HAS_WIN32 = False

# Directory of the frozen EXE (PyInstaller) or this source file (dev mode).
# Used to locate pylinphonc.service.json next to the executable.
_EXE_DIR = (
    pathlib.Path(sys.executable).parent
    if getattr(sys, "frozen", False)
    else pathlib.Path(__file__).parent
)
_SVC_CFG     = _EXE_DIR / "pylinphonc.service.json"
_SVC_NAME    = "PyLinphonc"
_SVC_DISPLAY = "PyLinphonc SIP Client"
_SVC_DESC    = "Linphone SIP client service – drop-in replacement for linphonc.exe"


def _reg_to_legacy(state: int) -> int:
    """Map LinphoneRegistrationState to the legacy linphonc return value (1 or -1)."""
    return 1 if state == REG_OK else -1


def _make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="pylinphonc – drop-in replacement for linphonc.exe using liblinphone 5.x"
    )
    parser.add_argument("-a", dest="autoanswer", action="store_true",
                        help="Automatically accept incoming calls")
    parser.add_argument("-d", dest="debug_level", type=int, default=1,
                        help="Log level (0=quiet, 1=normal, 3=debug)")
    parser.add_argument("-l", dest="logfile", default=None,
                        help="Path to log file")
    parser.add_argument("-c", dest="config", default=None,
                        help="Path to linphonerc config file")
    parser.add_argument("--dll-dir", dest="dll_dir", default=None,
                        help="Directory containing liblinphone shared library; "
                             "default: directory of this script")
    parser.add_argument("--reregister-interval", dest="reregister_interval",
                        type=int, default=30,
                        help="Seconds between automatic re-registration attempts "
                             "when registration is lost (0 = disabled, default: 30)")
    return parser


def _run_core(args, stop_event: threading.Event | None = None) -> None:
    """Core SIP loop. Called from CLI main() and from Windows service SvcDoRun()."""

    # In service mode stop_event is provided by SvcStop(); in CLI mode we own it.
    _shutdown      = stop_event if stop_event is not None else threading.Event()
    _need_register = threading.Event()
    service_mode   = stop_event is not None

    # ── Logging ─────────────────────────────────────────────────────────────
    log_level = logging.DEBUG if args.debug_level >= 3 else logging.INFO
    handlers: list = [logging.StreamHandler(sys.stderr)]
    if args.logfile:
        handlers.append(logging.FileHandler(args.logfile, encoding="utf-8"))
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)-5s %(message)s",
        handlers=handlers,
    )
    log = logging.getLogger("pylinphonc")

    # ── Resolve paths ────────────────────────────────────────────────────────
    # When built with PyInstaller (--onefile or --onedir), all bundled files
    # (DLLs, share/) are extracted to sys._MEIPASS at startup.
    # In that case --dll-dir is not required; we default to the bundle dir.
    _bundle_dir = getattr(sys, "_MEIPASS", None)
    script_dir  = _bundle_dir or os.path.dirname(os.path.abspath(__file__))

    dll_dir  = args.dll_dir or script_dir
    lib_name = get_lib_name()

    if not os.path.isfile(os.path.join(dll_dir, lib_name)):
        log.error("%s not found in: %s", lib_name, dll_dir)
        if _bundle_dir:
            log.error("Bundle may be missing the SDK DLLs – rebuild with build.bat.")
        else:
            log.error("Use --dll-dir to point to the SDK lib directory.")
        sys.exit(1)

    config_path = args.config
    if not config_path:
        candidate = os.path.join(script_dir, "linphonerc")
        if os.path.isfile(candidate):
            config_path = candidate
        else:
            log.warning("No linphonerc found at %s – starting without config.", candidate)

    log.info("DLL directory : %s", dll_dir)
    log.info("Config file   : %s", config_path or "(none)")
    log.info("Auto-answer   : %s", args.autoanswer)
    if service_mode:
        log.info("Running as Windows service")

    # ── Load shared library ──────────────────────────────────────────────────
    # liblinphone searches for grammar files (e.g. share/belr/grammars/vcard_grammar.belr)
    # relative to the process working directory at the time the DLL is loaded.
    # We walk up from dll_dir until we find a share/belr/grammars/ directory.
    #
    # Supported SDK layouts:
    #
    #   NuGet package (content/ renamed to share/ after extraction):
    #     <sdk_root>/lib/win/x64/liblinphone.dll   ← --dll-dir  (3 levels up = sdk_root)
    #     <sdk_root>/share/belr/grammars/
    #
    #   Windows app installer (7-zip extracted):
    #     <sdk_root>/bin/liblinphone.dll            ← --dll-dir  (1 level up = sdk_root)
    #     <sdk_root>/share/belr/grammars/
    #
    # Do NOT restore CWD after loading – the DLL also uses it for later grammar loads.
    def _find_sdk_root(start: str) -> str | None:
        candidate = start
        for _ in range(5):
            if os.path.isdir(os.path.join(candidate, "share", "belr", "grammars")):
                return candidate
            parent = os.path.dirname(candidate)
            if parent == candidate:
                break
            candidate = parent
        return None

    top_resources_dir = _find_sdk_root(dll_dir)
    if top_resources_dir is None:
        log.warning(
            "share/belr/grammars/ not found anywhere above %s – "
            "grammar files may be missing. See KNOWN_ISSUES.md for details.",
            dll_dir,
        )
        top_resources_dir = os.path.dirname(dll_dir)  # best-effort fallback
    else:
        log.info("SDK root (CWD for DLL load): %s", top_resources_dir)

    os.chdir(top_resources_dir)
    # Add dll_dir to PATH so that DLLs loaded transitively by liblinphone
    # (e.g. SOCI sqlite3 backend via LoadLibraryA) can be resolved.
    os.environ["PATH"] = dll_dir + os.pathsep + os.environ.get("PATH", "")
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(dll_dir)   # Python 3.8+ on Windows
    try:
        lib = ctypes.CDLL(os.path.join(dll_dir, lib_name))
    except OSError as exc:
        log.error("Failed to load %s: %s", lib_name, exc)
        sys.exit(1)

    CallStateCbType = setup_lib(lib)

    # ── Call-state callback (auto-answer) ────────────────────────────────────
    # The callback instance MUST be kept alive in a variable that outlives the
    # iterate loop – otherwise Python frees the memory and the function pointer
    # becomes invalid, causing a segfault.
    @CallStateCbType
    def _on_call_state_changed(core, call, state, message):
        msg_str = message.decode(errors="replace") if message else ""
        log.debug("Call state changed: state=%d msg=%s", state, msg_str)
        if args.autoanswer and state == CALL_INCOMING:
            log.info("Incoming call – accepting (auto-answer)")
            rc = lib.linphone_call_accept(call)
            if rc != 0:
                log.warning("linphone_call_accept failed: %d", rc)

    # ── Create core ──────────────────────────────────────────────────────────
    factory = lib.linphone_factory_get()
    if not factory:
        log.error("linphone_factory_get() returned NULL")
        sys.exit(1)

    core = lib.linphone_factory_create_core_3(
        factory,
        config_path.encode() if config_path else None,
        None,   # factory_config_path
        None,   # system_context (Android only)
    )
    if not core:
        log.error("linphone_factory_create_core_3() returned NULL")
        sys.exit(1)

    cbs = lib.linphone_factory_create_core_cbs(factory)
    if not cbs:
        log.error("linphone_factory_create_core_cbs() returned NULL")
        sys.exit(1)
    lib.linphone_core_cbs_set_call_state_changed(cbs, _on_call_state_changed)
    lib.linphone_core_add_callbacks(core, cbs)

    rc = lib.linphone_core_start(core)
    if rc != 0:
        log.error("linphone_core_start() failed: %d", rc)
        sys.exit(1)

    log.info("Linphone core started%s",
             " (service mode – no stdin)" if service_mode else " – waiting for commands on stdin ...")

    # ── stdin reader thread (CLI mode only) ───────────────────────────────────
    if not service_mode:
        def _stdin_reader() -> None:
            try:
                for raw in sys.stdin:
                    cmd = raw.strip().lower()
                    if not cmd:
                        continue

                    if cmd == "status register":
                        account = lib.linphone_core_get_default_account(core)
                        if account:
                            state = lib.linphone_account_get_state(account)
                            legacy = _reg_to_legacy(state)
                        else:
                            log.warning("No default account – sending registered=-1")
                            legacy = -1
                        print(f"registered={legacy}", flush=True)
                        log.debug("status register → registered=%d", legacy)

                    elif cmd == "register":
                        log.info("Re-registration requested")
                        _need_register.set()

                    elif cmd in ("quit", "exit"):
                        log.info("Shutdown command received: %s", cmd)
                        _shutdown.set()
                        break

                    else:
                        log.debug("Unknown command ignored: %r", cmd)
            except EOFError:
                pass
            except Exception as exc:
                log.error("stdin reader error: %s", exc)
            finally:
                _shutdown.set()

        reader = threading.Thread(target=_stdin_reader, daemon=True, name="stdin-reader")
        reader.start()

    # ── Main iterate loop ─────────────────────────────────────────────────────
    log.info("Starting iterate loop (20 ms tick)")
    _last_reregister = 0.0
    try:
        while not _shutdown.is_set():
            lib.linphone_core_iterate(core)

            if _need_register.is_set():
                _need_register.clear()
                account = lib.linphone_core_get_default_account(core)
                if account:
                    lib.linphone_account_refresh_register(account)
                    log.info("linphone_account_refresh_register() called")
                    _last_reregister = time.monotonic()
                else:
                    log.warning("Re-registration requested but no default account")

            # Auto-reregister: if registration is lost, retry periodically
            elif args.reregister_interval > 0:
                now = time.monotonic()
                if now - _last_reregister >= args.reregister_interval:
                    account = lib.linphone_core_get_default_account(core)
                    if account:
                        state = lib.linphone_account_get_state(account)
                        if state == REG_FAILED:
                            log.info("Registration lost – triggering re-registration")
                            lib.linphone_account_refresh_register(account)
                            _last_reregister = now

            time.sleep(0.02)   # 20 ms – matches linphone_core_iterate recommendation

    except KeyboardInterrupt:
        log.info("KeyboardInterrupt – stopping")
    finally:
        log.info("Stopping Linphone core ...")
        lib.linphone_core_stop(core)
        log.info("Linphone core stopped.")


# ── Windows Service class ──────────────────────────────────────────────────────
if _HAS_WIN32:
    class _PylinphoncService(win32serviceutil.ServiceFramework):
        _svc_name_         = _SVC_NAME
        _svc_display_name_ = _SVC_DISPLAY
        _svc_description_  = _SVC_DESC

        def __init__(self, args):
            win32serviceutil.ServiceFramework.__init__(self, args)
            self._stop = threading.Event()

        def SvcStop(self):
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            self._stop.set()

        def SvcDoRun(self):
            servicemanager.LogMsg(
                servicemanager.EVENTLOG_INFORMATION_TYPE,
                servicemanager.PYS_SERVICE_STARTED,
                (self._svc_name_, ""),
            )
            if not _SVC_CFG.exists():
                servicemanager.LogErrorMsg(
                    f"pylinphonc: service config not found: {_SVC_CFG}\n"
                    f"Re-run: pylinphonc install <args>"
                )
                return
            saved     = json.loads(_SVC_CFG.read_text(encoding="utf-8"))
            svc_args  = _make_parser().parse_args(saved.get("args", []))
            _run_core(svc_args, stop_event=self._stop)
            servicemanager.LogMsg(
                servicemanager.EVENTLOG_INFORMATION_TYPE,
                servicemanager.PYS_SERVICE_STOPPED,
                (self._svc_name_, ""),
            )


def _svc_install(extra_args: list) -> None:
    """Register pylinphonc.exe as a Windows service and start it."""
    if not _HAS_WIN32:
        print("ERROR: pywin32 is required.  pip install pywin32", file=sys.stderr)
        sys.exit(1)

    # Validate args before saving
    _make_parser().parse_args(extra_args)

    _SVC_CFG.write_text(json.dumps({"args": extra_args}), encoding="utf-8")
    print(f"Service config saved: {_SVC_CFG}")

    exe_path = sys.executable
    hscm = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_CREATE_SERVICE)
    try:
        hs = win32service.CreateService(
            hscm,
            _SVC_NAME,
            _SVC_DISPLAY,
            win32service.SERVICE_ALL_ACCESS,
            win32service.SERVICE_WIN32_OWN_PROCESS,
            win32service.SERVICE_AUTO_START,
            win32service.SERVICE_ERROR_NORMAL,
            exe_path,
            None, 0, None, None, None,
        )
        win32service.ChangeServiceConfig2(
            hs, win32service.SERVICE_CONFIG_DESCRIPTION, _SVC_DESC
        )
        # Restart on failure: 3 attempts with 5 s delay, reset counter after 24 h
        win32service.ChangeServiceConfig2(
            hs,
            win32service.SERVICE_CONFIG_FAILURE_ACTIONS,
            {
                "ResetPeriod": 86400,
                "RebootMsg":   None,
                "Command":     None,
                "Actions": [
                    (win32service.SC_ACTION_RESTART, 5000),
                    (win32service.SC_ACTION_RESTART, 5000),
                    (win32service.SC_ACTION_RESTART, 5000),
                ],
            },
        )
        win32service.StartService(hs, None)
        win32service.CloseServiceHandle(hs)
        print(f"Service '{_SVC_NAME}' installed and started.")
    except win32service.error as exc:
        if exc.winerror == 1073:   # ERROR_SERVICE_EXISTS
            print(f"Service '{_SVC_NAME}' already exists. Run 'uninstall' first.",
                  file=sys.stderr)
        else:
            print(f"Failed to install service: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        win32service.CloseServiceHandle(hscm)


def _svc_uninstall() -> None:
    """Stop and remove the Windows service."""
    if not _HAS_WIN32:
        print("ERROR: pywin32 is required.  pip install pywin32", file=sys.stderr)
        sys.exit(1)
    try:
        win32serviceutil.StopService(_SVC_NAME)
    except Exception:
        pass
    try:
        win32serviceutil.RemoveService(_SVC_NAME)
        print(f"Service '{_SVC_NAME}' removed.")
    except Exception as exc:
        print(f"Failed to remove service: {exc}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    # ── Service subcommands ──────────────────────────────────────────────────
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == "install":
            _svc_install(sys.argv[2:])
            return
        elif cmd in ("uninstall", "remove"):
            _svc_uninstall()
            return
        elif cmd == "start":
            if not _HAS_WIN32:
                print("ERROR: pywin32 required.", file=sys.stderr); sys.exit(1)
            win32serviceutil.StartService(_SVC_NAME)
            print(f"Service '{_SVC_NAME}' started.")
            return
        elif cmd == "stop":
            if not _HAS_WIN32:
                print("ERROR: pywin32 required.", file=sys.stderr); sys.exit(1)
            win32serviceutil.StopService(_SVC_NAME)
            print(f"Service '{_SVC_NAME}' stopped.")
            return

    # ── SCM invocation detection ─────────────────────────────────────────────
    # When Windows SCM starts the frozen EXE as a service, argv has only the
    # program name (no extra args). We try to connect to the SCM dispatcher;
    # error 1063 (ERROR_FAILED_SERVICE_CONTROLLER_CONNECT) means we are NOT
    # running as a service, so we fall through to normal CLI mode.
    if _HAS_WIN32 and len(sys.argv) == 1 and _SVC_CFG.exists():
        try:
            servicemanager.Initialize()
            servicemanager.PrepareToHostSingle(_PylinphoncService)
            servicemanager.StartServiceCtrlDispatcher()
            return
        except win32service.error as exc:
            if exc.winerror != 1063:
                raise
        # Not called by SCM – fall through to CLI

    # ── Normal CLI mode ──────────────────────────────────────────────────────
    args = _make_parser().parse_args()
    _run_core(args)
