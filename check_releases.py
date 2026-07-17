import json
import os
import sys
import requests

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


def get_endoflife_cycles(slug):
    resp = requests.get(f"https://endoflife.date/api/{slug}.json", timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if slug == "ubuntu":
        # LTS only
        return [e["cycle"] for e in data if e.get("lts")]
    if slug == "windows-server":
        # LTSC only — year-based cycles like 2019, 2022, 2025; skip SAC (23h2-ac, 20h2-sac etc.)
        return [e["cycle"] for e in data if e["cycle"].isdigit()]
    if slug == "freebsd":
        # Only major versions >= 13 (minor point releases tracked separately are noise)
        result = []
        for e in data:
            cycle = e["cycle"]
            try:
                major = int(cycle.split(".")[0])
                if major >= 13:
                    result.append(cycle)
            except ValueError:
                pass
        return result
    return [e["cycle"] for e in data]



def post_to_slack(webhook_url, releases):
    lines = "\n".join(f"• {r}" for r in releases)
    payload = {"text": f":new: *New OS releases detected:*\n{lines}"}
    resp = requests.post(webhook_url, json=payload, timeout=10)
    resp.raise_for_status()


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True)


def main():
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        print("SLACK_WEBHOOK_URL not set", file=sys.stderr)
        sys.exit(1)

    state = load_state()
    new_releases = []

    for vendor_key, slug in ENDOFLIFE_VENDORS.items():
        try:
            cycles = get_endoflife_cycles(slug)
        except Exception as e:
            print(f"[{vendor_key}] fetch error: {e}", file=sys.stderr)
            continue

        known = set(state.get(vendor_key, []))
        fresh = [c for c in cycles if c not in known]
        if fresh:
            if vendor_key == "freebsd":
                # Deduplicate by major version — report "9" not "9.0", "9.1"
                seen_majors = set()
                for cycle in fresh:
                    major = cycle.split(".")[0]
                    if major not in seen_majors:
                        seen_majors.add(major)
                        new_releases.append(f"*{vendor_key}* {major}")
            else:
                for cycle in fresh:
                    new_releases.append(f"*{vendor_key}* {cycle}")
        state[vendor_key] = cycles

    save_state(state)

    if new_releases:
        post_to_slack(webhook_url, new_releases)
        print(f"Posted {len(new_releases)} new release(s) to Slack")
        for r in new_releases:
            print(f"  {r}")
    else:
        print("No new releases")


if __name__ == "__main__":
    main()
