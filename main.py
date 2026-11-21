from __future__ import annotations

import asyncio
import html
import logging
import os
import re
import random
import sqlite3
import uuid
from dataclasses import dataclass, field
from typing import Optional

import uuid
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
LOBBY_SECONDS = 10  # Temporary solo-demo lobby; restore to 120 after testing.
EXPLANATION_SECONDS = 30
GAME_START_COUNTDOWN = 30
VOTING_SECONDS = 30
SPY_GUESS_SECONDS = 30

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("whos-the-spy")

# Simple everyday English + Hindi/Hinglish word groups.
# Every pair comes from the same familiar topic, so clues are easy to explain.
WORD_GROUPS = [
    ["chai", "coffee", "doodh", "lassi", "juice", "paani", "sharbat", "soda", "nimbu paani", "milkshake"],
    ["roti", "naan", "paratha", "puri", "bread", "pizza", "burger", "sandwich", "pasta", "noodles"],
    ["samosa", "kachori", "pakora", "kachcha", "kachumber", "momos", "fries", "chips", "popcorn", "biscuit"],
    ["aloo", "pyaz", "tamatar", "gajar", "matar", "bhindi", "gobhi", "baingan", "mirchi", "adrak"],
    ["mango", "apple", "banana", "orange", "grapes", "papaya", "guava", "watermelon", "coconut", "pineapple"],
    ["jalebi", "gulab jamun", "rasgulla", "laddu", "barfi", "cake", "ice cream", "chocolate", "toffee", "cookie"],
    ["dal", "chawal", "rajma", "chole", "biryani", "pulao", "khichdi", "kadhi", "paneer", "butter chicken"],
    ["namak", "cheeni", "mirch", "haldi", "jeera", "dhaniya", "elaichi", "laung", "dalchini", "ajwain"],
    ["school", "college", "classroom", "teacher", "student", "principal", "homework", "exam", "blackboard", "notebook"],
    ["pencil", "pen", "eraser", "sharpener", "scale", "marker", "crayon", "book", "bag", "lunchbox"],
    ["mobile", "phone", "charger", "earphones", "headphones", "speaker", "remote", "keyboard", "mouse", "laptop"],
    ["instagram", "youtube", "whatsapp", "telegram", "facebook", "snapchat", "reel", "meme", "selfie", "status"],
    ["cricket", "football", "hockey", "kabaddi", "badminton", "tennis", "basketball", "volleyball", "chess", "carrom"],
    ["bat", "ball", "wicket", "stumps", "helmet", "gloves", " jersey", "whistle", "goal", "referee"],
    ["shirt", "tshirt", "jeans", "pant", "shorts", "kurta", "saree", "dress", "skirt", "jacket"],
    ["bra", "panty", "socks", "vest", "underwear", "pajama", "night suit", "towel", "dupatta", "cap"],
    ["shoes", "slippers", "sandals", "boots", "heels", "sneakers", "socks", "shoelace", "belt", "wallet"],
    ["soap", "shampoo", "conditioner", "toothpaste", "toothbrush", "comb", "mirror", "perfume", "deodorant", "face wash"],
    ["bed", "pillow", "blanket", "mattress", "bedsheet", "sofa", "chair", "table", "stool", "cupboard"],
    ["fan", "cooler", "AC", "heater", "fridge", "washing machine", "mixer", "microwave", "iron", "TV"],
    ["ghar", "kamra", "rasoi", "bathroom", "balcony", "chhat", "darwaza", "khidki", "seedhi", "garden"],
    ["mummy", "papa", "bhai", "behen", "dadi", "nani", "dada", "nana", "chacha", "mama"],
    ["dog", "cat", "cow", "buffalo", "goat", "sheep", "horse", "donkey", "camel", "monkey"],
    ["lion", "tiger", "elephant", "giraffe", "zebra", "bear", "fox", "wolf", "deer", "rabbit"],
    ["crow", "pigeon", "parrot", "sparrow", "peacock", "hen", "duck", "eagle", "owl", "hen"],
    ["ant", "bee", "butterfly", "mosquito", "fly", "spider", "cockroach", "lizard", "frog", "snake"],
    ["sun", "moon", "star", "cloud", "rain", "snow", "wind", "thunder", "rainbow", "fog"],
    ["summer", "winter", "monsoon", "spring", "morning", "afternoon", "evening", "night", "today", "tomorrow"],
    ["car", "bus", "train", "metro", "bike", "scooter", "cycle", "truck", "auto", "tractor"],
    ["airport", "railway station", "bus stop", "market", "mall", "park", "zoo", "cinema", "hospital", "hotel"],
    ["Delhi", "Mumbai", "Chandigarh", "Ludhiana", "Amritsar", "Jaipur", "Agra", "Pune", "Goa", "Kolkata"],
    ["doctor", "nurse", "teacher", "police", "driver", "chef", "farmer", "singer", "actor", "dancer"],
    ["king", "queen", "prince", "princess", "joker", "policeman", "superhero", "villain", "ghost", "monster"],
    ["wedding", "birthday", "party", " picnic", "holiday", "festival", "Diwali", "Holi", "Eid", "Christmas"],
    ["phone call", "message", "voice note", "video call", "group chat", "missed call", "alarm", " ringtone", "password", "emoji"],
    ["laugh", "cry", "smile", "sleep", "snore", "yawn", "dance", "sing", "shout", "whisper"],
    ["pankha", "jhadu", "pocha", "balti", "mug", "plate", "glass", "spoon", "fork", "katori"],
    ["chappal", "joota", "topi", "pagdi", "chashma", "ghadi", "chain", "ring", "bangle", "earring"],
    ["pocket", "button", "zip", "collar", "sleeve", "hood", "lace", "purse", "bag", "suitcase"],
    ["pizza", "dosa", "idli", "dhokla", "pav bhaji", "chole bhature", "poha", "upma", "paratha", "maggi"],
    ["water", "fire", "earth", "air", "sand", "mud", "stone", "wood", "metal", "plastic"],
    ["red", "blue", "green", "yellow", "pink", "purple", "black", "white", "orange", "brown"],
    ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"],
    ["money", "coin", "note", "wallet", "ATM", "bank", "UPI", "QR code", "salary", "pocket money"],
    ["wedding card", "gift", "balloon", "candle", "cake topper", "confetti", "ribbon", "decoration", "flower", "bouquet"],
    ["meme", "joke", "prank", "roast", "comedy", "funny video", "cartoon", "filter", "sticker", "GIF"],
    ["traffic", "signal", "zebra crossing", "speed breaker", "helmet", "seat belt", "parking", "petrol", "diesel", "puncture"],
    ["crush", "best friend", "classmate", "neighbour", "roommate", "teammate", "cousin", "guest", "stranger", "celebrity"],
    ["soap opera", "movie", "web series", "song", "dance video", "news", "cartoon show", "game show", "music video", "short film"],
    ["pani puri", "golgappa", "bhel puri", "sev puri", "dahi puri", "papdi chaat", "tikki", "chaat", "kulcha", "kulfi"],
]

def build_word_pair_bank() -> int:
    """Replace obscure dictionary pairs with thousands of familiar, easy-to-explain pairs."""
    pairs = set()
    for group in WORD_GROUPS:
        words = list(dict.fromkeys(word.strip() for word in group if word.strip()))
        for i in range(len(words)):
            for j in range(i + 1, len(words)):
                left, right = sorted((words[i], words[j]), key=str.casefold)
                pairs.add((left, right))
    with sqlite3.connect(DATABASE_PATH) as db:
        db.execute("CREATE TABLE IF NOT EXISTS word_bank_meta (version INTEGER NOT NULL)")
        row = db.execute("SELECT version FROM word_bank_meta LIMIT 1").fetchone()
        if row and row[0] == 2:
            return db.execute("SELECT COUNT(*) FROM word_pair_bank").fetchone()[0]

        # Replace the old WordNet table once, removing its per-column UNIQUE limits.
        db.execute("DROP TABLE IF EXISTS word_pair_bank")
        db.execute("""CREATE TABLE word_pair_bank (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word_a TEXT NOT NULL,
            word_b TEXT NOT NULL,
            used INTEGER NOT NULL DEFAULT 0
        )""")
        db.executemany(
            "INSERT INTO word_pair_bank(word_a, word_b, used) VALUES(?, ?, 0)",
            sorted(pairs, key=lambda pair: (pair[0].casefold(), pair[1].casefold())),
        )
        db.execute("DELETE FROM word_bank_meta")
        db.execute("INSERT INTO word_bank_meta(version) VALUES(2)")
        count = db.execute("SELECT COUNT(*) FROM word_pair_bank").fetchone()[0]
    return count


@dataclass
class Player:
    user_id: int
    name: str
    username: Optional[str] = None
    is_npc: bool = False

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
    vote_is_tiebreaker: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    task: Optional[asyncio.Task] = None
    turn_task: Optional[asyncio.Task] = None
    vote_task: Optional[asyncio.Task] = None
    guess_task: Optional[asyncio.Task] = None
    npc_task: Optional[asyncio.Task] = None

    def player(self, user_id: int) -> Optional[Player]:
        return next((p for p in self.players if p.user_id == user_id), None)

    def active_players(self) -> list[Player]:
        return [p for p in self.players if p.user_id in self.active]


GAMES: dict[str, Game] = {}
CHAT_GAMES: dict[int, str] = {}
BOT_USERNAME = ""

def next_word_pair() -> tuple[str, str]:
    """Return a pair without reusing either word until the full bank is exhausted."""
    with sqlite3.connect(DATABASE_PATH, timeout=30) as db:
        row = db.execute(
            "SELECT id, word_a, word_b FROM word_pair_bank "
            "WHERE used = 0 ORDER BY RANDOM() LIMIT 1"
        ).fetchone()
        if row is None:
            db.execute("UPDATE word_pair_bank SET used = 0")
            row = db.execute(
                "SELECT id, word_a, word_b FROM word_pair_bank "
                "ORDER BY RANDOM() LIMIT 1"
            ).fetchone()
        if row is None:
            raise RuntimeError("The word-pair bank is empty.")
        db.execute("UPDATE word_pair_bank SET used = 1 WHERE id = ?", (row[0],))
        return row[1], row[2]


def db_init() -> None:
    with sqlite3.connect(DATABASE_PATH) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS players (
            user_id INTEGER PRIMARY KEY, name TEXT NOT NULL, username TEXT,
            joined_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS word_pair_bank (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word_a TEXT NOT NULL UNIQUE,
            word_b TEXT NOT NULL UNIQUE,
            used INTEGER NOT NULL DEFAULT 0
        )""")
    pair_count = build_word_pair_bank()
    log.info("Loaded %s unique word pairs (%s unique words).", pair_count, pair_count * 2)

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
        [InlineKeyboardButton("📢 Join Channel", url=url, style="primary")],
        [InlineKeyboardButton("✅ I've Joined — Verify", callback_data="verify_channel", style="success")],
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
    return InlineKeyboardMarkup([[InlineKeyboardButton("🎮 Join Game", url=deep_link, style="success")]])

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
        await asyncio.sleep(5)
        if game.phase != "lobby":
            return
        try:
            await context.bot.send_message(
                game.chat_id,
                "⏳ <b>5 seconds left! Demo game is starting.</b>",
                reply_to_message_id=game.lobby_message_id,
                parse_mode=ParseMode.HTML,
            )
        except TelegramError:
            log.exception("Could not send lobby reminder")
        await asyncio.sleep(5)
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
    user = update.effective_user
    if not message or not chat or chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        if message:
            await message.reply_text("Use /spy in a Telegram group.")
        return
    if not user or not await check_membership(context.bot, user.id):
        await send_channel_gate(message)
        return
    current_id = CHAT_GAMES.get(chat.id)
    if current_id and current_id in GAMES:
        await message.reply_text("A game is already running in this group.")
        return

    game_id = uuid.uuid4().hex[:10]
    game = Game(game_id=game_id, chat_id=chat.id, lobby_message_id=0)
    # Temporary demo mode: the command sender plus four clearly-labelled NPCs.
    game.players.append(Player.from_user(user))
    npc_names = random.sample(["Alex", "Jordan", "Riley", "Taylor", "Morgan", "Casey", "Jamie", "Avery"], 4)
    for index, npc_name in enumerate(npc_names, start=1):
        game.players.append(Player(user_id=-index, name=f"{npc_name} (Demo)", username=None, is_npc=True))
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
    log.info("Demo lobby %s opened in %s with four NPCs", game_id, chat.id)

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
    for task in (game.turn_task, game.vote_task, game.guess_task, game.npc_task):
        if task:
            task.cancel()
    await message.reply_text("🛑 The game has been cancelled.")
    cleanup_game(game)

def main_menu_markup() -> InlineKeyboardMarkup:
    add_to_group_url = f"https://t.me/{BOT_USERNAME}?startgroup=true"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Bot to Your Group", url=add_to_group_url, style="success")],
        [
            InlineKeyboardButton("📜 Rules", callback_data="menu:rules", style="primary"),
            InlineKeyboardButton("💬 Discussion", url="https://t.me/+WJYnfYWc_GU0Y2U1", style="success"),
        ],
    ])


def rules_text() -> str:
    return (
        "📜 <b>WHO'S THE SPY? — GAME RULES</b>\n\n"
        "<b>🎯 Objective</b>\n"
        "• Civilians share one secret word.\n"
        "• The Spy gets a related but different word.\n"
        "• Civilians must identify the Spy; the Spy must blend in.\n\n"
        "<b>🎮 How a game works</b>\n"
        "1. Start a lobby with /spy in a group.\n"
        "2. At least 5 players must join within 2 minutes.\n"
        "3. Everyone receives their secret word in the bot's DM.\n"
        "4. The game begins 30 seconds after the words are sent.\n"
        "5. Each player gets a 30-second turn to give clues about their word.\n"
        "6. During voting, everyone can discuss freely before choosing a player.\n"
        "7. Everyone gets 30 seconds to vote. Missing votes count as no vote.\n\n"
        "<b>🗳️ Voting</b>\n"
        "• You cannot vote for yourself.\n"
        "• The player with the most votes is eliminated.\n"
        "• A tie starts another vote between the tied players.\n"
        "• If the eliminated player is not the Spy, another round begins.\n\n"
        "<b>🕵️ Final chance</b>\n"
        "If the Spy is caught, they get 30 seconds to guess the civilians' word. "
        "A correct guess wins the game for the Spy; otherwise, civilians win.\n\n"
        "<b>⚠️ Important</b>\n"
        "• Join the required channel and press /start in the bot's DM before playing.\n"
        "• Keep your secret word private.\n"
        "• During explanation turns, only the active player's messages are accepted.\n"
        "• Group discussion stays open during voting."
    )
async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    if not await check_membership(context.bot, query.from_user.id):
        await query.answer("Please join @xyronschannel before using the bot.", show_alert=True)
        return
    if query.data == "menu:rules":
        await query.answer()
        await query.edit_message_text(
            rules_text(),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Back to Menu", callback_data="menu:home", style="primary")
            ]]),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    elif query.data == "menu:home":
        await query.answer()
        await query.edit_message_text(
            "╭━━━ 🕵️ ━━━╮\n"
            "<b>WHO'S THE SPY?</b>\n"
            "╰━━━━━━━━━━╯\n\n"
            "Welcome, detective.\n\n"
            "Your mission is simple:\n"
            "Blend in. Read the room. Question everything.\n\n"
            "Somewhere in the group, someone has a different word.\n"
            "They'll do everything they can to avoid being exposed.\n\n"
            "Think you can figure out who's pretending?\n\n"
            "The investigation starts in your group chat.",
            reply_markup=main_menu_markup(),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )


async def rules_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    if message and user:
        if not await check_membership(context.bot, user.id):
            await send_channel_gate(message)
            return
        await message.reply_text(
            rules_text(),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Main Menu", callback_data="menu:home", style="primary")
            ]]),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )


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
            await message.reply_text(
                "⌛ <b>This lobby has closed.</b>\nAsk the group to start a fresh game with /spy.",
                parse_mode=ParseMode.HTML,
            )
            return
        async with game.lock:
            if game.phase != "lobby":
                await message.reply_text("⌛ This lobby has already started.")
                return
            if game.player(user.id):
                await message.reply_text("✅ You're already in! Keep this chat open for your secret word.")
                return
            if len(game.players) >= 30:
                await message.reply_text("🚫 This lobby is full (30 players).")
                return
            game.players.append(Player.from_user(user))
            await message.reply_text(
                "🎉 <b>YOU'RE IN!</b>\n\n"
                "Your place is confirmed. Keep this chat open — your secret word will arrive here when the game begins.",
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
        "╭━━━ 🕵️ ━━━╮\n"
        "<b>WHO'S THE SPY?</b>\n"
        "╰━━━━━━━━━━╯\n\n"
        "Welcome, detective.\n\n"
        "Your mission is simple:\n"
        "Blend in. Read the room. Question everything.\n\n"
        "Somewhere in the group, someone has a different word.\n"
        "They'll do everything they can to avoid being exposed.\n\n"
        "Think you can figure out who's pretending?\n\n"
        "The investigation starts in your group chat.",
        reply_markup=main_menu_markup(),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )

async def verify_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.from_user:
        return
    if await check_membership(context.bot, query.from_user.id):
        await query.answer("Membership verified!")
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
    game.phase = "starting"
    game.active = [p.user_id for p in game.players]
    game.spy_id = random.choice(game.active)
    game.civilian_word, game.spy_word = next_word_pair()
    random.shuffle(game.active)

    failed = []
    for player in game.players:
        word = game.spy_word if player.user_id == game.spy_id else game.civilian_word
        if player.is_npc:
            continue
        try:
            await context.bot.send_message(
                player.user_id,
                (
                    f"🕵️ <b>YOU ARE THE SPY!</b>\n\nYou are the only Spy. Blend in with the others.\n\nYour secret word is: <b>{html.escape(word)}</b>"
                    if player.user_id == game.spy_id else
                    f"🔐 <b>YOUR SECRET WORD</b>\n\nYour word is: <b>{html.escape(word)}</b>"
                ),

                parse_mode=ParseMode.HTML,
            )
        except (Forbidden, TelegramError):
            failed.append(player.user_id)

    if failed:
        game.active = [uid for uid in game.active if uid not in failed]
        game.players = [p for p in game.players if p.user_id not in failed]
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
        "Words have been sent to your DMs ⚡",
        parse_mode=ParseMode.HTML,
    )
    await asyncio.sleep(GAME_START_COUNTDOWN)
    if game.phase != "starting":
        return
    await start_explanation_round(game, context)

async def start_explanation_round(game: Game, context: ContextTypes.DEFAULT_TYPE) -> None:
    game.phase = "explaining"
    game.round_no = max(1, game.round_no)
    game.turn_index = 0
    game.explanations = {}
    game.votes = {}
    await prompt_current_player(game, context)

async def prompt_current_player(game: Game, context: ContextTypes.DEFAULT_TYPE) -> None:
    active = game.active_players()
    if game.turn_index >= len(active):
        await open_voting(game, context)
        return
    player = active[game.turn_index]
    if player.is_npc:
        if game.turn_index == 0:
            heading = f"🗣️ <b>ROUND {game.round_no}</b>\n\n"
        else:
            heading = ""
        clues = [
            "You might use it every morning.",
            "It is something many people know well.",
            "You can find it in different places.",
            "It is associated with everyday life.",
            "Some people prefer it over its alternative.",
        ]
        await context.bot.send_message(game.chat_id, heading + f"🎙️ <b>{html.escape(player.name)}'s turn</b>\n{html.escape(random.choice(clues))}", parse_mode=ParseMode.HTML)
        game.turn_index += 1
        game.turn_task = asyncio.create_task(npc_next_turn(game, context))
        return
    turn_label = f"@{player.username}" if player.username else player.name
    heading = f"🗣️ <b>ROUND {game.round_no}</b>\n\n" if game.turn_index == 0 else ""
    await context.bot.send_message(
        game.chat_id,
        heading + f"🎙️ <b>{html.escape(turn_label)}, describe your word.</b>",
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )
    if game.turn_task and game.turn_task is not asyncio.current_task():
        game.turn_task.cancel()
    game.turn_task = asyncio.create_task(
        explanation_timeout(game, context, game.round_no, game.turn_index)
    )

async def npc_next_turn(game: Game, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await asyncio.sleep(3)
        async with game.lock:
            if game.phase == "explaining":
                await prompt_current_player(game, context)
    except asyncio.CancelledError:
        return
    except Exception:
        log.exception("NPC turn failed")


async def explanation_timeout(
    game: Game,
    context: ContextTypes.DEFAULT_TYPE,
    round_no: int,
    turn_index: int,
) -> None:
    try:
        await asyncio.sleep(EXPLANATION_SECONDS)
        async with game.lock:
            if (game.phase != "explaining" or game.round_no != round_no
                    or game.turn_index != turn_index):
                return
            active = game.active_players()
            if game.turn_index < len(active):
                game.turn_index += 1
                await prompt_current_player(game, context)
    except asyncio.CancelledError:
        return
    except Exception:
        log.exception("Explanation timer failed")

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
        # Do not inspect or delete chat messages outside explanation turns.
        return
    async with game.lock:
        if game.phase != "explaining":
            return
        active = game.active_players()
        if game.turn_index >= len(active):
            try:
                await message.delete()
            except TelegramError:
                pass
            return
        current = active[game.turn_index]
        if user.id != current.user_id:
            try:
                await message.delete()
            except TelegramError:
                pass
            return
        # Current player may send unlimited messages during the full 30-second window.

def voting_text(game: Game) -> str:
    players = {p.user_id: p for p in game.players}
    counts: dict[int, int] = {}
    for target_id in game.votes.values():
        counts[target_id] = counts.get(target_id, 0) + 1
    totals = "\n".join(
        f"• {html.escape(players[uid].name)} — <b>{count}</b>"
        for uid, count in sorted(counts.items(), key=lambda item: (-item[1], players[item[0]].name))
        if uid in players
    ) or "• No votes yet"
    heading = (
        f"⚖️ <b>TIE-BREAKER · ROUND {game.round_no}</b>"
        if game.vote_is_tiebreaker else f"🗳️ <b>VOTING · ROUND {game.round_no}</b>"
    )
    return (
        f"{heading}\n\n"
        f"{totals}\n\n"
        f"🗳️ <b>{len(game.votes)}/{len(game.active)} votes</b> · "
        f"⏳ <b>{VOTING_SECONDS}s</b>"
    )


def voting_markup(game: Game) -> InlineKeyboardMarkup:
    candidates = game.vote_candidates or game.active
    players = {p.user_id: p for p in game.players}
    styles = ["danger", "primary", "success"]
    rows = []
    for index, uid in enumerate(candidates):
        player = players.get(uid)
        if player:
            rows.append([InlineKeyboardButton(
                f"🔴 {player.name[:55]}",
                callback_data=f"vote:{game.game_id}:{uid}",
                style=styles[index % len(styles)]
            )])
    return InlineKeyboardMarkup(rows)


async def voting_timeout(game: Game, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await asyncio.sleep(VOTING_SECONDS)
        async with game.lock:
            if game.phase == "voting":
                await finish_voting(game, context)
    except asyncio.CancelledError:
        return
    except Exception:
        log.exception("Voting timer failed")


async def open_voting(game: Game, context: ContextTypes.DEFAULT_TYPE) -> None:
    game.phase = "voting"
    game.votes = {}
    game.vote_candidates = list(game.active)
    # Demo NPCs cast their votes automatically so a solo test can reach a result.
    npc_ids = [p.user_id for p in game.active_players() if p.is_npc]
    for npc_id in npc_ids:
        choices = [uid for uid in game.vote_candidates if uid != npc_id]
        if choices:
            game.votes[npc_id] = random.choice(choices)
    sent = await context.bot.send_message(
        game.chat_id,
        voting_text(game),
        reply_markup=voting_markup(game),
        parse_mode=ParseMode.HTML,
    )
    game.vote_message_id = sent.message_id
    if game.vote_task:
        game.vote_task.cancel()
    game.vote_task = asyncio.create_task(voting_timeout(game, context))


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

async def finish_voting(game: Game, context: ContextTypes.DEFAULT_TYPE) -> None:
    if game.phase != "voting":
        return
    game.phase = "resolving"
    if game.vote_task and game.vote_task is not asyncio.current_task():
        game.vote_task.cancel()
    game.vote_task = None
    counts: dict[int, int] = {}
    for target_id in game.votes.values():
        counts[target_id] = counts.get(target_id, 0) + 1
    if not counts:
        await context.bot.send_message(game.chat_id, "⏳ Voting ended with no votes. Nobody is eliminated; the game continues.")
        game.round_no += 1
        await start_explanation_round(game, context)
        return
    highest = max(counts.values())
    tied = [uid for uid, count in counts.items() if count == highest]
    if len(tied) > 1:
        game.phase = "voting"
        game.vote_is_tiebreaker = True
        game.vote_candidates = tied
        game.votes = {}
        for npc in [p for p in game.active_players() if p.is_npc]:
            choices = [uid for uid in tied if uid != npc.user_id]
            if choices:
                game.votes[npc.user_id] = random.choice(choices)
        try:
            await context.bot.edit_message_text(
                voting_text(game),
                chat_id=game.chat_id,
                message_id=game.vote_message_id,
                reply_markup=voting_markup(game),
                parse_mode=ParseMode.HTML,
            )
        except TelegramError:
            log.exception("Could not update voting message for tie-breaker")
        game.vote_task = asyncio.create_task(voting_timeout(game, context))
        return
    if game.vote_message_id:
        try:
            await context.bot.edit_message_text(
                voting_text(game) + "\n\n🔒 <b>CLOSED</b>",
                chat_id=game.chat_id,
                message_id=game.vote_message_id,
                reply_markup=None,
                parse_mode=ParseMode.HTML,
            )
        except TelegramError:
            pass
    eliminated_id = tied[0]
    eliminated = game.player(eliminated_id)
    players = {p.user_id: p for p in game.players}

    # Decide mention style from the number of distinct people named anywhere
    # in this complete breakdown, including voters, targets, tally, and elimination.
    mentioned_ids = set(game.votes.keys()) | set(game.votes.values()) | set(counts.keys())
    if eliminated_id is not None:
        mentioned_ids.add(eliminated_id)
    single_person = len(mentioned_ids) == 1

    def linked_name(player: Player, limit: int = 14) -> str:
        label = player.name if len(player.name) <= limit else player.name[:limit - 1].rstrip() + "…"
        escaped = html.escape(label)
        if player.is_npc:
            return escaped
        if single_person and player.username:
            return "@" + html.escape(player.username)
        href = (
            f"https://t.me/{html.escape(player.username)}"
            if player.username else f"tg://user?id={player.user_id}"
        )
        return f'<a href="{href}">{escaped}</a>'

    def aligned_name(player: Player, width: int = 15) -> str:
        label = player.name if len(player.name) <= width else player.name[:width - 1].rstrip() + "…"
        # Figure spaces keep the vote marker aligned without relying on Markdown spacing.
        padding = "\u2007" * max(1, width - len(label) + 1)
        return linked_name(player, width) + padding

    result_lines = []
    for voter_id, target_id in game.votes.items():
        voter = players.get(voter_id)
        target = players.get(target_id)
        if voter and target:
            result_lines.append(f"• {aligned_name(voter)}🔴 {linked_name(target)}")
    tally_lines = [
        f"• {linked_name(players[uid])}: <b>{count}</b> vote(s)"
        for uid, count in sorted(counts.items(), key=lambda x: -x[1])
        if uid in players
    ]
    await context.bot.send_message(
        game.chat_id,
        "📊 <b>FINAL VOTE BREAKDOWN</b>\n" +
        ("\n".join(result_lines) or "No votes") +
        "\n\n" +
        "\n".join(tally_lines) +
        f"\n\n🚪 <b>{linked_name(eliminated) if eliminated else 'A player'}</b> has been eliminated!",
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
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
    spy_player = game.player(game.spy_id) if game.spy_id else None
    if spy_player and spy_player.is_npc:
        correct = random.random() < 0.35
        await context.bot.send_message(game.chat_id, f"🎯 <b>{html.escape(spy_player.name)}</b> is making a final guess...", parse_mode=ParseMode.HTML)
        await asyncio.sleep(3)
        await end_game(game, context, spy_wins=correct, reason=("The demo Spy guessed the civilians' word correctly!" if correct else "The demo Spy guessed the wrong word."))
        return
    options = [game.civilian_word]
    # Use only words from the simple everyday bank for the Spy's final choices.
    with sqlite3.connect(DATABASE_PATH) as db:
        distractors = [
            row[0] for row in db.execute(
                "SELECT word_a FROM word_pair_bank WHERE word_a != ? "
                "UNION SELECT word_b FROM word_pair_bank WHERE word_b != ?",
                (game.civilian_word, game.civilian_word),
            ).fetchall()
        ]
    options.extend(random.sample(distractors, min(3, len(distractors))))
    random.shuffle(options)
    guess_styles = ["primary", "success", "danger"]
    rows = [[InlineKeyboardButton(f"{word}", callback_data=f"guess:{game.game_id}:{i}", style=guess_styles[i % len(guess_styles)])]
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
        f"🕵️ The Spy has been identified! They have {SPY_GUESS_SECONDS} seconds for one final guess.",
    )
    game.guess_task = asyncio.create_task(spy_guess_timeout(game, context))


async def spy_guess_timeout(game: Game, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await asyncio.sleep(SPY_GUESS_SECONDS)
        if game.phase == "spy_guess":
            await end_game(game, context, spy_wins=False, reason="The Spy ran out of time without making a guess.")
    except asyncio.CancelledError:
        return
    except Exception:
        log.exception("Spy guess timer failed")


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
    if game.guess_task:
        game.guess_task.cancel()
        game.guess_task = None
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
    for task_name in ("turn_task", "vote_task", "guess_task", "npc_task"):
        task = getattr(game, task_name)
        if task and task is not asyncio.current_task():
            task.cancel()
        setattr(game, task_name, None)
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
    async def post_init(application: Application) -> None:
        global BOT_USERNAME
        me = await application.bot.get_me()
        BOT_USERNAME = me.username or ""
        if not BOT_USERNAME:
            raise RuntimeError("The bot must have a Telegram username for Join Game deep links.")
        log.info("Bot started as @%s; required channel: %s", BOT_USERNAME, REQUIRED_CHANNEL)

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("rules", rules_command))
    app.add_handler(CallbackQueryHandler(menu_callback, pattern=r"^menu:"))
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