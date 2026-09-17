# tools/

Python 3.11+, без сторонніх пакетів.

| Скрипт | Що робить |
|---|---|
| `barony.py` | спільний код: список файлів гри, які беремо (`TXT_FILES`, `JSON_FILES`, `FILES`), правила, які поля JSON перекладаються, парсер `en.txt`, читання/запис `strings.tsv` |
| `extract.py` | оновлює `translation/strings.tsv` (з колонкою `context`) і `translation/files/` із `source/`, зберігаючи наявні переклади; `--from-game` спершу копіює свіжі файли з гри в `source/`; `--unmatched` показує рядки JSON, що не підпали під жодне правило (перевірка після оновлення гри) |
| `build.py` | збирає мод у `build/uk-UA/`: `source/` з підставленими перекладами зі `strings.tsv` (лише файли, де є переклад), книги зі `strings.tsv` (`books/*.txt`, CRLF), перекладені файли з `translation/files/`, `assets/`; `--install` / `--uninstall` — покласти в `<гра>/mods/uk-UA/` або прибрати |
| `glossary.py` | перевіряє `translation/glossary.tsv` (унікальні `id`, статуси) і генерує з нього `GLOSSARY.md`; `--weblate out.csv` — експорт затверджених термінів у глосарій Weblate |
| `weblate.py` | міст із Weblate: `push` — TSV → PO-файли в гілку `weblate`, `pull` — переклади з PO назад у `strings.tsv` і `glossary.tsv`; `export DIR` — лише записати PO без git |
| `validate.py` | перевіряє плейсхолдери в перекладах `strings.tsv`: printf (`%s`, `%d`, `%+d%%`… — той самий набір у тому ж порядку), кількість `$`, у сюжеті `^` і `*N`, відсутність `#` у `*.txt`; код виходу 1 при помилках |

```bash
python tools/extract.py --from-game     # після оновлення гри: оновити source/ і strings.tsv
python tools/extract.py --unmatched     # чи не з'явилося в JSON нових текстових полів
python tools/validate.py                # перед PR: плейсхолдери в перекладах
python tools/build.py --install         # зібрати мод і поставити в гру (увімкнути: Custom Content -> Local Mods)
python tools/weblate.py push            # після змін у main: оновити гілку weblate
python tools/weblate.py pull            # забрати переклади з Weblate у strings.tsv, переглянути diff, закомітити
```

Тека гри типово `C:\Program Files (x86)\Steam\steamapps\common\Barony`; інша — через `--game`.

## Формат strings.tsv

Один запис на рядок, поля через табуляцію, без лапок. Перенос рядка всередині тексту записується як `\n`, табуляція — `\t`, зворотна скісна — `\\`. Відкривається будь-яким табличним або текстовим редактором.

| Колонка | Зміст |
|---|---|
| `file` | шлях файлу в грі (`lang/en.txt`, `data/achievements.json`, …) |
| `key` | для `en.txt` — числовий id; для JSON — шлях до поля через `/` (`achievements/BARONY_ACH_BONK/name`, `text/3`); `/@` наприкінці — перекладається ключ словника, а не значення |
| `original` | оригінальний текст |
| `translation` | переклад; порожньо — у грі лишиться оригінал |
| `status` | порожньо — готовий переклад; будь-що інше — чернетка, у мод не потрапляє, у Weblate — needs editing. `fuzzy` — не вичитано (у Weblate «needs editing»); `unresolved` — у рядку є термін без затвердженого перекладу в глосарії |
| `entities` | `id` термінів із `glossary.tsv`, що трапляються в рядку, через `\|` (`-` — термінів нема); у Weblate — у коментарі як «сутності: термін → переклад» |
| `tone` | характер рядка через `\|` (`joke`, `threat`, `command`, `solemn`…; `-` — нейтрально) — підказка перекладачу, у Weblate — у коментарі |
| `context` | опис рядка для перекладача: для `en.txt` — коментар розділу з файлу гри (або уточнення з `TXT_SECTION_CONTEXT`), для JSON — опис файлу з `FILE_CONTEXT` у `barony.py`. Заповнюється для нових рядків, можна правити руками; `extract.py --refresh-context` перегенерує все. У Weblate — коментар під оригіналом |

## Weblate

Джерело правди — `strings.tsv` у `main`. Weblate працює з гілкою **`weblate`**, у якій лежать лише PO-файли: `po/uk-UA/<файл гри>.po` — один компонент на файл гри (дрібні файли `data/story/*` і `data/scripts/*` зібрано в один компонент кожні, див. `GROUPS` у `weblate.py`) плюс `po/uk-UA/glossary.po`. `weblate.py` тримає робочу копію цієї гілки в `build/weblate` (git worktree).

Цикл роботи:

1. Зміни в `main` (оновлення гри, правки TSV руками, глосарій) → `python tools/weblate.py push`. Weblate підтягне гілку сам (webhook або періодично).
2. Перекладачі працюють у Weblate; Weblate комітить у гілку `weblate`.
3. `python tools/weblate.py pull` → переклади потрапляють у `strings.tsv`/`glossary.tsv`. Переглянь diff, закоміть у `main` (PR). Рядки «needs editing» (fuzzy) не імпортуються; рядки, чий оригінал у `main` уже змінився після останнього push, теж — спершу зроби `push`.

Налаштування компонента у Weblate (Docker, self-hosted):

| Поле | Значення |
|---|---|
| Repository | URL цього репозиторію (для запису — SSH-ключ Weblate у Deploy keys з правом write) |
| Repository branch / Push branch | `weblate` |
| File mask | `po/*/lang/en.txt.po` (`*` — код мови; для кожного компонента — свій файл гри) |
| File format | gettext PO (bilingual, без шаблону) |
| Source language / Language | English / Ukrainian |
| Glossary | компонент із file mask `po/*/glossary.po`, прапорець «Use as a glossary» |

Weblate сам покаже терміни глосарію під кожним рядком і перевірить плейсхолдери `%s`/`%d` (перевірка «Formatted strings» — C-format).
