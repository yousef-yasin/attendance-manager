# Release Process

How to build, verify, sign and publish a Windows release of Attendance Manager.

## Prerequisites

- Windows 10/11 x64
- Python 3.10 or newer (`py -3` or `python` on `PATH`)
- Inno Setup 6. If it is missing, `build.bat` installs it per-user with `winget`.

## 1. Prepare

1. Update `__version__` in `src/attendance_manager/__init__.py`. It is also used for the EXE
   version resource and the installer.
2. Move the *Unreleased* entries in `CHANGELOG.md` under the new version and date.
3. If the database schema changed, **append** a migration to `persistence/schema.py` (never edit
   an existing one) and add a test.
4. Make sure CI is green on `main`.

## 2. Build

```bat
build.bat
```

`scripts\build.ps1` then:

1. creates an isolated `.venv-build` and installs the pinned dependencies;
2. runs the test suite (pass `-SkipTests` only if the same commit was just tested);
3. renders the icon assets (`packaging\make_icon.py`, source design `packaging\assets\app_icon.svg`);
4. freezes the application with PyInstaller (`packaging\attendance_manager.spec`, one-folder build
   with version resource, icon, locale catalogs and Qt's Arabic translations) into
   `dist\AttendanceManager\`;
5. runs the frozen `AttendanceManager.exe --self-test` (import → match → UI → report → backup);
6. compiles the Inno Setup installer (`packaging\installer.iss`).

The build ends with `BUILD SUCCEEDED` and the installer path:

```
dist\installer\Attendance Manager Setup.exe
```

`dist\` and `build\` are ignored by git. **Never commit the installer**; it is published as a
GitHub Release asset (step 5).

## 3. Verify

On a clean Windows user account (or a virtual machine):

1. Install `Attendance Manager Setup.exe` and confirm that the desktop and Start Menu shortcuts
   open the application.
2. Switch **English → العربية → English**: the layout must mirror to right-to-left and back.
   Close and reopen the application and confirm that the language was remembered.
3. Create a course from a master list, add several weekly attendance files, and check the
   dashboard figures and the students page.
4. Export the Excel report and open it in Excel.
5. Close and reopen the application: the course and its sessions must still be there.
6. Uninstall from *Settings → Apps*: the program folder, the shortcuts and the *Apps* entry must be
   gone, while `%LOCALAPPDATA%\AttendanceManager` (user data) remains.

Silent installation for IT deployment:

```bat
"Attendance Manager Setup.exe" /VERYSILENT /SUPPRESSMSGBOXES /TASKS=desktopicon
"%LOCALAPPDATA%\Programs\Attendance Manager\unins000.exe" /VERYSILENT
```

(`/DIR="…"` installs to another folder; the uninstaller is always `unins000.exe` in the install
folder.)

## 4. Sign

Unsigned binaries trigger Windows SmartScreen and can be flagged by heuristic antivirus engines.
For public distribution, sign both the executable and the installer with a code-signing
certificate:

```bat
signtool sign /fd sha256 /tr http://timestamp.digicert.com /td sha256 /a dist\AttendanceManager\AttendanceManager.exe
signtool sign /fd sha256 /tr http://timestamp.digicert.com /td sha256 /a "dist\installer\Attendance Manager Setup.exe"
```

Sign `AttendanceManager.exe` **before** compiling the installer (run the Inno Setup step again
after signing) so that the installed executable is signed too. Keep certificates and private keys
out of the repository (`*.pfx`, `*.p12`, `*.pem` and `*.key` are ignored).

### Antivirus false positives

Some antivirus products flag PyInstaller's windowed launcher heuristically. For example, 360 Total
Security reported `Win64/Heur.Generic.H8oACBEA` on
`PyInstaller\bootloader\Windows-64bit-intel\runw.exe`. The build then fails with *"PyInstaller does
not include a pre-compiled bootloader"* because the file was deleted.

Do **not** modify or disguise the launcher to get past the scanner. Instead:

1. let the build machine's antivirus trust the project folder, or pause it for the duration of the
   build, then run `build.bat` again;
2. restore the quarantined file as trusted if needed (`pip install --force-reinstall --no-deps
   pyinstaller==<pinned version>` in `.venv-build` restores it);
3. sign the release binaries (above) and report the false positive to the vendor.

## 5. Publish

1. Commit the version bump and changelog, then tag the release:

   ```bash
   git tag -a v1.0.0 -m "Attendance Manager 1.0.0"
   git push origin main --tags
   ```

2. On GitHub, create a **Release** from the tag, paste the changelog entry, and attach
   `Attendance Manager Setup.exe` as a release asset. Publishing a SHA-256 checksum is
   recommended:

   ```powershell
   Get-FileHash "dist\installer\Attendance Manager Setup.exe" -Algorithm SHA256
   ```
