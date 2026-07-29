#!/usr/bin/env python3
import json
import re
import sys
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

TEAM_URL = "https://zolotaybutsa.ru/team/1304217"
TEAM_NAME = "ФА ОТДАЙ ПАС"
OUT_PATH = "data/matches.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; OtdayPasBot/1.0; +https://otdaypas.ru)"}

RU_MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}


def parse_ru_datetime(date_text, time_text):
    m = re.match(r"^(\d{1,2})\s+([а-яё]+)\s+(\d{4})$", date_text.strip(), re.IGNORECASE)
    if not m:
        return None
    day, month_name, year = m.groups()
    month = RU_MONTHS.get(month_name.lower())
    if not month:
        return None
    hh, mm = 0, 0
    tm = re.match(r"^(\d{1,2}):(\d{2})$", (time_text or "").strip())
    if tm:
        hh, mm = int(tm.group(1)), int(tm.group(2))
    try:
        return datetime(int(year), month, int(day), hh, mm)
    except ValueError:
        return None


def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def get_recent_match_ids():
    soup = fetch(TEAM_URL)
    ids = []
    for a in soup.select('a[href^="/match/"]'):
        href = a.get("href", "")
        m = re.match(r"^/match/(\d+)$", href)
        if m and m.group(1) not in ids:
            ids.append(m.group(1))
    return ids


def text_of(el):
    return el.get_text(strip=True) if el else ""


def parse_match(match_id):
    soup = fetch(f"https://zolotaybutsa.ru/match/{match_id}")
    game = soup.select_one("section.game")
    if not game:
        return None

    units = game.select(".game__unit")
    if len(units) != 2:
        return None
    team_names = [text_of(u.select_one(".game__team-name")) for u in units]

    scores = [text_of(s) for s in game.select(".score__item")]
    scores = [s for s in scores if s != ""]
    if len(scores) < 2:
        return None

    home, away = team_names[0], team_names[1]
    score_home, away_score = scores[0], scores[1]

    is_home = TEAM_NAME in home
    is_away = TEAM_NAME in away
    if not is_home and not is_away:
        return None

    opponent = away if is_home else home
    our_score_s = score_home if is_home else away_score
    opp_score_s = away_score if is_home else score_home

    result = None
    try:
        our_score, opp_score = int(our_score_s), int(opp_score_s)
        result = "В" if our_score > opp_score else ("П" if our_score < opp_score else "Н")
    except ValueError:
        our_score, opp_score = None, None

    date_text = text_of(game.select_one(".game__date"))
    time_text = text_of(game.select_one(".game__time"))
    dt = parse_ru_datetime(date_text, time_text)

    return {
        "id": match_id,
        "date": date_text,
        "weekday": text_of(game.select_one(".game__info-middle")),
        "time": time_text,
        "sort_key": dt.isoformat() if dt else "",
        "venue": text_of(game.select_one(".game__stadium")),
        "tournament": text_of(game.select_one(".game__tournament")),
        "division": text_of(game.select_one(".game__round")),
        "tour": text_of(game.select_one(".game__tour")),
        "is_home": is_home,
        "opponent": opponent,
        "our_score": our_score,
        "opp_score": opp_score,
        "result": result,
        "source_url": f"https://zolotaybutsa.ru/match/{match_id}",
    }


def main():
    ids = get_recent_match_ids()
    matches = []
    for mid in ids:
        try:
            m = parse_match(mid)
            if m:
                matches.append(m)
        except Exception as e:
            print(f"skip {mid}: {e}", file=sys.stderr)

    # dedupe (site lists some match links more than once), then sort by real
    # match date/time, newest first -- do NOT rely on link order in the page.
    seen = set()
    deduped = []
    for m in matches:
        if m["id"] in seen:
            continue
        seen.add(m["id"])
        deduped.append(m)
    ordered = sorted(deduped, key=lambda m: m["sort_key"], reverse=True)

    out = {
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "team": TEAM_NAME,
        "source": TEAM_URL,
        "matches": ordered,
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"wrote {len(ordered)} matches to {OUT_PATH}")


if __name__ == "__main__":
    main()
