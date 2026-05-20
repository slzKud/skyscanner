#!/usr/bin/env python3
"""
Flight Search - SkyScanner flight price search with HTML results.
"""

import argparse
import datetime
import json
import os
import sys
import webbrowser
from dataclasses import dataclass
from typing import Optional

import requests

from skyscanner.types import CabinClass
from skyscanner import SkyScanner


CABIN_MAP = {
    "economy": CabinClass.ECONOMY,
    "premium_economy": CabinClass.PREMIUM_ECONOMY,
    "business": CabinClass.BUSINESS,
    "first": CabinClass.FIRST,
}

LOGO_DIR = "logos"
LOGO_URL = "https://logos.skyscnr.com/images/airlines/favicon/{code}.png"


def collect_airline_codes(data: dict) -> set:
    """Collect unique airline codes from search results."""
    codes = set()
    for bucket in data["itineraries"]["buckets"]:
        for item in bucket["items"]:
            for leg in item["legs"]:
                for seg in leg.get("segments", []):
                    mc = seg.get("marketingCarrier", {})
                    code = mc.get("alternateId") or mc.get("displayCode")
                    if code:
                        codes.add(code)
                    oc = seg.get("operatingCarrier", {})
                    code = oc.get("alternateId") or oc.get("displayCode")
                    if code:
                        codes.add(code)
    return codes


def download_logos(codes: set, base_dir: str = LOGO_DIR) -> dict[str, str]:
    """Download airline logos, return {code: local_path}."""
    os.makedirs(base_dir, exist_ok=True)
    paths = {}
    headers = {"User-Agent": "Mozilla/5.0"}
    for code in sorted(codes):
        local = os.path.join(base_dir, f"{code}.png")
        paths[code] = local
        if os.path.exists(local):
            continue
        url = LOGO_URL.format(code=code)
        try:
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image/"):
                with open(local, "wb") as f:
                    f.write(r.content)
                print(f"  Logo cached: {code}")
            else:
                print(f"  Logo not found: {code} (HTTP {r.status_code})")
        except Exception as e:
            print(f"  Logo error {code}: {e}")
    return paths


@dataclass
class SearchConfig:
    origin: str
    destination: str
    depart_date: str
    return_date: str
    adults: int = 1
    child_ages: list = None
    cabin_class: CabinClass = CabinClass.ECONOMY
    output: str = "prices.html"


def parse_args():
    parser = argparse.ArgumentParser(description="Search flight prices and generate HTML report")
    parser.add_argument("--from", dest="origin", help="Origin airport code (e.g. JFK)")
    parser.add_argument("--to", dest="destination", help="Destination airport code (e.g. LHR)")
    parser.add_argument("--depart", help="Departure date (YYYY-MM-DD)")
    parser.add_argument("--return", dest="return_date", help="Return date (YYYY-MM-DD)")
    parser.add_argument("--adults", type=int, default=1, help="Number of adults (default: 1)")
    parser.add_argument("--children", type=str, default="", help="Child ages comma-separated (e.g. 9,13)")
    parser.add_argument("--cabin", choices=list(CABIN_MAP.keys()), default="economy",
                        help="Cabin class (default: economy)")
    parser.add_argument("--output", default="prices.html", help="Output HTML file (default: prices.html)")
    parser.add_argument("--open", action=argparse.BooleanOptionalAction, default=True,
                        help="Open browser after generation (default: True)")
    parser.add_argument("--from-json", dest="from_json", type=str, default=None,
                        help="Generate HTML from saved JSON file instead of searching")
    return parser.parse_args()


def prompt_input():
    print("=== Flight Search ===\n")
    origin = input("Origin airport code (e.g. JFK): ").strip().upper()
    dest = input("Destination airport code (e.g. LHR): ").strip().upper()
    depart = input("Departure date (YYYY-MM-DD, e.g. 2026-08-20): ").strip()
    return_date = input("Return date (YYYY-MM-DD, e.g. 2026-08-25): ").strip()
    adults_str = input("Adults (default 1): ").strip()
    adults = int(adults_str) if adults_str else 1
    children_str = input("Child ages comma-separated (e.g. 9,13, leave blank for none): ").strip()
    print("\nCabin class:")
    for i, (key, val) in enumerate(CABIN_MAP.items(), 1):
        print(f"  {i}. {key.replace('_', ' ').title()}")
    cabin_choice = input("Select (1-4, default 1): ").strip()
    cabin = list(CABIN_MAP.values())[int(cabin_choice) - 1] if cabin_choice else CabinClass.ECONOMY
    return SearchConfig(
        origin=origin,
        destination=dest,
        depart_date=depart,
        return_date=return_date,
        adults=adults,
        child_ages=[int(a) for a in children_str.split(",") if a.strip()] if children_str else [],
        cabin_class=cabin,
    )


def validate_date(date_str: str) -> datetime.datetime:
    try:
        dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        if dt <= datetime.datetime.now():
            print(f"  Warning: date {date_str} is in the past. Results may be empty.")
        return dt
    except ValueError:
        print(f"  Error: invalid date '{date_str}'. Use YYYY-MM-DD format.")
        sys.exit(1)


def generate_html(data: dict, config: SearchConfig, logo_paths: dict[str, str] | None = None) -> str:
    itin = data["itineraries"]
    buckets = itin["buckets"]
    first_item = buckets[0]["items"][0]
    origin_name = first_item["legs"][0]["origin"]["name"]
    dest_name = first_item["legs"][0]["destination"]["name"]
    depart_dt = datetime.datetime.fromisoformat(first_item["legs"][0]["departure"])
    is_roundtrip = len(first_item["legs"]) > 1
    return_dt = datetime.datetime.fromisoformat(first_item["legs"][1]["departure"]) if is_roundtrip else None

    def leg_html(leg, label):
        carriers = leg.get("carriers", {})
        marketing = carriers.get("marketing", [])
        airline = marketing[0]["name"] if marketing else "Unknown"
        airline_code = marketing[0]["alternateId"] if marketing else ""
        dep = datetime.datetime.fromisoformat(leg["departure"])
        arr = datetime.datetime.fromisoformat(leg["arrival"])
        duration = leg["durationInMinutes"]
        stops = leg["stopCount"]
        segments = leg.get("segments", [])
        stop_text = "Direct" if stops == 0 else f"{stops} stop" + ("s" if stops > 1 else "")

        def logo_img(code, size=20):
            if not logo_paths or code not in logo_paths:
                return ""
            p = logo_paths[code]
            if not os.path.exists(p):
                return ""
            return f'<img class="alogo" src="../{p}" width="{size}" height="{size}" alt="{code}">'

        # Build segment details
        seg_html = ""
        for i, seg in enumerate(segments):
            seg_org = seg["origin"]["displayCode"]
            seg_dst = seg["destination"]["displayCode"]
            seg_dep = datetime.datetime.fromisoformat(seg["departure"])
            seg_arr = datetime.datetime.fromisoformat(seg["arrival"])
            seg_dur = seg["durationInMinutes"]
            seg_carrier = seg.get("marketingCarrier", {})
            sc = seg_carrier.get("alternateId") or seg_carrier.get("displayCode") or airline_code
            sn = seg_carrier.get("name", airline)
            fn = seg.get("flightNumber", "")
            seg_al = f"{sn} ({sc})" if sc != airline_code else airline

            seg_airline_tag = ""
            if sc != airline_code or fn:
                seg_airline_tag = f'<div class="seg-airline">{logo_img(sc)} {seg_al} <strong>{sc}{fn}</strong></div>'

            seg_html += f"""
              <div class="seg-row">
                <div class="seg-point">
                  <span class="time">{seg_dep.strftime('%H:%M')}</span>
                  <span class="code">{seg_org}</span>
                  <span class="date">{seg_dep.strftime('%b %d')}</span>
                </div>
                <div class="seg-line">
                  <div class="seg-dot"></div>
                  <div class="seg-bar"></div>
                  <div class="seg-dot"></div>
                  <div class="seg-time">{seg_dur // 60}h {seg_dur % 60}m</div>
                  {seg_airline_tag}
                </div>
                <div class="seg-point right">
                  <span class="time">{seg_arr.strftime('%H:%M')}</span>
                  <span class="code">{seg_dst}</span>
                  <span class="date">{seg_arr.strftime('%b %d')}</span>
                </div>
              </div>"""

            # Layover between segments
            if i < len(segments) - 1:
                next_seg = segments[i + 1]
                curr_arr = datetime.datetime.fromisoformat(seg["arrival"])
                next_dep = datetime.datetime.fromisoformat(next_seg["departure"])
                layover = int((next_dep - curr_arr).total_seconds() / 60)
                seg_html += f"""
              <div class="layover">
                <span class="layover-icon">&#9201;</span>
                Layover {seg_dst} &middot; {layover // 60}h {layover % 60}m
              </div>"""

        if stops == 0:
            fn = segments[0].get("flightNumber", "") if segments else ""
            leg_logo = logo_img(airline_code)
            return f"""
        <div class="leg">
          <div class="leg-header">{label}</div>
          <div class="leg-meta">{leg_logo} {airline} ({airline_code}) <strong class="fn">{airline_code}{fn}</strong></div>
          <div class="leg-times">
            <div class="leg-point">
              <span class="time">{dep.strftime('%H:%M')}</span>
              <span class="code">{leg['origin']['displayCode']}</span>
              <span class="date">{dep.strftime('%b %d')}</span>
            </div>
            <div class="leg-arrow">
              <div class="bar"></div>
              <span>{duration // 60}h {duration % 60}m</span>
              <span class="stops">{stop_text}</span>
            </div>
            <div class="leg-point right">
              <span class="time">{arr.strftime('%H:%M')}</span>
              <span class="code">{leg['destination']['displayCode']}</span>
              <span class="date">{arr.strftime('%b %d')}</span>
            </div>
          </div>
        </div>"""
        else:
            return f"""
        <div class="leg">
          <div class="leg-header">{label} &middot; {stop_text} &middot; {duration // 60}h {duration % 60}m total</div>
          <div class="seg-list">{seg_html}</div>
        </div>"""

    color_map = {"Best": "#2563eb", "Cheapest": "#059669", "Fastest": "#7c3aed", "Direct": "#d97706"}
    items_html = ""
    for bucket in buckets:
        color = color_map.get(bucket["id"], "#666")
        for item in bucket["items"]:
            items_html += f"""
        <div class="card" data-bucket="{bucket['id'].lower()}">
          <div class="card-header">
            <span class="tag" style="background:{color}">{bucket['id']}</span>
            <span class="price">{item['price']['formatted']}</span>
          </div>
          {leg_html(item['legs'][0], 'Departure')}
          {leg_html(item['legs'][1], 'Return') if len(item['legs']) > 1 else ''}
        </div>"""

    child_text = ""
    if config.child_ages:
        child_text = f" · {len(config.child_ages)} child(ren) ages {','.join(str(a) for a in config.child_ages)}"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{config.origin} → {config.destination} · Flight Search</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; background:#f1f5f9; color:#1e293b; padding:24px; }}
  .wrap {{ max-width:800px; margin:0 auto; }}
  h1 {{ font-size:24px; }}
  .sub {{ color:#64748b; font-size:14px; margin-bottom:20px; }}
  .filters {{ display:flex; gap:8px; margin-bottom:16px; flex-wrap:wrap; }}
  .filters button {{
    padding:6px 18px; border-radius:20px; border:1px solid #cbd5e1; background:#fff;
    cursor:pointer; font-size:13px; font-weight:500; transition:all .15s;
  }}
  .filters button:hover {{ border-color:#94a3b8; }}
  .filters button.on {{ background:#1e293b; color:#fff; border-color:#1e293b; }}
  .count {{ font-size:13px; color:#64748b; margin-bottom:16px; }}
  .card {{
    background:#fff; border-radius:12px; padding:20px; margin-bottom:16px;
    box-shadow:0 1px 3px rgba(0,0,0,.08); display:none;
  }}
  .card.show {{ display:block; }}
  .card-header {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:16px; }}
  .tag {{ font-size:11px; font-weight:700; color:#fff; padding:3px 12px; border-radius:12px; text-transform:uppercase; letter-spacing:.5px; }}
  .price {{ font-size:28px; font-weight:700; }}
  .leg {{ border-top:1px solid #e2e8f0; padding-top:14px; margin-top:14px; }}
  .leg:first-of-type {{ border-top:0; margin-top:0; }}
  .leg-header {{ font-size:12px; font-weight:600; color:#64748b; text-transform:uppercase; letter-spacing:.5px; margin-bottom:4px; }}
  .leg-meta {{ font-size:13px; color:#475569; margin-bottom:10px; }}
  .leg-times {{ display:flex; align-items:center; gap:16px; }}
  .leg-point {{ min-width:100px; }}
  .leg-point.right {{ text-align:right; flex:1; }}
  .time {{ font-size:22px; font-weight:600; display:block; }}
  .code {{ font-size:13px; color:#64748b; }}
  .date {{ font-size:11px; color:#94a3b8; }}
  .alogo {{ vertical-align:middle; margin-right:4px; border-radius:3px; }}
  .fn {{ font-weight:600; color:#1e293b; }}
  .leg-arrow {{ flex:1; text-align:center; font-size:12px; color:#64748b; }}
  .leg-arrow .bar {{ height:2px; background:#cbd5e1; margin:6px 0 4px; }}
  .stops {{ display:block; font-size:11px; color:#94a3b8; }}
  .seg-list {{ margin-top:10px; }}
  .seg-row {{ display:flex; align-items:center; gap:12px; margin-bottom:4px; }}
  .seg-point {{ min-width:90px; }}
  .seg-point.right {{ text-align:right; flex:1; }}
  .seg-line {{ flex:1; text-align:center; position:relative; padding:0 4px; }}
  .seg-dot {{ width:8px; height:8px; border-radius:50%; background:#94a3b8; display:inline-block; vertical-align:middle; }}
  .seg-bar {{ height:2px; background:#cbd5e1; flex:1; margin:0 4px; display:inline-block; vertical-align:middle; width:calc(100% - 40px); }}
  .seg-time {{ font-size:11px; color:#64748b; margin-top:2px; }}
  .seg-airline {{ font-size:10px; color:#94a3b8; margin-top:1px; }}
  .layover {{ font-size:12px; color:#d97706; background:#fffbeb; padding:5px 12px; border-radius:6px; margin:4px 0 8px 12px; display:inline-block; }}
  .layover-icon {{ margin-right:4px; }}
  @media(max-width:600px){{ .leg-times {{ flex-direction:column; gap:8px; }} .leg-point.right {{ text-align:center; }} .seg-row {{ flex-direction:column; gap:2px; }} .seg-point.right {{ text-align:center; }} }}
</style>
</head>
<body>
<div class="wrap">
  <h1>{config.origin} → {config.destination}</h1>
  <p class="sub">{origin_name} → {dest_name} · {depart_dt.strftime('%b %d')}{' – ' + return_dt.strftime('%b %d, %Y') if return_dt else ' (one-way)'} · {config.adults} adult(s){child_text} · {config.cabin_class.value.replace('_', ' ').title()}</p>

  <div class="filters">
    <button class="on" data-f="all">All</button>
    {"".join(f'<button data-f="{b["id"].lower()}">{b["id"]}</button>' for b in buckets)}
  </div>

  <p class="count"><span id="n">{sum(len(b["items"]) for b in buckets)}</span> flights found</p>
  <div id="cards">{items_html}</div>
</div>
<script>
  let f = 'all';
  document.querySelectorAll('.filters button').forEach(b => b.addEventListener('click',()=>{{
    document.querySelectorAll('.filters button').forEach(x=>x.classList.remove('on'));
    b.classList.add('on'); f=b.dataset.f; fl();
  }}));
  function fl() {{
    let n=0;
    document.querySelectorAll('.card').forEach(c=>{{const m=f=='all'||c.dataset.bucket==f;c.classList.toggle('show',m);if(m)n++;}});
    document.getElementById('n').textContent=n;
  }}
  fl();
</script>
</body>
</html>"""


def main():
    args = parse_args()

    # --from-json mode: regenerate HTML from saved JSON
    if args.from_json:
        print(f"Reading saved data from {args.from_json}...")
        with open(args.from_json) as f:
            data = json.load(f)
        first_item = data["itineraries"]["buckets"][0]["items"][0]
        leg0 = first_item["legs"][0]
        is_roundtrip = len(first_item["legs"]) > 1
        config = SearchConfig(
            origin=leg0["origin"]["displayCode"],
            destination=leg0["destination"]["displayCode"],
            depart_date="",
            return_date="",
            output=args.output,
        )
        codes = collect_airline_codes(data)
        print(f"Collecting {len(codes)} airline logos...")
        logo_paths = download_logos(codes)
        html = generate_html(data, config, logo_paths)
        os.makedirs("results", exist_ok=True)
        out_path = os.path.join("results", os.path.basename(args.output))
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)
        abs_path = os.path.abspath(out_path)
        print(f"Report saved to: {abs_path}")
        webbrowser.open(f"file://{abs_path}")
        return

    # If any required arg is missing, fall back to interactive mode
    if not all([args.origin, args.destination, args.depart, args.return_date]):
        print("Missing arguments, switching to interactive mode.\n")
        config = prompt_input()
    else:
        config = SearchConfig(
            origin=args.origin.upper(),
            destination=args.destination.upper(),
            depart_date=args.depart,
            return_date=args.return_date,
            adults=args.adults,
            child_ages=[int(a) for a in args.children.split(",") if a.strip()] if args.children else [],
            cabin_class=CABIN_MAP[args.cabin],
            output=args.output,
        )

    # Validate dates
    depart_dt = validate_date(config.depart_date)
    return_dt = validate_date(config.return_date)

    print(f"\nSearching {config.origin} → {config.destination}...")
    print(f"  Depart: {config.depart_date}  Return: {config.return_date}")
    print(f"  {config.adults} adult(s), cabin: {config.cabin_class.value}")
    if config.child_ages:
        print(f"  Children ages: {config.child_ages}")
    print()

    scanner = SkyScanner()
    print("Initialized.")

    origin = scanner.get_airport_by_code(config.origin)
    dest = scanner.get_airport_by_code(config.destination)
    print(f"  {origin.title} → {dest.title}")

    prices = scanner.get_flight_prices(
        origin=origin,
        destination=dest,
        depart_date=depart_dt,
        return_date=return_dt,
        adults=config.adults,
        childAges=config.child_ages,
        cabinClass=config.cabin_class,
    )

    # Determine one-way
    is_roundtrip = bool(config.return_date)

    buckets = prices.json["itineraries"]["buckets"]
    print(f"\nFound {sum(len(b['items']) for b in buckets)} flights in {len(buckets)} categories.")

    # Download airline logos
    codes = collect_airline_codes(prices.json)
    print(f"Collecting {len(codes)} airline logos...")
    logo_paths = download_logos(codes)

    # Save JSON and HTML to results directory
    os.makedirs("results", exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    date_str = config.depart_date.replace("-", "")
    suffix = "ow" if not is_roundtrip else ""
    base = f"{config.origin}_{config.destination}_{date_str}{suffix}_{timestamp}"
    json_path = os.path.join("results", f"{base}.json")
    html_path = os.path.join("results", f"{base}.html")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(prices.json, f, indent=2)
    print(f"Data saved to:   {os.path.abspath(json_path)}")

    html = generate_html(prices.json, config, logo_paths)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    abs_path = os.path.abspath(html_path)
    print(f"Report saved to: {abs_path}")

    if args.open if hasattr(args, 'open') and args.open is not None else True:
        webbrowser.open(f"file://{abs_path}")
        print("Opened in browser.")


if __name__ == "__main__":
    main()
