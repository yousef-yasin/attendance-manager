# Real fixtures (not committed)

Put the real exported files here to run the real-data tests:

- `00.xls` (or `0.xls`) — master student list
- `11.xls`, `22.xls`, `33.xls`, `44.xls` — weekly Microsoft Teams attendance reports

They contain student names and IDs, so this folder is ignored by git. The tests
that need them are skipped automatically when the files are absent; the
synthetic fixtures in `../synthetic` reproduce the same formats.
