"""transit_search's voice: what a route says on its tile and in its news.

Handed one JSON argument (see mywant's want_voice.go) and prints one JSON
object, {"say": ...}. A route knows where its asker goes at this time of day
("home", from the engine: {"part", "place", "param", "value", "here", ...}),
and talks like it: the usual way home said as the usual thing, a route
somewhere else that evening noticed.
"""

import json
import sys


def first_leg(answer):
    """The departure, its line and the arrival of an itinerary (a list of legs)."""
    if not isinstance(answer, list) or not answer:
        return None
    legs = [l for l in answer if isinstance(l, dict)]
    if not legs:
        return None
    return {
        "depart": legs[0].get("depart_time", ""),
        "line": legs[0].get("line", ""),
        "arrive": legs[-1].get("arrive_time", ""),
    }


def speak(inp):
    params = inp.get("params") or {}
    origin, dest = params.get("from", ""), params.get("to", "")
    event = inp.get("event") or {}
    home = inp.get("home") or {}
    answer = event.get("result") if event.get("kind") == "output" else inp.get("last_answer")
    leg = first_leg(answer)
    news = event.get("kind") == "output"

    place, part = home.get("place", ""), home.get("part", "")
    usual = ""
    if home.get("here"):
        usual = "いつもの" + ({"to": f"{place}行き", "from": f"{place}から"}.get(home.get("param"), place))

    if news:
        if not leg:
            return None  # the notice says it plainly
        when = f"{leg['depart']}発、{leg['arrive']}着"
        if usual:
            return [f"{usual}、{when}です", f"{usual}は{leg['line']}で{when}"]
        if place and home.get("param") == "to":
            return [f"{dest}へ{when}。{part}は{place}じゃないんですね"]
        return None

    # Standing on the tile.
    if usual and leg:
        return [f"{usual}、前は{leg['depart']}発でした", f"{part}は{place}ですよね"]
    if usual:
        return [f"{part}は{usual}ですね"]
    if place and home.get("param") == "to" and dest:
        return [f"{dest}行き。{part}はいつも{place}なのに"]
    if leg and origin and dest:
        return [f"{origin}→{dest}、前は{leg['depart']}発でした"]
    return None


def main():
    inp = json.loads(sys.argv[1]) if len(sys.argv) > 1 else json.load(sys.stdin)
    print(json.dumps({"say": speak(inp)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
