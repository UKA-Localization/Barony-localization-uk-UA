# Changelog

Формат — [Keep a Changelog](https://keepachangelog.com/uk/1.1.0/). Версії локалізації — `<версія-гри>-<номер-релізу>`, напр. `5.0.2-1`.

## [Unreleased]

### Added
- Скелет репозиторію.
- Тека `assets/` — оверлей теки гри (шлях у репо = шлях у грі).
- Шрифти гри з кириличними гліфами (`assets/fonts/`, 9 файлів).
- Оригінальні тексти гри v5.0.2 (`source/`, 104 файли), `translation/strings.tsv` (19 171 рядок) і `translation/files/` (38 файлів: книги, списки імен).
- `tools/extract.py` — витягування рядків із файлів гри зі збереженням наявних перекладів.
- `translation/glossary.tsv` як джерело глосарію і `tools/glossary.py`, що генерує з нього `GLOSSARY.md` та експорт для Weblate.
- `tools/weblate.py` — синхронізація `strings.tsv` ⇄ PO-файли в гілці `weblate` для Weblate (компонент на файл гри + глосарій).
- `tools/build.py` — збірка мода `build/uk-UA/` та встановлення в `mods/` гри.
- `tools/validate.py` — перевірка плейсхолдерів у перекладах.
- CI (GitHub Actions): глосарій, плейсхолдери, актуальність `translation/`, збірка мода.
- Колонки `status` (непорожній — чернетка: не в мод, у Weblate — needs editing), `context` (опис рядка), `entities` (терміни глосарію в рядку) і `tone` (характер рядка) у `strings.tsv`; у `glossary.tsv` — `id` і `status`.
- `translation/STYLE.md` — правила стилю; `translation/pipeline.toml` — технічний опис файлів проєкту.
