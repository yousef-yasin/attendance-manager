"""Frozen-app entry point used by PyInstaller."""

from attendance_manager.app import main

if __name__ == "__main__":
    raise SystemExit(main())
