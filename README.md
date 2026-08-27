# os-release-monitor

A small daily job that watches for new OS releases and posts them to Slack.

## What it does

[`check_releases.py`](check_releases.py) queries the [endoflife.date](https://endoflife.date) API for a fixed set of vendors, and on every run:

1. Fetches the current release cycles per vendor, with vendor-specific filtering (see [Tracked vendors](#tracked-vendors) below).
2. Compares them against previously seen cycles (`state.json`) and posts a Slack message for any newly detected release.
3. Regenerates a full end-of-life dataset for every tracked cycle — both machine-readable (`eol_data.json`) and a human-readable Markdown report (`eol_data.md`) — regardless of whether anything new was found.

If a vendor's fetch fails, the other vendors are still processed and saved, but the run exits non-zero at the end so the failure is visible instead of silently keeping stale data.

Only the standard library is used (`urllib`), so no dependency installation step is needed.

## Tracked vendors

| Vendor | endoflife.date slug | Filtering rule |
| --- | --- | --- |
| Ubuntu | `ubuntu` | LTS releases only |
| Debian | `debian` | All cycles |
| Rocky Linux | `rocky-linux` | All cycles |
| AlmaLinux | `almalinux` | All cycles |
| CentOS Stream | `centos-stream` | All cycles |
| Windows Server | `windows-server` | LTSC releases only |
| Proxmox VE | `proxmox-ve` | All cycles |
| FreeBSD | `freebsd` | Major versions ≥ 13 (point releases collapsed to their major) |

Add or adjust vendors in `ENDOFLIFE_VENDORS`, and their filtering rules in `filter_cycles()`.

## Data files

- **`state.json`** — internal dedupe cache of known cycle names per vendor, used only to detect new releases. Not meant for external consumption.
- **`eol_data.json`** — the full end-of-life dataset for every tracked cycle: release date, latest point release, support/EOL dates, and days until/since EOL.
- **`eol_data.md`** — the same data rendered as a Markdown report (one table per vendor), meant as a quick-glance human view. Renders directly in GitHub's file browser.

Both files are regenerated and committed on every scheduled run (see [`.github/workflows/monitor.yml`](.github/workflows/monitor.yml)).

## Running it yourself

Fork this repo, then:

1. Create a [Slack Incoming Webhook](https://api.slack.com/messaging/webhooks) and add its URL as a repository secret named `SLACK_WEBHOOK_URL` (Settings → Secrets and variables → Actions).
2. The workflow runs daily at 09:00 UTC via a GitHub Actions schedule, and can also be triggered manually from the Actions tab.

### Running locally

Requires Python 3.9+, no extra dependencies:

```bash
SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..." python3 check_releases.py
```

Set `DRY_RUN=true` to skip the Slack post entirely and print any detected releases to stdout instead — useful for testing without a webhook. `state.json`, `eol_data.json`, and `eol_data.md` are still generated normally.

## License

MIT — see [LICENSE](LICENSE).
