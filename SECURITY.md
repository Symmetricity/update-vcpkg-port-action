# Security Policy

Thanks for helping keep this GitHub Action and its users safe.

## Supported Versions

Security fixes are made for the latest `v1` release line. Consumers should use
`Symmetricity/update-vcpkg-port-action@v1` for the latest backward-compatible
release, or pin to a full commit SHA for stricter reproducibility.

## Reporting a Vulnerability

Do not report security vulnerabilities through public GitHub issues,
discussions, or pull requests.

Use GitHub private vulnerability reporting for this repository if it is
available. If private reporting is unavailable, open a minimal public issue
asking for a private security contact, but do not include exploit details,
secrets, tokens, logs containing credentials, or proof-of-concept payloads.

Include as much of the following information as possible in the private report:

- The affected action version, tag, or commit SHA
- The affected workflow permissions and event trigger
- Whether the workflow runs on hosted or self-hosted runners
- The relevant `with:` inputs and vcpkg triplet
- Steps to reproduce the issue
- Expected and actual behavior
- Potential impact, including whether secrets, repository contents, generated
  port files, or vcpkg fork branches may be affected
- Any proof of concept or logs, with secrets removed

Reports are triaged as time permits. Valid reports will be handled with
coordinated disclosure and a fix release when appropriate.
