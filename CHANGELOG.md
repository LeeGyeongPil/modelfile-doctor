# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-11-12

### Added
- Modelfile checks: encoding (UTF-8/BOM/UTF-16), instructions, PARAMETER names/types/ranges, MESSAGE roles, duplicate TEMPLATE/SYSTEM, stop values, FROM paths (MF rules).
- Go `text/template` structure checks: delimiters, block balance, Jinja leftovers, unknown variables (TP rules).
- Dependency-free GGUF key/value reader (v2/v3) that never reads tensor data.
- Comparison of TEMPLATE/stop/num_ctx with GGUF metadata (CT rules), also for model names through a local Ollama server (`--ollama`).
- Text and JSON output, exit codes 0/1/2, `--strict`, `--select`, `--ignore`, `--list-rules`.
- English and Korean output (`--lang`, `MODELFILE_DOCTOR_LANG`, `LC_ALL`/`LC_MESSAGES`/`LANG`).
- `demo` command (synthetic GGUF without weights) and `inspect` command.
