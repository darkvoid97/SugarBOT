<div align="center">

# SugarBOT

[![Python](https://img.shields.io/badge/python-3.13-3776AB.svg?logo=python)](https://www.python.org/)
[![discord.py](https://img.shields.io/badge/discord.py-2.7.1-5865F2.svg?logo=discord)](https://pypi.org/project/discord.py/)
[![License: MIT](https://img.shields.io/badge/License-MIT-orange.svg)](https://github.com/darkvoid97/SugarBOT/blob/main/LICENSE)

</div>

#### Description:
SugarBOT is a general multi-purpose Discord bot, built with Python using the `discord.py` API wrapper framework, featuring modular cogs, and at the current state, it brings together AI features (powered by Google Gemini), server announcements, voice channel functionality, and general utility commands.

## About this project
This project was built as the final project of CS50's Introduction to Programming with Python (CS50P), an open course from Harvard University taught by David J. Malan. It covers core Python fundamentals including functions, conditionals, loops, data structures, file I/O, regular expressions, unit testing, and object-oriented programming.

Learn more at [cs50.harvard.edu/python](https://cs50.harvard.edu/python/).

## Features
- **Modular Cogs Architecture**: Commands are organized into separate cogs (`ai_functions`, `announcements`, `general`, `voice`), making features easier to maintain, test, and extend.
- **General & Moderation Tools**: Check bot latency, fetch user avatars, pull random memes via the [Meme API](https://github.com/D3vd/Meme_Api), and use owner-restricted commands to bulk-delete messages (`/purge`) or publish styled server announcements (`/announce`).
- **Voice Channel Audio**: *[NOTE: This module won't be shared here, as using these functions could potentially bring the risk of breaking YouTube and other similiar platform's Terms of Service]*
- **AI Features (powered by Google Gemini)**:
  - **Channel Summarization (`/summarize`)**: Summarizes recent messages in a text channel or thread while anonymizing sensitive user information before inference and restoring it afterward.
  - **Text & Image Translation (`/translate`)**: Translates text from messages, prompts, or images into English, including via a message context menu command.
  - **General Q&A (`/ask`)**: Ask questions directly to AI from Discord.
  - **AI Trivia (`/aitrivia`)**: Play interactive trivia rounds with questions generated for user-selected categories.

## Getting Started
### Prerequisites
- Python (built and tested with Python 3.13)
- FFmpeg (https://ffmpeg.org/download.html) for voice channel audio playback

### Installation
1. **Extract or clone the project** and open a terminal in the repository root:
    ```bash
    git clone https://github.com/darkvoid97/SugarBOT.git
    cd SugarBOT
    ```
2. **Install Python dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
3. **Configure environment variables:** Copy or rename `.env.example` to `.env` and fill in your credentials:
    ```
    DISCORD_TOKEN=Your-Discord-Token-Here
    OWNER_ID=Your-Discord-Account-ID-Here
    GEMINI_API_KEY=Your-Gemini-API-Key-Here
    ```
4. **Run the bot:**
    ```bash
    python project.py
    ```
### Discord Setup
1. Open the [**Discord Developer Portal**](https://discord.com/developers/home) and select your application.
2. Under **OAuth2 → URL Generator**, select the `bot` and `applications.commands` scopes.
3. Choose the permissions your server needs (using `Administrator` avoids permission issues during testing and setup), then open the generated URL to invite SugarBOT to your server.

## Usage
Most commands use Discord slash (`/`) commands, with `.` prefix or context menu support where noted:
| Command | Access | Description |
| -------- | ------- | ------- |
`/ping` or `.ping` | Everyone | Checks bot latency and replies with a random message.
`.help` | Everyone | Displays the default discord.py help menu.
`/avatar` or `.avatar` | Everyone | Fetches the profile picture of a specified user or bot.
`/meme`| Everyone | Fetches a random meme using the [Meme API](https://github.com/D3vd/Meme_Api).
`/purge` | Owner only | Bulk-deletes messages in a channel with optional filters.
`.sync` | Owner only | Syncs global slash commands.
`/announce` | Owner only | Opens a modal form to compose and confirm a styled server announcement.
`/summarize` | Everyone | Summarizes recent activity in a selected text channel or thread using AI.
`/translate` | Everyone | Translates provided text, a message, or text inside an image into English using AI (also available via the message context menu).
`/ask` | Everyone | Sends a question to the AI model and returns the response.
`/aitrivia` | Everyone | Starts an AI-generated trivia game on user-specified categories.

## Testing
As per the CS50P course's requests, `project.py` includes three helper functions supporting the `build_msg` function, which formats Discord message data into readable strings intended for terminal or log-file output (file/stream logging is kept disabled by default to avoid terminal clutter during testing).

Run the unit tests for these helpers with **pytest**:
```bash
pytest test_project.py
```

## Project Structure
```
├── project.py              # Entry point, cog loader, command sync, message helpers
├── test_project.py         # pytest unit tests for helper functions
├── requirements.txt        # Python package dependencies
├── .env.example            # Template for required environment variables
└── cogs/
    ├── ai_functions.py     # Gemini-powered commands
    ├── announcements.py    # Modal and confirmation view workflow for /announce
    ├── general.py          # /ping, /avatar, /purge, and /meme commands
    └── voice.py
```
<br><hr>

- ### [CS50 Python Problem Sets solutions](https://github.com/darkvoid97/CS50P)