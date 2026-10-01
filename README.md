# 🎁 Auto Collect MyGames

<div align="center">

![Platform](https://img.shields.io/badge/Platform-Windows-blue?style=for-the-badge&logo=windows)
![Python](https://img.shields.io/badge/Python-3.10%2B-brightgreen?style=for-the-badge&logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-Modern%20GUI-009688?style=for-the-badge&logo=fastapi)
![License](https://img.shields.io/badge/License-MIT-purple?style=for-the-badge)

**Automated daily reward & promotional items collector for MY.GAMES Market with a modern cyberpunk dark GUI.**

</div>

---

### ⚠️ Disclaimer
> This project is a **purely amateur hobby/pet-project**, created exclusively for personal use and friends.
> The program only includes **games that the author personally plays** (currently: **Rush Royale** and **War Robots**).
> This project is unofficial, not affiliated with, endorsed by, or sponsored by MY.GAMES or the respective game developers. All product names, logos, and brands are property of their respective owners.

---

## 🎮 Supported Games

| Game | Collectibles | Player Identification |
| :--- | :--- | :--- |
| **Rush Royale** | Free summoning bells (10 bells/month), seasonal gifts, promotional item packs | In-game Player ID (e.g. `40734920`) |
| **War Robots** | Daily free gifts, currency, supplies | Pilot ID & Platform selection (Android / iOS / Steam) |

---

## ✨ Features

- 🚀 **Zero-Code for Friends**: No command line knowledge or manual YAML editing required. Game IDs and platforms are entered and saved directly on the cards in the main dashboard.
- 🔑 **Unified 1-Click Authentication**: Log in to your MY.GAMES account via the standard web login window (Email, Google, VK). You only need to authenticate once — sessions remain valid for up to 3 months via sliding session cookies.
- 🎨 **Modern Cyberpunk UI**: Sleek dark futuristic interface with neon accents, smooth animations, and a live real-time color terminal for logs.
- 🛡 **Smart Modal & Banner Dismissal**: Automatically dismisses GDPR overlays, cookie consent popups, and VPN notices that intercept click events on MY.GAMES Market.
- 🔔 **Notifications**: Optional push notifications to Telegram or Discord upon successful reward collection.
- 📦 **Standalone Releases**: Compile the entire project into a single directory or `.exe` distribution with one click (`build.bat`), requiring no Python installation for end users.

---

## 🚀 Quick Start

### Option 1: Pre-built Release (No Python Needed)
1. Go to the [Releases](../../releases) section of this repository.
2. Download `AutoCollect-Release.zip` and extract it to any folder.
3. Run `AutoCollect.exe`.

### Option 2: Running from Source
1. Clone the repository:
   ```bash
   git clone https://github.com/Cyr3ss/MyGames-Collector.git
   cd MyGames-Collector
   ```
2. Install dependencies:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\pip install -r requirements.txt
   .\.venv\Scripts\playwright install chromium
   ```
3. Launch the application:
   ```
   START_APP.bat
   ```

---

## 🛠 Building a Standalone Release (`.exe`)

To compile the application into a standalone executable package:
1. Run:
   ```
   build.bat
   ```
2. The script will automatically:
   - Verify Python and install PyInstaller if needed.
   - Bundle all UI assets and Playwright browser components.
   - Output the build to `dist/AutoCollect/` and compress it into `dist/AutoCollect-Release.zip`.

### Publishing Releases to GitHub:
1. Navigate to your GitHub repository.
2. In the right sidebar, click **Releases** ➔ **Draft a new release**.
3. Create a version tag (e.g., `v1.0.0`).
4. Attach `dist/AutoCollect-Release.zip` to the release assets.
5. Click **Publish release**.

---

## 📁 Project Structure

```
Auto Collect MyGames/
├── app.py                # Unified engine: FastAPI backend, browser automation & game collectors
├── config.example.yaml   # Configuration template (config.yaml is auto-generated on first launch)
├── ui/                   # Modern desktop UI frontend
│   ├── index.html        # Modern desktop UI markup
│   ├── style.css         # Dark cyberpunk theme & styling
│   └── app.js            # Dashboard logic, reactive ID inputs & live log stream
├── START_APP.bat         # One-click launcher from source
├── build.bat             # Automated release builder (PyInstaller + ZIP packaging)
├── requirements.txt      # Python dependencies
└── sessions/             # Encrypted local browser sessions (in .gitignore)
```

---

## 📄 License

Distributed under the MIT License. See `LICENSE` for details.
