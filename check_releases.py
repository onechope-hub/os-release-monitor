import datetime
import json
import os
import sys
import urllib.request

ENDOFLIFE_VENDORS = {
    "ubuntu": "ubuntu",
    "debian": "debian",
    "rocky-linux": "rocky-linux",
    "almalinux": "almalinux",
    "centos-stream": "centos-stream",
    "windows-server": "windows-server",
    "proxmox-ve": "proxmox-ve",
    "freebsd": "freebsd",
}

STATE_FILE = "state.json"
EOL_DATA_FILE = "eol_data.json"
EOL_REPORT_FILE = "eol_data.md"
ENDOFLIFE_API_BASE = "https://endoflife.date/api"


def fetch_cycles(slug):
    req = urllib.request.Request(f"{ENDOFLIFE_API_BASE}/{slug}.json")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.load(resp)


def filter_cycles(slug, data):
    """Apply the per-vendor tracking rules and return the subset of cycle entries we care about."""
    if slug == "ubuntu":
        # LTS only
        return [e for e in data if e.get("lts")]
    if slug == "windows-server":
        # LTSC only, per the vendor's own lts flag (mirrors the ubuntu filter above)
        return [e for e in data if e.get("lts")]
    if slug == "freebsd":
        # Only major versions >= 13 (minor point releases tracked separately are noise)
        result = []
        for e in data:
            cycle = e["cycle"]
            try:
                major = int(cycle.split(".")[0])
                if major >= 13:
                    result.append(e)
            except ValueError:
                print(f"[freebsd] skipping unparsable cycle: {cycle!r}", file=sys.stderr)
        return result
    return list(data)


def get_endoflife_cycles(entries):
    return [e["cycle"] for e in entries]


def build_eol_records(entries):
    today = datetime.date.today()
    records = []
    for e in entries:
        eol = e.get("eol")
        is_eol = False
        days_until_eol = None
        if eol is True:
            is_eol = True
        elif isinstance(eol, str):
            try:
                eol_date = datetime.date.fromisoformat(eol)
                days_until_eol = (eol_date - today).days
                is_eol = eol_date <= today
            except ValueError:
                print(f"unparsable eol date: {eol!r}", file=sys.stderr)
        records.append(
            {
                "cycle": e["cycle"],
                "release_date": e.get("releaseDate"),
                "latest": e.get("latest"),
                "support": e.get("support"),
                "eol": eol,
                "is_eol": is_eol,
                "days_until_eol": days_until_eol,
            }
        )
    return records


def post_to_slack(webhook_url, releases):
    if os.environ.get("GITHUB_ACTIONS") != "true":
        # Avoid spamming the real channel from a local test run — only GitHub Actions
        # (or DRY_RUN=true, checked by the caller) should ever post for real.
        print("Not running in GitHub Actions, skipping Slack post", file=sys.stderr)
        return

    lines = "\n".join(f"• {r}" for r in releases)
    payload = {"text": f":new: *New OS releases detected:*\n{lines}"}
    req = urllib.request.Request(
        webhook_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10):
        pass


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True)


def load_eol_data():
    if os.path.exists(EOL_DATA_FILE):
        with open(EOL_DATA_FILE) as f:
            return json.load(f)
    return {"generated_at": None, "vendors": {}}


def save_eol_data(eol_data):
    with open(EOL_DATA_FILE, "w") as f:
        json.dump(eol_data, f, indent=2, sort_keys=True)


def _format_flexible_date(value):
    """Render an endoflife.date-style field (an ISO date, `true`, `false`, or absent)."""
    if isinstance(value, str):
        return value
    if value is True:
        return "Yes"
    return "—"


def _format_days_until_eol(days):
    if days is None:
        return "—"
    if days < 0:
        return f"{-days} days ago"
    return str(days)


def render_markdown_report(eol_data):
    """Render the collected EOL data as a human-readable Markdown report."""
    lines = ["# OS End-of-Life Report", ""]
    generated_at = eol_data.get("generated_at")
    if generated_at:
        lines.append(f"_Generated: {generated_at}_")
        lines.append("")
    lines.append(
        "Full machine-readable data: [`eol_data.json`](eol_data.json). "
        "Regenerated on every scheduled run."
    )
    lines.append("")

    vendors = eol_data.get("vendors", {})
    for vendor_key in sorted(vendors):
        lines.append(f"## {vendor_key}")
        lines.append("")
        lines.append("| Cycle | Release date | Latest | Support until | EOL | Status | Days until EOL |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- |")
        for record in vendors[vendor_key]:
            status = "🔴 EOL" if record.get("is_eol") else "🟢 Supported"
            lines.append(
                "| {cycle} | {release_date} | {latest} | {support} | {eol} | {status} | {days} |".format(
                    cycle=record.get("cycle", "—"),
                    release_date=record.get("release_date") or "—",
                    latest=record.get("latest") or "—",
                    support=_format_flexible_date(record.get("support")),
                    eol=_format_flexible_date(record.get("eol")),
                    status=status,
                    days=_format_days_until_eol(record.get("days_until_eol")),
                )
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def save_eol_report(eol_data):
    with open(EOL_REPORT_FILE, "w") as f:
        f.write(render_markdown_report(eol_data))


def is_dry_run():
    """True when the Slack notification should be skipped, e.g. for local testing
    without a webhook. git commit/push (state.json/eol_data.json/eol_data.md) is
    handled entirely by the GitHub Actions workflow, not by this script."""
    return os.environ.get("DRY_RUN") == "true"


def main():
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    dry_run = is_dry_run()
    if not webhook_url and not dry_run:
        print("SLACK_WEBHOOK_URL not set", file=sys.stderr)
        sys.exit(1)

    state = load_state()
    eol_data = load_eol_data()
    vendors_eol = eol_data.get("vendors", {})
    new_releases = []
    fetch_errors = []

    for vendor_key, slug in ENDOFLIFE_VENDORS.items():
        try:
            data = fetch_cycles(slug)
        except Exception as e:
            print(f"[{vendor_key}] fetch error: {e}", file=sys.stderr)
            fetch_errors.append(vendor_key)
            continue

        entries = filter_cycles(slug, data)
        cycles = get_endoflife_cycles(entries)

        known_list = state.get(vendor_key, [])
        if not cycles and known_list:
            print(f"[{vendor_key}] API returned an empty cycle list, keeping previous state", file=sys.stderr)
            continue

        known = set(known_list)
        fresh = [c for c in cycles if c not in known]
        if fresh:
            if vendor_key == "freebsd":
                # Seed from already-known majors so a routine point release of an
                # already-announced major (e.g. "13.6" after "13.5") never re-alerts.
                seen_majors = {c.split(".")[0] for c in known}
                for cycle in fresh:
                    major = cycle.split(".")[0]
                    if major not in seen_majors:
                        seen_majors.add(major)
                        new_releases.append(f"*{vendor_key}* {major}")
            else:
                for cycle in fresh:
                    new_releases.append(f"*{vendor_key}* {cycle}")
        state[vendor_key] = cycles
        vendors_eol[vendor_key] = build_eol_records(entries)

    if new_releases:
        if dry_run:
            print(f"Dry run, skipping Slack notification for {len(new_releases)} release(s)")
        else:
            post_to_slack(webhook_url, new_releases)
            print(f"Posted {len(new_releases)} new release(s) to Slack")
        for r in new_releases:
            print(f"  {r}")
    else:
        print("No new releases")

    save_state(state)
    eol_data["vendors"] = vendors_eol
    eol_data["generated_at"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    save_eol_data(eol_data)
    save_eol_report(eol_data)

    if fetch_errors:
        # Data for the failed vendor(s) is still whatever was last known (state/eol_data are
        # only overwritten on success), and any vendors that did succeed were already
        # committed above — but the run as a whole must fail so the pipeline surfaces that
        # endoflife.date couldn't be reached for some vendors instead of going unnoticed.
        print(f"Failed to fetch data for: {', '.join(fetch_errors)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
