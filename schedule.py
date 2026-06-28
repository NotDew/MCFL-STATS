from typing import Dict, List, Optional, Tuple

SCHEDULE: Dict[int, List[Tuple[str, str]]] = {
    1: [
        ("Parrots", "Bees"), ("Traders", "Masons"), ("Sniffers", "Shepherds"),
        ("Riptide", "Devilbats"), ("Slimes", "Raiders"), ("Wardens", "Vexes"),
    ],
    2: [
        ("Parrots", "Sniffers"), ("Traders", "Bees"), ("Masons", "Shepherds"),
        ("Riptide", "Raiders"), ("Slimes", "Vexes"), ("Wardens", "Devilbats"),
    ],
    3: [
        ("Parrots", "Shepherds"), ("Traders", "Sniffers"), ("Bees", "Masons"),
        ("Riptide", "Slimes"), ("Wardens", "Raiders"), ("Vexes", "Devilbats"),
    ],
    4: [
        ("Parrots", "Masons"), ("Traders", "Shepherds"), ("Bees", "Sniffers"),
        ("Riptide", "Vexes"), ("Slimes", "Wardens"), ("Raiders", "Devilbats"),
    ],
    5: [
        ("Parrots", "Traders"), ("Bees", "Shepherds"), ("Sniffers", "Masons"),
        ("Riptide", "Wardens"), ("Slimes", "Devilbats"), ("Vexes", "Raiders"),
    ],
    6: [
        ("Parrots", "Riptide"), ("Traders", "Raiders"), ("Bees", "Vexes"),
        ("Sniffers", "Slimes"), ("Masons", "Wardens"), ("Shepherds", "Devilbats"),
    ],
    7: [


    ],
}


def _norm(name: str) -> str:
    return name.strip().lower()


def find_week(team_a: str, team_b: str) -> Optional[int]:
    a, b = _norm(team_a), _norm(team_b)
    for week, matchups in SCHEDULE.items():
        for t1, t2 in matchups:
            if {_norm(t1), _norm(t2)} == {a, b}:
                return week
    return None


def all_teams() -> List[str]:
    teams = set()
    for matchups in SCHEDULE.values():
        for t1, t2 in matchups:
            teams.add(t1)
            teams.add(t2)
    return sorted(teams)
