---
name: mywant-transit-plugin
description: Yahoo!路線情報で乗り換え案内を検索し結果をJSONで返す。電車・バスの経路検索、出発・到着時刻の確認、乗換回数・料金の取得が必要なときに使用する。Playwright経由でChromeのCDPに接続する。
compatibility:
  python: ">=3.10"
  requires:
    - playwright (sync_api)
    - Chrome with remote debugging on port 9222
metadata:
  json-schema: see "出力JSON形式" section below
---

## 使い方

```bash
python3 "${CLAUDE_SKILL_DIR}/main.py" <出発地> <目的地> [HH:MM] [出発|到着]
```

例:
```bash
# 出発地・目的地のみ
python3 "${CLAUDE_SKILL_DIR}/main.py" 新宿 渋谷

# 時刻指定（出発）
python3 "${CLAUDE_SKILL_DIR}/main.py" 新宿 渋谷 09:30

# 時刻指定（到着）
python3 "${CLAUDE_SKILL_DIR}/main.py" 新宿 渋谷 09:30 到着
```

## 出力JSON形式

```json
{
  "from": "新宿",
  "to": "渋谷",
  "query_time": "09:30",
  "query_type": "到着",
  "routes": [
    {
      "index": 1,
      "departure": "09:05",
      "arrival": "09:30",
      "duration_minutes": 25,
      "fare": 220,
      "transfers": 1,
      "summary": "09:05発→09:30着25分（乗車25分）",
      "legs": [
        {
          "type": "depart",
          "time": "09:05",
          "station": "新宿",
          "line": "ＪＲ山手線",
          "direction": "渋谷・品川方面"
        },
        {
          "type": "arrive",
          "time": "09:30",
          "station": "渋谷"
        }
      ],
      "legs_text": "新宿(09:05) ─[ＪＲ山手線]→ 渋谷(09:30)"
    }
  ],
  "raw_text": "..."
}
```

### フィールド説明

| フィールド | 型 | 説明 |
|---|---|---|
| `from` | string | 出発地 |
| `to` | string | 目的地 |
| `query_time` | string | 検索時刻（HH:MM、未指定時は空文字） |
| `query_type` | string | `"出発"` または `"到着"` |
| `routes` | array | 候補ルートのリスト |
| `routes[n].index` | integer | ルート番号（1始まり） |
| `routes[n].departure` | string | 出発時刻（HH:MM） |
| `routes[n].arrival` | string | 到着時刻（HH:MM） |
| `routes[n].duration_minutes` | integer | 所要時間（分） |
| `routes[n].fare` | integer | 運賃（円） |
| `routes[n].transfers` | integer | 乗換回数 |
| `routes[n].summary` | string | サマリーテキスト |
| `routes[n].legs` | array | 各区間の詳細 |
| `routes[n].legs[m].type` | string | `"depart"` または `"arrive"` |
| `routes[n].legs[m].time` | string | 時刻（HH:MM） |
| `routes[n].legs[m].station` | string | 駅名 |
| `routes[n].legs[m].line` | string | 路線名（depart のみ） |
| `routes[n].legs[m].direction` | string | 行き先方面（depart のみ） |
| `routes[n].legs_text` | string | 区間テキスト要約 |
| `raw_text` | string | ページ本文（先頭80行） |

### エラー時

```json
{ "error": "ブラウザに接続できません (http://127.0.0.1:9222): ...", "routes": [] }
```
