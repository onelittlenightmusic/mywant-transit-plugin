#!/usr/bin/env python3
"""
transit: Yahoo!路線情報で乗り換え案内を検索してJSONで出力する。

結果ページはサーバー側で組み立てられるので、検索条件をクエリに載せて取得した
HTML を innerText 相当の行に落とせば足りる。ブラウザも外部パッケージも要らない
（Python 標準ライブラリのみ）。

使い方:
  python3 main.py <出発地> <目的地> [HH:MM] [出発|到着]

出力形式 (JSON):
{
  "from": "新宿", "to": "渋谷", "query_time": "09:30", "query_type": "到着",
  "final_result": "{...}",  // build_view()が生成する経由地込みJSON文字列
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
      "itinerary": [
        {"from": "新宿", "depart_time": "09:05",
         "line": "ＪＲ山手線", "direction": "渋谷・品川方面",
         "to": "渋谷", "arrive_time": "09:30"}
      ],
      "legs_text": "新宿(09:05) ─[ＪＲ山手線]→ 渋谷(09:30)"
    }
  ],
  // カード描画用の軽量版（全ルート候補）。routes から legs/summary を落としたもの
  "route_views": [
    {"index": 1, "departure": "09:05", "arrival": "09:30", "duration_minutes": 25,
     "fare": 220, "transfers": 1, "itinerary": [...]}
  ],
  "raw_text": "..."
}
"""
import datetime
import html as html_module
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

SEARCH_URL = "https://transit.yahoo.co.jp/search/result"
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
TIMEOUT_SECONDS = 20


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


def report_progress(percentage, message=""):
    print(json.dumps({"_progress": percentage, "_message": message}, ensure_ascii=False), flush=True)


def error_out(message: str) -> None:
    print(json.dumps({"error": message, "routes": []}, ensure_ascii=False), flush=True)
    sys.exit(1)


STATION_NOISE = ["時刻表", "出口", "地図", "乗り換え", "構内図", "バス停地図"]


def clean_station_name(raw: str) -> str:
    """UI付加テキスト（時刻表・出口・地図など）を除去して駅名だけ返す。"""
    for noise in STATION_NOISE:
        raw = raw.replace(noise, "")
    return raw.strip()


def station_after_marker(marker: str, lines: list[str], index: int) -> tuple[str, int]:
    """発着マーカーに続く駅名を返す（一致しなければ空文字）。

    ブラウザは表のセルを 1 行にまとめて "発\t新宿" にするが、HTML から起こすと
    "発" と "新宿" が別の行になる。どちらの形でも読めるようにしておく。
    """
    if index >= len(lines):
        return "", index
    line = lines[index]
    same_line = re.match(rf"^{marker}[\t\s]+(.+)", line)
    if same_line:
        return clean_station_name(same_line.group(1)), index + 1
    if line == marker and index + 1 < len(lines):
        return clean_station_name(lines[index + 1]), index + 2
    return "", index


# ── 取得 ─────────────────────────────────────────────────────────────────────

def build_search_url(from_st: str, to_st: str, time_str: str, dep_arr: str) -> str:
    """検索条件をそのままクエリに載せる。結果ページはサーバー側で組み立てられるので、
    フォームを操作する必要はない。"""
    params = {
        "from":   from_st,
        "to":     to_st,
        "ticket": "ic",
        # type=1: 指定時刻に出発 / type=4: 指定時刻に到着
        "type":   "4" if dep_arr == "到着" else "1",
        # 交通手段はサイトのフォーム初期値に合わせる。URL 検索では既定で
        # 新幹線が外れるため、明示しないと東京→新大阪が在来線だけになる。
        "shin":   "1",  # 新幹線
        "ex":     "1",  # 有料特急
        "hb":     "1",  # 高速バス
        "al":     "1",  # 飛行機
        "lb":     "1",  # 連絡バス
        "sr":     "1",  # 座席指定
    }
    if time_str:
        hour, minute = time_str.split(":")
        today = datetime.date.today()
        params.update({
            "y":  f"{today.year:04d}",
            "m":  f"{today.month:02d}",
            "d":  f"{today.day:02d}",
            "hh": f"{int(hour):02d}",
            # 分は十の位と一の位を別パラメータで渡す Yahoo 独自の形式
            "m1": str(int(minute) // 10),
            "m2": str(int(minute) % 10),
        })
    return SEARCH_URL + "?" + urllib.parse.urlencode(params)


def fetch_page(url: str) -> str:
    request = urllib.request.Request(url, headers={
        "User-Agent":      USER_AGENT,
        "Accept-Language": "ja,en;q=0.8",
    })
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        error_out(f"Yahoo!路線情報が {exc.code} を返しました")
    except urllib.error.URLError as exc:
        error_out(f"Yahoo!路線情報に接続できません: {exc.reason}")
    except TimeoutError:
        error_out(f"Yahoo!路線情報が {TIMEOUT_SECONDS} 秒以内に応答しませんでした")
    return ""  # error_out で終了済み


# ブラウザの innerText と同じ行に落とすためのタグ分類。ブロック要素は改行、
# 表のセルはタブ、インライン要素（span/a/strong など）は区切らない。
BLOCK_END_TAGS = r"</(?:div|p|li|tr|h[1-6]|dt|dd|table|ul|ol|section|article|form|header|footer)>"


def html_to_lines(html: str) -> list[str]:
    """結果ページの HTML を innerText 相当の行リストに変換する。"""
    html = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", html)
    html = re.sub(r"(?i)<br\s*/?>", "\n", html)
    html = re.sub(r"(?i)</(td|th)>", "\t", html)
    # 路線名と方面は同じ行に並ぶので、方面だけタブで切り出せるようにしておく
    html = re.sub(r'(?i)<span class="destination">', "\t", html)
    html = re.sub("(?i)" + BLOCK_END_TAGS, "\n", html)
    html = re.sub(r"(?s)<[^>]+>", "", html)
    html = html_module.unescape(html)

    lines: list[str] = []
    for line in html.splitlines():
        line = re.sub(r"[ \u3000]+", " ", line).strip()
        line = re.sub(r"\t+", "\t", line).strip("\t ")
        if line:
            lines.append(line)
    return lines


def parse_transfer_at(lines: list[str], index: int) -> tuple[str, str, str, int] | None:
    """乗換駅の "HH:MM着" "HH:MM発" "駅名" の並びを読む。

    起終点は時刻と発着マーカーが別行になるが、乗換駅では時刻に発着が付いて
    到着・出発が続けて並ぶ。返り値は (到着時刻, 出発時刻, 駅名, 次の走査位置)。
    """
    if index + 2 >= len(lines):
        return None
    arrive = re.match(r"^(\d{1,2}:\d{2})着$", lines[index])
    depart = re.match(r"^(\d{1,2}:\d{2})発$", lines[index + 1])
    if not arrive or not depart:
        return None
    station = clean_station_name(lines[index + 2])
    if not station:
        return None
    return arrive.group(1), depart.group(1), station, index + 3


def fill_line_and_direction(leg: dict, lines: list[str], start: int) -> None:
    """出発legの後続行から路線名と方面を拾う。"""
    for j in range(start, min(start + 8, len(lines))):
        line = lines[j]
        if re.match(r"^\[発\]", line) or re.match(r"^\d+駅", line) or re.match(r"^\d{1,2}:\d{2}", line):
            break
        if line in STATION_NOISE:
            continue
        if line and "円" not in line and not re.match(r"^\d", line):
            # "ＪＲ山手線内回り\t渋谷・品川方面" のようにタブ区切りで届く
            name, _, destination = line.partition("\t")
            if not leg["line"]:
                leg["line"] = name.strip()
                leg["direction"] = destination.strip()
            elif not leg["direction"]:
                leg["direction"] = name.strip()


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
        "itinerary": [],
        "legs_text": "",
    }

    for line in lines:
        # サマリー行: "19:49発→19:56着7分（乗車7分）" or "23:41発→00:41着1時間0分"
        m = re.search(r"(\d{1,2}:\d{2})発→(\d{1,2}:\d{2})着(?:(\d+)時間)?(\d+)分", line)
        if m:
            route["departure"] = m.group(1)
            route["arrival"] = m.group(2)
            hours = int(m.group(3) or 0)
            mins  = int(m.group(4))
            route["duration_minutes"] = hours * 60 + mins
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
    # パターン1（乗換駅）: "05:02着" "05:10発" "品川" と時刻に発着が付いて並ぶ
    # パターン2（起終点）: 単独時刻行 → 次行が "発"/"着"（同一行にタブ区切りの場合もある）
    i = 0
    while i < len(lines):
        transfer = parse_transfer_at(lines, i)
        if transfer:
            arrive_time, depart_time, station, after = transfer
            route["legs"].append({"type": "arrive", "time": arrive_time, "station": station})
            leg = {
                "type": "depart",
                "time": depart_time,
                "station": station,
                "line": "",
                "direction": "",
            }
            fill_line_and_direction(leg, lines, after)
            route["legs"].append(leg)
            i = after
            continue

        if re.match(r"^\d{1,2}:\d{2}$", lines[i]) and i + 1 < len(lines):
            time_val = lines[i]
            next_line = lines[i + 1]

            dep_station, after_dep = station_after_marker("発", lines, i + 1)
            arr_station, after_arr = station_after_marker("着", lines, i + 1)

            if dep_station:
                station = dep_station
                leg: dict = {
                    "type": "depart",
                    "time": time_val,
                    "station": station,
                    "line": "",
                    "direction": "",
                }
                fill_line_and_direction(leg, lines, after_dep)
                route["legs"].append(leg)
                i = after_dep
                continue

            elif arr_station:
                route["legs"].append({"type": "arrive", "time": time_val, "station": arr_station})
                i = after_arr
                continue

        i += 1

    # itinerary: depart/arrive ペアを1区間(セグメント)に統合
    # 例: [{from, depart_time, line, direction, to, arrive_time}, ...]
    route["itinerary"] = build_itinerary(route["legs"])

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


def build_itinerary(legs: list[dict]) -> list[dict]:
    """
    depart/arrive ペアを1区間(セグメント)ずつまとめた配列を返す。

    返り値の各要素:
      {
        "from": "新宿",
        "depart_time": "09:05",
        "line": "ＪＲ山手線",
        "direction": "渋谷・品川方面",
        "to": "渋谷",
        "arrive_time": "09:30"
      }
    乗換がある場合はその分だけ要素が増える。
    """
    segments: list[dict] = []
    i = 0
    while i < len(legs):
        dep = legs[i]
        if dep["type"] == "depart" and i + 1 < len(legs) and legs[i + 1]["type"] == "arrive":
            arr = legs[i + 1]
            segments.append({
                "from":        dep["station"],
                "depart_time": dep["time"],
                "line":        dep.get("line", ""),
                "direction":   dep.get("direction", ""),
                "to":          arr["station"],
                "arrive_time": arr["time"],
            })
            i += 2
        else:
            i += 1
    return segments


# ── ルートサマリーJSON ────────────────────────────────────────────────────────

def build_route_summary(route: dict, from_st: str, to_st: str,
                        query_time: str, query_type: str) -> dict:
    """
    1ルートの構造化サマリーJSONを生成する（summary_json フィールドに格納）。

    {
      "from", "to", "query_time", "query_type",
      "departure", "arrival", "duration_minutes", "fare", "transfers",
      "text_summary",   ← 元のテキストサマリー行
      "legs_text",      ← 人間可読の経路文字列
      "itinerary"       ← 経由地・利用電車の配列
    }
    """
    return {
        "from":             from_st,
        "to":               to_st,
        "query_time":       query_time,
        "query_type":       query_type,
        "departure":        route.get("departure", ""),
        "arrival":          route.get("arrival", ""),
        "duration_minutes": route.get("duration_minutes", 0),
        "fare":             route.get("fare", 0),
        "transfers":        route.get("transfers", 0),
        "text_summary":     route.get("summary", ""),
        "legs_text":        route.get("legs_text", ""),
        "itinerary":        route.get("itinerary", []),
    }


def build_route_view(route: dict) -> dict:
    """
    カード表示用の軽量ルート情報。routes をそのまま state に載せると legs や
    summary(JSON文字列) が重複して肥大するので、描画に要る分だけを取り出す。
    """
    return {
        "index":            route.get("index", 0),
        "departure":        route.get("departure", ""),
        "arrival":          route.get("arrival", ""),
        "duration_minutes": route.get("duration_minutes", 0),
        "fare":             route.get("fare", 0),
        "transfers":        route.get("transfers", 0),
        "itinerary":        route.get("itinerary", []),
    }


# ── メイン ───────────────────────────────────────────────────────────────────

def search_and_extract(from_st: str, to_st: str, time_str: str, dep_arr: str) -> dict:
    lines = html_to_lines(fetch_page(build_search_url(from_st, to_st, time_str, dep_arr)))

    routes = parse_routes_from_lines(lines)

    # route["summary"] をテキストから構造化JSON文字列（itinerary込み）に置き換える。
    # build_route_summary は TEXT summary を先に読んでから上書きするため順序に注意。
    for route in routes:
        route["summary"] = json.dumps(
            build_route_summary(route, from_st, to_st, time_str, dep_arr),
            ensure_ascii=False,
        )

    return {
        "from":        from_st,
        "to":          to_st,
        "query_time":  time_str,
        "query_type":  dep_arr,
        "routes":      routes,
        "route_views": [build_route_view(r) for r in routes],
        "raw_text":    "\n".join(lines[:80]),
    }


def main() -> None:
    from_st, to_st, time_str, dep_arr = parse_args(sys.argv[1:])

    report_progress(20, f"Searching route: {from_st} → {to_st}")
    data = search_and_extract(from_st, to_st, time_str, dep_arr)

    if not data["routes"]:
        error_out(f"{from_st} → {to_st} のルートが見つかりませんでした")

    report_progress(90, f"Found {len(data['routes'])} routes")
    report_progress(100, "Done")
    print(json.dumps(data, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
