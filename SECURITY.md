# Security Policy

## Reporting a vulnerability
Please do not open a public issue. Use GitHub's private reporting instead:
**Security tab → Report a vulnerability**. I aim to respond within 7 days.

## Practices in this repository
- No secrets in code: configuration comes from environment variables; `.env` files are git-ignored.
- Pre-commit hooks (gitleaks, detect-private-key) block secrets before they are committed.
- CI runs Bandit (static security analysis), pip-audit (vulnerable dependencies),
  CodeQL and Gitleaks on every push.
- Dependabot opens weekly pull requests for dependency and GitHub Actions updates.
- All data is synthetic; no personal data is stored in this repository.
- SQL uses parameterized queries only; API inputs are validated with strict schemas.
- Model files are verified by SHA-256 checksum before loading.
