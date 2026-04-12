#!/usr/bin/env python3
"""
transit: Yahoo!路線情報で乗り換え案内を検索してJSONで出力する。

使い方:
  python3 main.py <出発地> <目的地> [HH:MM] [出発|到着]

出力形式 (JSON):
{
  "from": "新宿", "to": "渋谷", "query_time": "09:30", "query_type": "到着",
  "routes": [
    {
      "index": 1, "departure": "09:05", "arrival": "09:30",
      "duration_minutes": 25, "fare": 220, "transfers": 1,
      "summary": "09:05発→09:30着25分（乗車25分）",
      "legs": [
        {"type": "depart", "time": "09:05", "station": "新宿",
         "line": "ＪＲ山手線", "direction": "渋谷・品川方面"},
        {"type": "arrive", "time": "09:30", "station": "渋谷"}
      ],
      "legs_text": "新宿(09:05) ─[ＪＲ山手線]→ 渋谷(09:30)"
    }
  ],
  "raw_text": "..."
}
"""
import json
import re
import sys
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

CDP_URL = "http://127.0.0.1:9222"
YAHOO_TRANSIT_URL = "https://transit.yahoo.co.jp/"


def parse_args(args: list[str]) -> tuple[str, str, str, str]:
    if len(args) < 2:
        error_out("使い方: python3 main.py <出発地> <目的地> [HH:MM] [出発|到着]")
    from_station, to_station = args[0], args[1]
    time_str, dep_arr = "", "出発"
    for arg in args[2:]:
        if re.match(r"^\d{1,2}:\d{2}$", arg):
            time_str = arg
        elif arg in ("到着", "arrival"):
            dep_arr = "到着"
        elif arg in ("出発", "departure"):
            dep_arr = "出発"
    return from_station, to_station, time_str, dep_arr


def error_out(message: str) -> None:
    print(json.dumps({"error": message, "routes": []}, ensure_ascii=False))
    sys.exit(1)


def clean_station_name(raw: str) -> str:
    """UI付加テキスト（時刻表・出口・地図など）を除去して駅名だけ返す。"""
    for noise in ["時刻表", "出口", "地図", "乗り換え", "構内図", "バス停地図"]:
        raw = raw.replace(noise, "")
    return raw.strip()


# ── ページ操作 ────────────────────────────────────────────────────────────────

def fill_and_submit(page, from_st: str, to_st: str, time_str: str, dep_arr: str) -> None:
    page.goto(YAHOO_TRANSIT_URL, wait_until="domcontentloaded", timeout=15000)
    try:
        page.wait_for_selector("form", timeout=10000)
    except PlaywrightTimeout:
        error_out("Yahoo!路線情報の読み込みがタイムアウトしました。")

    from_input = (page.query_selector("input#sfrom")
                  or page.query_selector("input[name='from']")
                  or page.query_selector("input[placeholder*='出発']"))
    if not from_input:
        error_out("出発地入力欄が見つかりません。")
    from_input.fill(from_st)

    to_input = (page.query_selector("input#sto")
                or page.query_selector("input[name='to']")
                or page.query_selector("input[placeholder*='到着']"))
    if not to_input:
        error_out("目的地入力欄が見つかりません。")
    to_input.fill(to_st)

    if time_str:
        h, m = time_str.split(":")
        hour_sel = page.query_selector("select[name='hh']") or page.query_selector("select#hh")
        min_sel  = page.query_selector("select[name='m1']") or page.query_selector("select#m1")
        if hour_sel:
            hour_sel.select_option(h.zfill(2))
        if min_sel:
            min_sel.select_option(m.zfill(2))
        if dep_arr == "到着":
            arr_radio = (page.query_selector("input[value='1'][name='type']")
                         or page.query_selector("input[id*='arrival']"))
            if arr_radio:
                arr_radio.click()

    submit_btn = (page.query_selector("input[type='submit'][value*='検索']")
                  or page.query_selector("button[type='submit']")
                  or page.query_selector("input.searchBtn"))
    if not submit_btn:
        error_out("検索ボタンが見つかりません。")
    submit_btn.click()

    try:
        page.wait_for_selector(".routeResult, .routeList, #result", timeout=15000)
    except PlaywrightTimeout:
        error_out("検索結果の読み込みがタイムアウトしました。")


# ── テキストパーサー ──────────────────────────────────────────────────────────

def parse_routes_from_lines(lines: list[str]) -> list[dict]:
    """
    ページ全体の行リストから詳細ルートブロックを抽出してリストで返す。

    Yahoo!路線のページには「コンパクト要約」と「詳細」の2種類の
    ルートブロックが存在する。詳細ブロックは "HH:MM発→HH:MM着" パターンで識別。
    """
    # "ルートN" ヘッダーの位置を収集
    route_positions: list[tuple[int, int]] = []
    for i, line in enumerate(lines):
        m = re.match(r"^ルート(\d+)$", line)
        if m:
            route_positions.append((i, int(m.group(1))))

    if not route_positions:
        return []

    # 各ルートのブロック（ヘッダー行の次行〜次ルートの手前まで）
    blocks: list[tuple[int, list[str]]] = []
    for idx, (pos, num) in enumerate(route_positions):
        end = route_positions[idx + 1][0] if idx + 1 < len(route_positions) else len(lines)
        blocks.append((num, lines[pos + 1 : end]))

    # 詳細ブロックのみ（"HH:MM発→" を含む）を選別し、同番号の場合は後者優先
    seen: dict[int, list[str]] = {}
    for num, blk in blocks:
        if any(re.search(r"\d{1,2}:\d{2}発→", l) for l in blk):
            seen[num] = blk

    return [parse_single_route(num, seen[num]) for num in sorted(seen)]


def parse_single_route(num: int, lines: list[str]) -> dict:
    route: dict = {
        "index": num,
        "departure": "",
        "arrival": "",
        "duration_minutes": 0,
        "fare": 0,
        "transfers": 0,
        "summary": "",
        "legs": [],
        "legs_text": "",
    }

    for line in lines:
        # サマリー行: "19:49発→19:56着7分（乗車7分）"
        m = re.search(r"(\d{1,2}:\d{2})発→(\d{1,2}:\d{2})着(\d+)分", line)
        if m:
            route["departure"] = m.group(1)
            route["arrival"] = m.group(2)
            route["duration_minutes"] = int(m.group(3))
            route["summary"] = line

        # 乗換回数
        m = re.match(r"乗換：(\d+)回", line)
        if m:
            route["transfers"] = int(m.group(1))

        # 料金（最初にヒットしたものを使用）
        if not route["fare"]:
            m = re.search(r"(?:IC優先：)?(\d[\d,]+)円", line)
            if m:
                route["fare"] = int(m.group(1).replace(",", ""))

    # 区間(leg)を抽出
    # パターン: 単独時刻行 → 次行が "発\t駅名..." or "着\t駅名..."
    i = 0
    while i < len(lines):
        if re.match(r"^\d{1,2}:\d{2}$", lines[i]) and i + 1 < len(lines):
            time_val = lines[i]
            next_line = lines[i + 1]

            dep_m = re.match(r"^発[\t\s]+(.+)", next_line)
            arr_m = re.match(r"^着[\t\s]+(.+)", next_line)

            if dep_m:
                station = clean_station_name(dep_m.group(1))
                leg: dict = {
                    "type": "depart",
                    "time": time_val,
                    "station": station,
                    "line": "",
                    "direction": "",
                }
                # 後続行から路線名・方面を取得
                for j in range(i + 2, min(i + 8, len(lines))):
                    l = lines[j]
                    if re.match(r"^\[発\]", l) or re.match(r"^\d+駅", l) or re.match(r"^\d{1,2}:\d{2}$", l):
                        break
                    if l and "円" not in l and not re.match(r"^\d", l):
                        if not leg["line"]:
                            leg["line"] = l
                        elif not leg["direction"]:
                            leg["direction"] = l
                route["legs"].append(leg)
                i += 2
                continue

            elif arr_m:
                station = clean_station_name(arr_m.group(1))
                route["legs"].append({"type": "arrive", "time": time_val, "station": station})
                i += 2
                continue

        i += 1

    # legs_text: "新宿(19:49) ─[ＪＲ山手線]→ 渋谷(19:56)" 形式
    parts: list[str] = []
    for leg in route["legs"]:
        if leg["type"] == "depart":
            entry = f"{leg['station']}({leg['time']})"
            if leg.get("line"):
                entry += f" ─[{leg['line']}]→"
            parts.append(entry)
        else:
            parts.append(f"{leg['station']}({leg['time']})")
    route["legs_text"] = " ".join(parts) if parts else route["summary"]

    return route


# ── メイン ───────────────────────────────────────────────────────────────────

def search_and_extract(page, from_st: str, to_st: str, time_str: str, dep_arr: str) -> dict:
    fill_and_submit(page, from_st, to_st, time_str, dep_arr)

    raw = page.inner_text("body")
    lines = [l.strip() for l in raw.splitlines() if l.strip()]

    routes = parse_routes_from_lines(lines)

    return {
        "from": from_st,
        "to": to_st,
        "query_time": time_str,
        "query_type": dep_arr,
        "routes": routes,
        "raw_text": "\n".join(lines[:80]),
    }


def main() -> None:
    from_st, to_st, time_str, dep_arr = parse_args(sys.argv[1:])

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(CDP_URL)
        except Exception as e:
            error_out(f"ブラウザに接続できません ({CDP_URL}): {e}")

        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.pages[0] if context.pages else context.new_page()

        data = search_and_extract(page, from_st, to_st, time_str, dep_arr)
        print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
