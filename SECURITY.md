# Security Policy

## Reporting a Vulnerability

Please **do not** open a public issue for security vulnerabilities.

Instead, report them privately via
[GitHub private vulnerability reporting](https://github.com/Andres-3DArtist/wled_hyperion_bridge/security/advisories/new)
or by opening an issue with minimal details and asking for a private contact.

Include if possible:

- Integration version and Home Assistant version
- What you expected vs. what happened
- Logs with secrets redacted (tokens, internal hostnames)

## Scope Notes

- Hyperion API tokens are stored in Home Assistant's config entry storage
  (never in this repository) and are redacted from diagnostics output.
- This integration talks to WLED and Hyperion over the local network in
  plain HTTP/TCP by default. Do not expose those device ports to untrusted
  networks.
