# app.py — Streamlit reviewer for "Top Streamed Songs"
# Run: streamlit run app.py
# Uses: not_liked_alltime_kworb.csv, decisions.csv, kept.csv, your Spotify account/playlist
from __future__ import annotations

import os, csv, re, unicodedata, webbrowser
from typing import List, Dict, Optional
import streamlit as st
import requests
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from ftfy import fix_text

INPUT_CSV     = "not_liked_alltime_kworb.csv"
DECISIONS_CSV = "decisions.csv"
KEPT_CSV      = "kept.csv"
PLAYLIST_NAME = "Spotify_Comparer: Top Streamed Songs"

ENABLE_SEARCH_FALLBACK = True
SEARCH_LIMIT = 5

# ---------- text helpers ----------
def de_mojibake(s: str) -> str:
    return fix_text(s or "")

def strip_diacritics(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")

def clean_title_for_search(s: str) -> str:
    s = s or ""
    s = re.sub(r"\s*\(.*?\)", "", s)  # drop (...) like (with …), (Remaster), etc.
    s = re.sub(r"\s*\[.*?\]", "", s)  # drop […]
    s = s.replace("–", "-")
    return s.strip()

# ---------- I/O ----------
@st.cache_data(show_spinner=False)
def load_candidates(path: str) -> List[Dict]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Missing {path}. Run kworb_vs_liked.py first.")
    rows: List[Dict] = []
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            row["title"]  = de_mojibake(row.get("title")  or "")
            row["artist"] = de_mojibake(row.get("artist") or "")
            try:
                row["streams"] = int(row.get("streams", "0"))
            except:
                row["streams"] = 0
            rows.append(row)
    rows.sort(key=lambda x: x["streams"], reverse=True)
    return rows

@st.cache_data(show_spinner=False)
def load_decisions(path: str) -> Dict[str, str]:
    if not os.path.exists(path):
        return {}
    out: Dict[str, str] = {}
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            k = row.get("key") or ""
            d = row.get("decision") or ""
            if k and d:
                out[k] = d
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

# ---------- Spotify ----------
@st.cache_resource(show_spinner=False)
def get_sp_client() -> spotipy.Spotify:
    load_dotenv()
    cid = os.getenv("SPOTIPY_CLIENT_ID")
    sec = os.getenv("SPOTIPY_CLIENT_SECRET")
    redir = os.getenv("SPOTIPY_REDIRECT_URI", "http://localhost:8888/callback")
    if not cid or not sec:
        st.stop()
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
    created = sp.user_playlist_create(uid, name, public=False, description="Built by Spotify_comparer Streamlit app")
    return created["id"]

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

    title  = clean_title_for_search(de_mojibake(row.get("title") or ""))
    artist = de_mojibake(row.get("artist") or "")
    title_plain  = strip_diacritics(title)
    artist_plain = strip_diacritics(artist)

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
            return cand
    return None

def fetch_track_meta(sp: spotipy.Spotify, track_id: str) -> Dict:
    try:
        tr = sp.track(track_id)
        return tr or {}
    except Exception:
        return {}

def add_to_playlist(sp: spotipy.Spotify, playlist_id: str, track_ids: List[str]):
    if not track_ids:
        return
    sp.playlist_add_items(playlist_id, track_ids)

# ---------- UI ----------
st.set_page_config(page_title="Spotify Comparer — Top Streamed Reviewer", page_icon="🎧", layout="centered")

st.title("🎧 Spotify Comparer — Top Streamed Reviewer")
st.caption("Review not-liked all-time streamed songs and build your playlist. Keep/Skip and resume anytime.")

cols = st.columns([1,1,1])
with cols[0]:
    st.write("CSV:", f"`{INPUT_CSV}`")
with cols[1]:
    st.write("Log:", f"`{DECISIONS_CSV}`")
with cols[2]:
    st.write("Kept:", f"`{KEPT_CSV}`")

# Load data
rows = load_candidates(INPUT_CSV)
decisions = load_decisions(DECISIONS_CSV)

# Session state
if "index" not in st.session_state:
    st.session_state.index = 0
if "playlist_id" not in st.session_state:
    st.session_state.playlist_id = None

sp = get_sp_client()

# Setup playlist (cached for run)
if not st.session_state.playlist_id:
    st.session_state.playlist_id = get_or_create_playlist(sp, PLAYLIST_NAME)

# Skip already-decided items to resume
while st.session_state.index < len(rows):
    if decisions.get(make_key(rows[st.session_state.index])) in ("keep", "skip"):
        st.session_state.index += 1
    else:
        break

if st.session_state.index >= len(rows):
    st.success("🎉 All done — nothing left to review!")
    st.stop()

r = rows[st.session_state.index]
key = make_key(r)

left = len(rows) - st.session_state.index
st.progress(st.session_state.index / len(rows), text=f"{st.session_state.index+1}/{len(rows)} reviewed")

title  = r.get("title") or ""
artist = r.get("artist") or ""
streams = int(r.get("streams") or 0)
url = r.get("spotify_url") or ""

st.subheader(f"{title}")
st.write(f"**Artist:** {artist} &nbsp; · &nbsp; **Streams:** {streams:,}")
if url:
    st.link_button("Open in Spotify", url, type="secondary")

# Try to get track id (for art/preview). We don't commit the decision yet.
tid = ensure_track_id(sp, r)

# Show album art & preview if we found a track
album_img_url = None
preview_url = None
if tid:
    meta = fetch_track_meta(sp, tid)
    images = ((meta.get("album") or {}).get("images") or [])
    if images:
        album_img_url = images[0].get("url")
    preview_url = meta.get("preview_url")

media_cols = st.columns([1,2])
with media_cols[0]:
    if album_img_url:
        st.image(album_img_url, use_container_width=True)
with media_cols[1]:
    if preview_url:
        st.audio(preview_url)
    else:
        st.caption("No 30s preview available for this track.")

st.divider()

btn_cols = st.columns(3)
with btn_cols[0]:
    back = st.button("⬅️ Back", use_container_width=True)
with btn_cols[1]:
    skip = st.button("Skip", type="secondary", use_container_width=True)
with btn_cols[2]:
    keep = st.button("✅ Keep (add to playlist)", type="primary", use_container_width=True)

# Handlers
from datetime import datetime, timezone
def log_decision(decision: str, track_id_for_log: str = ""):
    ts = datetime.now(timezone.utc).isoformat()
    append_decision(DECISIONS_CSV, {
        "timestamp": ts, "decision": decision, "key": key,
        "track_id": track_id_for_log, "title": title, "artist": artist,
        "streams": streams, "spotify_url": url
    })

if back:
    # Move back to previous undecided
    j = st.session_state.index - 1
    while j >= 0:
        if decisions.get(make_key(rows[j])) not in ("keep", "skip"):
            st.session_state.index = j
            st.rerun()
        j -= 1
    st.info("No previous undecided item.")
    st.stop()

if skip:
    log_decision("skip", r.get("track_id") or "")
    decisions[key] = "skip"
    st.session_state.index += 1
    st.rerun()

if keep:
    if not tid:
        st.warning("Couldn't resolve a Spotify track ID. Try 'Open in Spotify' to verify.")
    else:
        try:
            add_to_playlist(sp, st.session_state.playlist_id, [tid])
        except Exception as e:
            st.error(f"Add failed: {e}")
        else:
            ts = datetime.now(timezone.utc).isoformat()
            append_kept(KEPT_CSV, {
                "timestamp": ts, "track_id": tid, "title": title, "artist": artist,
                "streams": streams, "spotify_url": url, "playlist_id": st.session_state.playlist_id
            })
            log_decision("keep", tid)
            decisions[key] = "keep"
            st.session_state.index += 1
            st.success("Added to playlist!")
            st.rerun()
