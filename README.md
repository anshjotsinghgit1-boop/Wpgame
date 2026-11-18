# Who's the Spy? — Telegram Group Game

A Telegram group game bot built with Python and python-telegram-bot.

## Features

- `/spy` opens a host-free lobby for 2 minutes.
- The lobby message has a **Join Game** deep-link button.
- Players must start the bot in private chat and join **@xyronschannel** before entering a lobby.
- A reminder is posted as a reply to the lobby message when 1 minute remains.
- Games start automatically with at least 5 players; smaller lobbies are cancelled.
- Civilians receive the same secret word; the Spy receives a related word.
- Players explain in order. Out-of-turn group messages are deleted (bot needs Delete Messages permission).
- Inline voting updates one public message live, showing who voted for whom and the current totals.
- The player with the most votes is eliminated. If the Spy is caught, they get one private chance to guess the civilian word. A correct guess wins for the Spy; otherwise civilians win.
- If an innocent is eliminated, another explanation/voting round begins.

## Setup

1. Create a bot with @BotFather and copy its token.
2. Add the bot as an administrator in **@xyronschannel** so Telegram membership checks work reliably.
3. Add the bot to your game group and grant **Delete Messages** permission.
4. Copy `.env.example` to `.env` and set `BOT_TOKEN`.
5. Install and run:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## Environment

- `BOT_TOKEN` — required BotFather token.
- `REQUIRED_CHANNEL` — defaults to `@xyronschannel`.
- `DATABASE_PATH` — defaults to `spy_game.sqlite3`.

Never commit your real bot token. Keep `.env` private.

## Commands

- `/start` — private onboarding, channel verification, and game deep-link handling.
- `/spy` — open a 2-minute lobby in a group.
- `/cancelspy` — cancel the active game in the current group.

## Notes

Players must press **Start** in the bot's private chat at least once so the bot can send them their role privately. The bot cannot initiate a private conversation with a user who has never started it. The channel must be public or otherwise resolvable by the bot; membership checks use Telegram's `get_chat_member`.
