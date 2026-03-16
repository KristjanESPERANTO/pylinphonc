# Changelog

All notable changes to pylinphonc are documented here.

## [0.1.0] – unreleased

### Added
- Initial release: drop-in replacement for `linphonc.exe` 3.x
- stdin/stdout interface: `status register`, `register`, `quit`/`exit`
- Auto-answer mode (`-a`)
- Configurable log level and log file (`-d`, `-l`)
- `--dll-dir` for flexible SDK location
- Support for liblinphone 5.x (tested with 5.4.x / Windows app installer 6.1.0)
- CWD workaround for grammar file loading on Windows
- Platform-aware library name (Windows/Linux/macOS)
