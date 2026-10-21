# Contributing

Thank you for improving TUN NAT Hub. Changes to this project can affect privileged networking and physical RC output, so keep patches focused and make behavior observable.

## Before Opening a Change

1. Search existing issues and describe the hardware, Android version, Linux target, and RC input mode involved.
2. Separate reproducible defects from device-specific deployment questions.
3. Never attach ADB keys, SSH keys, credentials, firmware dumps, packet captures containing private traffic, or proprietary third-party applications.

## Development Checks

For Android changes, use JDK 17 and run:

```powershell
./scripts/build-android.ps1
```

For Linux/C++ changes, run:

```sh
./scripts/build-linux.sh
```

For every change, run:

```sh
python3 scripts/check-public-tree.py .
```

Add focused tests for protocol parsing, source ownership, freshness windows, and state transitions. Hardware-only changes should include the diagnostic counters or logs used to verify them and a description of the tested device setup.

## Commit and Review Style

- Use focused commits such as `feat(android): ...`, `fix(ubuntu): ...`, or `docs: ...`.
- Keep generated artifacts and local paths out of commits.
- Update both endpoints and protocol documentation when changing a wire format.
- Explain safety implications for TUN, NAT, ADB, USB permissions, or RC output.

By contributing, you agree that your contribution may be distributed under `GPL-3.0-only` and that you have the right to submit it. No Developer Certificate of Origin sign-off is currently required.
