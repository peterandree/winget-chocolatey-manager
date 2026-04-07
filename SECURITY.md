# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.3.x   | :white_check_mark: |
| 1.2.x   | :white_check_mark: |
| < 1.2   | :x:                |

## Deprecation Notice

`register_unmanaged_apps.py` (the root-level script) is **deprecated** as of
v1.3.0 and will be removed in v2.0.0. Please migrate to the `wincoman` CLI:

```powershell
# Old (deprecated)
python register_unmanaged_apps.py --dry-run

# New
uv run wincoman --dry-run
```

## Reporting a Vulnerability

To report a security vulnerability, please open a private security advisory
at https://github.com/peterandree/winget-chocolatey-manager/security/advisories/new.

You can expect an acknowledgement within 3 business days. Accepted
vulnerabilities will be patched in a new minor or patch release.
