"""Спільний код для роботи з текстовими файлами Barony.

Тексти гри розкидані по файлах різних форматів (усі — відносно теки гри):

  lang/en.txt, themes/*/lang/en.txt   «<id> <текст>#» або «<id>\\n<текст>#»; рядки з # — коментарі
  lang/*.json, data/**/*.json, …      JSON, у якому перекладається лише частина полів (див. JSON_FILES)
  books/*.txt, *names-*.txt, …        прості текстові файли, перекладаються цілком (FILES)

Українська ставиться як мод (mods/<назва>/…): гра накладає файли мода поверх своїх,
тому шлях у репозиторії = шлях у грі.
"""

import fnmatch
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

REPO = Path(__file__).resolve().parent.parent
SOURCE_DIR = REPO / "source"
TRANSLATION_DIR = REPO / "translation"
STRINGS_TSV = TRANSLATION_DIR / "strings.tsv"
FILES_DIR = TRANSLATION_DIR / "files"
ASSETS_DIR = REPO / "assets"
PUBLISH_DIR = REPO / "publish"
BUILD_DIR = REPO / "build"

DEFAULT_GAME_DIR = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Barony")

TSV_HEADER = ["file", "key", "original", "translation", "status", "context", "entities", "tone"]
# status: порожньо — готовий переклад; будь-що інше — чернетка, у мод не потрапляє (fuzzy — не вичитано, «needs editing»
# у Weblate; unresolved — у рядку є термін, ще не узгоджений у глосарії)
FUZZY = "fuzzy"
# entities — id термінів із glossary.tsv, що трапляються в рядку, через «|» («-» — нема); tone — характер рядка
# (теги через «|», список у translation/pipeline.toml). Довідкові колонки, можна правити руками.


# ---------------------------------------------------------------------------
# Які файли гри беремо в source/ (glob відносно теки гри)

# Файли з рядками «<id> текст#»
TXT_FILES = [
    "lang/en.txt",
    "themes/*/lang/en.txt",
]

# JSON-файли: glob -> правила, які поля перекладаються. Шлях до поля через «/»;
# «*» — будь-який один сегмент, «**» — будь-яка кількість, «@» наприкінці — ключ словника,
# а не значення. Правило може бути парою (шлях, умова(батьківський об'єкт) -> bool).
# Правило з «!» на початку — свідомо НЕ перекладається (щоб не світилося в --unmatched).
JSON_FILES: dict[str, list] = {
    "lang/book_names.json": ["book_names/*", "!comment"],
    "lang/item_names.json": ["items/*/name_identified", "items/*/name_unidentified", "spell_names/*/name"],
    "themes/*/lang/item_names.json": ["items/*/name_identified", "items/*/name_unidentified", "spell_names/*/name"],
    # {"НАЗВА В МЕНЮ": "внутрішній id"} — перекладається ключ, значення — id статті
    "lang/compendium_lang/contents_*.json": ["contents/*/*/@", "contents_alphabetical/*/*/@", "!contents/*/*", "!contents_alphabetical/*/*"],
    "lang/compendium_lang/lang_*.json": ["*/blurb/*", "*/details/*", "*/abilities/*", "*/inventory/*"],
    "items/item_tooltips.json": [
        "adjectives/*/*",
        "templates/*/*",
        "tooltips/*/icons/*/text",
        "tooltips/*/description/*",  # description-рядок (не список) — посилання на шаблон, не чіпаємо
        "tooltips/*/details/*/*/*",  # details: [{назва: [рядки]}]; рядок замість списку — шаблон
    ],
    "themes/*/items/item_tooltips.json": ["adjectives/*/*"],
    "data/achievements.json": ["achievements/*/name", "achievements/*/description"],
    "data/callout_wheel.json": [
        "help_strings/*",
        "**/text", "**/msg_says", "**/msg_emote", "**/msg_emote_you", "**/msg_emote_to_you",
    ],
    "data/follower_wheel.json": ["**/text"],
    "data/charsheet.json": ["hover_text/**", "level_strings/*/display_name", "level_strings/*/description"],
    "data/class_descriptions.json": ["descriptions/*/desc/*"],
    "data/race_descriptions.json": ["descriptions/*/title", "descriptions/*/left_align/*", "descriptions/*/right_align/*"],
    "data/compendium/events_text.json": ["tags/*/*/*", "custom_tags/*/*"],
    "data/monster_data.json": ["**/localized_name", "**/localized_short_name", "!comment"],
    "data/scripts/*/script.json": [
        "script_entries/*/sign/*",
        "script_entries/*/message/*",
        "script_entries/*/bubble_dialogue/*",
        "script_entries/*/bubble_grave/*",
        "script_entries/*/bubble_sign/*",
        # variables: type=text — текст; input_glyph/image — назва прив'язки чи шлях до картинки
        ("script_entries/*/variables/*/value", lambda parent: parent.get("type") == "text"),
        "!script_entries/*/variables/*/value",
    ],
    "data/story/*.json": ["text/*", "!images/*"],
    "data/tutorial_strings.json": ["window_title", "default_hover_text", "levels/*/title", "levels/*/desc"],
    "data/HUD_settings.json": ["dropdowns/*/title", "dropdowns/*/options/*/text"],
    "data/skillsheet_entries.json": [
        # префікси назв зілль, які прибирає таблиця алхімії — мають збігатися з перекладом назв предметів
        "alchemy_potion_names_to_filter/*",
        "skills/*/name", "skills/*/shortname", "skills/*/description", "skills/*/legend_text",
        "skills/*/effects/*/title", "skills/*/effects/*/title_short", "skills/*/effects/*/value",
    ],
    "data/status_effects.json": [
        "sustained_effects/*/name", "sustained_effects/*/name/*", "sustained_effects/*/desc",
        "effects/*/name", "effects/*/name/*", "effects/*/desc", "effects/*/desc/*",
    ],
}

# Ліміти гри: JSON читається у буфер фіксованого розміру (char buf[N] у джерелах Barony, src/mod_tools.cpp,
# src/interface/interface.cpp, src/init_game.cpp) — файл має бути МЕНШИМ за N байт, інакше обрізається і гра падає.
# Тому build.py пише JSON компактно й перевіряє розмір. Кирилиця — 2 байти на літеру, тож запас невеликий.
JSON_SIZE_LIMITS: dict[str, int] = {
    "lang/book_names.json": 8192,
    "lang/item_names.json": 131072,
    "themes/*/lang/item_names.json": 131072,
    "items/item_tooltips.json": 1 << 20,
    "themes/*/items/item_tooltips.json": 1 << 20,
    "lang/compendium_lang/contents_*.json": 65536,
    "lang/compendium_lang/lang_*.json": 120000,
    "data/compendium/events_text.json": 120000,
    "data/achievements.json": 120000,
    "data/class_descriptions.json": 32000,
    "data/race_descriptions.json": 32000,
    "data/scripts/*/script.json": 65536,
    "data/story/*.json": 65536,
    "data/*.json": 65536,
}
# lang/*.txt: один запис (до «#», з усіма рядками) читається в char data[1024] без перевірки меж.
TXT_ENTRY_LIMIT = 1024

# Файли, що перекладаються цілком (копія в translation/files/ за тим самим шляхом)
FILES = [
    "books/*.txt",
    "npcnames-female.txt",
    "npcnames-male.txt",
    "playernames-female.txt",
    "playernames-male.txt",
]

# Контекст рядків для перекладача (колонка context у strings.tsv): glob файлу -> опис.
# Для lang/*.txt контекст — коментар розділу (# …) з самого файлу гри; тут — лише уточнення до деяких розділів.
FILE_CONTEXT = {
    "lang/item_names.json": "назви предметів в однині; name_identified — розпізнаний, name_unidentified — нерозпізнаний; з малої літери",
    "themes/*/lang/item_names.json": "назви предметів святкових тем (merry — різдвяна, scarony — геловінська); з малої літери",
    "lang/book_names.json": "назви книг для читання в грі — як заголовки",
    "lang/compendium_lang/contents_*.json": "пункти меню компендіуму — ВЕЛИКИМИ ЛІТЕРАМИ, як в оригіналі; рядки з пробілами на початку — заголовки розділів",
    "lang/compendium_lang/lang_*.json": "стаття компендіуму: blurb — короткий опис, details — детально; нарізано по рядках екрана (~45 символів), кожен ключ — свій рядок",
    "items/item_tooltips.json": "підказка предмета: короткі технічні рядки з числами; [квадратні дужки] навколо ключових слів зберігати",
    "themes/*/items/item_tooltips.json": "стан їжі у святкових темах — прикметник перед назвою",
    "data/achievements.json": "досягнення Steam: name — коротка назва (часто гра слів), description — умова",
    "data/callout_wheel.json": "колесо реплік у мультиплеєрі: text — пункт меню; msg_says — репліка в чаті, %s на початку — ім'я гравця, лапки зберігати",
    "data/follower_wheel.json": "колесо наказів супутникам — короткі команди",
    "data/charsheet.json": "аркуш персонажа: підказки характеристик і назви локацій",
    "data/class_descriptions.json": "опис класу на екрані створення персонажа — нарізано по рядках екрана, перший рядок — назва класу",
    "data/race_descriptions.json": "опис раси: left_align/right_align — дві колонки таблиці рис, рядки короткі",
    "data/compendium/events_text.json": "статистика в компендіумі: default — підпис рядка з двокрапкою, format — шаблон значення",
    "data/monster_data.json": "імена іменованих монстрів і NPC",
    "data/scripts/*/script.json": "табличка навчального випробування: рядки ~25 символів, $ — місце значка клавіші; message — повідомлення в журнал",
    "data/story/*.json": "сюжетна сцена між рівнями: оповідь у другій особі, урочисто; ## — паузи, ^ — зміна картинки, *2/*3 — розмір вікна",
    "data/tutorial_strings.json": "меню навчальних випробувань: title — назва, desc — опис",
    "data/HUD_settings.json": "випадні меню HUD — короткі пункти",
    "data/skillsheet_entries.json": "вікно навичок: name — навичка, description — опис, effects — рядки таблиці «назва: значення»",
    "data/status_effects.json": "ефект стану: name — коротка назва, desc — опис",
}
TXT_SECTION_CONTEXT = {
    "baron herx subtitles": "репліки Барона Геркса, головного антагоніста: пихатий, зловісний, глузливий",
    "shopkeeper chit-chat": "репліки крамаря під час торгівлі: старосвітська ввічливість («Thou hast…»)",
    "sharur lines": "репліки Шарура — розумної булави-артефакту: самовпевнений, саркастичний",
    "headstone messages": "епітафії на надгробках, часто іронічні",
    "tinned food": "написи на консервах — жарти й абсурдні назви страв",
    "item quality strings": "стан предмета: прикметник перед назвою предмета, коротко",
    "death tips": "поради на екрані смерті — наказовий спосіб, коротко",
    "obituary messages": "некролог: %s — ім'я гравця",
    "item names": "назви предметів — з малої літери, узгодити з lang/item_names.json",
}


def file_context(relpath: str) -> str:
    for pattern, text in FILE_CONTEXT.items():
        if fnmatch.fnmatchcase(relpath, pattern):
            return text
    return ""


# Навмисно не беремо: data/seed_names.json (слова для назв сідів — переклад зробить сіди
# несумісними з іншими гравцями), data/skillsheet_leadership_entries.json (внутрішні ключі
# монстрів), README.txt, EDITING.txt, data/story/Readme.txt (документація, гравець її в грі не бачить).


def game_files(game_dir: Path, patterns: list[str]) -> list[Path]:
    """Файли гри за списком glob-шаблонів, у порядку шаблонів."""
    out: list[Path] = []
    for pattern in patterns:
        out.extend(sorted(p for p in game_dir.glob(pattern) if p.is_file()))
    return out


def rel(path: Path, base: Path) -> str:
    return path.relative_to(base).as_posix()


def rules_for(relpath: str) -> list | None:
    for pattern, rules in JSON_FILES.items():
        if fnmatch.fnmatchcase(relpath, pattern):
            return rules
    return None


def read_text(path: Path) -> str:
    return path.read_bytes().decode("utf-8-sig")


# ---------------------------------------------------------------------------
# lang/en.txt

@dataclass
class TxtEntry:
    id: str
    sep: str    # " " або "\r\n" — що стоїть між id і текстом в оригіналі
    text: str   # без завершального «#»; переноси — як у файлі (\r\n)


def parse_txt(data: str) -> Iterator[TxtEntry]:
    """Записи з en.txt. Текст може займати кілька рядків і закінчується «#» в кінці рядка."""
    lines = data.split("\r\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.startswith("#"):
            i += 1
            continue
        m = re.match(r"^(\d+)( |$)(.*)$", line)
        if not m:
            raise ValueError(f"рядок {i + 1}: не схоже на запис: {line!r}")
        sid, sep, rest = m.group(1), m.group(2) or "\r\n", m.group(3)
        chunk = [rest] if m.group(2) else []
        while not (chunk and chunk[-1].endswith("#")):
            i += 1
            chunk.append(lines[i])
        yield TxtEntry(sid, sep, "\r\n".join(chunk)[:-1])
        i += 1


def render_txt(data: str, translations: dict[str, str]) -> tuple[str, int]:
    """Той самий en.txt, але з підставленими перекладами (id -> текст із \\n). Коментарі й порожні рядки як були."""
    lines = data.split("\r\n")
    out, i, n = [], 0, 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^(\d+)( |$)(.*)$", line)
        if not line.strip() or line.startswith("#") or not m:
            out.append(line)
            i += 1
            continue
        sid, sep, rest = m.group(1), m.group(2) or "\r\n", m.group(3)
        chunk = [rest] if m.group(2) else []
        while not (chunk and chunk[-1].endswith("#")):
            i += 1
            chunk.append(lines[i])
        text = "\r\n".join(chunk)[:-1]
        if sid in translations:
            text = translations[sid].replace("\n", "\r\n")
            n += 1
        out.append(f"{sid}{sep}{text}#")
        i += 1
    return "\r\n".join(out), n


# ---------------------------------------------------------------------------
# JSON зі збереженням дубльованих ключів (у файлах гри вони трапляються)


class Obj(list):
    """JSON-об'єкт як список пар (ключ, значення) — порядок і дублікати збережено."""

    def get(self, key, default=None):
        for k, v in self:
            if k == key:
                return v
        return default


def load_json(path: Path):
    return json.loads(read_text(path), object_pairs_hook=Obj)


def escape_seg(seg: str) -> str:
    return seg.replace("~", "~0").replace("/", "~1")


def walk_strings(node, path: tuple[str, ...] = ()) -> Iterator[tuple[tuple[str, ...], object, str]]:
    """(шлях, батько, рядок) для кожного рядка JSON: значень в об'єктах/списках і ключів словників.

    Шлях до ключа словника закінчується сегментом «@». Дубльовані ключі отримують
    суфікс #2, #3, … (сегмент «a#2» — друге входження ключа «a»).
    """
    if isinstance(node, Obj):
        seen: dict[str, int] = {}
        for k, v in node:
            seen[k] = seen.get(k, 0) + 1
            seg = escape_seg(k) + (f"#{seen[k]}" if seen[k] > 1 else "")
            yield path + (seg, "@"), node, k
            if isinstance(v, str):
                yield path + (seg,), node, v
            else:
                yield from walk_strings(v, path + (seg,))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            if isinstance(v, str):
                yield path + (str(i),), node, v
            else:
                yield from walk_strings(v, path + (str(i),))


def apply_json(node, translations: dict[str, str], path: tuple[str, ...] = ()) -> int:
    """Підставляє переклади (ключ як у walk_strings -> текст) у дерево JSON на місці. Повертає кількість замін."""
    n = 0
    if isinstance(node, Obj):
        seen: dict[str, int] = {}
        for i, (k, v) in enumerate(node):
            seen[k] = seen.get(k, 0) + 1
            seg = escape_seg(k) + (f"#{seen[k]}" if seen[k] > 1 else "")
            key_path = "/".join(path + (seg, "@"))
            if key_path in translations:
                k = translations[key_path]
                n += 1
            if isinstance(v, str):
                val_path = "/".join(path + (seg,))
                if val_path in translations:
                    v = translations[val_path]
                    n += 1
            else:
                n += apply_json(v, translations, path + (seg,))
            node[i] = (k, v)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            if isinstance(v, str):
                val_path = "/".join(path + (str(i),))
                if val_path in translations:
                    node[i] = translations[val_path]
                    n += 1
            else:
                n += apply_json(v, translations, path + (str(i),))
    return n


def dump_json(node, indent: int = 0) -> str:
    """JSON з Obj (пари, дублікати ключів збережено), відступ 4 пробіли, без екранування не-ASCII."""
    pad, inner = "    " * indent, "    " * (indent + 1)
    if isinstance(node, Obj):
        if not node:
            return "{}"
        items = [f"{inner}{json.dumps(k, ensure_ascii=False)}: {dump_json(v, indent + 1)}" for k, v in node]
        return "{\n" + ",\n".join(items) + f"\n{pad}}}"
    if isinstance(node, list):
        if not node:
            return "[]"
        if all(not isinstance(v, (Obj, list)) for v in node):
            return "[" + ", ".join(dump_json(v) for v in node) + "]"
        return "[\n" + ",\n".join(f"{inner}{dump_json(v, indent + 1)}" for v in node) + f"\n{pad}]"
    return json.dumps(node, ensure_ascii=False)


def dump_json_compact(node) -> str:
    """Те саме без пробілів і переносів — для білду, щоб уміститись у буфери гри (JSON_SIZE_LIMITS)."""
    if isinstance(node, Obj):
        return "{" + ",".join(f"{json.dumps(k, ensure_ascii=False)}:{dump_json_compact(v)}" for k, v in node) + "}"
    if isinstance(node, list):
        return "[" + ",".join(dump_json_compact(v) for v in node) + "]"
    return json.dumps(node, ensure_ascii=False)


def json_size_limit(file: str) -> int | None:
    """Ліміт розміру файлу в грі (байти) за JSON_SIZE_LIMITS; None — невідомий."""
    for pattern, limit in JSON_SIZE_LIMITS.items():
        if fnmatch.fnmatchcase(file, pattern):
            return limit
    return None


def match_path(path: tuple[str, ...], pattern: str) -> bool:
    """«*» і «**» не покривають сегмент «@» (ключ словника) — його треба вказати явно."""
    pat = pattern.split("/")

    def rec(i: int, j: int) -> bool:
        if j == len(pat):
            return i == len(path)
        if pat[j] == "**":
            return any(rec(k, j + 1) for k in range(i, len(path) + 1) if "@" not in path[i:k])
        if i < len(path) and (pat[j] == path[i] or (pat[j] == "*" and path[i] != "@")):
            return rec(i + 1, j + 1)
        return False

    return rec(0, 0)


def _matches(path, parent, rule) -> bool:
    pattern, when = rule if isinstance(rule, tuple) else (rule, None)
    return match_path(path, pattern.lstrip("!")) and (when is None or when(parent))


def translatable_strings(root, rules: list) -> Iterator[tuple[str, str]]:
    """(ключ, текст) для всіх рядків JSON, що підпадають під правила. Порожні рядки пропускаються."""
    for path, parent, value in walk_strings(root):
        if not value.strip():
            continue
        for rule in rules:
            if _matches(path, parent, rule):
                if not (rule if isinstance(rule, str) else rule[0]).startswith("!"):
                    yield "/".join(path), value
                break


def ignored_strings(root, rules: list) -> Iterator[str]:
    """Ключі рядків, що підпали під «!»-правила."""
    for path, parent, value in walk_strings(root):
        for rule in rules:
            if _matches(path, parent, rule):
                if (rule if isinstance(rule, str) else rule[0]).startswith("!"):
                    yield "/".join(path)
                break


def all_strings(root) -> Iterator[tuple[str, str]]:
    for path, _parent, value in walk_strings(root):
        if value.strip():
            yield "/".join(path), value


# ---------------------------------------------------------------------------
# translation/strings.tsv — один запис на рядок, поля через табуляцію.
# У полях перенос рядка, табуляція і зворотна скісна записуються як \n, \t, \\.

_ESCAPES = {"\\": "\\\\", "\n": "\\n", "\t": "\\t"}
_UNESCAPES = {"\\": "\\", "n": "\n", "t": "\t"}


def escape_field(s: str) -> str:
    return "".join(_ESCAPES.get(c, c) for c in s)


def unescape_field(s: str) -> str:
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s) and s[i + 1] in _UNESCAPES:
            out.append(_UNESCAPES[s[i + 1]])
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def read_strings_tsv(path: Path = STRINGS_TSV) -> list[list[str]]:
    """Рядки без заголовка: [file, key, original, translation, status, context, entities, tone]."""
    if not path.exists():
        return []
    rows = []
    for line in read_text(path).split("\n"):
        if not line or line.split("\t")[:4] == TSV_HEADER[:4]:
            continue
        fields = [unescape_field(f) for f in line.split("\t")]
        rows.append(fields + [""] * (len(TSV_HEADER) - len(fields)))
    return rows


def write_strings_tsv(rows: list[list[str]], path: Path = STRINGS_TSV) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["\t".join(TSV_HEADER)] + ["\t".join(escape_field(f) for f in row) for row in rows]
    path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
