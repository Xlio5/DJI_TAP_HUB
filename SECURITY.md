# Security Policy

## Supported Version

Security fixes are applied to the current `main` branch. This project does not currently maintain parallel security-supported release branches.

## Reporting a Vulnerability

Do not publish credentials, private keys, device identifiers, or an exploitable report in a public issue.

Use GitHub private vulnerability reporting when it is enabled for the repository. If it is not available, contact the maintainer through a private channel listed on the repository owner's GitHub profile and include:

- affected commit or version;
- required Android/Linux privileges and network position;
- minimal reproduction steps;
- impact and any known mitigation.

The maintainer will acknowledge receipt when available, validate the report, and coordinate disclosure after a fix. This community project does not promise a fixed response SLA.

## Deployment Assumptions

- Network ADB is restricted to a trusted management link.
- The Linux HTTP API is not exposed to an untrusted LAN or the internet.
- Device scripts run only on an intended, recoverable target.
- Android VPN, USB, accessibility, and Shizuku permissions are granted knowingly by the device owner.
