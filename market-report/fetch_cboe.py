#!/usr/bin/env python3
"""Fetch Cboe official equity put/call for a US session.

Usage: fetch_cboe.py RUN_DIR SESSION
       fetch_cboe.py RUN_DIR SESSION --html PATH   # parse a saved page (no network)

SESSION is the US cash session date (YYYY-MM-DD). The official Daily Market
Statistics page is requested with ?dt=SESSION. The figure is accepted only when
selectedDate equals SESSION and both EQUITY PUT/CALL RATIO and EQUITY OPTIONS
volume are present. If Cboe has not published that session yet (optionsData is
null), pc is left null — a prior day is never substituted.

Writes RUN_DIR/cboe.json and, when RUN_DIR/meta.json already exists, sets its
pc field to the same value. Raw HTML is saved as RUN_DIR/cboe.html when fetched.
"""
import argparse, json, os, re, sys
from urllib.request import Request, urlopen

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
PAGE = "https://www.cboe.com/markets/us/options/market-statistics/daily/"


def page_url(session):
    return f"{PAGE}?dt={session}"


def fetch_html(session, timeout=30):
    url = page_url(session)
    req = Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"})
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace"), url


def _unesc(html):
    # Next.js flight payload stores JSON with escaped quotes.
    return html.replace('\\"', '"')


def parse_cboe(html, session):
    text = _unesc(html)
    url = page_url(session)
    sd = re.search(r'"selectedDate"\s*:\s*"([0-9]{4}-[0-9]{2}-[0-9]{2})"', text)
    selected = sd.group(1) if sd else None
    odm = re.search(r'"optionsData"\s*:\s*(null|\{)', text)
    options_kind = odm.group(1) if odm else None

    if selected != session:
        return None, f"selectedDate {selected!r} does not match session {session}"
    if options_kind != "{":
        return None, f"official figures for {session} not published yet (optionsData is {options_kind or 'missing'})"

    rm = re.search(r'\{"name":"EQUITY PUT/CALL RATIO","value":"([^"]+)"\}', text)
    vm = re.search(r'"EQUITY OPTIONS":\[\{"name":"VOLUME","call":(\d+),"put":(\d+)', text)
    if not rm or not vm:
        return None, f"page for {session} is missing EQUITY PUT/CALL RATIO or EQUITY OPTIONS volume"

    try:
        ratio = float(rm.group(1))
    except ValueError:
        return None, f"unparseable EQUITY PUT/CALL RATIO {rm.group(1)!r}"
    calls = int(vm.group(1))
    puts = int(vm.group(2))
    pc = {
        "ratio": ratio,
        "calls": calls,
        "puts": puts,
        "time_text": f"{session} official close",
        "page_date": session,
        "url": url,
    }
    return pc, None


def write_result(run, pc, reason):
    os.makedirs(run, exist_ok=True)
    payload = {"pc": pc, "reason": reason}
    out = os.path.join(run, "cboe.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")
    meta_path = os.path.join(run, "meta.json")
    if os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        meta["pc"] = pc
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
            f.write("\n")
    return out


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("run")
    p.add_argument("session")
    p.add_argument("--html", help="parse this saved HTML instead of fetching")
    args = p.parse_args(argv)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.session):
        print(f"session must be YYYY-MM-DD, got {args.session}", file=sys.stderr)
        return 2
    if args.html:
        html = open(args.html, encoding="utf-8", errors="replace").read()
        url = page_url(args.session)
    else:
        html, url = fetch_html(args.session)
        os.makedirs(args.run, exist_ok=True)
        with open(os.path.join(args.run, "cboe.html"), "w", encoding="utf-8") as f:
            f.write(html)
    pc, reason = parse_cboe(html, args.session)
    write_result(args.run, pc, reason)
    if pc:
        print(
            f"cboe {args.session} ratio {pc['ratio']:.2f} "
            f"calls {pc['calls']:,} puts {pc['puts']:,} {url}"
        )
        return 0
    print(f"cboe {args.session} not found: {reason}", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
