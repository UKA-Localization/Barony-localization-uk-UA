"""Перевіряє плейсхолдери у перекладах translation/strings.tsv.

    python tools/validate.py            # код виходу 1, якщо є помилки
    python tools/validate.py --tokens   # показати, які printf-плейсхолдери є в текстах гри

Для кожного перекладеного рядка порівнюється з оригіналом:
  %s %d %+d %% …       — printf-плейсхолдери: той самий набір у тому ж порядку
                         (гра підставляє значення по черзі, переставляти не можна).
                         Список плейсхолдерів береться з самих оригіналів, а не з
                         повного синтаксису printf — щоб «50%, 75%» чи «% Max HP»
                         не вважалися плейсхолдерами
  $                    — місце значка клавіші в навчальних табличках: та сама кількість
  ^  *2                — у сюжетних текстах: зміна картинки і розмір вікна: те саме
  #                    — у lang/*.txt «#» завершує запис, у перекладі його бути не може
"""

import argparse
import re
import sys
from collections import Counter

from barony import STRINGS_TSV, read_strings_tsv

sys.stdout.reconfigure(encoding="utf-8")

# Кандидат у плейсхолдери: %% або %[прапорці][ширина][.точність][hh|h|ll|l]<літера>
CANDIDATE = re.compile(r"%(?:%|[-+#0]*\d*(?:\.\d*)?(?:hh|h|ll|l)?[a-zA-Z])")
SIZE = re.compile(r"\*\d")


def printf_tokens(rows: list[list[str]]) -> Counter:
    """Плейсхолдери, які реально трапляються в оригіналах, з кількістю."""
    counts: Counter = Counter()
    for _file, _key, original, *_ in rows:
        counts.update(CANDIDATE.findall(original))
    return counts


def printf_pattern(tokens) -> re.Pattern:
    return re.compile("|".join(re.escape(t) for t in sorted(tokens, key=len, reverse=True)))


def check(file: str, original: str, translation: str, printf: re.Pattern) -> list[str]:
    problems = []
    o, t = printf.findall(original), printf.findall(translation)
    if o != t:
        problems.append(f"printf: в оригіналі {o or '—'}, у перекладі {t or '—'}")
    if original.count("$") != translation.count("$"):
        problems.append(f"«$»: в оригіналі {original.count('$')}, у перекладі {translation.count('$')}")
    if file.startswith("data/story/"):
        if original.count("^") != translation.count("^"):
            problems.append(f"«^»: в оригіналі {original.count('^')}, у перекладі {translation.count('^')}")
        o, t = SIZE.findall(original), SIZE.findall(translation)
        if o != t:
            problems.append(f"розмір «*N»: в оригіналі {o or '—'}, у перекладі {t or '—'}")
    if file.endswith(".txt") and "#" in translation:
        problems.append("«#» у перекладі обірве запис у грі")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tokens", action="store_true", help="показати плейсхолдери з оригіналів і вийти")
    args = ap.parse_args()

    rows = read_strings_tsv()
    tokens = printf_tokens(rows)
    if args.tokens:
        for token, n in tokens.most_common():
            print(f"{n:6d}  {token}")
        return 0

    printf = printf_pattern(tokens)
    errors = 0
    for file, key, original, translation, *_ in rows:
        if not translation:
            continue
        for p in check(file, original, translation, printf):
            errors += 1
            print(f"{file}:{key}: {p}")
            print(f"    {original!r}")
            print(f"    {translation!r}")
    checked = sum(1 for r in rows if r[3])
    print(f"{STRINGS_TSV.name}: перевірено {checked} перекладів, помилок {errors}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
