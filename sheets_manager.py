import datetime
import re
import time
from typing import Dict, List, Optional, Tuple

import gspread
from gspread.exceptions import APIError
from google.oauth2.service_account import Credentials

from stat_parser import GameResult

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _is_rate_limit_error(exc) -> bool:
    try:
        return exc.response.status_code == 429
    except Exception:
        return "429" in str(exc) or "Quota exceeded" in str(exc)


def _maybe_wrap(obj, max_retries=6, base_delay=5):
    if isinstance(obj, (gspread.Worksheet, gspread.Spreadsheet, gspread.Client)):
        return _RetryingProxy(obj, max_retries, base_delay)
    if isinstance(obj, list):
        return [_maybe_wrap(item, max_retries, base_delay) for item in obj]
    return obj


class _RetryingProxy:
    def __init__(self, target, max_retries=6, base_delay=5):
        self._target = target
        self._max_retries = max_retries
        self._base_delay = base_delay

    def __getattr__(self, name):
        attr = getattr(self._target, name)
        if not callable(attr):
            return attr

        def wrapped(*args, **kwargs):
            delay = self._base_delay
            for attempt in range(self._max_retries + 1):
                try:
                    result = attr(*args, **kwargs)
                    return _maybe_wrap(result, self._max_retries, self._base_delay)
                except APIError as e:
                    if _is_rate_limit_error(e) and attempt < self._max_retries:
                        time.sleep(delay)
                        delay = min(delay * 2, 60)
                        continue
                    raise

        return wrapped

FIXED_COLUMNS = ["GameID", "Date", "Week", "Team", "TeamScore", "Opponent", "OppScore", "Player"]
NUM_FIXED_COLUMNS = len(FIXED_COLUMNS)


CURATED_STATS = [
    "FP", "QBR", "Passing YD", "Passing TD", "Rec YD", "Rec TD",
    "Rushing YD", "Rushing TD", "Tackles", "Sacks", "INT (D)", "INT (O)",
    "Swats", "Def TD",
]

AVERAGE_STATS = {"QBR"}


def _display_label(label: str) -> str:
    return f"{label} (AVG)" if label in AVERAGE_STATS else label

TOP_N = 5
BLOCKS_PER_ROW = 3
BLOCK_COLS = 3
BLOCK_ROWS = TOP_N + 3
GRID_TOTAL_COLS = BLOCKS_PER_ROW * BLOCK_COLS - 1
BANNER_ROW = 1
FIRST_BLOCK_ROW = 3

MEDALS = ["🥇 ", "🥈 ", "🥉 "]


COLOR_BANNER_BG = {"red": 0.10, "green": 0.13, "blue": 0.30}
COLOR_BANNER_TEXT = {"red": 1, "green": 1, "blue": 1}
COLOR_BLOCK_TITLE_BG = {"red": 0.16, "green": 0.32, "blue": 0.58}
COLOR_BLOCK_TITLE_TEXT = {"red": 1, "green": 1, "blue": 1}
COLOR_SUBHEADER_BG = {"red": 0.85, "green": 0.87, "blue": 0.91}
COLOR_ROW_EVEN = {"red": 1, "green": 1, "blue": 1}
COLOR_ROW_ODD = {"red": 0.96, "green": 0.97, "blue": 0.98}
COLOR_GOLD_TAB = {"red": 1.0, "green": 0.84, "blue": 0.0}
COLOR_BLUE_TAB = {"red": 0.27, "green": 0.45, "blue": 0.77}
COLOR_LIGHT_BLUE_TAB = {"red": 0.71, "green": 0.84, "blue": 0.93}
COLOR_GRAY_TAB = {"red": 0.45, "green": 0.45, "blue": 0.45}
COLOR_BORDER = {"red": 0.6, "green": 0.6, "blue": 0.6}

WEEK_RAW_RE = re.compile(r"^Week (\d+)$")
WEEK_LEADERBOARD_RE = re.compile(r"^Week (\d+) Leaderboard$")


def col_letter(n: int) -> str:
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


class SheetsManager:
    def __init__(self, service_account_file: str, spreadsheet_id: str, master_sheet_name: str = "AllGames"):
        creds = Credentials.from_service_account_file(service_account_file, scopes=SCOPES)
        self.client = _RetryingProxy(gspread.authorize(creds))
        self.spreadsheet = self.client.open_by_key(spreadsheet_id)
        self.master_name = master_sheet_name

        try:
            self.sheet = self.spreadsheet.worksheet(master_sheet_name)
        except gspread.WorksheetNotFound:
            self.sheet = self.spreadsheet.add_worksheet(title=master_sheet_name, rows=5000, cols=40)
            self.sheet.append_row(FIXED_COLUMNS)

        try:
            self.meta_sheet = self.spreadsheet.worksheet("_meta")
        except gspread.WorksheetNotFound:
            self.meta_sheet = self.spreadsheet.add_worksheet(title="_meta", rows=2000, cols=3)
            self.meta_sheet.append_row(["MessageID", "GameID", "Timestamp"])

        try:
            self.subs_sheet = self.spreadsheet.worksheet("_subs")
        except gspread.WorksheetNotFound:
            self.subs_sheet = self.spreadsheet.add_worksheet(title="_subs", rows=2000, cols=5)
            self.subs_sheet.append_row(["Timestamp", "GameID", "Player", "Team", "Note"])

        try:
            self.global_lb = self.spreadsheet.worksheet("Global Leaderboard")
        except gspread.WorksheetNotFound:
            self.global_lb = self.spreadsheet.add_worksheet(title="Global Leaderboard", rows=2000, cols=10)
            self._write_leaderboard_blocks(self.global_lb, self._get_headers(), week_filter=None)

        self._style_master_sheet()
        self._organize_tabs()


    def _get_headers(self) -> List[str]:
        return self.sheet.row_values(1)

    def _ensure_columns(self, needed_labels: List[str]) -> List[str]:
        headers = self._get_headers()
        missing = [lbl for lbl in needed_labels if lbl not in headers]
        if missing:
            new_headers = headers + missing
            self.sheet.update("A1", [new_headers])
            headers = new_headers
            self._rebuild_all_leaderboards(headers)
        return headers


    def _curated_stats_present(self, headers: List[str]) -> List[str]:
        return [label for label in CURATED_STATS if label in headers]

    def _grid_position(self, k: int) -> Tuple[int, int]:
        row_group, col_group = divmod(k, BLOCKS_PER_ROW)
        title_row = FIRST_BLOCK_ROW + row_group * BLOCK_ROWS
        start_col_idx0 = col_group * BLOCK_COLS
        return title_row, start_col_idx0

    def _write_leaderboard_blocks(self, sheet, headers: List[str], week_filter: Optional[int] = None):
        all_values = self.sheet.get_all_values()
        data_rows = all_values[1:]
        player_idx = headers.index("Player")
        week_idx = headers.index("Week")

        stats = self._curated_stats_present(headers)
        if not stats:
            return

        sheet_id = sheet.id
        content_requests = []

        for k, label in enumerate(stats):
            stat_idx = headers.index(label)
            totals: Dict[str, float] = {}
            counts: Dict[str, int] = {}
            display_name: Dict[str, str] = {}
            for row in data_rows:
                if week_filter is not None:
                    if len(row) <= week_idx or row[week_idx].strip() != str(week_filter):
                        continue
                if len(row) <= max(stat_idx, player_idx):
                    continue
                val_str = row[stat_idx].strip()
                if val_str == "":
                    continue
                try:
                    val = float(val_str)
                except ValueError:
                    continue
                player = row[player_idx].strip()
                if not player:
                    continue
                key = player.lower()
                display_name[key] = player
                totals[key] = totals.get(key, 0.0) + val
                counts[key] = counts.get(key, 0) + 1
            if label in AVERAGE_STATS:
                totals = {key: v / counts[key] for key, v in totals.items()}
            ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:TOP_N]
            ranked = [(display_name[key], v) for key, v in ranked]

            title_row, start_col_idx0 = self._grid_position(k)

            def text_cell(v):
                return {"userEnteredValue": {"stringValue": v}}

            def number_cell(v):
                return {"userEnteredValue": {"numberValue": v}}

            rows_data = [
                {"values": [text_cell(_display_label(label)), text_cell("")]},
                {"values": [text_cell("Player"), text_cell("Value")]},
            ]
            for i in range(TOP_N):
                if i < len(ranked):
                    name = ranked[i][0]
                    medal = MEDALS[i] if i < len(MEDALS) else ""
                    rows_data.append({"values": [text_cell(f"{medal}{name}"), number_cell(ranked[i][1])]})
                else:
                    rows_data.append({"values": [text_cell(""), text_cell("")]})

            content_requests.append({
                "updateCells": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": title_row - 1,
                        "endRowIndex": title_row - 1 + len(rows_data),
                        "startColumnIndex": start_col_idx0,
                        "endColumnIndex": start_col_idx0 + 2,
                    },
                    "rows": rows_data,
                    "fields": "userEnteredValue",
                }
            })

        title_text = "🏆  GLOBAL LEADERBOARD — ALL TIME" if week_filter is None else f"📅  WEEK {week_filter} LEADERBOARD"
        self._format_leaderboard_sheet(sheet, len(stats), title_text, content_requests)

    def _format_leaderboard_sheet(self, sheet, num_blocks: int, title_text: str, content_requests: Optional[list] = None):
        sheet_id = sheet.id
        num_row_groups = (num_blocks + BLOCKS_PER_ROW - 1) // BLOCKS_PER_ROW
        total_rows = FIRST_BLOCK_ROW + num_row_groups * BLOCK_ROWS
        requests = list(content_requests) if content_requests else []


        requests.append({
            "mergeCells": {
                "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1,
                           "startColumnIndex": 0, "endColumnIndex": GRID_TOTAL_COLS},
                "mergeType": "MERGE_ALL",
            }
        })
        requests.append({
            "updateCells": {
                "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1,
                           "startColumnIndex": 0, "endColumnIndex": 1},
                "rows": [{"values": [{"userEnteredValue": {"stringValue": title_text}}]}],
                "fields": "userEnteredValue",
            }
        })
        requests.append({
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1,
                           "startColumnIndex": 0, "endColumnIndex": GRID_TOTAL_COLS},
                "cell": {"userEnteredFormat": {
                    "backgroundColor": COLOR_BANNER_BG,
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE",
                    "textFormat": {"foregroundColor": COLOR_BANNER_TEXT, "fontSize": 14, "bold": True},
                }},
                "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,textFormat)",
            }
        })
        requests.append({
            "updateDimensionProperties": {
                "range": {"sheetId": sheet_id, "dimension": "ROWS", "startIndex": 0, "endIndex": 1},
                "properties": {"pixelSize": 32},
                "fields": "pixelSize",
            }
        })

        for k in range(num_blocks):
            title_row, start_col_idx0 = self._grid_position(k)
            r0 = title_row - 1
            c0 = start_col_idx0


            requests.append({
                "mergeCells": {
                    "range": {"sheetId": sheet_id, "startRowIndex": r0, "endRowIndex": r0 + 1,
                               "startColumnIndex": c0, "endColumnIndex": c0 + 2},
                    "mergeType": "MERGE_ALL",
                }
            })
            requests.append({
                "repeatCell": {
                    "range": {"sheetId": sheet_id, "startRowIndex": r0, "endRowIndex": r0 + 1,
                               "startColumnIndex": c0, "endColumnIndex": c0 + 2},
                    "cell": {"userEnteredFormat": {
                        "backgroundColor": COLOR_BLOCK_TITLE_BG,
                        "horizontalAlignment": "CENTER",
                        "textFormat": {"foregroundColor": COLOR_BLOCK_TITLE_TEXT, "bold": True, "fontSize": 11},
                    }},
                    "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,textFormat)",
                }
            })


            requests.append({
                "repeatCell": {
                    "range": {"sheetId": sheet_id, "startRowIndex": r0 + 1, "endRowIndex": r0 + 2,
                               "startColumnIndex": c0, "endColumnIndex": c0 + 2},
                    "cell": {"userEnteredFormat": {
                        "backgroundColor": COLOR_SUBHEADER_BG,
                        "textFormat": {"bold": True, "fontSize": 9},
                    }},
                    "fields": "userEnteredFormat(backgroundColor,textFormat)",
                }
            })


            for i in range(TOP_N):
                row_idx0 = r0 + 2 + i
                bg = COLOR_ROW_EVEN if i % 2 == 0 else COLOR_ROW_ODD
                requests.append({
                    "repeatCell": {
                        "range": {"sheetId": sheet_id, "startRowIndex": row_idx0, "endRowIndex": row_idx0 + 1,
                                   "startColumnIndex": c0, "endColumnIndex": c0 + 2},
                        "cell": {"userEnteredFormat": {"backgroundColor": bg, "textFormat": {"fontSize": 9}}},
                        "fields": "userEnteredFormat(backgroundColor,textFormat)",
                    }
                })


            border = {"style": "SOLID", "width": 1, "color": COLOR_BORDER}
            requests.append({
                "updateBorders": {
                    "range": {"sheetId": sheet_id, "startRowIndex": r0, "endRowIndex": r0 + 2 + TOP_N,
                               "startColumnIndex": c0, "endColumnIndex": c0 + 2},
                    "top": border, "bottom": border, "left": border, "right": border,
                    "innerHorizontal": border, "innerVertical": border,
                }
            })


        for col_group in range(BLOCKS_PER_ROW):
            base = col_group * BLOCK_COLS
            requests.append({
                "updateDimensionProperties": {
                    "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": base, "endIndex": base + 1},
                    "properties": {"pixelSize": 130},
                    "fields": "pixelSize",
                }
            })
            requests.append({
                "updateDimensionProperties": {
                    "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": base + 1, "endIndex": base + 2},
                    "properties": {"pixelSize": 70},
                    "fields": "pixelSize",
                }
            })
            requests.append({
                "updateDimensionProperties": {
                    "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": base + 2, "endIndex": base + 3},
                    "properties": {"pixelSize": 24},
                    "fields": "pixelSize",
                }
            })

        requests.append({
            "updateSheetProperties": {
                "properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}},
                "fields": "gridProperties.frozenRowCount",
            }
        })

        if requests:
            self.spreadsheet.batch_update({"requests": requests})

    def _rebuild_all_leaderboards(self, headers: List[str]):
        self._write_leaderboard_blocks(self.global_lb, headers, week_filter=None)
        for ws in self.spreadsheet.worksheets():
            m = WEEK_LEADERBOARD_RE.match(ws.title)
            if m:
                self._write_leaderboard_blocks(ws, headers, week_filter=int(m.group(1)))

    def refresh_leaderboards_for_week(self, week: int):
        headers = self._get_headers()
        self._write_leaderboard_blocks(self.global_lb, headers, week_filter=None)
        try:
            lb = self.spreadsheet.worksheet(f"Week {week} Leaderboard")
            self._write_leaderboard_blocks(lb, headers, week_filter=week)
        except gspread.WorksheetNotFound:
            pass

    def force_rebuild_all_leaderboards(self):
        headers = self._get_headers()
        self.global_lb.clear()
        self._write_leaderboard_blocks(self.global_lb, headers, week_filter=None)
        for ws in self.spreadsheet.worksheets():
            m = WEEK_LEADERBOARD_RE.match(ws.title)
            if m:
                ws.clear()
                self._write_leaderboard_blocks(ws, headers, week_filter=int(m.group(1)))

    def _tab_color_for(self, title: str) -> Optional[dict]:
        if title == self.master_name:
            return COLOR_GRAY_TAB
        if title == "Global Leaderboard":
            return COLOR_GOLD_TAB
        if WEEK_LEADERBOARD_RE.match(title):
            return COLOR_BLUE_TAB
        if WEEK_RAW_RE.match(title):
            return COLOR_LIGHT_BLUE_TAB
        return None

    def _organize_tabs(self):
        worksheets = self.spreadsheet.worksheets()
        by_title = {ws.title: ws for ws in worksheets}

        week_numbers = sorted({
            int(m.group(1)) for title in by_title
            if (m := WEEK_RAW_RE.match(title))
        })

        order = [self.master_name, "Global Leaderboard"]
        for w in week_numbers:
            order.append(f"Week {w}")
            order.append(f"Week {w} Leaderboard")
        order.append("_meta")
        order.append("_subs")

        requests = []
        idx = 0
        for title in order:
            ws = by_title.get(title)
            if ws is None:
                continue
            props = {"sheetId": ws.id, "index": idx}
            fields = ["index"]
            tab_color = self._tab_color_for(title)
            if tab_color is not None:
                props["tabColor"] = tab_color
                fields.append("tabColor")
            if title in ("_meta", "_subs"):
                props["hidden"] = True
                fields.append("hidden")
            requests.append({"updateSheetProperties": {"properties": props, "fields": ",".join(fields)}})
            idx += 1

        if requests:
            self.spreadsheet.batch_update({"requests": requests})

    def _style_master_sheet(self):
        sheet_id = self.sheet.id
        requests = [
            {
                "repeatCell": {
                    "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
                    "cell": {"userEnteredFormat": {
                        "backgroundColor": COLOR_GRAY_TAB,
                        "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                    }},
                    "fields": "userEnteredFormat(backgroundColor,textFormat)",
                }
            },
            {
                "updateSheetProperties": {
                    "properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}},
                    "fields": "gridProperties.frozenRowCount",
                }
            },
        ]
        self.spreadsheet.batch_update({"requests": requests})


    def ensure_week_sheet(self, week: int):
        name = f"Week {week}"
        lb_name = f"Week {week} Leaderboard"

        try:
            self.spreadsheet.worksheet(name)
        except gspread.WorksheetNotFound:
            ws = self.spreadsheet.add_worksheet(title=name, rows=3000, cols=40)
            formula = f'=QUERY({self.master_name}!A1:ZZ10000,"select * where C = {week}",1)'
            ws.update("A1", [[formula]], raw=False)

        try:
            self.spreadsheet.worksheet(lb_name)
        except gspread.WorksheetNotFound:
            lb = self.spreadsheet.add_worksheet(title=lb_name, rows=2000, cols=10)
            self._write_leaderboard_blocks(lb, self._get_headers(), week_filter=week)

        self._organize_tabs()


    @staticmethod
    def week_number_for_date(game_date: datetime.date, season_start: datetime.date) -> int:
        delta_days = (game_date - season_start).days
        return max(1, (delta_days // 7) + 1)


    def next_game_id(self) -> int:
        col = self.sheet.col_values(1)[1:]
        ids = [int(v) for v in col if v.strip().isdigit()]
        return (max(ids) + 1) if ids else 1

    def remember_message(self, message_id: int, game_id: int):
        self.meta_sheet.append_row([str(message_id), str(game_id), datetime.datetime.utcnow().isoformat()])

    def game_id_for_message(self, message_id: int) -> Optional[int]:
        records = self.meta_sheet.get_all_records()
        for r in reversed(records):
            if str(r.get("MessageID")) == str(message_id):
                return int(r["GameID"])
        return None


    def write_game(
        self,
        game: GameResult,
        game_id: int,
        week: int,
        game_date: Optional[datetime.date] = None,
        message_id: Optional[int] = None,
    ) -> int:
        game_date = game_date or datetime.date.today()

        all_labels = set()
        for team in game.teams:
            for p in team.players:
                all_labels.update(p.stats.keys())
        headers = self._ensure_columns(sorted(all_labels))

        self.ensure_week_sheet(week)

        rows_to_append = []
        for team in game.teams:
            opponent = next((t for t in game.teams if t is not team), None)
            for p in team.players:
                row = {h: "" for h in headers}
                row["GameID"] = game_id
                row["Date"] = game_date.isoformat()
                row["Week"] = week
                row["Team"] = team.name
                row["TeamScore"] = team.score
                row["Opponent"] = opponent.name if opponent else ""
                row["OppScore"] = opponent.score if opponent else ""
                row["Player"] = p.name
                for label, value in p.stats.items():
                    row[label] = value
                rows_to_append.append([row[h] for h in headers])


        self.sheet.append_rows(rows_to_append, value_input_option="RAW")
        self.refresh_leaderboards_for_week(week)

        if message_id is not None:
            self.remember_message(message_id, game_id)

        return game_id


    def get_week_for_game(self, game_id: int) -> Optional[int]:
        all_values = self.sheet.get_all_values()
        headers = all_values[0]
        gid_col = headers.index("GameID")
        week_col = headers.index("Week")
        for row in all_values[1:]:
            if row[gid_col].strip() == str(game_id):
                return int(row[week_col]) if row[week_col].strip().isdigit() else None
        return None

    def delete_game_rows(self, game_id: int):
        all_values = self.sheet.get_all_values()
        headers = all_values[0]
        gid_col = headers.index("GameID")
        rows_to_delete = [
            i + 1
            for i, row in enumerate(all_values[1:], start=2)
            if row[gid_col].strip() == str(game_id)
        ]
        for row_idx in sorted(rows_to_delete, reverse=True):
            self.sheet.delete_rows(row_idx)

    def overwrite_game(self, game: GameResult, game_id: int, week: int, game_date: Optional[datetime.date] = None):
        old_week = self.get_week_for_game(game_id)
        self.delete_game_rows(game_id)
        self.write_game(game, game_id, week, game_date=game_date)
        if old_week is not None and old_week != week:


            self.refresh_leaderboards_for_week(old_week)


    def update_single_stat(self, game_id: int, player: str, stat_label: str, value: float, mode: str = "set") -> Tuple[bool, Optional[float]]:
        headers = self._ensure_columns([stat_label])
        col_idx = headers.index(stat_label) + 1
        week_idx = headers.index("Week")

        all_values = self.sheet.get_all_values()
        gid_col = headers.index("GameID")
        player_col = headers.index("Player")

        for i, row in enumerate(all_values[1:], start=2):
            if row[gid_col].strip() == str(game_id) and row[player_col].strip().lower() == player.strip().lower():
                if mode == "add":
                    current_str = row[col_idx - 1].strip() if len(row) >= col_idx else ""
                    try:
                        current = float(current_str) if current_str else 0.0
                    except ValueError:
                        current = 0.0
                    new_value = current + value
                else:
                    new_value = value
                self.sheet.update_cell(i, col_idx, new_value)
                week = int(row[week_idx]) if row[week_idx].strip().isdigit() else None
                if week is not None:
                    self.refresh_leaderboards_for_week(week)
                return True, new_value
        return False, None

    def find_players_in_game(self, game_id: int) -> List[str]:
        all_values = self.sheet.get_all_values()
        headers = all_values[0]
        gid_col = headers.index("GameID")
        player_col = headers.index("Player")
        return [row[player_col] for row in all_values[1:] if row[gid_col].strip() == str(game_id)]


    def get_player_team_history(self, exclude_game_id: Optional[int] = None) -> Dict[str, dict]:
        headers = self._get_headers()
        all_values = self.sheet.get_all_values()
        player_idx = headers.index("Player")
        team_idx = headers.index("Team")
        gid_idx = headers.index("GameID")

        history: Dict[str, dict] = {}
        for row in all_values[1:]:
            if len(row) <= max(player_idx, team_idx, gid_idx):
                continue
            if exclude_game_id is not None and row[gid_idx].strip() == str(exclude_game_id):
                continue
            name = row[player_idx].strip()
            team = row[team_idx].strip()
            if not name or not team:
                continue
            key = name.lower()
            entry = history.setdefault(key, {"display": name, "teams": set()})
            entry["teams"].add(team)
            entry["display"] = name
        return history

    def get_multi_team_players(self) -> Dict[str, set]:
        history = self.get_player_team_history()
        return {v["display"]: v["teams"] for v in history.values() if len(v["teams"]) > 1}

    def get_team_stat_leaderboard(self, stat_labels: List[str], top_n: int = 3) -> Dict[str, List[Tuple[str, float]]]:
        headers = self._get_headers()
        all_values = self.sheet.get_all_values()
        data_rows = all_values[1:]
        team_idx = headers.index("Team")

        result: Dict[str, List[Tuple[str, float]]] = {}
        for label in stat_labels:
            if label not in headers:
                continue
            stat_idx = headers.index(label)
            totals_by_team: Dict[str, float] = {}
            counts_by_team: Dict[str, int] = {}
            for row in data_rows:
                if len(row) <= max(team_idx, stat_idx):
                    continue
                val_str = row[stat_idx].strip()
                if val_str == "":
                    continue
                try:
                    val = float(val_str)
                except ValueError:
                    continue
                team = row[team_idx].strip()
                if not team:
                    continue
                totals_by_team[team] = totals_by_team.get(team, 0.0) + val
                counts_by_team[team] = counts_by_team.get(team, 0) + 1
            if not totals_by_team:
                continue
            if label in AVERAGE_STATS:
                totals_by_team = {t: v / counts_by_team[t] for t, v in totals_by_team.items()}
            ranked = sorted(totals_by_team.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
            result[label] = ranked
        return result

    def get_player_stat_leaderboard(self, stat_label: str, top_n: int = 10) -> List[Tuple[str, str, float]]:
        headers = self._get_headers()
        if stat_label not in headers:
            return []
        all_values = self.sheet.get_all_values()
        data_rows = all_values[1:]
        player_idx = headers.index("Player")
        team_idx = headers.index("Team")
        stat_idx = headers.index(stat_label)

        totals: Dict[str, float] = {}
        counts: Dict[str, int] = {}
        most_recent_team: Dict[str, str] = {}
        display_name: Dict[str, str] = {}

        for row in data_rows:
            if len(row) <= max(player_idx, team_idx, stat_idx):
                continue
            name = row[player_idx].strip()
            if not name:
                continue
            key = name.lower()
            display_name[key] = name

            team = row[team_idx].strip()
            if team:
                most_recent_team[key] = team

            val_str = row[stat_idx].strip()
            if val_str:
                try:
                    totals[key] = totals.get(key, 0.0) + float(val_str)
                    counts[key] = counts.get(key, 0) + 1
                except ValueError:
                    pass

        if stat_label in AVERAGE_STATS:
            totals = {k: v / counts[k] for k, v in totals.items()}

        ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
        return [(display_name[k], most_recent_team.get(k, ""), total) for k, total in ranked]

    def get_single_team_stats(self, stat_labels: List[str], team_name: str) -> List[dict]:
        headers = self._get_headers()
        all_values = self.sheet.get_all_values()
        data_rows = all_values[1:]
        team_idx = headers.index("Team")
        target = team_name.strip().lower()

        results = []
        for label in stat_labels:
            if label not in headers:
                continue
            stat_idx = headers.index(label)
            totals_by_team: Dict[str, float] = {}
            counts_by_team: Dict[str, int] = {}
            for row in data_rows:
                if len(row) <= max(team_idx, stat_idx):
                    continue
                val_str = row[stat_idx].strip()
                if val_str == "":
                    continue
                try:
                    val = float(val_str)
                except ValueError:
                    continue
                team = row[team_idx].strip()
                if not team:
                    continue
                totals_by_team[team] = totals_by_team.get(team, 0.0) + val
                counts_by_team[team] = counts_by_team.get(team, 0) + 1

            if label in AVERAGE_STATS:
                totals_by_team = {t: v / counts_by_team[t] for t, v in totals_by_team.items()}

            match_key = next((t for t in totals_by_team if t.lower() == target), None)
            if match_key is None:
                continue

            team_total = totals_by_team[match_key]
            ranked_totals = sorted(totals_by_team.values(), reverse=True)
            rank = ranked_totals.index(team_total) + 1
            results.append({"label": label, "total": team_total, "rank": rank, "out_of": len(totals_by_team)})

        return results

    def get_same_week_multi_game_players(self) -> Dict[str, List[Tuple[int, int, str]]]:
        headers = self._get_headers()
        all_values = self.sheet.get_all_values()
        data_rows = all_values[1:]
        player_idx = headers.index("Player")
        week_idx = headers.index("Week")
        gid_idx = headers.index("GameID")
        team_idx = headers.index("Team")

        groups: Dict[Tuple[str, str], Dict[str, str]] = {}
        display_name: Dict[str, str] = {}

        for row in data_rows:
            if len(row) <= max(player_idx, week_idx, gid_idx, team_idx):
                continue
            name = row[player_idx].strip()
            week = row[week_idx].strip()
            gid = row[gid_idx].strip()
            team = row[team_idx].strip()
            if not name or not week or not gid:
                continue
            key_lower = name.lower()
            display_name[key_lower] = name
            group_key = (key_lower, week)
            groups.setdefault(group_key, {})[gid] = team

        flagged: Dict[str, List[Tuple[int, int, str]]] = {}
        for (key_lower, week), gid_team_map in groups.items():
            if len(gid_team_map) > 1:
                name = display_name[key_lower]
                entries = flagged.setdefault(name, [])
                for gid, team in gid_team_map.items():
                    entries.append((int(week), int(gid), team))

        for entries in flagged.values():
            entries.sort()

        return flagged

    def get_logged_matchups_by_week(self) -> Dict[int, set]:
        headers = self._get_headers()
        all_values = self.sheet.get_all_values()
        data_rows = all_values[1:]
        week_idx = headers.index("Week")
        team_idx = headers.index("Team")
        opp_idx = headers.index("Opponent")

        result: Dict[int, set] = {}
        for row in data_rows:
            if len(row) <= max(week_idx, team_idx, opp_idx):
                continue
            week_str = row[week_idx].strip()
            if not week_str.isdigit():
                continue
            team = row[team_idx].strip()
            opp = row[opp_idx].strip()
            if not team or not opp:
                continue
            week = int(week_str)
            result.setdefault(week, set()).add(frozenset({team.lower(), opp.lower()}))
        return result

    def get_latest_logged_week(self) -> Optional[int]:
        headers = self._get_headers()
        all_values = self.sheet.get_all_values()
        week_idx = headers.index("Week")
        weeks = [
            int(row[week_idx]) for row in all_values[1:]
            if len(row) > week_idx and row[week_idx].strip().isdigit()
        ]
        return max(weeks) if weeks else None

    def get_global_player_leaderboard(self, stat_labels: List[str], top_n: int = 5) -> Dict[str, List[Tuple[str, str, float]]]:
        headers = self._get_headers()
        all_values = self.sheet.get_all_values()
        data_rows = all_values[1:]
        player_idx = headers.index("Player")
        team_idx = headers.index("Team")

        result: Dict[str, List[Tuple[str, str, float]]] = {}
        for label in stat_labels:
            if label not in headers:
                continue
            stat_idx = headers.index(label)
            totals: Dict[str, float] = {}
            counts: Dict[str, int] = {}
            most_recent_team: Dict[str, str] = {}
            display_name: Dict[str, str] = {}
            for row in data_rows:
                if len(row) <= max(player_idx, team_idx, stat_idx):
                    continue
                name = row[player_idx].strip()
                if not name:
                    continue
                key = name.lower()
                display_name[key] = name
                team = row[team_idx].strip()
                if team:
                    most_recent_team[key] = team
                val_str = row[stat_idx].strip()
                if val_str:
                    try:
                        totals[key] = totals.get(key, 0.0) + float(val_str)
                        counts[key] = counts.get(key, 0) + 1
                    except ValueError:
                        pass
            if not totals:
                continue
            if label in AVERAGE_STATS:
                totals = {k: v / counts[k] for k, v in totals.items()}
            ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
            result[label] = [(display_name[k], most_recent_team.get(k, ""), total) for k, total in ranked]
        return result

    def most_recent_game_id_for_player(self, player_name: str) -> Optional[int]:
        headers = self._get_headers()
        all_values = self.sheet.get_all_values()
        player_idx = headers.index("Player")
        gid_idx = headers.index("GameID")
        target = player_name.strip().lower()
        last = None
        for row in all_values[1:]:
            if len(row) <= max(player_idx, gid_idx):
                continue
            if row[player_idx].strip().lower() == target and row[gid_idx].strip().isdigit():
                last = int(row[gid_idx])
        return last

    def log_sub(self, game_id: Optional[int], player: str, team: str, note: str = ""):
        self.subs_sheet.append_row([
            datetime.datetime.utcnow().isoformat(),
            str(game_id) if game_id is not None else "",
            player, team, note,
        ])

    def remove_player_stats_not_matching_team(self, player_name: str, keep_team: str) -> int:
        headers = self._get_headers()
        all_values = self.sheet.get_all_values()
        player_idx = headers.index("Player")
        team_idx = headers.index("Team")
        week_idx = headers.index("Week")
        target = player_name.strip().lower()
        keep = keep_team.strip().lower()

        rows_to_delete = []
        weeks_affected = set()
        for i, row in enumerate(all_values[1:], start=2):
            if len(row) <= max(player_idx, team_idx):
                continue
            if row[player_idx].strip().lower() != target:
                continue
            if row[team_idx].strip().lower() == keep:
                continue
            rows_to_delete.append(i)
            if len(row) > week_idx and row[week_idx].strip().isdigit():
                weeks_affected.add(int(row[week_idx]))

        for row_idx in sorted(rows_to_delete, reverse=True):
            self.sheet.delete_rows(row_idx)

        for week in weeks_affected:
            self.refresh_leaderboards_for_week(week)

        return len(rows_to_delete)


    def remove_players_from_game(self, game_id: int, player_names: List[str]) -> Tuple[bool, List[str], List[str]]:
        headers = self._get_headers()
        all_values = self.sheet.get_all_values()
        gid_col = headers.index("GameID")
        player_col = headers.index("Player")
        week_col = headers.index("Week")

        targets = {p.strip().lower(): p for p in player_names}
        matched_lower = set()
        rows_to_delete = []
        game_found = False
        week = None

        for i, row in enumerate(all_values[1:], start=2):
            if row[gid_col].strip() != str(game_id):
                continue
            game_found = True
            if week is None and row[week_col].strip().isdigit():
                week = int(row[week_col])
            player_lower = row[player_col].strip().lower()
            if player_lower in targets:
                rows_to_delete.append(i)
                matched_lower.add(player_lower)

        for row_idx in sorted(rows_to_delete, reverse=True):
            self.sheet.delete_rows(row_idx)

        if week is not None and rows_to_delete:
            self.refresh_leaderboards_for_week(week)

        removed = [targets[p] for p in matched_lower]
        not_found = [targets[p] for p in targets if p not in matched_lower]
        return game_found, removed, not_found


    def clear_all_data(self):
        self.sheet.clear()
        self.sheet.append_row(FIXED_COLUMNS)

        self.meta_sheet.clear()
        self.meta_sheet.append_row(["MessageID", "GameID", "Timestamp"])

        self.subs_sheet.clear()
        self.subs_sheet.append_row(["Timestamp", "GameID", "Player", "Team", "Note"])

        for ws in self.spreadsheet.worksheets():
            if WEEK_RAW_RE.match(ws.title) or WEEK_LEADERBOARD_RE.match(ws.title):
                self.spreadsheet.del_worksheet(ws)

        self.global_lb.clear()
        self._style_master_sheet()
        self._organize_tabs()


    def get_player_card_data(self, player_name: str, stat_labels: Optional[List[str]] = None) -> Optional[dict]:
        stat_labels = stat_labels if stat_labels is not None else CURATED_STATS
        headers = self._get_headers()
        all_values = self.sheet.get_all_values()
        data_rows = all_values[1:]
        player_idx = headers.index("Player")
        team_idx = headers.index("Team")

        target = player_name.strip().lower()
        player_rows = [
            row for row in data_rows
            if len(row) > player_idx and row[player_idx].strip().lower() == target
        ]
        if not player_rows:
            return None

        display_name = player_rows[-1][player_idx]
        team = player_rows[-1][team_idx] if len(player_rows[-1]) > team_idx else ""
        games_played = len(player_rows)

        stats_out = []
        for label in stat_labels:
            if label not in headers:
                continue
            stat_idx = headers.index(label)

            totals_by_player: Dict[str, float] = {}
            counts_by_player: Dict[str, int] = {}
            for row in data_rows:
                if len(row) <= stat_idx or len(row) <= player_idx:
                    continue
                val_str = row[stat_idx].strip()
                if val_str == "":
                    continue
                try:
                    val = float(val_str)
                except ValueError:
                    continue
                key = row[player_idx].strip().lower()
                totals_by_player[key] = totals_by_player.get(key, 0.0) + val
                counts_by_player[key] = counts_by_player.get(key, 0) + 1

            if label in AVERAGE_STATS:
                totals_by_player = {k: v / counts_by_player[k] for k, v in totals_by_player.items()}

            if target not in totals_by_player:
                continue

            player_total = totals_by_player[target]
            ranked_totals = sorted(totals_by_player.values(), reverse=True)
            rank = ranked_totals.index(player_total) + 1

            stats_out.append({
                "label": label,
                "total": player_total,
                "rank": rank,
                "out_of": len(totals_by_player),
            })

        return {
            "name": display_name,
            "team": team,
            "games_played": games_played,
            "stats": stats_out,
        }
