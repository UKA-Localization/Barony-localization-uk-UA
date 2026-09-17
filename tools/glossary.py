"""Глосарій: translation/glossary.tsv — джерело правди, GLOSSARY.md — згенерований вигляд.

    python tools/glossary.py                    # перевірити glossary.tsv і перегенерувати GLOSSARY.md
    python tools/glossary.py --check            # лише перевірити (для CI)
    python tools/glossary.py --weblate out.csv  # експорт у глосарій Weblate (CSV: source,target,note)

Колонки glossary.tsv (табуляція, без лапок):
  id           стабільний ідентифікатор (slug: baron_herx) — на нього посилається колонка entities у strings.tsv
  term         оригінальний термін
  variants     інші форми в оригіналі через «|» (Goblins, goblin) — щоб шукати в тексті
  translation  усталений переклад; порожньо — ще не узгоджено
  stem         основа перекладу для перевірки відмінків (Підземелл); порожньо — обчислюється
  forms        форми перекладу через «|», якщо основа не покриває (щури|щурів)
  note         примітка для перекладача
  category     розділ у GLOSSARY.md
  status       порожньо — затверджено; fuzzy — переклад не вичитано, не затверджено; new — перекладу ще нема
"""

import argparse
import csv
import io
import re
import sys
from pathlib import Path

from barony import TRANSLATION_DIR, read_text

sys.stdout.reconfigure(encoding="utf-8")

GLOSSARY_TSV = TRANSLATION_DIR / "glossary.tsv"
GLOSSARY_MD = TRANSLATION_DIR / "GLOSSARY.md"
COLUMNS = ["id", "term", "variants", "translation", "stem", "forms", "note", "category", "status"]
# status: порожньо — затверджено; fuzzy — переклад не вичитано; new — перекладу ще нема

# Закінчення, які відкидаємо, щоб отримати основу: «Підземелля» -> «Підземелл», «Щур» -> «Щур»
VOWELS = "аеєиіїоуюяь"


def auto_stem(translation: str) -> str:
    return " ".join(w[:-1] if len(w) > 3 and w[-1].lower() in VOWELS else w for w in translation.split())


class Term(dict):
    @property
    def sources(self) -> list[str]:
        return [self["term"]] + [v for v in self["variants"].split("|") if v]

    @property
    def stem(self) -> str:
        return self["stem"] or auto_stem(self["translation"])

    @property
    def forms(self) -> list[str]:
        return [f for f in self["forms"].split("|") if f]


def read_glossary(path: Path = GLOSSARY_TSV) -> list[Term]:
    lines = read_text(path).split("\n")
    header = lines[0].split("\t")
    if header != COLUMNS:
        raise ValueError(f"{path.name}: очікувано колонки {COLUMNS}, є {header}")
    terms = []
    for n, line in enumerate(lines[1:], start=2):
        if not line.strip():
            continue
        fields = line.split("\t")
        if len(fields) != len(COLUMNS):
            raise ValueError(f"{path.name}:{n}: {len(fields)} полів замість {len(COLUMNS)}")
        terms.append(Term(zip(COLUMNS, (f.strip() for f in fields))))
    return terms


def check(terms: list[Term]) -> list[str]:
    problems = []
    seen: dict[str, str] = {}
    ids: set[str] = set()
    for t in terms:
        if not re.fullmatch(r"[a-z0-9_]+", t["id"]):
            problems.append(f"{t['term']}: id «{t['id']}» — лише a-z, 0-9, _")
        if t["id"] in ids:
            problems.append(f"{t['term']}: id «{t['id']}» повторюється")
        ids.add(t["id"])
        if t["status"] not in ("", "fuzzy", "new"):
            problems.append(f"{t['term']}: невідомий status «{t['status']}»")
        if not t["term"]:
            problems.append(f"порожній term (переклад «{t['translation']}»)")
        if not t["category"]:
            problems.append(f"{t['term']}: порожня category")
        for s in t.sources:
            if s.lower() in seen and seen[s.lower()] != t["term"]:
                problems.append(f"{t['term']}: «{s}» уже є в терміні «{seen[s.lower()]}»")
            seen[s.lower()] = t["term"]
        if t["translation"] and t["stem"] and not t["translation"].lower().startswith(t["stem"].lower()):
            problems.append(f"{t['term']}: stem «{t['stem']}» не є початком перекладу «{t['translation']}»")
    return problems


def render_md(terms: list[Term]) -> str:
    out = [
        "# Глосарій",
        "",
        "Терміни з глосарію перекладаються **тільки** так, як тут зазначено. Порожня клітинка — переклад ще не узгоджено; пропонуйте варіант в issue або PR.",
        "",
        "Файл згенеровано з [glossary.tsv](glossary.tsv) (`python tools/glossary.py`) — правити треба його.",
    ]
    categories: dict[str, list[Term]] = {}
    for t in terms:
        categories.setdefault(t["category"], []).append(t)
    for category, items in categories.items():
        out += ["", f"## {category}", "", "| Оригінал | Переклад | Примітка |", "|---|---|---|"]
        for t in items:
            mark = {"fuzzy": " _(чернетка)_", "new": ""}.get(t["status"], "")
            out.append(f"| {t['term']} | {t['translation']}{mark} | {t['note']} |")
    return "\n".join(out) + "\n"


def export_weblate(terms: list[Term], path: Path) -> None:
    """CSV для імпорту в глосарій Weblate (source,target,note); неперекладені терміни пропускаються."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["source", "target", "note"])
    for t in terms:
        if t["translation"] and not t["status"]:
            w.writerow([t["term"], t["translation"], t["note"]])
    path.write_bytes(buf.getvalue().encode("utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="лише перевірити, нічого не писати")
    ap.add_argument("--weblate", type=Path, metavar="CSV", help="експортувати глосарій для Weblate")
    args = ap.parse_args()

    terms = read_glossary()
    problems = check(terms)
    for p in problems:
        print("!", p)
    done = sum(1 for t in terms if t["translation"] and not t["status"])
    drafts = sum(1 for t in terms if t["status"] == "fuzzy")
    print(f"glossary.tsv: {len(terms)} термінів, затверджено {done}" + (f", чернеток {drafts}" if drafts else ""))
    if problems:
        return 1
    if args.weblate:
        export_weblate(terms, args.weblate)
        print(f"експортовано для Weblate: {args.weblate}")
    if not args.check:
        GLOSSARY_MD.write_bytes(render_md(terms).encode("utf-8"))
        print(f"оновлено {GLOSSARY_MD.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
