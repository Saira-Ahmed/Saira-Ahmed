#!/usr/bin/env python3
"""
Robust streak updater:
- Fetches contribution calendar via GraphQL
- Fills missing days
- Computes current streak, longest streak, active days
- Writes streak.svg (fallback on error)
"""
import os
import sys
import argparse
import requests
import datetime
from collections import OrderedDict

GITHUB_API = "https://api.github.com/graphql"

QUERY = """
query($login:String!, $from:DateTime!, $to:DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        weeks {
          contributionDays {
            date
            contributionCount
          }
        }
      }
    }
  }
}
"""

SVG_TEMPLATE = """<svg xmlns="http://www.w3.org/2000/svg" width="720" height="160" viewBox="0 0 720 160" role="img" aria-label="GitHub streak card">
  <defs>
    <style>
      .bg{{fill:#0D1117}}
      .card{{fill:#071224;stroke:#0f172a;stroke-width:1;rx:12}}
      .title{{font:700 18px/1.1 'Segoe UI', Roboto, Arial;fill:#39C5FF}}
      .label{{font:600 12px/1.1 'Segoe UI', Roboto, Arial;fill:#9BE7C4}}
      .value{{font:700 28px/1.1 'Segoe UI', Roboto, Arial;fill:#ffffff}}
      .muted{{font:400 11px/1.1 'Segoe UI', Roboto, Arial;fill:#94a3b8}}
      .pill{{fill:#06202a;rx:8}}
      .small{{font:400 11px/1.1 'Segoe UI', Roboto, Arial;fill:#9be7c4}}
    </style>
  </defs>

  <rect width="720" height="160" class="bg" rx="12"/>

  <g transform="translate(20,16)">
    <rect x="0" y="0" width="680" height="128" class="card" rx="12"/>
    <text x="20" y="30" class="title">GitHub Streak — @{username}</text>
    <text x="20" y="48" class="muted">Updated: {updated}</text>

    <!-- Current streak -->
    <g transform="translate(24,62)">
      <rect width="240" height="50" class="pill" />
      <text x="16" y="20" class="label">Current Streak</text>
      <text x="16" y="42" class="value" id="current">{current_streak}d</text>
    </g>

    <!-- Longest streak -->
    <g transform="translate(288,62)">
      <rect width="240" height="50" class="pill" />
      <text x="16" y="20" class="label">Longest Streak</text>
      <text x="16" y="42" class="value" id="longest">{longest_streak}d</text>
    </g>

    <!-- Small stats on the right -->
    <g transform="translate(552,62)">
      <rect width="128" height="50" class="pill" />
      <text x="16" y="20" class="label">Active Days (365d)</text>
      <text x="16" y="42" class="value" id="total">{active_days}</text>
    </g>

    <text x="20" y="126" class="muted">{footer_text}</text>
  </g>
</svg>
"""

def iso_z(dt: datetime.datetime):
    return dt.replace(microsecond=0).isoformat() + "Z"

def fetch_contributions(login, token, days=365):
    to_dt = datetime.datetime.utcnow()
    from_dt = to_dt - datetime.timedelta(days=days)
    variables = {
        "login": login,
        "from": iso_z(from_dt),
        "to": iso_z(to_dt)
    }
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.post(GITHUB_API, json={"query": QUERY, "variables": variables}, headers=headers, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"GitHub API returned {resp.status_code}: {resp.text}")
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(f"GitHub API errors: {data['errors']}")
    weeks = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    days_list = []
    for w in weeks:
        for d in w["contributionDays"]:
            days_list.append({"date": d["date"], "count": d["contributionCount"]})
    days_list.sort(key=lambda x: x["date"])
    return days_list, from_dt.date(), to_dt.date()

def fill_missing_days(days_list, from_date, to_date):
    day_map = OrderedDict()
    for d in days_list:
        day_map[datetime.date.fromisoformat(d["date"])] = d["count"]
    cur = from_date
    while cur <= to_date:
        if cur not in day_map:
            day_map[cur] = 0
        cur = cur + datetime.timedelta(days=1)
    ordered = OrderedDict(sorted(day_map.items()))
    return ordered

def compute_streaks_from_map(day_map):
    active_days = sum(1 for c in day_map.values() if c > 0)
    longest = 0
    current = 0
    for count in day_map.values():
        if count > 0:
            current += 1
            if current > longest:
                longest = current
        else:
            current = 0
    today = datetime.date.today()
    cur_streak = 0
    day = today
    while day in day_map:
        if day_map[day] > 0:
            cur_streak += 1
        else:
            break
        day = day - datetime.timedelta(days=1)
    return cur_streak, longest, active_days

def write_svg(path, username, current_streak, longest_streak, active_days, footer_text):
    updated = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    svg = SVG_TEMPLATE.format(
        username=username,
        updated=updated,
        current_streak=current_streak,
        longest_streak=longest_streak,
        active_days=active_days,
        footer_text=footer_text.replace("&","&amp;")
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", required=True)
    parser.add_argument("--output", default="streak.svg")
    parser.add_argument("--days", type=int, default=365)
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        write_svg(args.output, args.username, 0, 0, 0, "Error: GITHUB_TOKEN missing in environment")
        print("GITHUB_TOKEN not found", file=sys.stderr)
        sys.exit(1)

    try:
        days_list, from_date, to_date = fetch_contributions(args.username, token, days=args.days)
        day_map = fill_missing_days(days_list, from_date, to_date)
        current_streak, longest_streak, active_days = compute_streaks_from_map(day_map)
        write_svg(args.output, args.username, current_streak, longest_streak, active_days, "Tip: this file is updated automatically by a GitHub Action (GraphQL)")
        print(f"Wrote {args.output}: current={current_streak}, longest={longest_streak}, active_days={active_days}")
    except Exception as e:
        err_msg = f"Error fetching contributions: {str(e)}"
        print(err_msg, file=sys.stderr)
        write_svg(args.output, args.username, 0, 0, 0, err_msg)
        sys.exit(1)

if __name__ == "__main__":
    main()
