# CANViewer

Interactive CAN bus signal explorer. Decode a log against a DBC, drag signals into frames, and inspect them as **discrete samples**, so gaps in a signal's reporting stay visible instead of being bridged by a line.

> Not affiliated with Vector's CANape.

## Install and run

Requires [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`); it fetches Python 3.11/3.12 and all dependencies for you.

```sh
git clone https://github.com/sushmit-dutta/CANViewer.git
cd CANViewer
uv sync
uv run canviewer --file capture.mf4 --dbc vehicle.dbc
```

Opens `http://127.0.0.1:8765`. Works offline.

| Flag | Default | Description |
|------|---------|-------------|
| `--file`, `-f` | required | `.mf4`, or `.asc`/`.blf`/`.trc` (converted to `.mf4`, cached) |
| `--dbc`, `-d` | required (`$CANVIEWER_DBC`) | DBC used to decode the log |
| `--tz` | `UTC` (`$CANVIEWER_TZ`) | IANA timezone for displayed times |
| `--host` / `--port` | `127.0.0.1` / `8765` | Bind address; there is no authentication, keep it local |
| `--cache-dir` | `~/.canviewer-cache` | Converted-log cache |
| `--title`, `--no-browser` | | Navbar title; don't open a browser |

## UI

- **Search**: several words must all match, in any order, case and `_` ignored. Searches signal, message, sender node, unit, DBC comment and CAN ID (`0x1a4` matches that ID's prefix). `*`/`?` wildcards; fuzzy fallback when nothing matches.
- **Frames**: drag signals or whole messages onto any frame card. Reorder with the `⠿` grip, resize by dragging the bottom bar. Size and zoom survive adding or removing frames.
- **Zoom** is shared across frames.
- **Legend**: click to hide/show a signal. `×` on a chip removes it.
- **Cursors**: `⊕ Cursor`, then click a plot (or press `.` at the pointer). Readouts show each signal's last sample at or before the cursor, with its age when older than 1 s. Panels are draggable.
- **Export HTML** writes the frames, cursors and values as a standalone report.

## Timestamps

Timestamps above 1e8 s are treated as absolute Unix time; smaller ones are relative to the MDF header start time.

## Development

```sh
uv run pytest
```
