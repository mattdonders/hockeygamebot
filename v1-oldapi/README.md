# Hockey Game Bot

[![Generic badge](https://img.shields.io/badge/version-2.1.0-brightgreen.svg)](https://shields.io/) [![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](http://makeapullrequest.com) [![Maintained](https://img.shields.io/maintenance/yes/2020)]() [![Python Version](https://img.shields.io/badge/python-3.6%20%7C%203.7-blue)]() [![Beerpay](https://img.shields.io/beerpay/mattdonders/nhl-twitter-bot)](https://beerpay.io/mattdonders/nhl-twitter-bot) ![Twitter Follow](https://img.shields.io/twitter/follow/njdevilsgamebot?label=%40NJDevilsGameBot&style=social)

The **Hockey Game Bot** is a Python application that leverages the NHL API and other hockey related statistics sites to send (near) real-time messages to social media platforms. The game bot allows fans of NHL teams to view the events & stats of a game all in one convenient place.

The game bot currently supports 3 social media platforms - Twitter, Discord & Slack. If you would like to add your own, feel free to submit your code via a Pull Request.

![EM_sKf8WoAg-DpL](https://user-images.githubusercontent.com/1444730/72755605-cdc2a080-3bc2-11ea-9f97-2c441ffff3a0.jpg)


# Game Bot Messages / Events

The messages are broken down into four sections for each part of a game day (and one extra section of the day after a game day). I am currently adding more events and features as they are requested or they are found to be useful in the context of following the game via social media. This list will be kept up to date as more types of messages and / or customizations to these are added.

Each message is linked to a sample tweet from the NJ Devils game bot Twitter account.

### Pre-Game Messages
- [Morning Gameday Image](https://twitter.com/NJDevilsGameBot/status/1211285800916262912?s=20) (w/ time, broadcast channel & hashtag)
- Season Series (w/ Points Leaders & TOI Leaders)
    - This becomes last season series if this is the first meeting.
- [Confirmed goalie for each team](https://twitter.com/NJDevilsGameBot/status/1211285812052217858?s=20) (with season & career stats).
- [Confirmed lines for each team](https://twitter.com/NJDevilsGameBot/status/1211331150830096384?s=20) (with lineup change checks)
    - If the lineup / lines for a game change, an updated message will be sent.
- [Referees and Linesman](https://twitter.com/NJDevilsGameBot/status/1211361363769122816?s=20)
- Preferred team starters (~5 minutes before game time)

### Live Game Messages
- Start of Period
    - [Players on-ice to start the period](https://twitter.com/NJDevilsGameBot/status/1211407931993931776?s=20)
    - [Actual start of period (puck drop)](https://twitter.com/NJDevilsGameBot/status/1211408825435250688?s=20)
    - [Period's opening faceoff winner and loser](https://twitter.com/NJDevilsGameBot/status/1211409084374769669?s=20)
- Penalties & Power Plays
    - [Team stats & NHL rank](https://twitter.com/NJDevilsGameBot/status/1211412373707378689?s=20)
    - Strength Status (PP, PK, etc)
    - *Coming Soon: End of penalty detection*
- Goals
    - [Near real time goal alerts](https://twitter.com/NJDevilsGameBot/status/1211412891943002112?s=20) (includes season totals and goal distance)
    - [First Goal](https://twitter.com/NJDevilsGameBot/status/1185610034518151169?s=20) & Career Milestone Alerts (every 100 goals, points or assists)
    - [Scoring & Assist Changes](https://twitter.com/NJDevilsGameBot/status/1211413943706619905?s=20)
    - [NHL Linked Highlights](https://twitter.com/NJDevilsGameBot/status/1216171832476422144?s=20)
- [Shots that hit the cross-bar or post](https://twitter.com/NJDevilsGameBot/status/1218721726525333505?s=20)
- [Notification of 1-minute remaining per period](https://twitter.com/NJDevilsGameBot/status/1216520670550642688?s=20)
- Intermission Reports
    - [Stat Charts w/ Scoring Summary](https://twitter.com/NJDevilsGameBot/status/1211417974017380353?s=20)
    - [Stat Leaders for Box Score Categories](https://twitter.com/NJDevilsGameBot/status/1211417977746317313?s=20)
    - [Team Overview Stat Splits](https://twitter.com/NJDevilsGameBot/status/1212913065035010048?s=20)
    - [Individual, on-ice, forward lines & defensive pair charts](https://twitter.com/NJDevilsGameBot/status/1212913083968036865?s=20)


### End of Game Messages
- [Final game report including next game, basic stats and scoring summary](https://twitter.com/NJDevilsGameBot/status/1211446491518316544?s=20)
- [Three Stars](https://twitter.com/NJDevilsGameBot/status/1211447335827496961?s=20)
- Advanced Stats Charts (via Natural Stat Trick)
    - [Team Overview stat percentage splits](https://twitter.com/NJDevilsGameBot/status/1212928684782436353?s=20)
    - [Individual, on-ice, forward lines & defensive pair stats for both teams](https://twitter.com/NJDevilsGameBot/status/1212928699311542272?s=20)
- [Game Score charts for both teams](https://twitter.com/NJDevilsGameBot/status/1217276585079951367?s=20) (via Hockey Stat Cards)

### Day After Game Messages
On the day after a game, the [game bot will generate two charts](https://twitter.com/NJDevilsGameBot/status/1217446411354152960?s=20) that provide context to how the team is performing for the entire season and in their last 10 games compared to the league average. The chart includes the following categories -
- Team Point Percentage
- Expected Goals & Actual Goals
- Shooting Percentage & Save Percentage
- High Danger Shooting Percentage & Save Percentage
- PDO (SPSV% - the sum of a team's shooting percentage and its save percentage)


# Getting Started

The game bot ideally runs on a server that is always on as it is built with that assumption in mind - this is because the game bot is set to start hours before the game and checks at defined intervals for updated information related to that day's game.

The stand-alone Python script can run on anything from a Raspberry Pi to an AWS EC2 instance, while the current Docker implementation can only run on x86_64 machines.

**Coming Soon**: Currently there is a Docker image that is built for x86_64 and I am currently working on building an image that supports Raspberry Pi ARMv7 / ARM64 machines.

### Prerequisites and Installation

To run the game bot you'll need [Python 3.6](https://www.python.org/downloads/release/python-368/) or higher (tested on 3.6.x & 3.7.x). A basic understanding of [virtualenv](https://docs.python.org/3/library/venv.html) and [pip](https://docs.python.org/3/installing/index.html) are required to get started.

To start the installation process, perform the following steps in order -
1. Download the most current release from Github.
    ```bash
    $ git clone git@github.com:mattdonders/nhl-twitter-bot.git
    ```

2. Change to the cloned directory, create a new virtual environment & activate it.
    ```bash
    $ cd nhl-twitter-bot
    $ python3 -m venv .env
    $ source .env/bin/activate
    ```

3. Install the Python requirements packages via pip.
   ```bash
   $ pip install -r requirements.txt
   ```


### Social Media Setup
In order for the game bot to send messages to social media, you will need API or Developer keys for each service.

* **If you are sending messages to Twitter**, Create a new [Twitter application](https://apps.twitter.com/app/new) by filling out the form on Twitter's website. Your account will be revied for developr access. Once completed, create a new application and request an Access Token once completed as 4 keys are needed for Twitter integration.
* **If you are sending messages to Discord**, create a new [Discord Webhook](https://support.discordapp.com/hc/en-us/articles/228383668-Intro-to-Webhooks) by going to your Discord channel, choosing settings, webhooks and click the “Create Webhook” button.

Once you have the application's keys and /or webhook URLs, rename `config-sample.yaml` to `config.yaml` and fill in the proper credentials.
```bash
$ cp hockeygamebot/config/config-sample.yaml hockeygamebot/config/config.yaml
```

Social media services are enabled & disabled through this configuration file as well (by marking them as True / False). Access tokens and keys are secret and should not be shared or uploaded to Github for any reason.

*There are two sets of Twitter credentials defined in the configuration file. The second set can be used to setup a debug / test account, but are not required and can be left blank.*

**This part of the config.yaml code is what you will edit to provide the API Keys / Tokens & Webhooks to the game bot process.**
```
# Team Name used if no --team argument is passed into the game bot
default:
    team_name: New Jersey Devils

# Enabling / disabling of social media services
socials:
    twitter: True
    discord: True
    slack: False

# Twitter API Keys / Tokens
# Only use debug if you have a secondary debug account
twitter:
    prod:
        consumer_key: XXX
        consumer_secret: XXX
        access_token: XXX
        access_secret: XXX
        handle: XXX
    debug:
        consumer_key: XXX
        consumer_secret: XXX
        access_token: XXX
        access_secret: XXX
        handle: XXX

# Discord Webhook URLs
# Only use debug if you have a secondary debug server / channel
discord:
    prod:
        webhook_url: https://discordapp.com/api/webhooks/XXX
    debug:
        webhook_url: https://discordapp.com/api/webhooks/XXX
```

## Execution

The Github repository contains a shell script named `hockeygamebot.sh` which will automatically start the Python script in the background and *disown* the process. When a Linux process is *disowned*, it means that you can disconnect from your Linux session (if running on a remote host) without stopping or interrupting the script process.

### Manual Execution

To start the bot using the script, run the `hockeygamebot.sh` command (modify the location to your cloned folder) -

`$HOME/python/nhl-twitter-bot/hockeygamebot.sh`


If you want to start the Python script from the command line and pass in debug arguments, you can execute the script directly. Some of these options are debug or testing options, but have not yet been cleaned up for this version of the script.
```
$ python -m hockeygamebot --help
usage: hockeygamebot [-h] [--notweets] [--console] [--debug] [--team TEAM]
                     [--debugtweets] [--debugsocial] [--localdata]
                     [--overridelines] [--yesterday] [--date DATE] [--split]
                     [--docker] [--discord] [--config CONFIG] [-v]

optional arguments:
  -h, --help       show this help message and exit
  --notweets       log tweets to console instead of Twitter
  --console        log to console instead of file
  --debug          print debug log items
  --team TEAM      override team in configuration
  --debugsocial    use debug social accounts
  --localdata      use local data instead of API
  --overridelines  override lines if None are returned
  --yesterday      get yesterday game on the schedule
  --date DATE      override game date
  --split          split squad game index
  --docker         running in a docker container
  --discord        Send messages to discord channel
  --config CONFIG  Overrides the config.yaml with another filename.
  -v               Increased verbosity.
```

### Automating The Game Bot

If you want to run the game bot automatically every day, you can setup a [cron job](https://linux.die.net/man/1/crontab) on Linux / Mac that restarts the bot everyday at any specified time (mine runs at 9:00AM so I can start checking other sites for game data as early as possible). You can edit your crontab file by executing the `crontab -e` command and pasting in the below line (again modifying the path to your script path).

Crontab is also supported in the [Windows Subsystem for Linux](https://docs.microsoft.com/en-us/windows/wsl/faq) if the game bot is running within this type of environment.

**A sample crontab entry -**

`0 9 * * * $HOME/python/nhl-twitter-bot/hockeygamebot.sh`


# Currently Operating Game Bots

As of March 15, 2020 there is currently game bot covereage for 12 of 31 teams. The table below contains information about the accounts, their respective owners and any notes. More than one person can run one for the same team without issue, but there will be overlap in the Twitter feed.

| Team Name             | Twitter Account  | Owner          | Notes                                             |
|-----------------------|------------------|----------------|---------------------------------------------------|
| Anaheim Ducks         |                  |                |                                                   |
| Arizona Coyotes       |[@CoyotesGameBot](https://twitter.com/CoyotesGameBot)  |[@mattdonders](https://twitter.com/mattdonders)   |                                                   |
| Boston Bruins         |                  |                |                                                   |
| Buffalo Sabres        |[@BotSabres](https://twitter.com/BotSabres)       |[@KurekRobbie](https://twitter.com/KurekRobbie)   |                                                   |
| Calgary Flames        |                  |                |                                                   |
| Carolina Hurricanes   |[@HurricanesBot](https://twitter.com/HurricanesBot)   |[@bancksholmes](https://twitter.com/bancksholmes) |                                                   |
| Chicago Blackhawks    |                  |                |                                                   |
| Colorado Avalanche    |                  |                |                                                   |
| Columbus Blue Jackets |[@CBJGameBot](https://twitter.com/CBJGameBot) |[@mattdonders](https://twitter.com/mattdonders)   | Willing to reliquensh to a Blue Jackets fan.             |
| Dallas Stars          |                  |                |                                                   |
| Detroit Red Wings     |                  |                |                                                   |
| Edmonton Oilers       |                  |                |                                                   |
| Florida Panthers      |                  |                |                                                   |
| Los Angeles Kings     |                  |                |                                                   |
| Minnesota Wild        |                  |                |                                                   |
| Montreal Canadiens    |                  |                |                                                   |
| Nashville Predators   |[@OTF_Preds_Bot](https://twitter.com/OTF_Preds_Bot)   |[@projpatsummit](https://twitter.com/projpatsummit) |                                                   |
| New Jersey Devils     |[@NJDevilsGameBot](https://twitter.com/NJDevilsGameBot) |[@mattdonders](https://twitter.com/mattdonders)   |                                                   |
| New York Islanders    |                  |                |                                                   |
| New York Rangers      |                  |                |                                                   |
| Ottawa Senators       |                  |                |                                                   |
| Philadelphia Flyers   |                  |                |                                                   |
| Pittsburgh Penguins   |[@bot_penguins](https://twitter.com/bot_penguins)   |[@skiminer36](https://twitter.com/skiminer36) |                                                   |
| Saint Louis Blues     |[@STLBluesGameBot](https://twitter.com/STLBluesGameBot) |[@mattdonders](https://twitter.com/mattdonders)   | Willing to reliquensh to a Blues fan.             |
| San Jose Sharks       |[@Sharks_Gamebot](https://twitter.com/Sharks_Gamebot)  |[@projpatsummit](https://twitter.com/projpatsummit) |                                                   |
| Tampa Bay Lighting    |                  |                |                                                   |
| Toronto Maple Leafs   |[@MapleLeafsBot](https://twitter.com/MapleLeafsBot)   |[@RevelMagic](https://twitter.com/RevelMagic)    |                           |
| Vancouver Canucks     |                  |                |                                                   |
| Vegas Golden Knights  |[@VGKGameBot](https://twitter.com/VGKGameBot)      |[@702goonie](https://twitter.com/702goonie)     | Forked version of V1 - not sure about V2 upgrade. |
| Washington Capitals   |[@CapitalsHill](https://twitter.com/CapitalsHill)    |[@CapitalsHill](https://twitter.com/CapitalsHill)  | Game bot mixed into regular feed.                 |
| Winnipeg Jets         |                  |                |                                                   |

## Versioning

We use [SemVer](http://semver.org/) for versioning. For the versions available, see the [tags on this repository](https://github.com/mattdonders/nhl-twitter-bot/tags).

## Authors

* **Matt Donders** - https://mattdonders.com

## Acknowledgments

Special thanks to all who have helped test along the way and provide data and stats to help improve the game bot and allow it to be a one-stop shop for most in-game events.

* **Natural Stat Trick** - http://www.naturalstattrick.com/
* **Hockey Stat Cards** - https://www.hockeystatcards.com/
* **Daily Faceoff** - https://www.dailyfaceoff.com/
* **Hockey Reference** - https://www.hockey-reference.com/
* **Scouting the Refs** - https://scoutingtherefs.com/
* An [up to date list](https://gitlab.com/dword4/nhlapi) of all NHL API endpoints.

