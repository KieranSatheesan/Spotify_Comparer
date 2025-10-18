# review_and_add.py
# Interactive CLI to review not_liked_alltime_kworb.csv and build a playlist
# "Spotify_Comparer: Top Streamed Songs".
#
# Controls:
#   k = keep (add to playlist)
#   s = skip
#   o = open Spotify URL in browser
#   b = back to previous
#   q = quit (saves progress)
#   ? = help
#
# Files:
#   INPUT : not_liked_alltime_kworb.csv  (rank,title,artist,streams,spotify_url,track_id)
#   OUTPUT: decisions.csv (append-only log of keep/skip with timestamp)
#           kept.csv      (append-only log of kept tracks with timestamp)
#
# Requirements: pip install spotipy python-dotenv ftfy

from __future__ import annotations
import os, csv, sys, webbrowser, re, unicodedata
from datetime import datetime, timezone
from typing import List, Dict, Optional
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from ftfy import fix_text

# Make console UTF-8 (fixes mojibake in Windows)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

INPUT_CSV = "not_liked_alltime_kworb.csv"
DECISIONS_CSV = "decisions.csv"
KEPT_CSV = "kept.csv"
PLAYLIST_NAME = "Spotify_Comparer: Top Streamed Songs"

# If a row lacks track_id, try to resolve via a smarter quick search:
ENABLE_SEARCH_FALLBACK = True
SEARCH_LIMIT = 5

def de_mojibake(s: str) -> str:
    return fix_text(s or "")

def read_candidates(path: str) -> List[Dict]:
    rows: List[Dict] = []
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            # fix any mojibake before showing/searching
            row["title"] = de_mojibake(row.get("title") or "")
            row["artist"] = de_mojibake(row.get("artist") or "")
            try:
                row["streams"] = int(row.get("streams", "0"))
            except Exception:
                row["streams"] = 0
            rows.append(row)
    rows.sort(key=lambda x: x["streams"], reverse=True)
    return rows

def read_decisions(path: str) -> Dict[str, str]:
    if not os.path.exists(path):
        return {}
    out: Dict[str, str] = {}
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            key = row.get("key") or ""
            dec = row.get("decision") or ""
            if key and dec:
                out[key] = dec
    return out

def append_decision(path: str, row: Dict):
    file_exists = os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "timestamp","decision","key","track_id","title","artist","streams","spotify_url"
        ])
        if not file_exists:
            w.writeheader()
        w.writerow(row)

def append_kept(path: str, row: Dict):
    file_exists = os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "timestamp","track_id","title","artist","streams","spotify_url","playlist_id"
        ])
        if not file_exists:
            w.writeheader()
        w.writerow(row)

def make_key(r: Dict) -> str:
    tid = (r.get("track_id") or "").strip()
    if tid:
        return f"id:{tid}"
    title = (r.get("title") or "").strip()
    artist = (r.get("artist") or "").strip()
    streams = str(r.get("streams") or "")
    return f"txt:{title}|{artist}|{streams}"

def get_sp_client() -> spotipy.Spotify:
    load_dotenv()
    cid = os.getenv("SPOTIPY_CLIENT_ID")
    sec = os.getenv("SPOTIPY_CLIENT_SECRET")
    redir = os.getenv("SPOTIPY_REDIRECT_URI", "http://localhost:8888/callback")
    if not cid or not sec:
        sys.exit("Missing SPOTIPY_CLIENT_ID/SECRET in .env")
    scopes = "playlist-modify-private playlist-modify-public user-library-read"
    auth = SpotifyOAuth(
        client_id=cid, client_secret=sec, redirect_uri=redir,
        scope=scopes, cache_path=".spotipyoauthcache", show_dialog=False
    )
    return spotipy.Spotify(auth_manager=auth)

def get_or_create_playlist(sp: spotipy.Spotify, name: str) -> str:
    me = sp.current_user()
    uid = me["id"]
    limit, offset = 50, 0
    while True:
        resp = sp.current_user_playlists(limit=limit, offset=offset)
        items = resp.get("items") or []
        for pl in items:
            if pl.get("name") == name and pl.get("owner",{}).get("id") == uid:
                return pl["id"]
        if len(items) < limit:
            break
        offset += limit
    created = sp.user_playlist_create(uid, name, public=False, description="Built by Spotify_comparer CLI")
    return created["id"]

# ------- smarter search helpers -------
def _strip_diacritics(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")

def _clean_title_for_search(s: str) -> str:
    s = s or ""
    s = re.sub(r'\s*\(.*?\)', '', s)   # drop (...) like (with …), (Remaster)
    s = re.sub(r'\s*\[.*?\]', '', s)   # drop […]
    s = s.replace("–", "-")
    return s.strip()
# --------------------------------------

def ensure_track_id(sp: spotipy.Spotify, row: Dict) -> Optional[str]:
    tid = (row.get("track_id") or "").strip()
    if tid:
        return tid
    url = (row.get("spotify_url") or "").strip()
    if "open.spotify.com/track/" in url:
        try:
            return url.split("open.spotify.com/track/")[1].split("?")[0].split("/")[0]
        except Exception:
            pass
    if not ENABLE_SEARCH_FALLBACK:
        return None

    title = _clean_title_for_search(de_mojibake(row.get("title") or ""))
    artist = de_mojibake(row.get("artist") or "")

    title_plain = _strip_diacritics(title)
    artist_plain = _strip_diacritics(artist)

    queries = [
        f'track:"{title}" artist:"{artist}"',
        f'{title} {artist}',
        f'track:"{title_plain}" artist:"{artist_plain}"',
        f'{title_plain} {artist_plain}',
        title_plain,
        title,
    ]

    seen = set()
    for q in queries:
        try:
            res = sp.search(q=q, type="track", limit=SEARCH_LIMIT)
        except Exception:
            continue
        items = (res.get("tracks") or {}).get("items") or []
        for tr in items:
            cand = tr.get("id")
            if not cand or cand in seen:
                continue
            seen.add(cand)
            return cand
    return None

def add_to_playlist(sp: spotipy.Spotify, playlist_id: str, track_ids: List[str]):
    chunk = 100
    for i in range(0, len(track_ids), chunk):
        sp.playlist_add_items(playlist_id, track_ids[i:i+chunk])

def print_header():
    print("\nControls: [k]eep  [s]kip  [o]pen  [b]ack  [q]uit  [?]help")
    print("------------------------------------------------------------------")

def main():
    if not os.path.exists(INPUT_CSV):
        sys.exit(f"Missing {INPUT_CSV}. Run your kworb script first.")
    rows = read_candidates(INPUT_CSV)
    sp = get_sp_client()
    me_info = sp.current_user()
    me = me_info.get("display_name") or me_info.get("id")
    print(f"Authenticated as: {me}")

    playlist_id = get_or_create_playlist(sp, PLAYLIST_NAME)
    print(f'Using playlist: "{PLAYLIST_NAME}" (id={playlist_id})')

    decisions = read_decisions(DECISIONS_CSV)
    index = 0
    print_header()

    while index < len(rows):
        r = rows[index]
        key = make_key(r)
        if decisions.get(key) in ("keep", "skip"):
            index += 1
            continue

        title = r.get("title") or ""
        artist = r.get("artist") or ""
        try:
            streams = int(r.get("streams") or 0)
        except:
            streams = 0
        url = r.get("spotify_url") or ""
        print(f"\n[{index+1}/{len(rows)}] {title} — {artist}  | streams={streams:,}")
        if url:
            print(f"URL: {url}")

        cmd = input("Decision [k/s/o/b/q/?]: ").strip().lower()

        if cmd in ("?", "h"):
            print_header(); continue

        if cmd == "o":
            if url: webbrowser.open(url)
            else: print("No URL available.")
            continue

        if cmd == "b":
            j = index - 1
            while j >= 0:
                if decisions.get(make_key(rows[j])) not in ("keep", "skip"):
                    index = j; break
                j -= 1
            if j < 0: print("No previous undecided item.")
            continue

        if cmd == "q":
            print("Exiting. Progress saved to decisions.csv / kept.csv"); break

        if cmd not in ("k", "s"):
            print("Please type k/s/o/b/q/?"); continue

        ts = datetime.now(timezone.utc).isoformat()
        if cmd == "s":
            append_decision(DECISIONS_CSV, {
                "timestamp": ts, "decision": "skip", "key": key,
                "track_id": r.get("track_id") or "", "title": title,
                "artist": artist, "streams": streams, "spotify_url": url
            })
            decisions[key] = "skip"
            index += 1
            continue

        # keep
        tid = ensure_track_id(sp, r)
        if not tid:
            print("Couldn't resolve a Spotify track ID; not added. (Use 'o' to open & verify.)")
            retry = input("Mark as skip (y) or leave undecided (n)? [y/n]: ").strip().lower()
            if retry != "n":
                ts = datetime.now(timezone.utc).isoformat()
                append_decision(DECISIONS_CSV, {
                    "timestamp": ts, "decision": "skip", "key": key,
                    "track_id": "", "title": title,
                    "artist": artist, "streams": streams, "spotify_url": url
                })
                decisions[key] = "skip"
                index += 1
            continue

        try:
            add_to_playlist(sp, playlist_id, [tid])
        except Exception as e:
            print(f"Add failed: {e}")
            continue

        ts = datetime.now(timezone.utc).isoformat()
        append_decision(DECISIONS_CSV, {
            "timestamp": ts, "decision": "keep", "key": key,
            "track_id": tid, "title": title,
            "artist": artist, "streams": streams, "spotify_url": url
        })
        append_kept(KEPT_CSV, {
            "timestamp": ts, "track_id": tid, "title": title,
            "artist": artist, "streams": streams, "spotify_url": url,
            "playlist_id": playlist_id
        })
        decisions[key] = "keep"
        print("✓ Added to playlist.")
        index += 1

    print("Done.")

if __name__ == "__main__":
    main()
