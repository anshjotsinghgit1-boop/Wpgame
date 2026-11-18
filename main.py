from __future__ import annotations

import asyncio
import html
import logging
import os
import random
import sqlite3
import uuid
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, User
from telegram.constants import ChatType, ParseMode
from telegram.error import BadRequest, Forbidden, TelegramError
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler, ContextTypes,
    MessageHandler, filters,
)

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", "@xyronschannel").strip()
DATABASE_PATH = os.getenv("DATABASE_PATH", "spy_game.sqlite3")
MIN_PLAYERS = 5
LOBBY_SECONDS = 120

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("whos-the-spy")

# Related pairs: civilians receive the first word, the Spy receives the second.
WORD_PAIRS = [
    ("Coffee", "Tea"), ("Beach", "Swimming Pool"), ("Doctor", "Nurse"),
    ("Airplane", "Helicopter"), ("Pizza", "Burger"), ("Lion", "Tiger"),
    ("Guitar", "Violin"), ("Winter", "Summer"), ("Library", "Bookshop"),
    ("Moon", "Sun"), ("Train", "Metro"), ("Hotel", "Resort"),
    ("Football", "Basketball"), ("Laptop", "Tablet"), ("Candle", "Torch"),
    ("Desert", "Beach"), ("Shark", "Dolphin"), ("Castle", "Palace"),
    ("Rain", "Snow"), ("Camera", "Phone"), ("Pen", "Pencil"),
    ("Apple", "Mango"), ("Hospital", "Clinic"), ("River", "Lake"),
    ("Eagle", "Falcon"), ("Bus", "Tram"), ("Piano", "Keyboard"),
    ("Volcano", "Mountain"), ("Crown", "Tiara"), ("Sofa", "Armchair"),
]

@dataclass
class Player:
    user_id: int
    name: str
    username: Optional[str] = None

    @classmethod
    def from_user(cls, user: User) -> "Player":
        return cls(user.id, user.full_name, user.username)

    @property
    def mention(self) -> str:
        label = html.escape(self.name)
        if self.username:
            return f'<a href="https://t.me/{html.escape(self.username)}">{label}</a>'
        return f'<a href="tg://user?id={self.user_id}">{label}</a>'

@dataclass
class Game:
    game_id: str
    chat_id: int
    lobby_message_id: int
    players: list[Player] = field(default_factory=list)
    active: list[int] = field(default_factory=list)
    spy_id: Optional[int] = None
    civilian_word: Optional[str] = None
    spy_word: Optional[str] = None
    phase: str = "lobby"
    round_no: int = 1
    turn_index: int = 0
    explanations: dict[int, str] = field(default_factory=dict)
    votes: dict[int, int] = field(default_factory=dict)
    vote_message_id: Optional[int] = None
    vote_candidates: Optional[list[int]] = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    task: Optional[asyncio.Task] = None

    def player(self, user_id: int) -> Optional[Player]:
        return next((p for p in self.players if p.user_id == user_id), None)

    def active_players(self) -> list[Player]:
        return [p for p in self.players if p.user_id in self.active]


GAMES: dict[str, Game] = {}
CHAT_GAMES: dict[int, str] = {}
BOT_USERNAME = ""

def db_init() -> None:
    with sqlite3.connect(DATABASE_PATH) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS players (
            user_id INTEGER PRIMARY KEY, name TEXT NOT NULL, username TEXT,
            joined_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")

def remember_user(user: User) -> None:
    with sqlite3.connect(DATABASE_PATH) as db:
        db.execute(
            "INSERT INTO players(user_id,name,username) VALUES(?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET name=excluded.name, username=excluded.username",
            (user.id, user.full_name, user.username),
        )

def is_member_status(status: str, is_member: Optional[bool]) -> bool:
    return status in ("creator", "administrator", "member") or (
        status == "restricted" and bool(is_member)
    )

async def check_membership(bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        return is_member_status(member.status, getattr(member, "is_member", None))
    except TelegramError as exc:
        log.warning("Channel membership check failed for %s: %s", user_id, exc)
        return False

def channel_keyboard() -> InlineKeyboardMarkup:
    channel = REQUIRED_CHANNEL
    url = f"https://t.me/{channel.lstrip('@')}" if channel.startswith("@") else channel
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Join Channel", url=url)],
        [InlineKeyboardButton("✅ I've Joined — Verify", callback_data="verify_channel")],
    ])

async def send_channel_gate(message) -> None:
    await message.reply_text(
        f"To play **Who's the Spy?**, first join {REQUIRED_CHANNEL}.\n"
        "After joining, tap **I've Joined — Verify**.",
        reply_markup=channel_keyboard(),
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
    )

def lobby_markup(game_id: str) -> InlineKeyboardMarkup:
    deep_link = f"https://t.me/{BOT_USERNAME}?start=join_{game_id}"
    return InlineKeyboardMarkup([[InlineKeyboardButton("🎮 Join Game", url=deep_link)]])

def lobby_text(game: Game, seconds_left: int = LOBBY_SECONDS) -> str:
    names = "\n".join(f"• {html.escape(p.name)}" for p in game.players) or "• Waiting for players..."
    return (
        "🕵️ <b>WHO'S THE SPY?</b>\n\n"
        "A new game lobby is open!\n"
        f"👥 <b>Players:</b> {len(game.players)}/{MIN_PLAYERS}+\n"
        f"⏳ <b>Time:</b> {seconds_left // 60}:{seconds_left % 60:02d}\n\n"
        f"{names}\n\n"
        "Tap <b>Join Game</b> and open the bot in private chat to enter."
    )

async def start_lobby_timer(game: Game, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await asyncio.sleep(60)
        if game.phase != "lobby":
            return
        try:
            await context.bot.send_message(
                game.chat_id,
                "⏳ <b>1 minute left! Please join the game.</b>",
                reply_to_message_id=game.lobby_message_id,
                parse_mode=ParseMode.HTML,
            )
        except TelegramError:
            log.exception("Could not send lobby reminder")
        await asyncio.sleep(60)
        async with game.lock:
            if game.phase != "lobby":
                return
            if len(game.players) < MIN_PLAYERS:
                game.phase = "finished"
                await context.bot.send_message(
                    game.chat_id,
                    f"❌ Game cancelled — only {len(game.players)} player(s) joined. "
                    f"At least {MIN_PLAYERS} are required.",
                )
                cleanup_game(game)
                return
            await begin_game(game, context)
    except asyncio.CancelledError:
        return
    except Exception:
        log.exception("Lobby timer crashed")
        cleanup_game(game)

def cleanup_game(game: Game) -> None:
    GAMES.pop(game.game_id, None)
    if CHAT_GAMES.get(game.chat_id) == game.game_id:
        CHAT_GAMES.pop(game.chat_id, None)

async def spy_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    chat = update.effective_chat
    if not message or not chat or chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        if message:
            await message.reply_text("Use /spy in a Telegram group.")
        return
    current_id = CHAT_GAMES.get(chat.id)
    if current_id and current_id in GAMES:
        await message.reply_text("A game is already running in this group.")
        return

    game_id = uuid.uuid4().hex[:10]
    game = Game(game_id=game_id, chat_id=chat.id, lobby_message_id=0)
    GAMES[game_id] = game
    CHAT_GAMES[chat.id] = game_id
    sent = await message.reply_text(
        lobby_text(game),
        reply_markup=lobby_markup(game_id),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )
    game.lobby_message_id = sent.message_id
    game.task = asyncio.create_task(start_lobby_timer(game, context))
    log.info("Lobby %s opened in %s", game_id, chat.id)

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    message = update.effective_message
    if not chat or not message:
        return
    game_id = CHAT_GAMES.get(chat.id)
    game = GAMES.get(game_id) if game_id else None
    if not game:
        await message.reply_text("There is no active game in this group.")
        return
    game.phase = "finished"
    if game.task:
        game.task.cancel()
    await message.reply_text("🛑 The game has been cancelled.")
    cleanup_game(game)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    if not message or not user or message.chat.type != ChatType.PRIVATE:
        return
    remember_user(user)
    payload = context.args[0] if context.args else ""

    if not await check_membership(context.bot, user.id):
        await send_channel_gate(message)
        return

    if payload.startswith("join_"):
        game_id = payload[5:]
        game = GAMES.get(game_id)
        if not game or game.phase != "lobby":
            await message.reply_text("That game lobby has closed. Ask the group to start a new /spy game.")
            return
        async with game.lock:
            if game.phase != "lobby":
                await message.reply_text("This lobby has already started.")
                return
            if game.player(user.id):
                await message.reply_text("✅ You're already in this game. Wait for it to start!")
                return
            if len(game.players) >= 30:
                await message.reply_text("This lobby is full (30 players).")
                return
            game.players.append(Player.from_user(user))
            await message.reply_text(
                f"✅ You're in! You've joined the game in <b>{html.escape(str(game.chat_id))}</b>. "
                "Keep this chat open — your secret word will arrive here when the game starts.",
                parse_mode=ParseMode.HTML,
            )
            try:
                await context.bot.edit_message_text(
                    lobby_text(game),
                    chat_id=game.chat_id,
                    message_id=game.lobby_message_id,
                    reply_markup=lobby_markup(game_id),
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
            except TelegramError:
                log.exception("Could not refresh lobby message")
        return

    await message.reply_text(
        "🕵️ Welcome to <b>Who's the Spy?</b>\n\n"
        "Join a game from a group's <b>Join Game</b> button. "
        f"You must be a member of {html.escape(REQUIRED_CHANNEL)}.",
        parse_mode=ParseMode.HTML,
    )

async def verify_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.from_user:
        return
    if await check_membership(context.bot, query.from_user.id):
        try:
            await query.edit_message_text(
                "✅ Membership verified! You're ready to join a game. "
                "Return to the group and tap its Join Game button."
            )
        except TelegramError:
            pass
    else:
        await query.answer("I can't see you in @xyronschannel yet. Join it, then try again.", show_alert=True)

async def begin_game(game: Game, context: ContextTypes.DEFAULT_TYPE) -> None:
    game.phase = "explaining"
    game.active = [p.user_id for p in game.players]
    game.spy_id = random.choice(game.active)
    game.civilian_word, game.spy_word = random.choice(WORD_PAIRS)
    random.shuffle(game.active)

    failed = []
    for player in game.players:
        word = game.spy_word if player.user_id == game.spy_id else game.civilian_word
        try:
            await context.bot.send_message(
                player.user_id,
                "🕵️ <b>Your secret role</b>\n\n"
                f"Your word is: <b>{html.escape(word)}</b>\n\n"
                "Do not show this message or reveal your word. "
                "Explain it naturally when it's your turn.",
                parse_mode=ParseMode.HTML,
            )
        except (Forbidden, TelegramError):
            failed.append(player.user_id)

    if failed:
        game.active = [uid for uid in game.active if uid not in failed]
        if game.spy_id in failed:
            game.phase = "finished"
            await context.bot.send_message(
                game.chat_id,
                "❌ The Spy couldn't be reached in private chat, so this game has been cancelled. "
                "Players must press /start in the bot's DM before joining.",
            )
            cleanup_game(game)
            return
        if len(game.active) < MIN_PLAYERS:
            game.phase = "finished"
            await context.bot.send_message(
                game.chat_id,
                "❌ Not enough players could be reached in private chat. Game cancelled.",
            )
            cleanup_game(game)
            return

    await context.bot.send_message(
        game.chat_id,
        "🎮 <b>The game has started!</b>\n"
        f"👥 {len(game.active)} players are in. Everyone, check your bot DM for your secret word.\n"
        "🔒 Keep your word secret. Explanations begin now.",
        parse_mode=ParseMode.HTML,
    )
    await start_explanation_round(game, context)

async def start_explanation_round(game: Game, context: ContextTypes.DEFAULT_TYPE) -> None:
    game.phase = "explaining"
    game.round_no = max(1, game.round_no)
    game.turn_index = 0
    game.explanations = {}
    game.votes = {}
    await context.bot.send_message(
        game.chat_id,
        f"🗣️ <b>Explanation round {game.round_no}</b>\n"
        "Each player must describe their word without saying it. "
        "Only the player whose turn it is should send a message.",
        parse_mode=ParseMode.HTML,
    )
    await prompt_current_player(game, context)

async def prompt_current_player(game: Game, context: ContextTypes.DEFAULT_TYPE) -> None:
    active = game.active_players()
    if game.turn_index >= len(active):
        await open_voting(game, context)
        return
    player = active[game.turn_index]
    await context.bot.send_message(
        game.chat_id,
        f"🎙️ {player.mention} — it's your turn to explain! "
        "Send one short explanation in the group.",
        parse_mode=ParseMode.HTML,
    )

async def group_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if not message or not chat or not user or chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return
    if message.text and message.text.startswith("/"):
        return
    game_id = CHAT_GAMES.get(chat.id)
    game = GAMES.get(game_id) if game_id else None
    if not game or game.phase != "explaining":
        return
    async with game.lock:
        active = game.active_players()
        if game.turn_index >= len(active):
            return
        current = active[game.turn_index]
        if user.id != current.user_id:
            try:
                await message.delete()
            except TelegramError:
                log.warning("Could not delete out-of-turn message in %s", chat.id)
            await context.bot.send_message(
                chat.id,
                f"⚠️ {Player.from_user(user).mention}, please let {current.mention} explain the word!",
                parse_mode=ParseMode.HTML,
            )
            return
        if user.id in game.explanations:
            await message.reply_text("You've already explained this round. Please wait for the others.")
            return
        game.explanations[user.id] = message.text or "[non-text message]"
        game.turn_index += 1
        await prompt_current_player(game, context)

def voting_text(game: Game) -> str:
    players = {p.user_id: p for p in game.players}
    lines = []
    for voter in game.active_players():
        target_id = game.votes.get(voter.user_id)
        if target_id:
            target = players.get(target_id)
            lines.append(f"{html.escape(voter.name)} ➜ {html.escape(target.name if target else 'Unknown')}")
        else:
            lines.append(f"{html.escape(voter.name)} ➜ <i>Not voted yet</i>")
    counts: dict[int, int] = {}
    for target_id in game.votes.values():
        counts[target_id] = counts.get(target_id, 0) + 1
    totals = "\n".join(
        f"• {html.escape(players[uid].name)}: <b>{count}</b>"
        for uid, count in sorted(counts.items(), key=lambda item: (-item[1], players[item[0]].name))
        if uid in players
    ) or "• No votes yet"
    return (
        f"🗳️ <b>VOTE — ROUND {game.round_no}</b>\n\n"
        "<b>Who voted for whom:</b>\n" + "\n".join(lines) +
        "\n\n<b>Live totals:</b>\n" + totals +
        f"\n\n✅ Votes: <b>{len(game.votes)}/{len(game.active)}</b>"
    )

def voting_markup(game: Game) -> InlineKeyboardMarkup:
    candidates = game.vote_candidates or game.active
    players = {p.user_id: p for p in game.players}
    rows = []
    for uid in candidates:
        player = players.get(uid)
        if player:
            rows.append([InlineKeyboardButton(player.name[:60], callback_data=f"vote:{game.game_id}:{uid}")])
    return InlineKeyboardMarkup(rows)

async def open_voting(game: Game, context: ContextTypes.DEFAULT_TYPE) -> None:
    game.phase = "voting"
    game.votes = {}
    game.vote_candidates = list(game.active)
    sent = await context.bot.send_message(
        game.chat_id,
        voting_text(game),
        reply_markup=voting_markup(game),
        parse_mode=ParseMode.HTML,
    )
    game.vote_message_id = sent.message_id

async def vote_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.from_user:
        return
    try:
        _, game_id, target_raw = query.data.split(":")
        target_id = int(target_raw)
    except (ValueError, AttributeError):
        await query.answer("This vote button is invalid.", show_alert=True)
        return
    game = GAMES.get(game_id)
    if not game or game.phase != "voting":
        await query.answer("This vote is closed.", show_alert=True)
        return
    async with game.lock:
        voter_id = query.from_user.id
        if voter_id not in game.active:
            await query.answer("Only active players can vote.", show_alert=True)
            return
        if voter_id in game.votes:
            await query.answer("You've already voted.", show_alert=True)
            return
        if target_id not in (game.vote_candidates or []):
            await query.answer("That player isn't eligible in this vote.", show_alert=True)
            return
        if voter_id == target_id:
            await query.answer("You can't vote for yourself.", show_alert=True)
            return
        game.votes[voter_id] = target_id
        await query.answer("Vote recorded!")
        try:
            await context.bot.edit_message_text(
                voting_text(game),
                chat_id=game.chat_id,
                message_id=game.vote_message_id,
                reply_markup=voting_markup(game),
                parse_mode=ParseMode.HTML,
            )
        except BadRequest as exc:
            if "Message is not modified" not in str(exc):
                log.warning("Voting message edit failed: %s", exc)
        if len(game.votes) == len(game.active):
            await finish_voting(game, context)

async def finish_voting(game: Game, context: ContextTypes.DEFAULT_TYPE) -> None:
    if game.phase != "voting":
        return
    game.phase = "resolving"
    counts: dict[int, int] = {}
    for target_id in game.votes.values():
        counts[target_id] = counts.get(target_id, 0) + 1
    if not counts:
        game.phase = "finished"
        await context.bot.send_message(game.chat_id, "No valid votes were cast. Game cancelled.")
        cleanup_game(game)
        return
    highest = max(counts.values())
    tied = [uid for uid, count in counts.items() if count == highest]
    if len(tied) > 1:
        game.phase = "voting"
        game.vote_candidates = tied
        game.votes = {}
        sent = await context.bot.send_message(
            game.chat_id,
            "⚖️ <b>It's a tie!</b> Vote again between the tied players.\n\n" + voting_text(game),
            reply_markup=voting_markup(game),
            parse_mode=ParseMode.HTML,
        )
        game.vote_message_id = sent.message_id
        return
    eliminated_id = tied[0]
    eliminated = game.player(eliminated_id)
    result_lines = []
    players = {p.user_id: p for p in game.players}
    for voter_id, target_id in game.votes.items():
        voter = players.get(voter_id)
        target = players.get(target_id)
        if voter and target:
            result_lines.append(f"• {voter.mention} voted for {target.mention}")
    await context.bot.send_message(
        game.chat_id,
        "📊 <b>FINAL VOTE BREAKDOWN</b>\n" +
        ("\n".join(result_lines) or "No votes") +
        "\n\n" +
        "\n".join(f"• {html.escape(players[uid].name)}: <b>{count}</b> vote(s)" for uid, count in sorted(counts.items(), key=lambda x: -x[1])) +
        f"\n\n🚪 {eliminated.mention if eliminated else 'A player'} has been eliminated!",
        parse_mode=ParseMode.HTML,
    )
    if eliminated_id == game.spy_id:
        await ask_spy_guess(game, context)
        return
    game.active = [uid for uid in game.active if uid != eliminated_id]
    if len(game.active) <= 2:
        await end_game(game, context, spy_wins=True, reason="The Spy survived until only two players remained.")
        return
    await context.bot.send_message(
        game.chat_id,
        "❌ That player was not the Spy. The game continues with another round!",
    )
    game.round_no += 1
    await start_explanation_round(game, context)

async def ask_spy_guess(game: Game, context: ContextTypes.DEFAULT_TYPE) -> None:
    game.phase = "spy_guess"
    options = [game.civilian_word]
    # Offer plausible distractors; only the exact civilian word wins.
    distractors = [pair[0] for pair in WORD_PAIRS if pair[0] != game.civilian_word]
    options.extend(random.sample(distractors, min(3, len(distractors))))
    random.shuffle(options)
    rows = [[InlineKeyboardButton(word, callback_data=f"guess:{game.game_id}:{i}")]
            for i, word in enumerate(options)]
    try:
        await context.bot.send_message(
            game.spy_id,
            "🎯 <b>You were caught!</b>\n\nYou get one final chance to steal the win. "
            "What was the civilians' word?",
            reply_markup=InlineKeyboardMarkup(rows),
            parse_mode=ParseMode.HTML,
        )
        game._guess_options = options
    except TelegramError:
        await end_game(game, context, spy_wins=False, reason="The Spy could not receive the final guess.")
        return
    await context.bot.send_message(
        game.chat_id,
        "🕵️ The Spy has been identified! They're getting one final chance to guess the civilians' word.",
    )

async def guess_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.from_user:
        return
    try:
        _, game_id, index_raw = query.data.split(":")
        index = int(index_raw)
    except (ValueError, AttributeError):
        await query.answer("Invalid guess.", show_alert=True)
        return
    game = GAMES.get(game_id)
    if not game or game.phase != "spy_guess" or query.from_user.id != game.spy_id:
        await query.answer("This final guess isn't for you.", show_alert=True)
        return
    options = getattr(game, "_guess_options", [])
    if index < 0 or index >= len(options):
        await query.answer("Invalid guess.", show_alert=True)
        return
    chosen = options[index]
    await query.answer("Guess locked!")
    try:
        await query.edit_message_text(f"Your guess: <b>{html.escape(chosen)}</b>", parse_mode=ParseMode.HTML)
    except TelegramError:
        pass
    await end_game(
        game, context,
        spy_wins=(chosen == game.civilian_word),
        reason=("The Spy guessed the civilians' word correctly!" if chosen == game.civilian_word
                else "The Spy guessed the wrong word."),
    )

async def end_game(game: Game, context: ContextTypes.DEFAULT_TYPE, spy_wins: bool, reason: str) -> None:
    game.phase = "finished"
    spy = game.player(game.spy_id) if game.spy_id else None
    winner = "🕵️ <b>THE SPY WINS!</b>" if spy_wins else "🎉 <b>THE CIVILIANS WIN!</b>"
    await context.bot.send_message(
        game.chat_id,
        f"{winner}\n\n{html.escape(reason)}\n\n"
        f"🕵️ Spy: {spy.mention if spy else 'Unknown'}\n"
        f"👥 Civilians' word: <b>{html.escape(game.civilian_word or '')}</b>\n"
        f"🕵️ Spy's word: <b>{html.escape(game.spy_word or '')}</b>",
        parse_mode=ParseMode.HTML,
    )
    cleanup_game(game)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.exception("Unhandled Telegram update error", exc_info=context.error)

def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN is missing. Set it in your environment or .env file.")
    db_init()
    app = Application.builder().token(BOT_TOKEN).build()

    async def post_init(application: Application) -> None:
        global BOT_USERNAME
        me = await application.bot.get_me()
        BOT_USERNAME = me.username or ""
        if not BOT_USERNAME:
            raise RuntimeError("The bot must have a Telegram username for Join Game deep links.")
        log.info("Bot started as @%s; required channel: %s", BOT_USERNAME, REQUIRED_CHANNEL)

    app.post_init = post_init
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("spy", spy_command))
    app.add_handler(CommandHandler("cancelspy", cancel_command))
    app.add_handler(CallbackQueryHandler(verify_channel_callback, pattern=r"^verify_channel$"))
    app.add_handler(CallbackQueryHandler(vote_callback, pattern=r"^vote:"))
    app.add_handler(CallbackQueryHandler(guess_callback, pattern=r"^guess:"))
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & ~filters.COMMAND, group_text_handler))
    app.add_error_handler(error_handler)
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
