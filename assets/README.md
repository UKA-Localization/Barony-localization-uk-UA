# assets/

Ресурси, потрібні для локалізації, окрім самого тексту.

**Правило: шлях у репо = шлях у грі.** `assets/` — це оверлей теки гри: файл лежить тут за тим самим відносним шляхом, куди він має потрапити при встановленні (`assets/fonts/pixelmix.ttf` → `<тека гри>/fonts/pixelmix.ttf`). `build.py` кладе `assets/**` у мод разом із перекладеними текстами (`mods/<назва>/fonts/pixelmix.ttf`), гра накладає файли мода поверх своїх — оригінали не змінюються. Жодних таблиць «що куди» у скриптах.

## fonts/

Покриття перевіряється за `translation/strings.tsv` (разом із чернетками,
для порожніх перекладів — оригінал) та `translation/files/*.txt`.
Додано відсутні `« » – — № ~` і комбінований наголос U+0301;
порожні гліфи лапок/тире також враховано. Наявні непорожні гліфи,
їхні метрики та міжрядкові інтервали збережені. Наголос має нульову
ширину й OpenType-позиціювання над літерою, перевірене на «Ви́кувати».
Відображення у самій грі ще потребує перевірки її текстовим рушієм.

Скрипти доповнення й перевірки описані у [tools/README.md](../tools/README.md).

Шрифти гри, доповнені кириличними гліфами для української. Оригінали — з `fonts/` гри (Barony v4.x); нові гліфи намальовано в стилі кожного шрифту.

| Файл | Гарнітура | Автор | Ліцензія оригіналу |
|---|---|---|---|
| `alphbeta.ttf` | Alpha Beta BRK | Brian Kent (ÆNIGMA Fonts) | freeware |
| `kongtext.ttf` | Kongtext | codeman38 | free (див. readme автора) |
| `pixel_maz.ttf`, `pixel_maz_large.ttf`, `pixel_maz_multiline.ttf`, `PixelMaz_monospace.ttf` | Pixel Maz | allthatmaz (FontStruct) | [CC BY-NC 3.0](http://creativecommons.org/licenses/by-nc/3.0/) |
| `pixelmix.ttf` | pixelmix | Andrew Tyler | [CC BY-NC-ND 3.0](http://creativecommons.org/licenses/by-nc-nd/3.0/us/) |
| `pixelmix_bold.ttf` | pixelmix bold | FontStruct | [CC BY-SA 3.0](http://creativecommons.org/licenses/by-sa/3.0/) |
| `scream.ttf` | Scream When You're Ready To Die | Andrew McCluskey (FontStruct) | [CC BY-SA 3.0](http://creativecommons.org/licenses/by-sa/3.0/) |

Модифіковані шрифти поширюються на умовах ліцензій оригіналів; на них не поширюється ліцензія перекладу з [LICENSE.md](../LICENSE.md).
