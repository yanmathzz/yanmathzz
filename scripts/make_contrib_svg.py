"""Gera o grafico de contribuicoes do README a partir dos commits reais.

Por que nao usar a contributionsCollection da API: ela so devolve o que o token
enxerga publicamente (aqui, 66 de ~338), entao o grafico saia quase vazio. Este
script percorre todos os repositorios acessiveis — publicos e privados — e conta
os commits do autor, o que reproduz o volume que o GitHub mostra no perfil.

Precisa de um token com escopo `repo` em GITHUB_TOKEN. Sem acesso aos privados o
resultado fica incompleto, por isso o script sinaliza a cobertura no final.

    GITHUB_TOKEN=$(gh auth token) python scripts/make_contrib_svg.py
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "contributions.svg"

LOGIN = os.environ.get("PROFILE_LOGIN", "yanmathzz")
API = "https://api.github.com"

CELL = 11.0
GAP = 3.0
STEP = CELL + GAP
RADIUS = 2.5

PAD_L = 30.0
PAD_T = 34.0
PAD_R = 12.0
PAD_B = 30.0

# escala do GitHub, tema escuro / tema claro
DARK = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]
LIGHT = ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"]

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
WEEKDAYS = {1: "Mon", 3: "Wed", 5: "Fri"}

REVEAL = 0.30
COL_STAGGER = 0.028
ROW_STAGGER = 0.012
START = 0.2


def token() -> str:
    t = os.environ.get("GITHUB_TOKEN")
    if not t:
        sys.exit("erro: defina GITHUB_TOKEN (ex.: GITHUB_TOKEN=$(gh auth token))")
    return t


def api(path: str, params: dict | None = None) -> list | dict:
    url = f"{API}/{path.lstrip('/')}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"bearer {token()}",
            "Accept": "application/vnd.github+json",
            "User-Agent": f"{LOGIN}-profile",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r), r.headers.get("Link", "")
    except urllib.error.HTTPError:
        # repo sem commits, sem acesso ou vazio: nao interrompe a coleta
        return [], ""


def paged(path: str, params: dict) -> list:
    out, page = [], 1
    while True:
        data, link = api(path, {**params, "per_page": 100, "page": page})
        if not isinstance(data, list) or not data:
            break
        out.extend(data)
        if 'rel="next"' not in link:
            break
        page += 1
        if page > 10:  # teto de seguranca
            break
    return out


def collect_days() -> tuple[Counter, int, int, int]:
    """Conta commits por dia em todos os repositorios acessiveis."""
    since = (datetime.now(timezone.utc) - timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%SZ")
    repos = paged("user/repos", {"affiliation": "owner,collaborator,organization_member"})

    days: Counter = Counter()
    total = private_repos = 0
    for r in repos:
        commits = paged(f"repos/{r['full_name']}/commits", {"author": LOGIN, "since": since})
        n = 0
        for c in commits:
            stamp = ((c.get("commit") or {}).get("author") or {}).get("date")
            if stamp:
                days[stamp[:10]] += 1
                n += 1
        if n:
            total += n
            if r.get("private"):
                private_repos += 1
    return days, total, len(repos), private_repos


def level_of(count: int, peak: int) -> int:
    if count <= 0:
        return 0
    if peak <= 1:
        return 1
    ratio = count / peak
    for i, limit in enumerate((0.15, 0.35, 0.65)):
        if ratio <= limit:
            return i + 1
    return 4


def build_weeks() -> list[list[date]]:
    """53 semanas terminando hoje, comecando num domingo (como o GitHub)."""
    today = date.today()
    start = today - timedelta(days=364)
    start -= timedelta(days=(start.weekday() + 1) % 7)  # recua ate domingo
    weeks, cur = [], start
    while cur <= today:
        week = [cur + timedelta(days=i) for i in range(7)]
        weeks.append(week)
        cur += timedelta(days=7)
    return weeks


def main() -> None:
    days, total, n_repos, n_private = collect_days()
    weeks = build_weeks()
    today = date.today()
    peak = max(days.values(), default=0)

    width = PAD_L + len(weeks) * STEP + PAD_R
    height = PAD_T + 7 * STEP + PAD_B

    label = "commit" if total == 1 else "commits"
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" '
        f'viewBox="0 0 {width:.2f} {height:.2f}" role="img" '
        f'aria-label="{total} {label} by {LOGIN} in the last year">',
        "<style>",
        ".t{font-family:'SFMono-Regular',Consolas,'Liberation Mono',Menlo,monospace;font-size:9px;fill:#7d8590}"
        ".h{font-family:'SFMono-Regular',Consolas,'Liberation Mono',Menlo,monospace;font-size:11px;fill:#c9d1d9}",
        "@media (prefers-color-scheme: light){.h{fill:#1f2328}.t{fill:#59636e}}",
    ]
    for i, c in enumerate(DARK):
        parts.append(f".c{i}{{fill:{c}}}")
    parts.append("@media (prefers-color-scheme: light){")
    for i, c in enumerate(LIGHT):
        parts.append(f".c{i}{{fill:{c}}}")
    parts.append("}")
    parts.append("</style>")

    parts.append(f'<text class="h" x="{PAD_L:.1f}" y="14">{total} {label} in the last year</text>')

    last_month = None
    for wi, week in enumerate(weeks):
        m = week[0].month
        if m != last_month:
            if wi < len(weeks) - 2:
                parts.append(
                    f'<text class="t" x="{PAD_L + wi * STEP:.1f}" y="{PAD_T - 6:.1f}">{MONTHS[m - 1]}</text>'
                )
            last_month = m

    for wd, lb in WEEKDAYS.items():
        parts.append(f'<text class="t" x="0" y="{PAD_T + wd * STEP + CELL * 0.82:.1f}">{lb}</text>')

    for wi, week in enumerate(weeks):
        for wd, day in enumerate(week):
            if day > today:
                continue
            n = days.get(day.isoformat(), 0)
            lvl = level_of(n, peak)
            begin = START + wi * COL_STAGGER + wd * ROW_STAGGER
            word = "commit" if n == 1 else "commits"
            # opacity ja nasce em 1: sem SMIL o grafico aparece completo.
            parts.append(
                f'<rect class="c{lvl}" x="{PAD_L + wi * STEP:.1f}" y="{PAD_T + wd * STEP:.1f}" '
                f'width="{CELL}" height="{CELL}" rx="{RADIUS}" opacity="1">'
                f"<title>{day.isoformat()}: {n} {word}</title>"
                f'<animate attributeName="opacity" from="0" to="1" dur="{REVEAL}s" '
                f'begin="{begin:.3f}s" fill="freeze"/>'
                "</rect>"
            )

    ly = PAD_T + 7 * STEP + 16
    lx = width - PAD_R - 5 * STEP - 46
    parts.append(f'<text class="t" x="{lx:.1f}" y="{ly + 8.5:.1f}">less</text>')
    for i in range(5):
        parts.append(
            f'<rect class="c{i}" x="{lx + 26 + i * STEP:.1f}" y="{ly:.1f}" '
            f'width="{CELL}" height="{CELL}" rx="{RADIUS}"/>'
        )
    parts.append(f'<text class="t" x="{lx + 26 + 5 * STEP + 4:.1f}" y="{ly + 8.5:.1f}">more</text>')
    parts.append("</svg>")

    OUT.write_text("\n".join(parts), encoding="utf-8")
    print(
        f"ok: {OUT.name} — {total} commits em {len(days)} dias, pico {peak}; "
        f"{n_repos} repositorios varridos, {n_private} privados com commits"
    )

    # o workflow usa isso para nao substituir um grafico rico por um vazio
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
            fh.write(f"total={total}\n")


if __name__ == "__main__":
    main()
