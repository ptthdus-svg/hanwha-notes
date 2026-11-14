"""네이버 뉴스 검색 API로 한화 이글스 야구 기사를 모아 clips.json 에 더해요.
GitHub Actions(.github/workflows/news.yml)가 매일 실행해요. 표준 라이브러리만 써요.
환경 변수: NAVER_CLIENT_ID, NAVER_CLIENT_SECRET (NAVER API HUB 키)
"""
import datetime as dt
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from email.utils import parsedate_to_datetime
from pathlib import Path

KST = dt.timezone(dt.timedelta(hours=9))
OUT = Path(__file__).resolve().parent.parent / "clips.json"
EP = "https://naverapihub.apigw.ntruss.com/search/v1/news"
LOOKBACK_H = 36  # 최근 36시간 기사 (하루 두 번 돌아도 빈틈 없게)

QUERIES = [
    "한화 이글스", "한화이글스", "한화 야구", "한화 감독", "류지현 감독", "한화 단장", "한화 코치",
    "한화 FA", "한화 외국인", "한화 트레이드", "한화 2차 드래프트", "한화 경기", "한화 선발",
    "노시환", "강백호 한화", "문현빈", "허인서", "김서현 한화", "정우주", "문동주", "류현진 한화",
    "왕옌청", "왓슨 한화", "최재훈 한화", "박상원 한화", "채은성", "심우준", "황영묵", "엄상백",
    "폰세 한화", "와이스 한화", "대전 볼파크", "한화생명 볼파크",
]
# 야구 기사인지 판단할 단어 (제목+요약에 하나는 있어야 함)
BASEBALL = re.compile(r"이글스|야구|KBO|감독|코치|투수|타자|포수|내야|외야|선발|불펜|마무리|홈런|타율|평균자책|"
                      r"FA|드래프트|트레이드|포스팅|MLB|메이저리그|캠프|볼파크|연봉|계약|시즌|구단|단장|등판|"
                      r"APBC|WBC|국가대표|대표팀|2군|퓨처스")
# 야구가 아닌 '한화' 기사
NOT_BASEBALL = re.compile(r"한화생명(?!\s*(이글스|볼파크|e?파크))|한화에어로|한화오션|한화솔루션|한화시스템|한화큐셀|"
                          r"한화투자|한화자산|한화손해|한화호텔|한화갤러리아|한화건설|한화엔진|한화비전|한화모멘텀|"
                          r"부회장|회장|그룹|한화토탈|오케스트라|장학|봉사|기부|주가|증시|방산|e스포츠|LCK|롤드컵|리그 오브 레전드|\(한화\s*약|한화\s*약\s*[\d,]|한화로\s*약")
HANWHA = re.compile(r"한화|이글스")
# 제목에 한화/이글스가 없어도 한화 기사로 보는 이름(감독·단장·선수)
HH_NAMES = re.compile(r"류지현|석장현|노시환|문현빈|허인서|김서현|정우주|문동주|류현진|왕옌청|왓슨|최재훈|박상원|채은성|"
                      r"심우준|강백호|이기창|황영묵|엄상백|하주석|이도윤|최인호|김태연|폰세|와이스|페라자")

SOURCES = {
    "osen.co.kr": "OSEN", "xportsnews.com": "엑스포츠뉴스", "sportschosun.com": "스포츠조선",
    "sports.khan.co.kr": "스포츠경향", "sports.donga.com": "스포츠동아", "isplus.com": "일간스포츠",
    "mydaily.co.kr": "마이데일리", "mk.co.kr": "매일경제", "newsis.com": "뉴시스", "news1.kr": "뉴스1",
    "yna.co.kr": "연합뉴스", "sportalkorea.com": "스포탈코리아", "spotvnews.co.kr": "스포티비뉴스",
    "starnewskorea.com": "스타뉴스", "sports.chosun.com": "스포츠조선", "chosun.com": "조선일보",
    "joongang.co.kr": "중앙일보", "hani.co.kr": "한겨레", "khan.co.kr": "경향신문", "donga.com": "동아일보",
    "sedaily.com": "서울경제", "hankyung.com": "한국경제", "seoul.co.kr": "서울신문", "newspim.com": "뉴스핌",
    "maniareport.com": "마니아리포트", "stnsports.co.kr": "STN뉴스", "sportsworldi.com": "스포츠월드",
    "sportsseoul.com": "스포츠서울", "sports.hankooki.com": "스포츠한국", "dailysportshankook.co.kr": "데일리스포츠한국",
    "nocutnews.co.kr": "노컷뉴스", "ytn.co.kr": "YTN", "sbs.co.kr": "SBS", "kbs.co.kr": "KBS", "imbc.com": "MBC",
    "tvchosun.com": "TV조선", "jtbc.co.kr": "JTBC", "fnnews.com": "파이낸셜뉴스", "edaily.co.kr": "이데일리",
    "mhnse.com": "MHN스포츠", "topstarnews.net": "톱스타뉴스", "wikitree.co.kr": "위키트리", "ggilbo.com": "금강일보",
    "daejonilbo.com": "대전일보", "cctoday.co.kr": "충청투데이", "joongdo.co.kr": "중도일보", "tjb.co.kr": "TJB",
    "thesportstimes.co.kr": "더스포츠타임스", "spochoo.com": "스포츠춘추", "slist.kr": "스포츠W", "news.nate.com": "네이트 뉴스",
}


def clean(s):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", "", s or "")).split())


def source_of(url):
    host = urllib.parse.urlparse(url).netloc.lower().removeprefix("www.").removeprefix("m.")
    for dom, name in SOURCES.items():
        if host == dom or host.endswith("." + dom):
            return name
    return host


def category_of(text):
    if re.search(r"FA|영입|이적|트레이드|포스팅|재계약|결별|방출|외국인|아시아쿼터|보상선수|2차 드래프트|계약", text):
        return "FA·이적"
    if re.search(r"감독|단장|코치|구단|볼파크|야구장|홈구장|증축|대전시|팬|응원|대표이사|프런트|시상|행사|티켓", text):
        return "구단"
    if re.search(r"경기|승리|패배|[0-9]+-[0-9]+|연승|연패|선발 등판|APBC|WBC|한일전|대표팀|연습경기|순위", text):
        return "경기"
    return "선수"


def bigrams(s):
    s = re.sub(r"[^가-힣A-Za-z0-9]", "", s)
    return {s[i:i + 2] for i in range(len(s) - 1)}


def similar(a, b):
    A, B = bigrams(a), bigrams(b)
    if not (A and B):
        return False
    r = len(A & B) / min(len(A), len(B))
    if r >= 0.5:
        return True
    # 같은 한화 인물 조합이 제목에 나오고 표현만 다른 기사(예: 같은 경기 라인업 기사 여러 개)
    na, nb = set(HH_NAMES.findall(a)), set(HH_NAMES.findall(b))
    return bool(na) and na == nb and r >= 0.25


def fetch(q, H):
    url = EP + "?" + urllib.parse.urlencode({"query": q, "display": 100, "start": 1, "sort": "date"})
    req = urllib.request.Request(url, headers=H)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r).get("items", [])
        except Exception as e:  # 일시 오류는 재시도
            err = e
            time.sleep(2)
    print("검색 실패:", q, err)
    return []


def main():
    cid, sec = os.environ.get("NAVER_CLIENT_ID"), os.environ.get("NAVER_CLIENT_SECRET")
    if not cid or not sec:
        sys.exit("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 가 없어요")
    H = {"X-NCP-APIGW-API-KEY-ID": cid, "X-NCP-APIGW-API-KEY": sec}
    now = dt.datetime.now(KST)
    since = now - dt.timedelta(hours=LOOKBACK_H)

    clips = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else []
    known_urls = {c["url"] for c in clips}
    recent_titles = [c["title"] for c in clips if c.get("date", "") >= (now - dt.timedelta(days=4)).strftime("%Y-%m-%d")]
    known_ids = {c["id"] for c in clips}

    cand = {}
    for q in QUERIES:
        for it in fetch(q, H):
            try:
                pub = parsedate_to_datetime(it["pubDate"]).astimezone(KST)
            except Exception:
                continue
            if pub < since:
                continue
            url = it.get("originallink") or it.get("link")
            title, desc = clean(it.get("title")), clean(it.get("description"))
            text = title + " " + desc
            if not url or url in known_urls or url in cand:
                continue
            if not HANWHA.search(text) or NOT_BASEBALL.search(text) or not BASEBALL.search(text):
                continue
            # 한화가 중심인 기사만: 제목에 한화/이글스 또는 한화 감독·선수 이름
            if not (HANWHA.search(title) or HH_NAMES.search(title)):
                continue
            if NOT_BASEBALL.search(title):
                continue
            cand[url] = {"pub": pub, "title": title, "desc": desc, "url": url}
        time.sleep(0.1)

    # 최신순으로 보며 같은 기사(제목이 거의 같은 것)는 하나만
    picked = []
    for c in sorted(cand.values(), key=lambda x: x["pub"], reverse=True):
        if any(similar(c["title"], p["title"]) for p in picked) or any(similar(c["title"], t) for t in recent_titles):
            continue
        picked.append(c)

    added = []
    for c in picked:
        base = c["pub"].strftime("%Y%m%d") + "-n" + c["pub"].strftime("%H%M")
        i, n = base, 1
        while i in known_ids:
            n += 1
            i = f"{base}-{n}"
        known_ids.add(i)
        summary = c["desc"]
        if len(summary) > 140:
            summary = summary[:139].rstrip() + "…"
        added.append({
            "id": i, "date": c["pub"].strftime("%Y-%m-%d"), "category": category_of(c["title"] + " " + c["desc"]),
            "title": c["title"], "summary": summary, "source": source_of(c["url"]), "url": c["url"],
            "addedAt": now.isoformat(timespec="minutes"), "pubAt": c["pub"].isoformat(timespec="minutes"),
        })

    if not added:
        print("새 기사 없음")
        return
    clips += added
    clips.sort(key=lambda x: (x.get("date", ""), x.get("pubAt") or x.get("addedAt", "")), reverse=True)
    OUT.write_text(json.dumps(clips, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"추가 {len(added)}건")
    for a in added:
        print(" -", a["date"], a["category"], a["title"], "|", a["source"])
    nf = os.environ.get("NOTIFY_FILE")
    if nf:  # 알림용: 건수와 가장 최근 기사 제목
        Path(nf).write_text(json.dumps({"count": len(added), "first": added[0]["title"]}, ensure_ascii=False), encoding="utf-8")
    gh = os.environ.get("GITHUB_OUTPUT")
    if gh:
        with open(gh, "a", encoding="utf-8") as f:
            f.write(f"added={len(added)}\n")


if __name__ == "__main__":
    main()
