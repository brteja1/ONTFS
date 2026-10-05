# Changelog

## Unreleased

- Contradiction reports now include only predicates declared as
  `owl:FunctionalProperty`. Existing multi-valued properties no longer produce
  contradiction reports by default; declare single-valued relations as
  functional to opt in.
- Local file identifiers are moving to graph-relative `ontfs:file/...` URIs.
  Existing graphs should be converted with `ontfs migrate-uris` after reviewing
  `ontfs migrate-uris --dry-run`.
- Added entity lifecycle, Boolean hierarchical tag selection, optional SHACL
  validation, multi-evidence fact history, and budgeted pointer-only recall.
- Vector search now has a persistent content-addressed cache, optional
  Sentence Transformers backend, explicit `--hashed` name, and watcher
  invalidation; `--vector` remains compatible.
