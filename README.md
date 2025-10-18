# 🎧 Spotify Comparer — Top Streamed vs Liked Songs  

Wanted to see which of Spotify’s **most streamed songs of all time** weren’t already in my own **Liked Songs**… so I built a small tool to find out.  

A Python + Streamlit project that compares your Spotify **Liked Songs** to the **most streamed songs ever** (via [Kworb.net](https://kworb.net/spotify/)).  
Discover which global hits you *don’t* have liked — and add them directly to your own playlist.

---

## 💡 Motivation  

I wanted to see which songs from Spotify’s *most streamed ever* list I somehow didn’t have in my Liked Songs.  
To my surprise, I was missing **Cruel Summer — Taylor Swift** (banger).  
A little less surprising was **Clean Baby Sleep White Noise (Loopable)** — although technically still a “top streamed song.”  

So I made a small personal project to find the overlap (or lack thereof) — and turned it into something others could easily reuse too.

---

## 🚀 Features  
- Fetches the current **all-time most streamed songs** on Spotify.  
- Compares them with your **personal Liked Songs** using the Spotify API.  
- Generates neat CSV summaries (`liked_alltime_kworb.csv`, `not_liked_alltime_kworb.csv`).  
- Offers both:
  - 🧠 **CLI interface** to step through tracks and add them to a playlist.  
  - 🌐 **Streamlit web app** to browse, preview, and add songs interactively.  
- Automatically creates or updates a playlist:  
  > `Spotify_Comparer: Top Streamed Songs`

---

## 🧰 Scripts  

| Script | Purpose |
|--------|----------|
| `compare_kworb_to_liked.py` | Fetch and compare top streamed vs your Liked Songs |
| `cli_playlist_builder.py` | Interactive command-line tool to review and add songs |
| `spotify_comparer_app.py` | Streamlit web app interface for browsing and adding |
| `.env` *(not committed)* | Holds your Spotify API credentials (see below) |

---

## ⚙️ Setup  

Clone the repo and create your virtual environment:

```bash
git clone https://github.com/<yourusername>/spotify-comparer.git
cd spotify-comparer
python -m venv .venv
.\.venv\Scripts\activate  # (on macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
```

Then create a `.env` file in the project root with your Spotify Developer credentials:

```
SPOTIPY_CLIENT_ID=your_client_id
SPOTIPY_CLIENT_SECRET=your_client_secret
SPOTIPY_REDIRECT_URI=http://127.0.0.1:8888/callback
```

You can get these from [Spotify for Developers](https://developer.spotify.com/dashboard/).  
Make sure your redirect URI matches exactly (`http://127.0.0.1:8888/callback`).

---

## ▶️ How to Run  

### Option 1: Compare + CSV output
```bash
python compare_kworb_to_liked.py
```
This will create two CSVs:
- `liked_alltime_kworb.csv`
- `not_liked_alltime_kworb.csv`

---

### Option 2: CLI playlist builder
```bash
python cli_playlist_builder.py
```
Interactively review each unliked song — press:
- `k` to keep (add to playlist)  
- `s` to skip  
- `o` to open in browser  

---

### Option 3: Streamlit web app
```bash
streamlit run spotify_comparer_app.py
```
Opens a simple browser interface to review, play previews, and add songs with a click.

---

## 📁 Folder Overview  

| Path | Description |
|------|--------------|
| `compare_kworb_to_liked.py` | Core comparison logic |
| `cli_playlist_builder.py` | Command-line playlist tool |
| `spotify_comparer_app.py` | Streamlit web UI |
| `requirements.txt` | Python dependencies |
| `.gitignore` | Clean repo setup |
| `not_liked_alltime_kworb.csv` | Example output file |
| `example_decisions.csv` | Example of interactive session log |
| `.env` *(local only)* | Your private API keys (not uploaded) |

---

## ✨ Notes  
- Built purely as a personal curiosity project.  
- Reusable by anyone with a Spotify account and developer credentials.  
- All API calls are read-only (except when adding to your own playlist).  
- No personal data is shared or stored outside your machine.  
