import re
from dataclasses import dataclass, field
from typing import Dict, List


RE_BARE_COMP_PCT = re.compile(r"^(\d+)\s*/\s*(\d+)\s*\((\d+)%\)$")
RE_LABEL_FRACTION = re.compile(r"^([A-Za-z0-9]+)\s*:\s*(\d+)\s*/\s*(\d+)$")
RE_LABEL_NUMBER = re.compile(r"^([A-Za-z0-9 ]+?)\s*:\s*(-?\d+(?:\.\d+)?)$")
RE_NUMBER_LABEL = re.compile(r"^(-?\d+(?:\.\d+)?)\s+(.+)$")


@dataclass
class PlayerStats:
    name: str
    stats: Dict[str, float] = field(default_factory=dict)
    unparsed: List[str] = field(default_factory=list)


@dataclass
class TeamResult:
    name: str
    score: int
    players: List[PlayerStats] = field(default_factory=list)


@dataclass
class GameResult:
    teams: List[TeamResult]
    raw_text: str


class ParseError(Exception):
    pass


def _parse_token(token: str) -> Dict[str, float]:
    token = token.strip()
    if not token:
        return {}

    m = RE_BARE_COMP_PCT.match(token)
    if m:
        comp, att, pct = m.groups()
        return {
            "Pass Comp": float(comp),
            "Pass Att": float(att),
            "Pass Pct": float(pct),
        }

    m = RE_LABEL_FRACTION.match(token)
    if m:
        label, made, att = m.groups()
        return {
            f"{label} Made": float(made),
            f"{label} Att": float(att),
        }

    m = RE_LABEL_NUMBER.match(token)
    if m:
        label, value = m.groups()
        return {label.strip(): float(value)}

    m = RE_NUMBER_LABEL.match(token)
    if m:
        value, label = m.groups()
        return {label.strip(): float(value)}


    raise ParseError(token)


def _parse_player_line(line: str) -> PlayerStats:
    if ":" not in line:
        raise ParseError(f"Player line missing ':' separator: {line!r}")
    name, rest = line.split(":", 1)
    name = name.strip()
    ps = PlayerStats(name=name)

    for raw_token in rest.split(","):
        raw_token = raw_token.strip()
        if not raw_token:
            continue
        try:
            parsed = _parse_token(raw_token)
            ps.stats.update(parsed)
        except ParseError:
            ps.unparsed.append(raw_token)

    return ps


TEAM_HEADER_RE = re.compile(r"^(.+?)\s*-\s*(-?\d+)$")


def parse_game_message(text: str) -> GameResult:
    raw_text = text

    text = re.sub(r"^```[a-zA-Z]*\n?|```$", "", text.strip())


    blocks = [b.strip() for b in re.split(r"\n\s*\n", text.strip()) if b.strip()]

    teams: List[TeamResult] = []
    for block in blocks:
        lines = [l for l in block.splitlines() if l.strip()]
        if not lines:
            continue
        header = lines[0].strip()
        m = TEAM_HEADER_RE.match(header)
        if not m:
            raise ParseError(f"Couldn't parse team header: {header!r}")
        team_name, score = m.groups()
        team = TeamResult(name=team_name.strip(), score=int(score))

        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue
            team.players.append(_parse_player_line(line))

        teams.append(team)

    if len(teams) < 2:
        raise ParseError("Expected at least 2 team blocks, found " + str(len(teams)))

    return GameResult(teams=teams, raw_text=raw_text)


if __name__ == "__main__":
    sample = """Masons - 56
NotDew: 10 Rec, 300 Rec YD, 2 Rec TD, 11 Tackles, FP: 83.0
Cosmiclolll: 1 Sacks, 3 Pressures, FP: 22.0
Criipy: QBR: 101.0, 12/23 (52%), 3 Passing TD, 295 Passing YD, 2 INT (O), 5 Rush, -40 Rushing YD, 4 Tackles, 2 Sacks, 2 Pressures, 2PT: 1/3, FP: 79.1
Its_Iron: QBR: 86.8, 17/42 (40%), 4 Passing TD, 494 Passing YD, 3 INT (O), 4 Rush, -44 Rushing YD, 3 Tackles, 6 Swats, XP: 1/1, 2PT: 3/4, FP: 81.3
KingSnoopie409: 2 Pressures, FP: 8.0
Kofeyy: 15 Rec, 489 Rec YD, 5 Rec TD, 1 Rush, 5 Rushing YD, 1 Rushing TD, 4 Tackles, 1 Sacks, 1 Pressures, 3 INT (D), FP: 156.7

Shepherds - 63
rhettoricals: 11 Rec, 346 Rec YD, 7 Rec TD, 1 Rush, 2 Rushing YD, 6 Tackles, 1 Pressures, 1 Safeties, XP: 1/1, FP: 127.8
HD_81: 3 Rec, 49 Rec YD, 4 Tackles, FP: 17.4
SteppaNick: 3 Rec, 35 Rec YD, 1 Rush, 0 Rushing YD, 5 Tackles, 1 INT (D), FP: 24.2
Shxrkq: QBR: 108.3, 22/40 (55%), 8 Passing TD, 592 Passing YD, 3 INT (O), 5 Rush, -13 Rushing YD, 7 Tackles, 3 Sacks, 3 Pressures, 1 INT (D), 1 Swats, FG: 0/1, XP: 6/6, 2PT: 0/2, FP: 183.7
ffdwz: 5 Rec, 162 Rec YD, 1 Rec TD, 3 Tackles, 2 INT (D), FP: 51.1
TheJehovah: 1 Tackles, 5 Sacks, 16 Pressures, 1 INT (D), 1 Def TD, 2 Swats, FP: 137.5"""

    result = parse_game_message(sample)
    for team in result.teams:
        print(f"\n=== {team.name} ({team.score}) ===")
        for p in team.players:
            print(f"  {p.name}: {p.stats}")
            if p.unparsed:
                print(f"    !! UNPARSED: {p.unparsed}")
