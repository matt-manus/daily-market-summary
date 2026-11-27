import re, sys, time, json
from urllib.request import Request, urlopen
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
def count(f):
    url = f"https://finviz.com/screener.ashx?v=111&f={f}&ft=4"
    for a in range(3):
        try:
            t = urlopen(Request(url, headers={"User-Agent": UA, "Accept": "text/html"}), timeout=25).read().decode("utf-8", "replace")
            m = re.search(r'"result_count"\s*:\s*(\d+)', t) or re.search(r'#1 / (\d[\d,]*)', t) or re.search(r'(\d[\d,]*)\s+Total', t)
            if m: return int(m.group(1).replace(",", ""))
            if "No results" in t or "0 Total" in t: return 0
        except Exception as e:
            print("err", f, e, file=sys.stderr)
        time.sleep(1.5 * (a + 1))
    return None
out = {}
for idx in ("idx_sp500", "idx_ndx", "idx_rut"):
    out[idx] = {}
    for k, f in (("total", idx), ("a20", idx + ",ta_sma20_pa"), ("a50", idx + ",ta_sma50_pa"), ("a200", idx + ",ta_sma200_pa"), ("up", idx + ",ta_change_u"), ("down", idx + ",ta_change_d")):
        out[idx][k] = count(f); time.sleep(0.7)
    print(idx, out[idx], flush=True)
json.dump(out, open(sys.argv[1], "w"), indent=1)
