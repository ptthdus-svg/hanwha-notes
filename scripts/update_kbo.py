"""KBO 공식 홈페이지에서 한화 경기 일정·결과와 리그 순위를 읽어 kbo.json 으로 저장해요.
GitHub Actions(.github/workflows/kbo.yml)가 매일 실행해요. 표준 라이브러리만 써요.
"""
import datetime as dt
import html
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://www.koreabaseball.com"
UA = "Mozilla/5.0 (compatible; hanwha-notes/1.0)"
KST = dt.timezone(dt.timedelta(hours=9))
OUT = Path(__file__).resolve().parent.parent / "kbo.json"
SERIES = {"정규시즌": "0,9,6", "포스트시즌": "3,4,5,7"}


def fetch(url, data=None, referer=None):
    headers = {"User-Agent": UA}
    if data is not None:
        headers["X-Requested-With"] = "XMLHttpRequest"
        data = urllib.parse.urlencode(data).encode()
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8-sig")


def text(s):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", s or "")).split())


def month_games(series, year, month, team):
    raw = fetch(BASE + "/ws/Schedule.asmx/GetScheduleList",
                {"leId": 1, "srIdList": SERIES[series], "seasonId": year, "gameMonth": f"{month:02d}", "teamId": team},
                referer=BASE + "/Schedule/Schedule.aspx")
    rows = json.loads(raw).get("rows") or []
    games, day = [], None
    for r in rows:
        cells = r.get("row") or []
        if cells and cells[0].get("Class") == "day":
            day = text(cells[0]["Text"])
            cells = cells[1:]
        if not day or len(cells) < 8:
            continue
        play = next((c for c in cells if c.get("Class") == "play"), None)
        if not play or not play.get("Text"):
            continue
        m = re.search(r"<span>([^<]+)</span><em>(.*?)</em><span>([^<]+)</span>", play["Text"])
        if not m:
            continue
        away, mid, home = m.group(1).strip(), m.group(2), m.group(3).strip()
        scores = re.findall(r'<span class="(win|lose|same)">(\d+)</span>', mid)
        time_ = text(next((c["Text"] for c in cells if c.get("Class") == "time"), ""))
        rest = [text(c["Text"]) for c in cells[cells.index(play) + 3:]]  # 리뷰, 하이라이트 다음: TV, 라디오, 구장, 비고
        mm, dd = re.match(r"(\d+)\.(\d+)", day).groups()
        g = {
            "date": f"{year}-{int(mm):02d}-{int(dd):02d}",
            "time": time_,
            "away": away,
            "home": home,
            "stadium": rest[2] if len(rest) > 2 else "",
            "note": "" if (len(rest) < 4 or rest[3] in ("-", "")) else rest[3],
            "series": series,
        }
        if len(scores) == 2:
            g["awayScore"], g["homeScore"] = int(scores[0][1]), int(scores[1][1])
        games.append(g)
    return games


def season_games(year):
    out = []
    for m in range(3, 12):
        out += month_games("정규시즌", year, m, "HH")
    post = []
    for m in (10, 11):
        post += month_games("포스트시즌", year, m, "HH")
    seen, games = set(), []
    for g in out + post:
        k = (g["date"], g["away"], g["home"], g["time"], g["series"])
        if k not in seen:
            seen.add(k)
            games.append(g)
    hh = [g for g in games if g["series"] == "정규시즌" and "한화" in (g["away"], g["home"])]
    ps = [g for g in games if g["series"] == "포스트시즌"]
    return hh, ps


def standings():
    page = fetch(BASE + "/Record/TeamRank/TeamRankDaily.aspx")
    tbl = re.search(r'<table[^>]*class="tData"[^>]*>(.*?)</table>', page, re.S)
    body = tbl.group(1) if tbl else page
    date = re.search(r'id="cphContents_cphContents_cphContents_lblSearchDateTitle"[^>]*>([^<]+)<', page)
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S):
        tds = [text(td) for td in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(tds) < 12 or not tds[0].isdigit():
            continue
        rows.append({"rank": int(tds[0]), "team": tds[1], "g": int(tds[2]), "w": int(tds[3]), "l": int(tds[4]), "d": int(tds[5]),
                     "pct": tds[6], "gb": tds[7], "last10": tds[8], "streak": tds[9], "home": tds[10], "away": tds[11]})
        if len(rows) == 10:
            break
    return rows, (text(date.group(1)) if date else "")


def main():
    now = dt.datetime.now(KST)
    year = now.year
    data = {"updatedAt": now.isoformat(timespec="minutes")}
    # 다음 시즌 일정이 발표됐으면 그것까지
    hh, ps = season_games(year)
    nxt, _ = season_games(year + 1) if now.month >= 10 else ([], [])
    data["season"] = year
    data["games"] = hh + nxt
    data["postseason"] = ps
    data["standings"], data["standingsDate"] = standings()
    if len(data["standings"]) != 10 or not data["games"]:
        print("KBO 응답이 예상과 달라 저장하지 않아요", len(data["standings"]), len(data["games"]))
        sys.exit(1)
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    same = {k: v for k, v in old.items() if k != "updatedAt"} == {k: v for k, v in data.items() if k != "updatedAt"}
    if same:
        print("변경 없음")
        return
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print("저장:", len(data["games"]), "경기 /", len(data["postseason"]), "포스트시즌 / 순위", data["standingsDate"])


if __name__ == "__main__":
    main()
