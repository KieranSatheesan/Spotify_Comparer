# 🎧 Spotify Comparer — Top Streamed vs Liked Songs

A Python + Streamlit tool that compares your Spotify **Liked Songs** to the **most streamed songs of all time** (via [Kworb.net](https://kworb.net/spotify/)).  
Discover which global hits you *don’t* have liked — and add them directly to your own playlist.

## Features
- Fetches the current all-time most streamed tracks on Spotify.
- Compares against your personal Liked Songs.
- Generates clean CSV summaries.
- Interactive web app (Streamlit) to review, preview, and add songs.
- Automatic playlist creation: `Spotify_Comparer: Top Streamed Songs`.

## Scripts
| Script | Purpose |
|--------|----------|
| `compare_kworb_to_liked.py` | Fetch + compare top streamed vs your liked songs |
| `streamlit_spotify_comparer.py` | Streamlit web app to browse and add songs interactively |

## Setup
```bash
git clone https://github.com/<yourusername>/spotify-comparer.git
cd spotify-comparer
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt