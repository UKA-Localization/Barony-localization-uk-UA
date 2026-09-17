"""Збирає мод з українським перекладом і (за бажанням) ставить його в гру.

    python tools/build.py                 # -> build/uk-UA/
    python tools/build.py --install       # зібрати й скопіювати в <гра>/mods/uk-UA/
    python tools/build.py --drafts        # включити й чернетки (status непорожній) — для перевірки в грі
    python tools/build.py --uninstall     # прибрати мод із гри
    python tools/build.py --install --game "D:\\Games\\Barony"

Мод — це тека з файлами за тими самими шляхами, що в грі; гра накладає їх поверх своїх.
У мод потрапляють лише файли, в яких є хоч один переклад (плюс assets/ цілком):
  lang/en.txt та інші *.txt зі рядками   — оригінал із підставленими перекладами зі strings.tsv
  *.json                                  — те саме для JSON (структуру збережено, форматування — своє)
  translation/files/*                     — як є, якщо відрізняються від source/
  assets/**                               — як є (шрифти тощо)
Рядки без перекладу лишаються англійськими.

Увімкнути мод у грі: головне меню -> Custom Content -> Local Mods -> uk-UA -> Load Mod.
"""

import argparse
import filecmp
import shutil
import sys
from pathlib import Path

from barony import (
    ASSETS_DIR, BUILD_DIR, DEFAULT_GAME_DIR, FILES, FILES_DIR, JSON_FILES, PUBLISH_DIR, SOURCE_DIR, TXT_ENTRY_LIMIT, TXT_FILES,
    apply_json, dump_json_compact, game_files, json_size_limit, load_json, read_strings_tsv, read_text, rel, render_txt,
)

sys.stdout.reconfigure(encoding="utf-8")

MOD_NAME = "uk-UA"
OUTPUT = BUILD_DIR / MOD_NAME


def load_translations(drafts: bool = False) -> dict[str, dict[str, str]]:
    """file -> {key: translation} для готових перекладів (status порожній); з drafts — і чернетки."""
    out: dict[str, dict[str, str]] = {}
    for file, key, _original, translation, status, *_ in read_strings_tsv():
        if translation and (drafts or not status):
            out.setdefault(file, {})[key] = translation
    return out


def write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def build(drafts: bool = False) -> Path:
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    translations = load_translations(drafts)
    problems: list[str] = []
    total = 0

    for path in game_files(SOURCE_DIR, TXT_FILES):
        file = rel(path, SOURCE_DIR)
        tr = translations.get(file)
        if not tr:
            continue
        for key, text in tr.items():
            if "#" in text:
                problems.append(f"{file}:{key}: «#» у перекладі обірве рядок у грі")
            size = len(f"{key} {text}#\r\n".encode("utf-8"))
            if size >= TXT_ENTRY_LIMIT:
                problems.append(f"{file}:{key}: запис {size} байт ≥ {TXT_ENTRY_LIMIT} — переповнить буфер гри, скоротити")
        rendered, n = render_txt(read_text(path), tr)
        write(OUTPUT / file, rendered.encode("utf-8"))
        total += n
        print(f"  {n:5d}  {file}")

    for path in game_files(SOURCE_DIR, list(JSON_FILES)):
        file = rel(path, SOURCE_DIR)
        tr = translations.get(file)
        if not tr:
            continue
        root = load_json(path)
        n = apply_json(root, tr)
        if n != len(tr):
            problems.append(f"{file}: {len(tr) - n} ключів зі strings.tsv не знайдено у файлі — запусти extract.py")
        # компактно: гра читає JSON у буфер фіксованого розміру (див. JSON_SIZE_LIMITS)
        data = dump_json_compact(root).encode("utf-8")
        limit = json_size_limit(file)
        if limit and len(data) >= limit:
            problems.append(f"{file}: {len(data)} байт ≥ ліміт гри {limit} — обріжеться при читанні, скоротити тексти")
        write(OUTPUT / file, data)
        total += n
        print(f"  {n:5d}  {file}")

    files = 0
    for path in game_files(SOURCE_DIR, FILES):
        file = rel(path, SOURCE_DIR)
        translated = FILES_DIR / file
        if translated.exists() and not filecmp.cmp(path, translated, shallow=False):
            write(OUTPUT / file, translated.read_bytes())
            files += 1
    if files:
        print(f"  {files:5d}  файлів із translation/files/")

    assets = 0
    for path in ASSETS_DIR.rglob("*"):
        if path.is_file() and path.name != "README.md":
            write(OUTPUT / path.relative_to(ASSETS_DIR), path.read_bytes())
            assets += 1
    print(f"  {assets:5d}  файлів із assets/")

    # обкладинка мода: гра показує її в списку модів і бере для Steam Workshop
    preview = PUBLISH_DIR / "preview.png"
    if preview.exists():
        write(OUTPUT / "preview.png", preview.read_bytes())

    print(f"{OUTPUT.relative_to(OUTPUT.parents[1])}: {total} перекладених рядків")
    for p in problems:
        print("!", p)
    if problems:
        sys.exit(1)
    return OUTPUT


def install(built: Path, game_dir: Path) -> int:
    if not (game_dir / "lang" / "en.txt").exists():
        print(f"не знайдено теку гри: {game_dir}", file=sys.stderr)
        return 1
    target = game_dir / "mods" / MOD_NAME
    # Не rmtree: якщо гра запущена, шрифти заблоковані, і видалення обривається на півдорозі,
    # лишаючи мод понівеченим. Копіюємо поверх, зайве прибираємо, заблоковане пропускаємо.
    wanted = {p.relative_to(built) for p in built.rglob("*") if p.is_file()}
    locked: list[Path] = []
    for rel_path in sorted(wanted):
        src, dst = built / rel_path, target / rel_path
        if dst.exists() and filecmp.cmp(src, dst, shallow=False):
            continue
        try:
            write(dst, src.read_bytes())
        except PermissionError:
            locked.append(rel_path)
    if target.exists():
        for p in sorted(target.rglob("*"), reverse=True):
            if p.is_file() and p.relative_to(target) not in wanted:
                try:
                    p.unlink()
                except PermissionError:
                    locked.append(p.relative_to(target))
            elif p.is_dir() and not any(p.iterdir()):
                p.rmdir()
    print(f"встановлено: {target}")
    if locked:
        print(f"! гра запущена — не оновлено {len(locked)} файлів (заблоковані): " + ", ".join(str(x) for x in locked[:5]))
        return 1
    return 0


def uninstall(game_dir: Path) -> int:
    target = game_dir / "mods" / MOD_NAME
    if target.exists():
        shutil.rmtree(target)
        print(f"видалено: {target}")
    else:
        print(f"нічого видаляти: {target}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--install", action="store_true", help="скопіювати мод у теку гри")
    ap.add_argument("--uninstall", action="store_true", help="видалити мод із гри")
    ap.add_argument("--drafts", action="store_true", help="включити чернетки (status непорожній), для перевірки в грі")
    ap.add_argument("--game", type=Path, default=DEFAULT_GAME_DIR, help="тека гри (типово — Steam за замовчуванням)")
    args = ap.parse_args()

    if args.uninstall:
        return uninstall(args.game)
    built = build(args.drafts)
    if args.install:
        return install(built, args.game)
    return 0


if __name__ == "__main__":
    sys.exit(main())
