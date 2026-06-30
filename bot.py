import os
import asyncio
import datetime
import difflib
import logging
import re
from typing import Dict, List, Literal, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
import aiohttp

from stat_parser import parse_game_message, ParseError, GameResult
from sheets_manager import SheetsManager, CURATED_STATS
from player_card import render_player_card, ALL_CARD_STATS
from team_stats_card import render_team_stats_card, render_single_team_card
from leaderboard_card import render_stat_leaderboard_card
from global_leaderboard_card import render_global_leaderboard_card
from league_card import render_league_card
import schedule

load_dotenv()

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
REFEREE_CHANNEL_ID = int(os.environ["REFEREE_CHANNEL_ID"])
REFEREE_ROLE_ID = os.environ.get("REFEREE_ROLE_ID")
GOOGLE_SERVICE_ACCOUNT_FILE = os.environ["GOOGLE_SERVICE_ACCOUNT_FILE"]
GOOGLE_SHEET_ID = os.environ["GOOGLE_SHEET_ID"]
MASTER_SHEET_NAME = os.environ.get("MASTER_SHEET_NAME", "AllGames")
GUILD_ID = os.environ.get("GUILD_ID")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("stats-bot")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

sheets = SheetsManager(GOOGLE_SERVICE_ACCOUNT_FILE, GOOGLE_SHEET_ID, MASTER_SHEET_NAME)


async def fetch_minecraft_head(username: str, size: int = 100) -> Optional[bytes]:
    url = f"https://mc-heads.net/avatar/{username}/{size}.png"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    return await resp.read()
    except Exception:
        pass
    return None


def resolve_week(game: GameResult) -> Tuple[Optional[int], str, str]:
    team_a, team_b = game.teams[0].name, game.teams[1].name
    return schedule.find_week(team_a, team_b), team_a, team_b


class TeamCorrectionView(discord.ui.View):
    def __init__(self, author_id: int, suggestions: list, timeout: float = 60):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.choice: Optional[str] = None
        for name in suggestions:
            self.add_item(self._suggestion_button(name))
        self.add_item(self._none_button())

    async def _authorized(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the person who posted this can answer.", ephemeral=True)
            return False
        return True

    def _suggestion_button(self, name: str) -> discord.ui.Button:
        button = discord.ui.Button(label=name, style=discord.ButtonStyle.primary)

        async def callback(interaction: discord.Interaction):
            if not await self._authorized(interaction):
                return
            self.choice = name
            await interaction.response.defer()
            self.stop()

        button.callback = callback
        return button

    def _none_button(self) -> discord.ui.Button:
        button = discord.ui.Button(label="None of these", style=discord.ButtonStyle.secondary)

        async def callback(interaction: discord.Interaction):
            if not await self._authorized(interaction):
                return
            self.choice = None
            await interaction.response.defer()
            self.stop()

        button.callback = callback
        return button


async def clarify_unmatched_teams(send, author_id: int, game: GameResult) -> Optional[GameResult]:
    known_teams = schedule.all_teams()
    known_lower = {t.lower() for t in known_teams}

    for team in game.teams:
        if team.name.strip().lower() in known_lower:
            continue

        suggestions = difflib.get_close_matches(team.name, known_teams, n=3, cutoff=0.6)
        if not suggestions:
            return None

        view = TeamCorrectionView(author_id, suggestions)
        await send(
            content=f"⚠️ I don't recognize **{team.name}** from the schedule. Did you mean one of these?",
            view=view,
        )
        timed_out = await view.wait()
        if timed_out or view.choice is None:
            return None

        await send(content=f"✅ Got it -- treating that as **{view.choice}**.")
        team.name = view.choice

    return game


def find_team_conflicts(game: GameResult, exclude_game_id: Optional[int] = None) -> dict:
    history = sheets.get_player_team_history(exclude_game_id=exclude_game_id)
    conflicts = {}
    for team in game.teams:
        for p in team.players:
            entry = history.get(p.name.strip().lower())
            if not entry:
                continue
            existing_teams = entry["teams"]
            if team.name.strip().lower() not in {t.lower() for t in existing_teams}:
                conflicts[p.name] = (team.name, existing_teams)
    return conflicts


class TeamChoiceView(discord.ui.View):
    MOVED = "__MOVED__"

    def __init__(self, author_id: int, team_options: list, moved_label: str, timeout: Optional[float] = None):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.choice: Optional[str] = None
        for team_name in team_options[:4]:
            self.add_item(self._team_button(team_name))
        self.add_item(self._moved_button(moved_label))

    async def _authorized(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the person who posted this can answer.", ephemeral=True)
            return False
        return True

    def _team_button(self, team_name: str) -> discord.ui.Button:
        button = discord.ui.Button(label=team_name, style=discord.ButtonStyle.secondary)

        async def callback(interaction: discord.Interaction):
            if not await self._authorized(interaction):
                return
            self.choice = team_name
            await interaction.response.defer()
            self.stop()

        button.callback = callback
        return button

    def _moved_button(self, label: str) -> discord.ui.Button:
        button = discord.ui.Button(label=label, style=discord.ButtonStyle.primary)

        async def callback(interaction: discord.Interaction):
            if not await self._authorized(interaction):
                return
            self.choice = self.MOVED
            await interaction.response.defer()
            self.stop()

        button.callback = callback
        return button


async def resolve_team_conflicts(send, author_id: int, conflicts: dict) -> list:
    excluded = []
    for player, (current_team, existing_teams) in conflicts.items():
        team_options = sorted(existing_teams)
        view = TeamChoiceView(author_id, team_options, moved_label=f"Moved teams (now {current_team})")
        await send(
            content=(
                f"👀 **{player}** was previously logged with **{', '.join(team_options)}**, but this game has them on **{current_team}**.\n"
                f"Which team do they actually play for?"
            ),
            view=view,
        )
        timed_out = await view.wait()
        if timed_out or view.choice is None:
            await send(content=f"⏱️ No response for **{player}** -- recording their stats as posted. Run `/sub` afterward if needed.")
            continue
        if view.choice == TeamChoiceView.MOVED:
            await send(content=f"✅ Got it -- **{current_team}** is now treated as **{player}**'s current team.")
        else:
            selected_team = view.choice
            excluded.append((player, current_team, selected_team))
            await send(
                content=(
                    f"✅ Got it -- **{player}** actually plays for **{selected_team}**. "
                    f"Their stats for this game (listed under **{current_team}**) won't be recorded."
                )
            )
    return excluded


def _strip_players(game: GameResult, names_to_exclude: set) -> GameResult:
    lower_excluded = {n.strip().lower() for n in names_to_exclude}
    for team in game.teams:
        team.players = [p for p in team.players if p.name.strip().lower() not in lower_excluded]
    return game


def build_recap_embed(game, game_id: int, week: int, title: str) -> discord.Embed:
    embed = discord.Embed(title=f"{title} -- Game #{game_id} (Week {week})", color=discord.Color.green())
    for team in game.teams:
        names = ", ".join(p.name for p in team.players)
        embed.add_field(name=f"{team.name} ({team.score})", value=names or "no players parsed", inline=False)

    unparsed_lines = []
    for team in game.teams:
        for p in team.players:
            if p.unparsed:
                unparsed_lines.append(f"**{p.name}**: {', '.join(p.unparsed)}")
    if unparsed_lines:
        embed.color = discord.Color.orange()
        embed.add_field(
            name="⚠️ Some stats couldn't be read and were NOT saved",
            value="\n".join(unparsed_lines)[:1000],
            inline=False,
        )

    return embed


def build_error_embed(err: str) -> discord.Embed:
    embed = discord.Embed(title="Couldn't parse this as a game result", color=discord.Color.red())
    embed.add_field(name="Reason", value=str(err)[:1000])
    embed.set_footer(text="No changes were made to the sheet.")
    return embed


def build_schedule_error_embed(team_a: str, team_b: str) -> discord.Embed:
    embed = discord.Embed(
        title="Couldn't find this matchup on the schedule",
        color=discord.Color.orange(),
    )
    embed.add_field(
        name="Teams parsed",
        value=f"{team_a} vs {team_b}",
        inline=False,
    )
    embed.add_field(
        name="What to check",
        value=(
            "Make sure both team names exactly match the schedule (typos won't match). "
            "If this is a Bowl Week game not yet on the schedule, add the matchup to "
            "`schedule.py`, or log it now and fix the week afterward with `/setweek`."
        ),
        inline=False,
    )
    embed.set_footer(text="No changes were made to the sheet.")
    return embed


@bot.event
async def on_ready():
    if GUILD_ID:
        guild = discord.Object(id=int(GUILD_ID))
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        bot.tree.clear_commands(guild=None)
        await bot.tree.sync()
        log.info(f"Synced {len(synced)} commands to guild {GUILD_ID} (instant); cleared lingering global commands")
    else:
        synced = await bot.tree.sync()
        log.info(f"Synced {len(synced)} commands globally (can take up to ~1hr to appear)")
    log.info(f"Logged in as {bot.user}")


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    original = getattr(error, "original", error)
    command_name = interaction.command.name if interaction.command else "?"
    log.error(f"Command '{command_name}' failed: {type(original).__name__}: {original}")

    message = "⚠️ Something went wrong running that command -- please try again."
    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except Exception:
        pass


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    if message.channel.id != REFEREE_CHANNEL_ID:
        return

    try:
        game = parse_game_message(message.content)
    except ParseError as e:
        await message.reply(embed=build_error_embed(str(e)), mention_author=False)
        return

    week, team_a, team_b = resolve_week(game)
    if week is None:
        async def send(content=None, view=None):
            return await message.channel.send(content=content, view=view)
        clarified = await clarify_unmatched_teams(send, message.author.id, game)
        if clarified is not None:
            game = clarified
            week, team_a, team_b = resolve_week(game)
        if week is None:
            await message.reply(embed=build_schedule_error_embed(team_a, team_b), mention_author=False)
            return

    conflicts = find_team_conflicts(game)

    excluded = []
    if conflicts:
        async def send(content=None, view=None):
            return await message.channel.send(content=content, view=view)
        excluded = await resolve_team_conflicts(send, message.author.id, conflicts)
        if excluded:
            game = _strip_players(game, {p for p, _, _ in excluded})

    game_date = message.created_at.date()
    game_id = sheets.next_game_id()
    sheets.write_game(game, game_id, week, game_date=game_date, message_id=message.id)
    await message.reply(embed=build_recap_embed(game, game_id, week, "Game logged"), mention_author=False)

    for player, current_team, real_team in excluded:
        sheets.log_sub(game_id, player, current_team, note=f"Sub appearance, not recorded. Real team: {real_team}")


@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    if after.author.bot:
        return
    if after.channel.id != REFEREE_CHANNEL_ID:
        return

    game_id = sheets.game_id_for_message(after.id)
    if game_id is None:
        await on_message(after)
        return

    try:
        game = parse_game_message(after.content)
    except ParseError as e:
        await after.reply(embed=build_error_embed(str(e)), mention_author=False)
        return

    week, team_a, team_b = resolve_week(game)
    if week is None:
        async def send(content=None, view=None):
            return await after.channel.send(content=content, view=view)
        clarified = await clarify_unmatched_teams(send, after.author.id, game)
        if clarified is not None:
            game = clarified
            week, team_a, team_b = resolve_week(game)
        if week is None:
            await after.reply(embed=build_schedule_error_embed(team_a, team_b), mention_author=False)
            return

    game_date = after.created_at.date()
    sheets.overwrite_game(game, game_id, week, game_date=game_date)
    await after.reply(embed=build_recap_embed(game, game_id, week, "Game updated"), mention_author=False)


def _is_referee():
    async def predicate(interaction: discord.Interaction) -> bool:
        if REFEREE_ROLE_ID is None:
            return True
        role_ids = {r.id for r in getattr(interaction.user, "roles", [])}
        return int(REFEREE_ROLE_ID) in role_ids
    return app_commands.check(predicate)


@bot.tree.command(name="playercard", description="Generate a stat card image for a player: season totals and rank in each tracked stat")
@app_commands.describe(player="Player's in-game name (must match how it was logged)")
async def playercard(interaction: discord.Interaction, player: str):
    await interaction.response.defer(thinking=True)

    card_data = sheets.get_player_card_data(player, stat_labels=ALL_CARD_STATS)
    if card_data is None:
        await interaction.followup.send(f"⚠️ No games found for **{player}**. Check the spelling matches exactly how it was logged.")
        return

    avatar_bytes = await fetch_minecraft_head(card_data["name"])
    buf = render_player_card(card_data, avatar_bytes=avatar_bytes)
    filename = "".join(c for c in card_data["name"] if c.isalnum()) or "player"
    await interaction.followup.send(file=discord.File(buf, filename=f"{filename}_card.png"))


async def team_autocomplete(interaction: discord.Interaction, current: str):
    current_lower = current.lower()
    matches = [t for t in schedule.all_teams() if current_lower in t.lower()]
    return [app_commands.Choice(name=t, value=t) for t in matches[:25]]


@bot.tree.command(name="teamstats", description="Show the top 3 teams in each stat, or one team's own stats if you specify a team")
@app_commands.describe(team="Optional -- show this specific team's stats instead of the top 3 overall")
@app_commands.autocomplete(team=team_autocomplete)
async def teamstats(interaction: discord.Interaction, team: Optional[str] = None):
    await interaction.response.defer(thinking=True)

    if team is not None:
        matched = next((t for t in schedule.all_teams() if t.lower() == team.strip().lower()), None)
        if matched is None:
            suggestions = difflib.get_close_matches(team, schedule.all_teams(), n=3, cutoff=0.5)
            hint = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
            await interaction.followup.send(f"⚠️ I don't recognize the team **{team}**.{hint}")
            return

        stats = sheets.get_single_team_stats(CURATED_STATS, matched)
        buf = render_single_team_card(matched, stats)
        await interaction.followup.send(file=discord.File(buf, filename=f"{matched}_stats.png"))
        return

    team_leaderboard = sheets.get_team_stat_leaderboard(CURATED_STATS, top_n=3)
    if not team_leaderboard:
        await interaction.followup.send("⚠️ No stats recorded yet.")
        return

    buf = render_team_stats_card(team_leaderboard)
    await interaction.followup.send(file=discord.File(buf, filename="team_stats.png"))


async def stat_autocomplete(interaction: discord.Interaction, current: str):
    current_lower = current.lower()
    matches = [s for s in CURATED_STATS if current_lower in s.lower()]
    return [app_commands.Choice(name=s, value=s) for s in matches[:25]]


@bot.tree.command(name="leaderboard", description="Show the top 10 players in a given stat")
@app_commands.describe(stat="Which stat to rank, e.g. 'FP', 'Passing YD', 'Tackles'")
@app_commands.autocomplete(stat=stat_autocomplete)
async def leaderboard(interaction: discord.Interaction, stat: str):
    await interaction.response.defer(thinking=True)

    matched = next((s for s in CURATED_STATS if s.lower() == stat.strip().lower()), None)
    if matched is None:
        suggestions = difflib.get_close_matches(stat, CURATED_STATS, n=3, cutoff=0.5)
        hint = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
        await interaction.followup.send(
            f"⚠️ I don't recognize the stat **{stat}**.{hint}\nValid stats: {', '.join(CURATED_STATS)}"
        )
        return

    ranked = sheets.get_player_stat_leaderboard(matched, top_n=10)
    if not ranked:
        await interaction.followup.send(f"⚠️ No recorded values for **{matched}** yet.")
        return

    buf = render_stat_leaderboard_card(matched, ranked)
    await interaction.followup.send(file=discord.File(buf, filename="leaderboard.png"))


@bot.tree.command(name="globalleaderboard", description="Show an image with the top 5 players in every tracked stat")
async def globalleaderboard(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)

    player_leaderboard = sheets.get_global_player_leaderboard(CURATED_STATS, top_n=5)
    if not player_leaderboard:
        await interaction.followup.send("⚠️ No stats recorded yet.")
        return

    buf = render_global_leaderboard_card(player_leaderboard)
    await interaction.followup.send(file=discord.File(buf, filename="global_leaderboard.png"))


@bot.tree.command(name="league", description="Show league standings and power rankings for every team")
async def league(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)

    standings = sheets.get_league_standings()
    if not standings:
        await interaction.followup.send("⚠️ No games logged yet.")
        return

    power_rankings = SheetsManager.compute_power_rankings(standings)
    buf = render_league_card(standings, power_rankings)
    await interaction.followup.send(file=discord.File(buf, filename="league.png"))


@bot.tree.command(name="ffw", description="Record a forfeit win for a team in a given week, so standings reflect it")
@app_commands.describe(
    week="Week number the forfeit happened in",
    winner="Team that gets the win",
    loser="Team that forfeited",
)
@app_commands.autocomplete(winner=team_autocomplete, loser=team_autocomplete)
@_is_referee()
async def ffw(interaction: discord.Interaction, week: int, winner: str, loser: str):
    await interaction.response.defer(thinking=True, ephemeral=True)

    matched_winner = next((t for t in schedule.all_teams() if t.lower() == winner.strip().lower()), None)
    matched_loser = next((t for t in schedule.all_teams() if t.lower() == loser.strip().lower()), None)

    if matched_winner is None or matched_loser is None:
        bad = winner if matched_winner is None else loser
        suggestions = difflib.get_close_matches(bad, schedule.all_teams(), n=3, cutoff=0.5)
        hint = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
        await interaction.followup.send(f"⚠️ I don't recognize the team **{bad}**.{hint}", ephemeral=True)
        return

    if matched_winner.lower() == matched_loser.lower():
        await interaction.followup.send("⚠️ Winner and loser can't be the same team.", ephemeral=True)
        return

    note = ""
    scheduled_week = schedule.find_week(matched_winner, matched_loser)
    if scheduled_week is not None and scheduled_week != week:
        note = f"\n(Note: the schedule lists {matched_winner} vs {matched_loser} as Week {scheduled_week}, not Week {week} -- logged anyway.)"

    game_id = sheets.add_forfeit(week, matched_winner, matched_loser)
    await interaction.followup.send(
        f"✅ Logged a forfeit win for **{matched_winner}** over **{matched_loser}** in Week {week} (game #{game_id}).{note}",
        ephemeral=True,
    )


@bot.tree.command(name="tie", description="Record a forfeit tie between two teams in a given week, so standings reflect it")
@app_commands.describe(
    week="Week number the forfeit happened in",
    team_a="First team",
    team_b="Second team",
)
@app_commands.autocomplete(team_a=team_autocomplete, team_b=team_autocomplete)
@_is_referee()
async def tie(interaction: discord.Interaction, week: int, team_a: str, team_b: str):
    await interaction.response.defer(thinking=True, ephemeral=True)

    matched_a = next((t for t in schedule.all_teams() if t.lower() == team_a.strip().lower()), None)
    matched_b = next((t for t in schedule.all_teams() if t.lower() == team_b.strip().lower()), None)

    if matched_a is None or matched_b is None:
        bad = team_a if matched_a is None else team_b
        suggestions = difflib.get_close_matches(bad, schedule.all_teams(), n=3, cutoff=0.5)
        hint = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
        await interaction.followup.send(f"⚠️ I don't recognize the team **{bad}**.{hint}", ephemeral=True)
        return

    if matched_a.lower() == matched_b.lower():
        await interaction.followup.send("⚠️ The two teams can't be the same.", ephemeral=True)
        return

    note = ""
    scheduled_week = schedule.find_week(matched_a, matched_b)
    if scheduled_week is not None and scheduled_week != week:
        note = f"\n(Note: the schedule lists {matched_a} vs {matched_b} as Week {scheduled_week}, not Week {week} -- logged anyway.)"

    game_id = sheets.add_tie(week, matched_a, matched_b)
    await interaction.followup.send(
        f"✅ Logged a forfeit tie between **{matched_a}** and **{matched_b}** in Week {week} (game #{game_id}).{note}",
        ephemeral=True,
    )


POWER_TITLES = {"qb": "QB POWER", "wr": "WR POWER", "line": "LINEMAN RATING"}


@bot.tree.command(name="power", description="Show the top 10 power-ranked players at a position")
@app_commands.describe(pos="Position to rank")
async def power(interaction: discord.Interaction, pos: Literal["qb", "wr", "line"]):
    await interaction.response.defer(thinking=True)

    ranked = sheets.get_position_power_rankings(pos, top_n=10)
    if not ranked:
        await interaction.followup.send(f"⚠️ No {pos.upper()} stats recorded yet.")
        return

    rows = [(r["player"], r["team"], r["power"]) for r in ranked]
    buf = render_stat_leaderboard_card(POWER_TITLES[pos], rows)
    await interaction.followup.send(file=discord.File(buf, filename=f"power_{pos}.png"))


@bot.tree.command(name="fixmissingteam", description="Restore a team's result in a game where they ended up with zero rows (e.g. an all-sub game)")
@app_commands.describe(
    game_id="The GameID the team is missing from",
    team="The team whose result needs restoring",
)
@app_commands.autocomplete(team=team_autocomplete)
@_is_referee()
async def fixmissingteam(interaction: discord.Interaction, game_id: int, team: str):
    await interaction.response.defer(thinking=True, ephemeral=True)

    matched = next((t for t in schedule.all_teams() if t.lower() == team.strip().lower()), None)
    if matched is None:
        suggestions = difflib.get_close_matches(team, schedule.all_teams(), n=3, cutoff=0.5)
        hint = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
        await interaction.followup.send(f"⚠️ I don't recognize the team **{team}**.{hint}", ephemeral=True)
        return

    ok = sheets.add_missing_team_result(game_id, matched)
    if ok:
        await interaction.followup.send(
            f"✅ Restored **{matched}**'s result for game #{game_id}, pulled from their opponent's row.",
            ephemeral=True,
        )
    else:
        await interaction.followup.send(
            f"⚠️ Couldn't find a row in game #{game_id} listing **{matched}** as the opponent. "
            f"Double check the GameID -- this only works if the *other* team's row for that game still exists.",
            ephemeral=True,
        )


@bot.tree.command(name="fixsacksallowed", description="For a two-way lineman, add the opponent's total Sacks per game to his Sacks Allowed total")
@app_commands.describe(player="Player's in-game name (must match exactly as logged)")
@_is_referee()
async def fixsacksallowed(interaction: discord.Interaction, player: str):
    await interaction.response.defer(thinking=True, ephemeral=True)

    results = sheets.apply_sacks_allowed_from_opponent(player)
    if not results:
        await interaction.followup.send(f"⚠️ No games found for **{player}**.", ephemeral=True)
        return

    lines = [f"✅ Updated **Sacks Allowed** for **{player}** across {len(results)} game(s):"]
    for r in results:
        lines.append(f"Game #{r['game_id']}: +{r['opponent_sacks']:g} (opponent's sacks that game) -> {r['old_value']:g} → {r['new_value']:g}")
    text = "\n".join(lines)
    if len(text) > 1900:
        text = text[:1900] + "\n... (truncated)"
    await interaction.followup.send(text, ephemeral=True)


@bot.tree.command(name="fixsacksallowedall", description="One-time backfill: adds opponent sacks to every player's Sacks Allowed total")
@_is_referee()
async def fixsacksallowedall(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True, ephemeral=True)

    players = sheets.get_lineman_players()
    if not players:
        await interaction.followup.send("⚠️ No players detected as linemen yet (need recorded Tackles/Sacks/INT (D)/etc).", ephemeral=True)
        return

    total_games_updated = 0
    per_player_summary = []
    for player in players:
        results = sheets.apply_sacks_allowed_from_opponent(player)
        if results:
            total_games_updated += len(results)
            per_player_summary.append(f"{player}: {len(results)} game(s)")
        await asyncio.sleep(1.1)

    lines = [f"✅ Backfilled **Sacks Allowed** for **{len(per_player_summary)}** player(s) across **{total_games_updated}** game row(s):"]
    lines.extend(per_player_summary[:30])
    if len(per_player_summary) > 30:
        lines.append(f"...and {len(per_player_summary) - 30} more.")
    lines.append(
        "\n⚠️ Going forward, new games posted with a `Sacks Allowed` value already factor the opponent's sacks in "
        "automatically -- only run this again if you need to re-backfill, since running it twice on the same "
        "games will double-count."
    )
    text = "\n".join(lines)
    if len(text) > 1900:
        text = text[:1900] + "\n... (truncated)"
    await interaction.followup.send(text, ephemeral=True)


@bot.tree.command(name="updatestat", description="Fix a single stat for one player in a specific game")
@app_commands.describe(
    game_id="The GameID shown when the game was logged",
    player="Player's in-game name (must match exactly as logged)",
    stat="Stat column name, e.g. 'FP', 'Rec YD', 'INT (D)'",
    value="The number to set or add",
    mode="'set' replaces the current value, 'add' adds to whatever it currently is (default: set)",
)
@_is_referee()
async def updatestat(interaction: discord.Interaction, game_id: int, player: str, stat: str, value: float, mode: Literal["set", "add"] = "set"):
    await interaction.response.defer(thinking=True, ephemeral=True)
    found, new_value = sheets.update_single_stat(game_id, player, stat, value, mode=mode)
    if found:
        if mode == "add":
            await interaction.followup.send(
                f"✅ Added **{value}** to **{stat}** for **{player}** in game #{game_id} -- new total: **{new_value}**.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                f"✅ Set **{stat}** to **{value}** for **{player}** in game #{game_id}.", ephemeral=True
            )
    else:
        players = sheets.find_players_in_game(game_id)
        hint = f" Players found in that game: {', '.join(players)}" if players else " No rows found for that GameID at all."
        await interaction.followup.send(
            f"⚠️ Couldn't find **{player}** in game #{game_id}.{hint}", ephemeral=True
        )


@bot.tree.command(name="checksubs", description="Flag any player logged in more than one game during the same week, for review")
@_is_referee()
async def checksubs(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True, ephemeral=True)

    flagged = sheets.get_same_week_multi_game_players()
    if not flagged:
        await interaction.followup.send("✅ No players found playing multiple games in the same week.", ephemeral=True)
        return

    lines = [f"⚠️ Found **{len(flagged)}** player(s) with multiple games logged in the same week:\n"]
    for player, entries in flagged.items():
        by_week: Dict[int, List[Tuple[int, str]]] = {}
        for week, gid, team in entries:
            by_week.setdefault(week, []).append((gid, team))
        week_strs = []
        for week in sorted(by_week):
            games_str = ", ".join(f"Game #{gid} ({team})" for gid, team in sorted(by_week[week]))
            week_strs.append(f"Week {week}: {games_str}")
        lines.append(f"**{player}** -- " + " | ".join(week_strs))

    text = "\n".join(lines)
    if len(text) > 1900:
        text = text[:1900] + "\n... (truncated)"
    await interaction.followup.send(text, ephemeral=True)


@bot.tree.command(name="checkgames", description="Check the schedule against logged games and flag any missing stat uploads")
@_is_referee()
async def checkgames(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True, ephemeral=True)

    latest_week = sheets.get_latest_logged_week()
    if latest_week is None:
        await interaction.followup.send("⚠️ No games logged yet, nothing to check.", ephemeral=True)
        return

    logged = sheets.get_logged_matchups_by_week()

    missing = []
    for week in range(1, latest_week + 1):
        matchups = schedule.SCHEDULE.get(week, [])
        logged_pairs = logged.get(week, set())
        for team_a, team_b in matchups:
            pair = frozenset({team_a.lower(), team_b.lower()})
            if pair not in logged_pairs:
                missing.append((week, team_a, team_b))

    if not missing:
        await interaction.followup.send(f"✅ All scheduled games through Week {latest_week} have stats logged.", ephemeral=True)
        return

    lines = [f"⚠️ Found **{len(missing)}** scheduled game(s) through Week {latest_week} missing stats:\n"]
    for week, team_a, team_b in missing:
        lines.append(f"Week {week}: **{team_a}** vs **{team_b}**")

    text = "\n".join(lines)
    if len(text) > 1900:
        text = text[:1900] + "\n... (truncated)"
    await interaction.followup.send(text, ephemeral=True)


@bot.tree.command(name="sub", description="Remove player(s) from a game's stats (e.g. they were subbed out)")
@app_commands.describe(
    players="Player name(s) to remove -- separate multiple with spaces or commas",
    game_id="Which game to remove them from. Leave blank to use the most recently logged game.",
)
@_is_referee()
async def sub(interaction: discord.Interaction, players: str, game_id: Optional[int] = None):
    await interaction.response.defer(thinking=True, ephemeral=True)

    if game_id is None:
        game_id = sheets.next_game_id() - 1
        if game_id < 1:
            await interaction.followup.send("⚠️ No games have been logged yet.", ephemeral=True)
            return

    names = [n for n in re.split(r"[,\s]+", players.strip()) if n]
    if not names:
        await interaction.followup.send("⚠️ Give at least one player name.", ephemeral=True)
        return

    game_found, removed, not_found = sheets.remove_players_from_game(game_id, names)

    if not game_found:
        await interaction.followup.send(f"⚠️ No rows found for game #{game_id}.", ephemeral=True)
        return

    lines = []
    if removed:
        lines.append(f"✅ Removed from game #{game_id}: **{', '.join(removed)}**")
    if not_found:
        players_in_game = sheets.find_players_in_game(game_id)
        hint = f" Players actually in that game: {', '.join(players_in_game)}" if players_in_game else ""
        lines.append(f"⚠️ Not found in game #{game_id}: **{', '.join(not_found)}**.{hint}")

    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="setweek", description="Manually set/override which week a game belongs to")
@app_commands.describe(game_id="The GameID to move", week="The week number to assign it to")
@_is_referee()
async def setweek(interaction: discord.Interaction, game_id: int, week: int):
    await interaction.response.defer(thinking=True, ephemeral=True)

    old_week = sheets.get_week_for_game(game_id)
    if old_week is None:
        await interaction.followup.send(f"⚠️ No rows found for game #{game_id}.", ephemeral=True)
        return

    headers = sheets._get_headers()
    week_col = headers.index("Week") + 1
    all_values = sheets.sheet.get_all_values()
    gid_col = headers.index("GameID")
    for i, row in enumerate(all_values[1:], start=2):
        if row[gid_col].strip() == str(game_id):
            sheets.sheet.update_cell(i, week_col, week)

    sheets.ensure_week_sheet(week)
    sheets.refresh_leaderboards_for_week(week)
    if old_week != week:
        sheets.refresh_leaderboards_for_week(old_week)

    await interaction.followup.send(f"✅ Moved game #{game_id} from Week {old_week} to Week {week}.", ephemeral=True)


@bot.tree.command(name="reparsegame", description="Re-run the parser on a message by ID and overwrite its game in the sheet")
@app_commands.describe(message_id="The Discord message ID of the original referee post")
@_is_referee()
async def reparsegame(interaction: discord.Interaction, message_id: str):
    await interaction.response.defer(thinking=True, ephemeral=True)

    channel = bot.get_channel(REFEREE_CHANNEL_ID)
    try:
        msg = await channel.fetch_message(int(message_id))
    except (discord.NotFound, ValueError):
        await interaction.followup.send("⚠️ Couldn't find that message in the referee channel.", ephemeral=True)
        return

    existing_id = sheets.game_id_for_message(msg.id)
    try:
        game = parse_game_message(msg.content)
    except ParseError as e:
        await interaction.followup.send(f"⚠️ Parse failed: {e}", ephemeral=True)
        return

    week, team_a, team_b = resolve_week(game)
    if week is None:
        async def send(content=None, view=None):
            return await interaction.followup.send(content=content, view=view, ephemeral=True)
        clarified = await clarify_unmatched_teams(send, interaction.user.id, game)
        if clarified is not None:
            game = clarified
            week, team_a, team_b = resolve_week(game)
        if week is None:
            await interaction.followup.send(
                f"⚠️ Couldn't find a schedule match for **{team_a} vs {team_b}**. "
                f"Check spelling against `schedule.py`, or log it and use `/setweek` afterward.",
                ephemeral=True,
            )
            return

    game_date = msg.created_at.date()
    game_id = existing_id if existing_id is not None else sheets.next_game_id()
    conflicts = find_team_conflicts(game, exclude_game_id=existing_id)

    excluded = []
    if conflicts:
        async def send(content=None, view=None):
            return await interaction.followup.send(content=content, view=view, ephemeral=True)
        excluded = await resolve_team_conflicts(send, interaction.user.id, conflicts)
        if excluded:
            game = _strip_players(game, {p for p, _, _ in excluded})

    if existing_id is not None:
        sheets.overwrite_game(game, game_id, week, game_date=game_date)
    else:
        sheets.write_game(game, game_id, week, game_date=game_date, message_id=msg.id)

    await interaction.followup.send(embed=build_recap_embed(game, game_id, week, "Re-parsed"), ephemeral=True)

    for player, current_team, real_team in excluded:
        sheets.log_sub(game_id, player, current_team, note=f"Sub appearance, not recorded. Real team: {real_team}")

    if conflicts:
        async def send(content=None, view=None):
            return await interaction.followup.send(content=content, view=view, ephemeral=True)
        await resolve_team_conflicts(send, interaction.user.id, conflicts, game_id)


class ConfirmClearView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=30)
        self.author_id = author_id
        self.confirmed: Optional[bool] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the person who ran this command can confirm it.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Yes, wipe everything", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = False
        await interaction.response.defer()
        self.stop()


@bot.tree.command(name="clearstats", description="TESTING ONLY: wipes every logged game, all weeks, and all leaderboards. Cannot be undone.")
@_is_referee()
async def clearstats(interaction: discord.Interaction):
    view = ConfirmClearView(interaction.user.id)
    await interaction.response.send_message(
        "⚠️ **This will permanently delete every logged game, all `Week N` / `Week N Leaderboard` sheets, "
        "and reset the Global Leaderboard.** `AllGames` goes back to empty. This cannot be undone.\n\n"
        "Are you sure?",
        view=view,
        ephemeral=True,
    )

    timed_out = await view.wait()
    if timed_out or not view.confirmed:
        await interaction.edit_original_response(content="❌ Cancelled -- nothing was deleted.", view=None)
        return

    await interaction.edit_original_response(content="🗑️ Wiping everything...", view=None)
    sheets.clear_all_data()
    await interaction.followup.send("✅ Done -- the sheet is back to a clean, empty state.", ephemeral=True)


@bot.tree.command(name="rebuildleaderboards", description="Wipe and regenerate every leaderboard sheet from scratch")
@_is_referee()
async def rebuildleaderboards(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True, ephemeral=True)
    sheets.force_rebuild_all_leaderboards()
    await interaction.followup.send("✅ Rebuilt the Global Leaderboard and every Week N Leaderboard sheet from scratch.", ephemeral=True)


@bot.tree.command(name="backfillgames", description="Scan the referee channel's history and log any games not yet in the sheet")
@app_commands.describe(
    after="Start date (YYYY-MM-DD) -- scans messages from this date onward",
    overwrite="If true, also re-parse and overwrite games that are already logged (default: skip them)",
)
@_is_referee()
async def backfillgames(interaction: discord.Interaction, after: str, overwrite: bool = False):
    await interaction.response.defer(thinking=True, ephemeral=True)

    try:
        start_date = datetime.date.fromisoformat(after)
    except ValueError:
        await interaction.followup.send("⚠️ Use YYYY-MM-DD format, e.g. 2026-06-01.", ephemeral=True)
        return

    channel = bot.get_channel(REFEREE_CHANNEL_ID)
    after_dt = datetime.datetime.combine(start_date, datetime.time.min)

    logged, skipped = 0, 0
    failed = []
    no_schedule_match = []
    next_id = sheets.next_game_id()

    async for msg in channel.history(limit=None, after=after_dt, oldest_first=True):
        if msg.author.bot:
            continue

        existing_game_id = sheets.game_id_for_message(msg.id)
        if existing_game_id is not None and not overwrite:
            skipped += 1
            continue

        try:
            game = parse_game_message(msg.content)
        except ParseError:
            failed.append(msg)
            continue

        week, team_a, team_b = resolve_week(game)
        if week is None:
            no_schedule_match.append((msg, team_a, team_b))
            continue

        game_date = msg.created_at.date()
        if existing_game_id is not None:
            sheets.overwrite_game(game, existing_game_id, week, game_date=game_date)
        else:
            sheets.write_game(game, next_id, week, game_date=game_date, message_id=msg.id)
            next_id += 1
        logged += 1

        await asyncio.sleep(2.0)

    await interaction.followup.send(
        f"✅ Backfill complete from {start_date.isoformat()} onward.\n"
        f"Logged: **{logged}**  |  Skipped (already logged): **{skipped}**  |  "
        f"Failed to parse: **{len(failed)}**  |  No schedule match: **{len(no_schedule_match)}**",
        ephemeral=True,
    )

    if failed:
        lines = []
        for m in failed[:10]:
            snippet = m.content[:60].replace("\n", " ")
            lines.append(f"- [{m.created_at.date()}]({m.jump_url}): `{snippet}...`")
        more = f"\n...and {len(failed) - 10} more." if len(failed) > 10 else ""
        await interaction.followup.send("Messages that didn't parse (first 10):\n" + "\n".join(lines) + more, ephemeral=True)

    if no_schedule_match:
        lines = []
        for m, team_a, team_b in no_schedule_match[:10]:
            lines.append(f"- [{m.created_at.date()}]({m.jump_url}): {team_a} vs {team_b}")
        more = f"\n...and {len(no_schedule_match) - 10} more." if len(no_schedule_match) > 10 else ""
        await interaction.followup.send(
            "Messages with no schedule match (first 10) -- check spelling or add to schedule.py:\n"
            + "\n".join(lines) + more,
            ephemeral=True,
        )

        await interaction.followup.send(
            f"Going through the **{len(no_schedule_match)}** unmatched game(s) now to see if any are just typos...",
            ephemeral=True,
        )
        for msg, team_a, team_b in no_schedule_match:
            try:
                game = parse_game_message(msg.content)
            except ParseError:
                continue

            async def send(content=None, view=None):
                return await interaction.followup.send(content=content, view=view, ephemeral=True)

            clarified = await clarify_unmatched_teams(send, interaction.user.id, game)
            if clarified is None:
                continue

            week, _, _ = resolve_week(clarified)
            if week is None:
                await interaction.followup.send(
                    f"⚠️ Still no schedule match for [this game]({msg.jump_url}) after clarifying -- skipping.",
                    ephemeral=True,
                )
                continue

            game_id = sheets.next_game_id()
            sheets.write_game(clarified, game_id, week, game_date=msg.created_at.date(), message_id=msg.id)
            await interaction.followup.send(
                embed=build_recap_embed(clarified, game_id, week, "Logged after clarification"),
                ephemeral=True,
            )
            await asyncio.sleep(2.0)

    multi_team = sheets.get_multi_team_players()
    if multi_team:
        await interaction.followup.send(
            f"👀 Found **{len(multi_team)}** player(s) logged under more than one team across everything in `AllGames` "
            f"(not just this backfill). Going through them one at a time.",
            ephemeral=True,
        )
        for player, teams in multi_team.items():
            team_options = sorted(teams)
            teams_str = ", ".join(team_options)
            view = TeamChoiceView(interaction.user.id, team_options, moved_label="Moved teams (all legit)")
            await interaction.followup.send(
                content=(
                    f"**{player}** has stats under multiple teams: **{teams_str}**.\n"
                    f"Which is their real team? (Picking one removes their stats logged under the others.)"
                ),
                view=view,
                ephemeral=True,
            )
            timed_out = await view.wait()
            if timed_out or view.choice is None:
                await interaction.followup.send(f"⏱️ No response for **{player}** -- leaving as-is.", ephemeral=True)
                continue
            if view.choice == TeamChoiceView.MOVED:
                await interaction.followup.send(f"✅ Got it, no changes needed -- **{player}**'s team history is intentional.", ephemeral=True)
            else:
                selected_team = view.choice
                removed_count = sheets.remove_player_stats_not_matching_team(player, selected_team)
                other_teams = ", ".join(t for t in team_options if t.lower() != selected_team.lower())
                sheets.log_sub(None, player, selected_team, note=f"Backfill cleanup: kept {selected_team}, removed {removed_count} row(s) under {other_teams}")
                await interaction.followup.send(
                    f"✅ Kept **{player}**'s stats under **{selected_team}** and removed **{removed_count}** row(s) logged under other teams.",
                    ephemeral=True,
                )


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)