# kworb_vs_liked.py
# Compare Kworb "all-time most streamed" vs your Liked Songs using:
# 1) direct track ID match, OR
# 2) normalized Title match + overlapping Artist sets (handles feat/with, remasters, soundtracks, primary-artist swaps).
#
# Outputs TWO CSVs: not_liked_alltime_kworb.csv and liked_alltime_kworb.csv
#
# Requirements: pip install requests beautifulsoup4 spotipy python-dotenv ftfy

from __future__ import annotations
import os, re, csv, html, unicodedata
from typing import List, Dict, Set, Tuple, Optional
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from ftfy import fix_text

# ---------------- Config ----------------
KWORB_URLS = [
    "https://kworb.net/spotify/songs.html",
    "https://kworb.net/spotify_songs.html",  # fallback (old path)
]
TOP_N = 3000
PRINT_TOP = 50

NOT_LIKED_CSV = "not_liked_alltime_kworb.csv"
LIKED_CSV     = "liked_alltime_kworb.csv"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/122.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://kworb.net/",
}
# ----------------------------------------

# =========== Mojibake fix ===========
def de_mojibake(s: str) -> str:
    return fix_text(s or "")
# ====================================

# =========== Normalization helpers ===========
def _strip_diacritics(s: str) -> str:
    # Señorita -> Senorita
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")

def _clean_feat_words(s: str) -> str:
    # remove 'feat/featuring/with …' segments
    return re.sub(r"\b(feat\.?|featuring|with)\b.*", "", s, flags=re.I)

def _clean_version_tags(s: str) -> str:
    # remove common edition/version tags in () or [] or after a dash
    s = re.sub(r"\s*-\s*(single|album|deluxe|live|radio edit|remaster(ed)?|version|edit|instrumental)\b.*", "", s, flags=re.I)
    s = re.sub(r"\s*\((?:live|radio edit|remaster(?:ed)?|version|edit|deluxe|single|album|demo|acoustic)[^)]*\)", "", s, flags=re.I)
    s = re.sub(r"\s*\[[^\]]*\]", "", s)
    return s

def _clean_soundtrack_stuff(s: str) -> str:
    # remove soundtrack / "From ..." / after long dashes
    s = re.sub(r"\s*-\s*from\s+\"[^\"]+\"", "", s, flags=re.I)
    s = re.sub(r"\s*-\s*from\s+’[^’]+’", "", s, flags=re.I)
    s = re.sub(r"\s*-\s*from\s+[^-]+$", "", s, flags=re.I)
    s = re.sub(r"\s*-\s*spider[- ]?man:.*$", "", s, flags=re.I)
    return s

def normalize_title(raw: str) -> str:
    s = de_mojibake(html.unescape(raw or ""))
    s = s.replace("–", "-")
    s = _clean_feat_words(s)
    s = _clean_version_tags(s)
    s = _clean_soundtrack_stuff(s)
    s = s.split(" - ")[0]
    s = s.split(" — ")[0]
    s = _strip_diacritics(s)
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s

def _split_artists(raw: str) -> List[str]:
    s = de_mojibake(html.unescape(raw or ""))
    s = re.sub(r"\s*(,|&| and | x | × |;|\+)\s*", ",", s, flags=re.I)
    s = re.sub(r"\s*\b(feat\.?|featuring|with)\b\s*", ",", s, flags=re.I)
    parts = [p.strip() for p in s.split(",") if p.strip()]
    return parts if parts else [s.strip()]

def normalize_artist_name(name: str) -> str:
    s = _clean_feat_words(de_mojibake(name))
    s = _strip_diacritics(s)
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s

def artist_set(raw: str) -> Set[str]:
    return {normalize_artist_name(p) for p in _split_artists(raw)}
# ============================================

# =========== Spotify helpers ===========
def get_all_saved_tracks(sp: spotipy.Spotify) -> List[Dict]:
    """Return full metadata for liked tracks (id, name, artists)."""
    out: List[Dict] = []
    limit, offset = 50, 0
    while True:
        resp = sp.current_user_saved_tracks(limit=limit, offset=offset)
        items = resp.get("items") or []
        if not items:
            break
        for it in items:
            tr = (it or {}).get("track") or {}
            if not tr:
                continue
            artists = ", ".join(a.get("name", "") for a in (tr.get("artists") or []))
            out.append(
                {
                    "id": tr.get("id") or "",
                    "name": tr.get("name") or "",
                    "artists": artists,
                }
            )
        offset += len(items)
    return out
# =======================================

# =========== Kworb scraping ===========
def extract_track_id_from_url(url: str) -> str:
    if not isinstance(url, str):
        return ""
    m = re.search(r"open\.spotify\.com/track/([A-Za-z0-9]+)", url)
    return m.group(1) if m else ""

def split_artist_title(s: str) -> Tuple[str, str]:
    s = s.strip()
    if " – " in s:
        return s.split(" – ", 1)
    if " - " in s:
        return s.split(" - ", 1)
    parts = re.split(r"\s[-–]\s", s)
    return (parts[0], parts[1]) if len(parts) >= 2 else ("", s)

def fetch_kworb_rows(max_rows: int = TOP_N) -> List[Dict]:
    last_err: Optional[Exception] = None
    for url in KWORB_URLS:
        try:
            r = requests.get(url, headers=HEADERS, timeout=25)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")

            target = None
            for tbl in soup.select("table"):
                hdrs = [th.get_text(strip=True).lower() for th in tbl.select("tr th")]
                if any("artist and title" in h for h in hdrs) and any("streams" in h for h in hdrs):
                    target = tbl
                    break
            if target is None:
                raise RuntimeError("Couldn't find Kworb all-time table.")

            headers = [th.get_text(strip=True) for th in target.select("tr th")]
            art_title_col = next((i for i,h in enumerate(headers) if "artist and title" in h.lower()), None)
            streams_col   = next((i for i,h in enumerate(headers) if "streams" in h.lower()), None)
            rank_col      = next((i for i,h in enumerate(headers) if "position" in h.lower() or "rank" in h.lower()), None)
            if art_title_col is None or streams_col is None:
                raise RuntimeError("Kworb table missing expected columns.")

            out: List[Dict] = []
            for tr in target.select("tr")[1:]:
                tds = tr.find_all("td")
                if not tds:
                    continue
                cells = [fix_text(td.get_text(" ", strip=True)) for td in tds]
                if len(cells) <= max(art_title_col, streams_col):
                    continue

                artist_title = de_mojibake(cells[art_title_col])
                if not artist_title:
                    continue
                artist, title = split_artist_title(artist_title)

                streams_txt = cells[streams_col]
                streams = int(re.sub(r"[^\d]", "", streams_txt) or 0)
                if streams <= 0:
                    continue

                # Try to grab Spotify link/ID if present
                spotify_url, track_id = "", ""
                link = tds[art_title_col].find("a", href=True)
                if link:
                    href = link["href"]
                    if "open.spotify.com/track/" in href:
                        spotify_url = href
                        track_id = extract_track_id_from_url(href)
                    else:
                        m = re.search(r"/track/([A-Za-z0-9]{10,})", href)
                        if m:
                            track_id = m.group(1)
                            spotify_url = f"https://open.spotify.com/track/{track_id}"

                rank = None
                if rank_col is not None and len(cells) > rank_col:
                    try: rank = int(re.sub(r"[^\d]", "", cells[rank_col]))
                    except: rank = None

                out.append({
                    "rank": rank,
                    "artist": artist,
                    "title": title,
                    "streams": streams,
                    "spotify_url": spotify_url,
                    "track_id": track_id,
                })
                if len(out) >= max_rows:
                    break

            if not out:
                raise RuntimeError("Parsed zero rows from Kworb.")
            return out

        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"Failed to fetch Kworb table: {last_err}")
# =======================================

def main():
    load_dotenv()
    client_id = os.getenv("SPOTIPY_CLIENT_ID")
    client_secret = os.getenv("SPOTIPY_CLIENT_SECRET")
    redirect_uri = os.getenv("SPOTIPY_REDIRECT_URI", "http://localhost:8888/callback")
    if not client_id or not client_secret:
        raise SystemExit("Missing SPOTIPY_CLIENT_ID/SECRET in .env")

    sp = spotipy.Spotify(
        auth_manager=SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope="user-library-read",
            cache_path=".spotipyoauthcache",
            show_dialog=False,
        )
    )
    me = sp.current_user()
    print("Authenticated as:", me.get("display_name") or me.get("id"))

    print("Fetching Kworb all-time table…")
    rows = fetch_kworb_rows(TOP_N)
    print(f"Kworb rows parsed: {len(rows)}")

    print("Fetching your Liked Songs…")
    liked_tracks = get_all_saved_tracks(sp)
    print("Liked tracks:", len(liked_tracks))

    # Build liked sets (ID + title→artistset), with mojibake fix applied
    liked_ids: Set[str] = {t["id"] for t in liked_tracks if t["id"]}
    title_to_artistset: Dict[str, Set[str]] = {}
    for t in liked_tracks:
        lt = normalize_title(de_mojibake(t["name"]))
        aset = artist_set(de_mojibake(t["artists"]))
        title_to_artistset.setdefault(lt, set()).update(aset)

    # Split rows into liked vs not liked:
    liked_rows: List[Dict] = []
    not_liked_rows: List[Dict] = []

    for r in rows:
        # 1) ID match
        id_match = r["track_id"] in liked_ids if r["track_id"] else False

        # 2) Title + Artist overlap
        t_norm = normalize_title(de_mojibake(r["title"]))
        kw_aset = artist_set(de_mojibake(r["artist"]))
        liked_aset = title_to_artistset.get(t_norm, set())
        name_match = bool(liked_aset and (kw_aset & liked_aset))

        if id_match or name_match:
            liked_rows.append(r)
        else:
            not_liked_rows.append(r)

    # Sort and save
    liked_rows.sort(key=lambda x: x["streams"], reverse=True)
    not_liked_rows.sort(key=lambda x: x["streams"], reverse=True)

    print(f"\nMatched as LIKED: {len(liked_rows)}")
    print(f"Remaining NOT LIKED: {len(not_liked_rows)}")

    print("\nTop NOT LIKED (by streams):\n")
    for i, r in enumerate(not_liked_rows[:PRINT_TOP], start=1):
        print(f"{i:>3}. {r['title']} — {r['artist']}  (streams={r['streams']:,})  {r['spotify_url']}")

    fields = ["rank", "title", "artist", "streams", "spotify_url", "track_id"]
    if liked_rows:
        with open(LIKED_CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for r in liked_rows:
                w.writerow(r)
        print(f"\nSaved {len(liked_rows)} rows to {LIKED_CSV}")

    if not_liked_rows:
        with open(NOT_LIKED_CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for r in not_liked_rows:
                w.writerow(r)
        print(f"Saved {len(not_liked_rows)} rows to {NOT_LIKED_CSV}")


if __name__ == "__main__":
    main()
