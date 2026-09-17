"""Міст між translation/strings.tsv (main) і PO-файлами для Weblate (гілка weblate).

    python tools/weblate.py push      # TSV -> PO, коміт і пуш у гілку weblate
    python tools/weblate.py pull      # PO з гілки weblate -> translation/strings.tsv, glossary.tsv
    python tools/weblate.py export DIR   # лише записати PO у DIR (без git)

У main PO-файлів немає — джерело правди там TSV. Гілка weblate містить тільки
po/uk-UA/<файл гри>.po — по одному компоненту Weblate на файл гри (винятки — GROUPS:
дрібні файли однієї теки збираються в один компонент). Глосарій — po/uk-UA/glossary.po.
Маска компонента у Weblate: po/*/<файл гри>.po.

Weblate працює з гілкою weblate через робочу копію в build/weblate (git worktree).
pull лише оновлює TSV — переглянь diff і закоміть у main звичайним чином.
"""

import argparse
import fnmatch
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from barony import BUILD_DIR, FUZZY, REPO, read_strings_tsv, read_text, write_strings_tsv
from glossary import COLUMNS as GLOSSARY_COLUMNS, GLOSSARY_TSV, read_glossary

sys.stdout.reconfigure(encoding="utf-8")

BRANCH = "weblate"
REMOTE = "origin"
WORKTREE = BUILD_DIR / "weblate"
PO_DIR = "po"
LANG = "uk-UA"  # тека в po/ і код мови компонента у Weblate

# Файли гри, які йдуть в один компонент (glob -> назва компонента). Решта — по файлу.
GROUPS = {
    "data/story/*.json": "data/story",
    "data/scripts/*/script.json": "data/scripts",
    "books/*.txt": "books",  # 34 книги, по одному рядку кожна — один компонент
}

HEADER = """msgid ""
msgstr ""
"Project-Id-Version: Barony uk-UA\\n"
"Language: {lang}\\n"
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Content-Transfer-Encoding: 8bit\\n"
"Plural-Forms: nplurals=3; plural=(n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2);\\n"
"X-Generator: tools/weblate.py\\n"
"""


def component_of(file: str) -> str:
    for pattern, name in GROUPS.items():
        if fnmatch.fnmatchcase(file, pattern):
            return name
    return file


def po_path(root: Path, component: str) -> Path:
    """po/<мова>/<компонент>.po — маска Weblate: po/*/<компонент>.po."""
    return root / PO_DIR / LANG / f"{component}.po"


# ---------------------------------------------------------------------------
# PO

def po_quote(s: str) -> str:
    s = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")
    return f'"{s}"'


def po_unquote(s: str) -> str:
    out, i = [], 0
    s = s.strip()[1:-1]
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            out.append({"n": "\n", "t": "\t", '"': '"', "\\": "\\"}.get(s[i + 1], s[i + 1]))
            i += 2
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


def write_po(path: Path, entries: list[tuple[str, str, str, str, str, bool]]) -> None:
    """entries: (file, key, original, translation, note, fuzzy)."""
    grouped = len({e[0] for e in entries}) > 1
    lines = [HEADER.format(lang=LANG)]
    for file, key, original, translation, note, fuzzy in entries:
        lines.append("")
        for line in note.split("\n"):
            if line:
                lines.append(f"#. {line}")
        if fuzzy and translation:
            lines.append("#, fuzzy")
        lines.append(f"#: {file}")
        lines.append(f"msgctxt {po_quote(f'{file}|{key}' if grouped else key)}")
        lines.append(f"msgid {po_quote(original)}")
        lines.append(f"msgstr {po_quote(translation)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))


def read_po(path: Path) -> list[dict]:
    """Записи PO: {file, key, msgid, msgstr, fuzzy}. Застарілі (#~) пропускаються."""
    entries, cur, field = [], None, None

    def flush():
        if cur and cur.get("msgid") is not None and cur["msgid"] != "":
            ctx = cur.get("msgctxt", "")
            file = cur.get("file", "")
            key = ctx[len(file) + 1:] if file and ctx.startswith(file + "|") else ctx
            entries.append({"file": file, "key": key, "msgid": cur["msgid"],
                            "msgstr": cur.get("msgstr", ""), "fuzzy": cur.get("fuzzy", False)})

    for line in read_text(path).split("\n"):
        line = line.rstrip("\r")
        if not line.strip():
            flush()
            cur, field = None, None
            continue
        if cur is None:
            cur = {}
        if line.startswith("#~"):
            cur["obsolete"] = True
            continue
        if line.startswith("#:"):
            cur["file"] = line[2:].strip()
        elif line.startswith("#,"):
            cur["fuzzy"] = "fuzzy" in line
        elif line.startswith("#"):
            pass
        elif line.startswith(("msgctxt ", "msgid ", "msgstr ")):
            field, _, value = line.partition(" ")
            cur[field] = po_unquote(value)
        elif line.startswith('"') and field:
            cur[field] += po_unquote(line)
    flush()
    return [e for e in entries if not e.get("obsolete")]


# ---------------------------------------------------------------------------
# TSV <-> PO

def export_po(out_dir: Path) -> dict[str, int]:
    rows = read_strings_tsv()
    components: dict[str, list] = {}
    glossary_terms = {t["id"]: t for t in read_glossary()}
    for file, key, original, translation, status, context, entities, tone in rows:
        note = context
        ids = [e for e in entities.split("|") if e and e != "-"]
        if ids:
            note += ("\n" if note else "") + "сутності: " + ", ".join(
                f"{glossary_terms[e]['term']} → {glossary_terms[e]['translation'] or '?'}" if e in glossary_terms else e for e in ids)
        if tone and tone != "-":
            note += ("\n" if note else "") + "тон: " + tone.replace("|", ", ")
        components.setdefault(component_of(file), []).append((file, key, original, translation, note, bool(status)))
    for name, entries in components.items():
        write_po(po_path(out_dir, name), entries)
    glossary = [(GLOSSARY_TSV.name, t["term"], t["term"], t["translation"], t["note"], bool(t["status"])) for t in read_glossary()]
    write_po(po_path(out_dir, "glossary"), glossary)
    return {name: len(entries) for name, entries in components.items()}


def import_po(in_dir: Path) -> None:
    rows = read_strings_tsv()
    index = {(r[0], r[1]): r for r in rows}
    updated, fuzzy, unknown, stale = 0, 0, 0, 0
    for po in sorted((in_dir / PO_DIR / LANG).rglob("*.po")):
        if po == po_path(in_dir, "glossary"):
            continue
        for e in read_po(po):
            row = index.get((e["file"], e["key"]))
            if row is None:
                unknown += 1
                continue
            if row[2] != e["msgid"]:
                stale += 1  # оригінал у main уже інший — переклад зі старого оригіналу не беремо
                continue
            status = (row[4] or FUZZY) if e["fuzzy"] and e["msgstr"] else ""  # fuzzy у Weblate не затирає unresolved
            if e["fuzzy"]:
                fuzzy += 1
            if (e["msgstr"], status) != (row[3], row[4]):
                row[3], row[4] = e["msgstr"], status
                updated += 1
    write_strings_tsv(rows)
    done = sum(1 for r in rows if r[3] and not r[4])
    print(f"strings.tsv: оновлено {updated} рядків, перекладено {done}/{len(rows)}")
    if fuzzy:
        print(f"  чернеток «needs editing» (status=fuzzy): {fuzzy}")
    if stale:
        print(f"  оригінал змінився після push (пропущено, зроби push): {stale}")
    if unknown:
        print(f"  ключів, яких уже нема в TSV (пропущено): {unknown}")

    gpo = po_path(in_dir, "glossary")
    if gpo.exists():
        entries = {e["msgid"]: e for e in read_po(gpo) if e["msgstr"]}
        lines = read_text(GLOSSARY_TSV).split("\n")
        changed = 0
        col_term, col_tr, col_status = (GLOSSARY_COLUMNS.index(c) for c in ("term", "translation", "status"))
        for i, line in enumerate(lines[1:], start=1):
            if not line.strip():
                continue
            f = line.split("\t")
            e = entries.get(f[col_term])
            if e is None:
                continue
            status = "fuzzy" if e["fuzzy"] else ""  # затверджений у Weblate термін (не fuzzy) знімає fuzzy/new
            if (e["msgstr"], status) != (f[col_tr], f[col_status]):
                f[col_tr], f[col_status] = e["msgstr"], status
                lines[i] = "\t".join(f)
                changed += 1
        if changed:
            GLOSSARY_TSV.write_bytes("\n".join(lines).encode("utf-8"))
            print(f"glossary.tsv: оновлено {changed} термінів — запусти tools/glossary.py")


# ---------------------------------------------------------------------------
# git

def git(*args, cwd: Path = REPO, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, check=check, capture_output=True, text=True, encoding="utf-8")


def ensure_worktree() -> None:
    """build/weblate — робоча копія гілки weblate (створюється порожньою, якщо гілки ще нема)."""
    git("fetch", REMOTE, BRANCH, check=False)
    if WORKTREE.exists() and (WORKTREE / ".git").exists():
        git("checkout", BRANCH, cwd=WORKTREE)
        git("pull", "--ff-only", REMOTE, BRANCH, cwd=WORKTREE, check=False)
        return
    WORKTREE.parent.mkdir(parents=True, exist_ok=True)
    have_local = git("rev-parse", "--verify", "-q", BRANCH, check=False).returncode == 0
    have_remote = git("rev-parse", "--verify", "-q", f"{REMOTE}/{BRANCH}", check=False).returncode == 0
    if have_local:
        git("worktree", "add", str(WORKTREE), BRANCH)
    elif have_remote:
        git("worktree", "add", "--track", "-b", BRANCH, str(WORKTREE), f"{REMOTE}/{BRANCH}")
    else:
        git("worktree", "add", "--orphan", "-b", BRANCH, str(WORKTREE))
        print(f"створено порожню гілку {BRANCH}")


def push() -> int:
    ensure_worktree()
    for old in (WORKTREE / PO_DIR).rglob("*.po"):
        old.unlink()
    counts = export_po(WORKTREE)
    git("add", "-A", cwd=WORKTREE)
    if not git("status", "--porcelain", cwd=WORKTREE).stdout.strip():
        print("гілка weblate вже актуальна")
        return 0
    main_rev = git("rev-parse", "--short", "HEAD").stdout.strip()
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    git("commit", "-q", "-m", f"Sync from main {main_rev} ({stamp})", cwd=WORKTREE)
    git("push", "-u", REMOTE, BRANCH, cwd=WORKTREE)
    print(f"{len(counts)} компонентів + глосарій, {sum(counts.values())} рядків -> {REMOTE}/{BRANCH}")
    return 0


def pull() -> int:
    ensure_worktree()
    import_po(WORKTREE)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("push", help="TSV -> PO у гілку weblate")
    sub.add_parser("pull", help="PO з гілки weblate -> TSV")
    exp = sub.add_parser("export", help="записати PO у теку без git")
    exp.add_argument("dir", type=Path)
    args = ap.parse_args()

    if args.cmd == "push":
        return push()
    if args.cmd == "pull":
        return pull()
    counts = export_po(args.dir)
    print(f"{len(counts)} компонентів + глосарій -> {args.dir / PO_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
