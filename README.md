# pylinphonc

Python replacement for `linphonc.exe` — the discontinued Linphone CLI client.

`linphonc.exe` was a small command-line SIP client shipped with Linphone 3.x (last release 2014).
It accepted commands via stdin and reported registration state via stdout — making it easy to
control from watchdog scripts. Linphone dropped the CLI client after 3.x when moving to a
Qt-based GUI. This project brings it back using the current **liblinphone 5.x SDK** via ctypes.

## Why this exists

- `linphonc.exe` hasn't been updated since ~2014 (GTK2, Windows XP era)
- The official PyPI package `linphone` was discontinued in 2023 and only supported Python ≤ 3.7
- No usable Python bindings exist for liblinphone on Windows with Python 3.8+
- This project fills that gap: Python 3.8+, Windows (tested), Linux/macOS (planned)

## stdin/stdout interface (linphonc.exe compatible)

| stdin command    | stdout output                       |
|------------------|-------------------------------------|
| `status register`| `registered=1` or `registered=-1`  |
| `register`       | *(triggers re-registration, silent)*|
| `quit` / `exit`  | *(shuts down cleanly)*              |

## Requirements

- Python 3.8+
- Linphone SDK 5.x (`liblinphone.dll` / `.so` / `.dylib`)

The SDK is **not bundled** — you must obtain it separately (see below).

## SDK setup (Windows)

1. Download the NuGet package directly (no nuget.exe needed — it's just a ZIP):

   https://gitlab.linphone.org/BC/public/linphone-sdk/-/packages/2867

   Click **Download** next to `linphonesdk.windows.5.4.97.nupkg`

2. Extract it:

   ```powershell
   $sdk = "C:\linphone-sdk"
   Rename-Item linphonesdk.windows.5.4.97.nupkg linphonesdk.windows.5.4.97.zip
   Expand-Archive linphonesdk.windows.5.4.97.zip -DestinationPath $sdk
   ```

3. Rename `content\` → `share\` so the DLL finds the grammar files:

   ```powershell
   Rename-Item "$sdk\content" "$sdk\share"
   ```

4. Use `$sdk\lib\win\x64` as your `--dll-dir`.

> **Newer versions** are listed at https://gitlab.linphone.org/BC/public/linphone-sdk/-/packages
> — filter by `LinphoneSDK.Windows`.

## Installation

```bash
pip install pylinphonc
# or from source:
git clone https://github.com/KristjanESPERANTO/pylinphonc
pip install ./pylinphonc
```

## Usage

```bash
# Basic (reads linphonerc from same directory as the script)
pylinphonc --dll-dir "C:\linphone-sdk\...\lib\win\x64"

# With config file and auto-answer
pylinphonc --dll-dir "C:\linphone-sdk\...\lib\win\x64" -c linphonerc -a

# With logging
pylinphonc --dll-dir "C:\linphone-sdk\...\lib\win\x64" -c linphonerc -a -d 1 -l pylinphonc.log

# As a module
python -m pylinphonc --dll-dir "..." -c linphonerc -a
```

### CLI arguments (compatible with linphonc.exe)

| Argument                    | Description                                      |
|-----------------------------|--------------------------------------------------|
| `-a`                        | Auto-answer incoming calls                       |
| `-d LEVEL`                  | Log level: 0=quiet, 1=normal, 3=debug            |
| `-l FILE`                   | Log file path                                    |
| `-c FILE`                   | linphonerc config file path                      |
| `--dll-dir DIR`             | Directory containing `liblinphone.dll`           |
| `--reregister-interval SEC` | Re-register when lost, every SEC seconds (default: 30, 0=off) |

## Known issues

### CWD side effect on Windows

`liblinphone.dll` (Windows build) locates grammar files
(`share/belr/grammars/vcard_grammar.belr` etc.) relative to the **process working
directory** at the time the DLL is loaded. pylinphonc walks up the directory tree
from `--dll-dir` until it finds `share/belr/grammars/`, sets `os.chdir()` to that
directory, and does **not** restore it afterwards. This is intentional — changing
CWD after DLL load may cause crashes.

If your application also uses relative paths for other files, pass absolute paths
to all arguments (`-c`, `-l`) when using pylinphonc.

## License

GNU Affero General Public License v3.0 or later (AGPL-3.0-or-later).

The Linphone SDK itself is also AGPLv3:
https://gitlab.linphone.org/BC/public/linphone-sdk

> **Note for commercial use:** If you want to use pylinphonc in proprietary software,
> you need a commercial Linphone SDK license from Belledonne Communications:
> https://www.linphone.org/contact
