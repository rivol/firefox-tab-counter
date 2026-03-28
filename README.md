# firefox-tab-counter

A single-file Python script that counts your open Firefox tabs by reading the session recovery file.

## Output

**Human-readable (default):**

```
Tabs:    142 (5 pinned)
Windows: 3 (52, 38, 52)
```

**InfluxDB line protocol (`--influx`):**

```
firefox_tabs tabs=142i,windows=3i,pinned=5i
```

## Usage

```sh
# Human-readable output
./tab_count.py

# InfluxDB line protocol
./tab_count.py --influx

# Explicit Firefox profile directory
./tab_count.py --profile ~/.mozilla/firefox/abc123.default
```

Requires [uv](https://docs.astral.sh/uv/). Dependencies (`lz4`) are managed automatically via inline script metadata -- no install step needed.

## Telegraf setup

Add an `exec` input to your Telegraf config:

```toml
[[inputs.exec]]
  commands = ["/path/to/tab_count.py --influx"]
  interval = "10m"
  timeout = "30s"
  data_format = "influx"
```

The first run may take longer as uv installs the `lz4` dependency. Subsequent runs are fast (~0.2s) since uv caches the environment.

This produces the `firefox_tabs` measurement with three fields:

| Field     | Type    | Description                |
|-----------|---------|----------------------------|
| `tabs`    | integer | Total open tabs            |
| `windows` | integer | Number of browser windows  |
| `pinned`  | integer | Number of pinned tabs      |

## How it works

Firefox periodically (~every 15s) writes its full session state to `sessionstore-backups/recovery.jsonlz4` inside the active profile directory. This is a JSON file compressed with Mozilla's `mozlz4` format (LZ4 block compression with an 8-byte magic header).

The script:

1. **Locates the profile** by parsing `profiles.ini` from known Firefox directories (snap, native Linux, macOS), or uses an explicit `--profile` path.
2. **Reads `recovery.jsonlz4`** -- skips the 8-byte header, decompresses with `lz4.block`, parses the JSON.
3. **Counts tabs** per window, including pinned tabs, and outputs the result.

Profile search order:
- `~/snap/firefox/common/.mozilla/firefox/` (Linux snap)
- `~/.mozilla/firefox/` (Linux native)
- `~/Library/Application Support/Firefox/` (macOS)
