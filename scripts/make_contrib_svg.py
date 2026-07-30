"""Gera o grafico de contribuicoes animado a partir dos dados reais do GitHub.

Consulta a API GraphQL, monta a grade de 53 semanas e escreve um SVG em que os
quadrados aparecem um a um, da esquerda para a direita. A animacao usa SMIL
porque o GitHub renderiza o SVG via <img> e nao executa JavaScript.

Precisa de um token em GITHUB_TOKEN (no CI, o proprio token do workflow serve).

    GITHUB_TOKEN=$(gh auth token) python scripts/make_contrib_svg.py
"""

import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "contributions.svg"

LOGIN = os.environ.get("PROFILE_LOGIN", "yanmathzz")
API = "https://api.github.com/graphql"

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays { date contributionCount weekday }
        }
      }
    }
  }
}
"""

CELL = 11.0
GAP = 3.0
STEP = CELL + GAP
RADIUS = 2.5

PAD_L = 30.0     # espaco para os rotulos de dia da semana
PAD_T = 34.0     # espaco para titulo e rotulos de mes
PAD_R = 12.0
PAD_B = 30.0     # espaco para a legenda

# escala do GitHub, tema escuro / tema claro
DARK = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]
LIGHT = ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"]

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
WEEKDAYS = {1: "Mon", 3: "Wed", 5: "Fri"}

REVEAL = 0.30        # duracao do fade de cada quadrado
COL_STAGGER = 0.028  # atraso entre colunas
ROW_STAGGER = 0.012  # atraso entre linhas dentro da coluna
START = 0.2


def fetch() -> dict:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("erro: defina GITHUB_TOKEN (ex.: GITHUB_TOKEN=$(gh auth token))")

    body = json.dumps({"query": QUERY, "variables": {"login": LOGIN}}).encode()
    req = urllib.request.Request(
        API,
        data=body,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": f"{LOGIN}-profile-art",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)

    if "errors" in payload:
        sys.exit(f"erro da API: {payload['errors']}")
    return payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]


def level_of(count: int, peak: int) -> int:
    """Bucket de cor 0-4, escalado pelo pico do proprio periodo."""
    if count <= 0:
        return 0
    if peak <= 1:
        return 1
    ratio = count / peak
    for i, limit in enumerate((0.15, 0.35, 0.65)):
        if ratio <= limit:
            return i + 1
    return 4


def main() -> None:
    cal = fetch()
    weeks = cal["weeks"]
    total = cal["totalContributions"]
    peak = max((d["contributionCount"] for w in weeks for d in w["contributionDays"]), default=0)

    width = PAD_L + len(weeks) * STEP + PAD_R
    height = PAD_T + 7 * STEP + PAD_B

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" '
        f'viewBox="0 0 {width:.2f} {height:.2f}" role="img" '
        f'aria-label="{LOGIN} contribution graph: {total} contributions in the last year">',
        "<style>",
        ".t{font-family:'SFMono-Regular',Consolas,'Liberation Mono',Menlo,monospace;font-size:9px;fill:#7d8590}"
        ".h{font-family:'SFMono-Regular',Consolas,'Liberation Mono',Menlo,monospace;font-size:11px;fill:#c9d1d9}",
        "@media (prefers-color-scheme: light){.h{fill:#1f2328}.t{fill:#59636e}}",
    ]
    # as cores dos quadrados trocam junto com o tema do GitHub
    for i, c in enumerate(DARK):
        parts.append(f".c{i}{{fill:{c}}}")
    parts.append("@media (prefers-color-scheme: light){")
    for i, c in enumerate(LIGHT):
        parts.append(f".c{i}{{fill:{c}}}")
    parts.append("}")
    parts.append("</style>")

    parts.append(
        f'<text class="h" x="{PAD_L:.1f}" y="14">{total} contributions in the last year</text>'
    )

    # rotulos de mes: escreve quando a semana estreia um mes novo
    last_month = None
    for wi, week in enumerate(weeks):
        first = week["contributionDays"][0]["date"]
        month = int(first[5:7])
        if month != last_month:
            # evita rotulo colado na borda direita
            if wi < len(weeks) - 2:
                x = PAD_L + wi * STEP
                parts.append(f'<text class="t" x="{x:.1f}" y="{PAD_T - 6:.1f}">{MONTHS[month - 1]}</text>')
            last_month = month

    for wd, label in WEEKDAYS.items():
        y = PAD_T + wd * STEP + CELL * 0.82
        parts.append(f'<text class="t" x="0" y="{y:.1f}">{label}</text>')

    for wi, week in enumerate(weeks):
        for day in week["contributionDays"]:
            wd = day["weekday"]
            lvl = level_of(day["contributionCount"], peak)
            x = PAD_L + wi * STEP
            y = PAD_T + wd * STEP
            begin = START + wi * COL_STAGGER + wd * ROW_STAGGER
            n = day["contributionCount"]
            plural = "contribution" if n == 1 else "contributions"
            parts.append(
                # opacity ja nasce em 1: sem SMIL o grafico aparece completo
                # em vez de sumir. A animacao so sobrepoe enquanto toca.
                f'<rect class="c{lvl}" x="{x:.1f}" y="{y:.1f}" width="{CELL}" height="{CELL}" '
                f'rx="{RADIUS}" opacity="1">'
                f"<title>{day['date']}: {n} {plural}</title>"
                f'<animate attributeName="opacity" from="0" to="1" dur="{REVEAL}s" '
                f'begin="{begin:.3f}s" fill="freeze"/>'
                "</rect>"
            )

    # legenda
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
    print(f"ok: {OUT.name} ({total} contribuicoes, {len(weeks)} semanas, pico {peak})")


if __name__ == "__main__":
    main()
