# Публікація

Матеріали для сторінок мода поза GitHub. У гру потрапляє лише `preview.png` (build.py копіює його в корінь мода —
Barony показує його в списку модів і бере як обкладинку при заливанні у Workshop).

| Файл | Куди |
|---|---|
| `preview.png` | 512×512, PNG. Зараз — **заглушка**, замінити на справжнє прев'ю. |
| `steam/description.uk.bbcode`, `steam/description.en.bbcode` | Опис сторінки Workshop українською та англійською у форматі Steam (BBCode) — вставляти як є. |
| `steam/meta.md` | Назва, теги, id предмета Workshop, нотатки до оновлень. |
| `github-release.md` | Шаблон нотаток до релізу на GitHub. |
| `kuli.md` | Картка для КУЛІ (Каталог української локалізації, kuli.com.ua): поля форми, опис, короткий опис. |
| `screenshots/` | Скриншоти для Workshop і README (PNG, 1920×1080). |

## Steam Workshop

Barony заливає моди сама: головне меню → **Custom Content** → **Upload** → тека `mods/Barony Ukrainian Localization` → назва, опис, теги
з `steam/` → **Upload**. Оновлення — там само, **Update**; опис при оновленні не перезаписується,
тож після зміни `steam/description.*.bbcode` його треба оновити на сторінці Workshop вручну.

Перед заливанням зібрати мод з `main` без чернеток: `python tools/build.py --install`.

## GitHub Releases

Тег `<версія-гри>-<номер>` (напр. `5.0.2-1`), архів `Barony-uk-UA-<тег>.zip` з текою `uk-UA/` усередині,
нотатки — за `github-release.md` (розділ із `CHANGELOG.md`).
