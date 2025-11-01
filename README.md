# Hockey Game Bot v2.0

[![Version](https://img.shields.io/badge/version-2.0.0-brightgreen.svg)](https://shields.io/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](http://makeapullrequest.com)
[![Maintained](https://img.shields.io/maintenance/yes/2025)]()
[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue)]()

The **Hockey Game Bot** is a Python application that leverages the NHL API and hockey statistics sites to send real-time game updates to social media platforms. The bot provides fans with a comprehensive view of NHL games including live events, statistics, and advanced analytics - all in one convenient place.

**New in v2.0**: Real-time monitoring dashboard with comprehensive tracking of bot health, API performance, and game statistics.

---

## 🎯 Features

### 📊 Real-Time Monitoring Dashboard
- **Live game state tracking** - Current score, period, time remaining
- **Comprehensive event counting** - Goals, penalties, shots, hits, blocks, and more
- **API performance monitoring** - Success/failure rates, call tracking
- **Bot health monitoring** - Status, uptime, errors, system health
- **Social media activity** - Post counts, timestamps, preview post status
- **Auto-refresh dashboard** - Updates every 2 seconds
- **Network accessible** - View from any device on your local network

### 🏒 Game Coverage
- **Pre-game messages** - Game time, season series, team stats, officials
- **Live game events** - Goals, penalties, period starts, shots on goal
- **Post-game reports** - Final stats, three stars, advanced analytics
- **Day-after analysis** - Season performance charts and trends

### 📱 Social Media Integration
Currently supports **Bluesky** with automatic post tracking and monitoring.

---

## 📸 Dashboard Preview

The dashboard provides real-time visibility into your bot:

```
┌─────────────────────────────────────────────────────────┐
│ 🏒 Hockey Bot Dashboard                                 │
│ Status: ● RUNNING      Last Update: 2s ago              │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  GAME INFORMATION                                        │
│  ┌──────────────────────────────────────────────────┐   │
│  │        NYR    @    NJD                          │   │
│  │         2          3                            │   │
│  └──────────────────────────────────────────────────┘   │
│  Period: 2nd          Time: 08:42                       │
│  Game ID: 2025020176  State: LIVE                       │
│                                                          │
│  EVENTS: Goals (5) | Penalties (4) | Shots (47)         │
│  API CALLS: 178 (98.9% success)                         │
│  POSTS SENT: 12                                          │
└─────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.11 or higher** (for optimal performance and security)
- Basic understanding of virtualenv and pip
- A server or computer that can run continuously (Raspberry Pi, AWS EC2, local machine, etc.)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/mattdonders/hockeygamebot.git
   cd hockeygamebot
   ```

2. **Create and activate virtual environment**
   ```bash
   python3 -m venv .env
   source .env/bin/activate  # On Windows: .env\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure your bot**
   ```bash
   cp config-sample.yaml config.yaml
   # Edit config.yaml with your team and API credentials
   ```

5. **Run the bot**
   ```bash
   python -m hockeygamebot --config config.yaml
   ```

6. **Access the dashboard**
   - The dashboard server starts automatically with the bot
   - Open your browser to: `http://localhost:8000/dashboard.html`
   - From phone/tablet: `http://YOUR_COMPUTER_IP:8000/dashboard.html`

---

## 📊 Dashboard Usage

### Accessing the Dashboard

**Option 1: Auto-start with Bot** (Recommended)
- Dashboard starts automatically when you run the bot
- Access at `http://localhost:8000/dashboard.html`

**Option 2: Standalone Dashboard Server**
- Useful for viewing status even after bot exits
- Run: `./start-dashboard.sh` (from project directory)
- Runs in background, survives bot restarts

### Dashboard Features

| Section | What It Shows |
|---------|---------------|
| **Game Information** | Live score, teams, period, time, venue, game state |
| **Bot Statistics** | Uptime, live loops processed, start time |
| **System Health** | Bot status (RUNNING/SLEEPING/ERROR), error count, health checks |
| **Game Events** | Total events, goals, penalties, shots, saves, hits, blocks, etc. |
| **API Performance** | Total API calls, success/failure rates, success percentage |
| **Social Media** | Posts sent, last post time, preview post status |

### Accessing from Phone/Tablet

1. **Find your computer's IP address:**
   ```bash
   # Mac
   ipconfig getifaddr en0

   # Linux
   hostname -I | awk '{print $1}'
   ```

2. **Open browser on phone and go to:**
   ```
   http://YOUR_COMPUTER_IP:8000/dashboard.html
   ```

3. **Bookmark it** for easy access during games!

---

## ⚙️ Configuration

### config.yaml Structure

```yaml
default:
  team_name: "New Jersey Devils"

bluesky:
  prod:
    account: "your-handle.bsky.social"
    password: "your-app-password"
  debug:
    account: "debug-handle.bsky.social"
    password: "your-debug-password"

script:
  live_sleep_time: 30  # Seconds between live game checks
```

### Command Line Arguments

```bash
python -m hockeygamebot [OPTIONS]

Options:
  --config CONFIG    Path to config file (default: config.yaml)
  --date DATE        Override game date (format: YYYY-MM-DD)
  --nosocial         Log messages instead of posting to social media
  --console          Log to console instead of file
  --debug            Enable debug logging
  --debugsocial      Use debug social accounts for testing
  -h, --help         Show help message
```

**Examples:**

```bash
# Normal operation
python -m hockeygamebot

# Testing mode (no social posts, console logging)
python -m hockeygamebot --nosocial --console

# Check specific date
python -m hockeygamebot --date 2025-10-30

# Debug mode with debug accounts
python -m hockeygamebot --debug --debugsocial
```

---

## 📁 Project Structure

```
hockeygamebot/
├── core/
│   ├── models/
│   │   ├── clock.py           # Game clock tracking
│   │   ├── game_context.py    # Centralized game state
│   │   └── team.py            # Team data models
│   ├── events/                # Event handlers
│   ├── integrations/          # External API integrations
│   ├── charts.py              # Chart generation
│   ├── final.py               # Post-game logic
│   ├── live.py                # Live game processing
│   ├── preview.py             # Pre-game messages
│   ├── rosters.py             # Roster management
│   └── schedule.py            # Game scheduling and API calls
├── socials/
│   ├── bluesky.py             # Bluesky integration
│   └── social_state.py        # Social post tracking
├── utils/
│   ├── config.py              # Configuration management
│   ├── others.py              # Utility functions
│   ├── retry.py               # Retry decorator
│   ├── sessions.py            # Session management
│   ├── team_details.py        # Team information
│   └── status_monitor.py      # Dashboard monitoring (NEW)
├── resources/                 # Fonts and static assets
├── images/                    # Generated charts
├── logs/                      # Log files
├── dashboard.html             # Real-time dashboard UI (NEW)
├── status.json                # Live bot status data (NEW)
├── hockeygamebot.py           # Main application
├── config.yaml                # Configuration file
└── requirements.txt           # Python dependencies
```

---

## 🎮 Game Bot Messages

### Pre-Game Messages
- **Game time announcement** - Time, venue, broadcast info, hashtags
- **Season series** - Team records against each other this season
- **Team statistics** - Pre-game stat comparison chart
- **Officials** - Referees and linesmen assigned to the game

### Live Game Messages
- **Period starts** - On-ice players, opening faceoff winner
- **Goals** - Real-time alerts with scorer, assists, and video highlights
- **Penalties** - Penalty description with power play stats
- **Shots and saves** - Notable saves and shot attempts
- **Intermission reports** - Period stats and team performance

### Post-Game Messages
- **Final score** - Game result with basic stats
- **Three stars** - Game's three stars (if available)
- **Advanced analytics** - Charts from Natural Stat Trick
- **Video highlights** - Game recap and condensed game videos

### Day After Messages
- **Season performance charts** - Team stats vs. league average
- **Last 10 games trends** - Recent performance analysis

---

## 🔧 Troubleshooting

### Dashboard Issues

**Dashboard shows "Error loading status.json"**
- Verify the bot is running
- Check that `status.json` exists in the project directory
- Ensure the web server is running (auto-starts with bot)
- Try refreshing the browser (Ctrl/Cmd + R)

**Dashboard not updating**
- Check browser console (F12) for JavaScript errors
- Verify bot is in the game loop (not sleeping for hours)
- Check `status.json` file modification time
- Status updates every time the game loop runs

**Can't access dashboard from phone**
- Ensure phone is on same WiFi network
- Verify firewall isn't blocking port 8000
- Check your computer's IP address hasn't changed
- Try `http://COMPUTER_IP:8000/dashboard.html`

**Web server logs cluttering console**
- The bot uses a silent HTTP handler to suppress logs
- If still seeing logs, ensure you're using the latest version

### Bot Issues

**Bot not starting**
- Check Python version: `python --version` (need 3.10+)
- Verify all dependencies installed: `pip install -r requirements.txt`
- Check config.yaml for syntax errors
- Review logs in `logs/` directory

**No social posts appearing**
- Verify Bluesky credentials in config.yaml
- Check if running with `--nosocial` flag (testing mode)
- Review logs for authentication errors
- Ensure account isn't rate-limited

**Bot not finding games**
- Check team name in config.yaml matches NHL team name
- Try `--date YYYY-MM-DD` to test with specific date
- Verify team has a game on the target date
- Check NHL API is accessible

**API calls showing high failure rate**
- Network connectivity issues - check your internet
- NHL API may be temporarily down
- Rate limiting - bot automatically retries failed calls
- Check logs for specific error messages

---

## 🤖 Automation

### Running at Startup with Cron

To automatically start the bot daily (e.g., 9:00 AM):

```bash
crontab -e
```

Add this line:
```
0 9 * * * cd /path/to/hockeygamebot && ./.env/bin/python -m hockeygamebot
```

### Running with systemd (Linux)

Create `/etc/systemd/system/hockeygamebot.service`:

```ini
[Unit]
Description=Hockey Game Bot
After=network.target

[Service]
Type=simple
User=your-username
WorkingDirectory=/path/to/hockeygamebot
ExecStart=/path/to/hockeygamebot/.env/bin/python -m hockeygamebot
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable hockeygamebot
sudo systemctl start hockeygamebot
sudo systemctl status hockeygamebot
```

---

## 🔒 Security Notes

- **Never commit config.yaml** - Contains API credentials
- **Use app passwords** - Don't use your main Bluesky password
- **Firewall dashboard port** - Only expose to trusted networks
- **Rotate credentials** - Change passwords periodically
- **Monitor access** - Check dashboard access logs if concerned

---

## 📈 Performance Tips

- **Raspberry Pi users**: Works great on Pi 4 with 2GB+ RAM
- **AWS/Cloud**: t2.micro instance is sufficient for single team
- **Network**: Stable internet connection is critical for API calls
- **Storage**: ~500MB for application + logs over season
- **Dashboard**: Minimal resource usage, designed for efficiency

---

## 🤝 Contributing

Contributions are welcome! Whether it's bug reports, feature requests, or code contributions:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📋 Versioning

We use [SemVer](http://semver.org/) for versioning. For available versions, see the [tags on this repository](https://github.com/mattdonders/hockeygamebot/tags).

---

## 👤 Author

**Matt Donders** - [mattdonders.com](https://mattdonders.com)

---

## 🙏 Acknowledgments

Special thanks to everyone who has helped test, provide feedback, and contribute data:

- **Natural Stat Trick** - [naturalstattrick.com](http://www.naturalstattrick.com/)
- **Hockey Stat Cards** - [hockeystatcards.com](https://www.hockeystatcards.com/)
- **Daily Faceoff** - [dailyfaceoff.com](https://www.dailyfaceoff.com/)
- **Hockey Reference** - [hockey-reference.com](https://www.hockey-reference.com/)
- **Scouting the Refs** - [scoutingtherefs.com](https://scoutingtherefs.com/)
- **NHL API Documentation** - [gitlab.com/dword4/nhlapi](https://gitlab.com/dword4/nhlapi)

---

## 📄 License

This project is open source and available for personal use. Please respect NHL data usage policies and rate limits.

---

## 🏒 Support

If you enjoy using this bot and want to support development:

- ⭐ Star this repository
- 🐛 Report bugs and issues
- 💡 Suggest new features
- 📢 Share with other hockey fans

---

**Built with ❤️ for hockey fans by hockey fans**
