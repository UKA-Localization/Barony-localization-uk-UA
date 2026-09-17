"""Витягує рядки для перекладу з оригінальних файлів гри.

    python tools/extract.py                 # оновити translation/ із source/
    python tools/extract.py --from-game     # спершу скопіювати свіжі файли з гри в source/
    python tools/extract.py --from-game --game "D:\\Games\\Barony"
    python tools/extract.py --unmatched     # показати рядки JSON, що не підпали під жодне правило

Що робить:
  source/            — копії файлів гри зі списків TXT_FILES, JSON_FILES, FILES (barony.py)
  translation/strings.tsv — усі рядки з lang/*.txt і JSON: file, key, original, translation, status, context, entities, tone
  translation/files/ — файли, що перекладаються цілком (списки імен): якщо файлу ще нема,
                       кладеться копія оригіналу; наявні переклади не зачіпаються

Наявні переклади, status, context, entities і tone у strings.tsv зберігаються. Для ключів, у яких змінився
оригінал, переклад лишається, але ключ виводиться у звіті — його треба переглянути.
Колонка context заповнюється для нових рядків (для lang/*.txt — коментар розділу з файлу гри,
для JSON — опис файлу з FILE_CONTEXT у barony.py); правити руками можна, --refresh-context
перегенерує її для всіх рядків.
"""

import argparse
import re
import shutil
import sys
from pathlib import Path
from typing import Iterator

from barony import (
    DEFAULT_GAME_DIR, FILES, FILES_DIR, JSON_FILES, SOURCE_DIR, STRINGS_TSV, TXT_FILES, TXT_SECTION_CONTEXT, WHOLE_FILES, WHOLE_KEY,
    all_strings, file_context, game_files, ignored_strings, load_json, read_strings_tsv, read_text, rel, rules_for,
    translatable_strings, write_strings_tsv,
)

sys.stdout.reconfigure(encoding="utf-8")


def copy_from_game(game_dir: Path) -> int:
    if not (game_dir / "lang" / "en.txt").exists():
        print(f"не знайдено теку гри: {game_dir}", file=sys.stderr)
        return 1
    patterns = TXT_FILES + list(JSON_FILES) + WHOLE_FILES + FILES
    n = 0
    for src in game_files(game_dir, patterns):
        dst = SOURCE_DIR / src.relative_to(game_dir)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        n += 1
    print(f"скопійовано з гри в source/: {n} файлів")
    return 0


def txt_entries_with_sections(data: str) -> Iterator[tuple[str, str, str]]:
    """(id, текст, розділ) для записів lang/*.txt; розділ — останній #-коментар перед записом."""
    section = ""
    lines = data.split("\r\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("#"):
            section = line.lstrip("#").strip()
            i += 1
            continue
        m = re.match(r"^(\d+)( |$)(.*)$", line)
        if not m:
            i += 1
            continue
        chunk = [m.group(3)] if m.group(2) else []
        while not (chunk and chunk[-1].endswith("#")):
            i += 1
            chunk.append(lines[i])
        yield m.group(1), "\n".join(chunk)[:-1], section
        i += 1


def extract_strings() -> list[tuple[str, str, str, str]]:
    """(file, key, original, context) з усіх файлів source/ у стабільному порядку."""
    out: list[tuple[str, str, str, str]] = []
    for path in game_files(SOURCE_DIR, TXT_FILES):
        relpath = rel(path, SOURCE_DIR)
        for sid, text, section in txt_entries_with_sections(read_text(path)):
            if text.strip():  # порожні записи («349 #») перекладати нічого
                context = TXT_SECTION_CONTEXT.get(section.lower(), section)
                out.append((relpath, sid, text, context))
    for path in game_files(SOURCE_DIR, list(JSON_FILES)):
        relpath = rel(path, SOURCE_DIR)
        context = file_context(relpath)
        for key, text in translatable_strings(load_json(path), rules_for(relpath)):
            out.append((relpath, key, text, context))
    for path in game_files(SOURCE_DIR, WHOLE_FILES):
        relpath = rel(path, SOURCE_DIR)
        text = read_text(path).replace("\r\n", "\n").rstrip("\n")
        out.append((relpath, WHOLE_KEY, text, f"{file_context(relpath)}; «{path.stem}»"))
    return out


def update_strings_tsv(refresh_context: bool = False) -> None:
    existing = {(r[0], r[1]): (r[2], r[3], r[4], r[5], r[6], r[7]) for r in read_strings_tsv()}
    rows: list[list[str]] = []
    added, changed = [], []
    for file, key, original, context in extract_strings():
        if (file, key) in existing:
            old_original, translation, status, old_context, entities, tone = existing[(file, key)]
            if old_original != original and translation:
                changed.append(f"{file}:{key}")
            if old_context and not refresh_context:
                context = old_context
        else:
            translation, status, entities, tone = "", "", "", ""
            if existing:
                added.append(f"{file}:{key}")
        rows.append([file, key, original, translation, status, context, entities, tone])

    removed = sorted(set(existing) - {(r[0], r[1]) for r in rows})
    write_strings_tsv(rows)

    total = len(rows)
    done = sum(1 for r in rows if r[3] and not r[4])
    drafts = sum(1 for r in rows if r[3] and r[4])
    print(f"{rel(STRINGS_TSV, STRINGS_TSV.parents[1])}: {total} рядків, перекладено {done} ({done * 100 // max(total, 1)}%)" + (f", чернеток {drafts}" if drafts else ""))
    per_file: dict[str, int] = {}
    for r in rows:
        per_file[r[0]] = per_file.get(r[0], 0) + 1
    for file, n in per_file.items():
        print(f"  {n:6d}  {file}")
    if added:
        print(f"нових ключів: {len(added)}")
    if removed:
        print(f"вилучених ключів (переклад втрачено): {len(removed)}")
        for file, key in removed:
            print(f"  - {file}:{key}")
    if changed:
        print(f"оригінал змінився, переклад треба переглянути: {len(changed)}")
        for k in changed:
            print("  !", k)


def update_files() -> None:
    new = 0
    for src in game_files(SOURCE_DIR, FILES):
        dst = FILES_DIR / src.relative_to(SOURCE_DIR)
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
            new += 1
    total = len(game_files(SOURCE_DIR, FILES))
    print(f"translation/files/: {total} файлів" + (f", додано копій оригіналу: {new}" if new else ""))


def looks_technical(key: str, value: str) -> bool:
    """Ключі словників, шляхи, ідентифікатори, формати — не текст для перекладу."""
    return (
        key.endswith("@")
        or value.startswith(("*", "#"))                        # шлях до ресурсу гри
        or re.fullmatch(r"[\w#*./%+:\-]+", value) is not None  # ідентифікатор, шлях, формат
        or re.search(r"\.(png|json|ttf|txt|wav|ogg)$", value) is not None
    )


def report_unmatched() -> None:
    """Рядки JSON, які не підпали під правила — щоб перевірити, чи не пропущено текст."""
    for path in game_files(SOURCE_DIR, list(JSON_FILES)):
        relpath = rel(path, SOURCE_DIR)
        root = load_json(path)
        rules = rules_for(relpath)
        known = {k for k, _ in translatable_strings(root, rules)} | set(ignored_strings(root, rules))
        rest = [(k, v) for k, v in all_strings(root) if k not in known and not looks_technical(k, v)]
        if rest:
            print(f"\n{relpath}: {len(rest)}")
            for k, v in rest:
                print(f"  {k} = {v[:70]!r}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from-game", action="store_true", help="скопіювати файли з гри в source/")
    ap.add_argument("--game", type=Path, default=DEFAULT_GAME_DIR, help="тека гри (типово — Steam за замовчуванням)")
    ap.add_argument("--unmatched", action="store_true", help="показати рядки JSON поза правилами і вийти")
    ap.add_argument("--refresh-context", action="store_true", help="перегенерувати колонку context для всіх рядків")
    args = ap.parse_args()

    if args.from_game and (rc := copy_from_game(args.game)):
        return rc
    if args.unmatched:
        report_unmatched()
        return 0
    update_strings_tsv(args.refresh_context)
    update_files()
    return 0


if __name__ == "__main__":
    sys.exit(main())
