# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [1.02] - 2026-10-22

### Added
- Environments: pick a predefined connection (Schema Registry URL, broker, mTLS, certificate paths, default topic/group) from the new Environment selector, or keep typing values yourself with `(custom)`. Definitions are JSON files in `./profiles`.
- The selected environment is re-applied on start; with `(custom)` the last entered values are restored.

## [1.01] - 2026-10-22

### Added
- Persistent settings: form values, theme and window geometry are saved to `settings.json` and restored on restart (#3).
- Installation instructions in the README (#4).

### Changed
- Application version is now defined in one place (`APP_VERSION`).

## [1.0]

### Added
- Initial release: Schema Registry loading, Avro payload randomizer, topic reading and writing, (m)TLS support.

### Fixed
- Schema panel is re-rendered after switching theme (#1).
