"""Английские строки интерфейса и сообщений (дополнение к i18n.EN).

Ключи — русский текст без крайних пробелов. Целые строки ищутся точно, а в составных
сообщениях (f-строках) фразы заменяются по отдельности.
"""

EN2 = {
    # ---------------------------------------------------------------- мастерская
    "Transmutation: обычный → магический (1–2 мода)": "Transmutation: normal → magic (1–2 mods)",
    "Alteration: перекатить магический предмет": "Alteration: reroll a magic item",
    "Augmentation: добавить мод магическому предмету": "Augmentation: add a mod to a magic item",
    "Regal: магический → редкий, +1 мод": "Regal: magic → rare, +1 mod",
    "Alchemy: обычный → редкий (4–6 модов)": "Alchemy: normal → rare (4–6 mods)",
    "Chaos: перекатить редкий предмет полностью": "Chaos: fully reroll a rare item",
    "Exalted: добавить случайный мод редкому предмету": "Exalted: add a random mod to a rare item",
    "Annulment: убрать случайный мод": "Annulment: remove a random mod",
    "Scouring: убрать все моды (кроме фрактуров)": "Scouring: remove all mods (except fractured)",
    "Divine: перекатить значения модов внутри их тиров": "Divine: reroll mod values within their tiers",
    "PoE Craft Helper — мастерская": "PoE Craft Helper — workshop",
    "Цели": "Goals", "Методы": "Methods", "Трейд": "Trade", "Сохранить как крафт": "Save as craft",
    "Сравнение методов": "Method comparison",
    "Отметь нужные моды во вкладке «Пул модов» и нажми «Посчитать» — здесь появятся все способы с ценой, "
    "шансом и расходом валюты, самый дешёвый — первым.":
        "Mark the wanted mods in «Mod pool» and press «Calculate» — every method shows up here with its cost, "
        "chance and currency use, cheapest first.",
    "Фоссилы — до 4": "Fossils — up to 4", "Как сдвинулись шансы": "How the odds shifted",
    "Цена крафта": "Craft cost",
    "Выбери эссенцию или фоссилы и нажми «Посчитать выбранное».":
        "Pick an essence or fossils and press «Calculate selection».",
    "Журнал крафта": "Craft log", "▶ Крутить до цели": "▶ Spam until goal",
    "Awakener's Orb — второе влияние": "Awakener's Orb — second influence",
    "случайный мод этого влияния": "random mod of this influence",
    "Аспекты духов-зверей (крафтовый суффикс)": "Beast aspects (crafted suffix)",
    "Из игры:": "From game:", "· осквернён (в игре валюта уже не сработает)": "· corrupted (currency won't work in game)",
    "Unveil у Jun": "Unveil at Jun", "Снять крафты верстака": "Remove bench crafts",
    "Harvest: те же моды": "Harvest: same mods", "Harvest +мод/−мод": "Harvest +mod/−mod",
    "Отпечаток (Craicic Chimeral)": "Imprint (Craicic Chimeral)", "Восстановить отпечаток": "Restore imprint",
    "обычный": "normal", "магический": "magic", "редкий": "rare", "уникальный": "unique",
    "Шаблоны": "Templates", "Шаги рецепта": "Recipe steps", "Шаг": "Step", "если": "if", "сделать": "do",
    "параметр": "parameter", "повторять, пока": "repeat until", "не больше раз": "at most times", "иначе": "else",
    "Прогон рецепта": "Recipe run",
    "Собери рецепт из шагов слева или возьми шаблон. Цели — моды, отмеченные в «Пуле модов». Прогон стартует с "
    "предмета в эмуляторе (или с белой базы) и повторяет весь путь много раз: видно шанс успеха, среднюю цену и "
    "сколько раз срабатывает каждый шаг.\n\nРецепт сохраняется вместе с крафтом («Калькулятор» → «Сохранить как "
    "крафт»).":
        "Build a recipe from steps on the left or take a template. Goals are the mods marked in «Mod pool». The run "
        "starts from the emulator item (or a white base) and repeats the whole path many times: you see the success "
        "rate, the average cost and how often each step fires.\n\nThe recipe is saved with the craft "
        "(«Calculator» → «Save as craft»).",
    "Рецепт дошёл до цели ✓": "Recipe reached the goal ✓", "Рецепт не дошёл до цели": "Recipe did not reach the goal",
    "Предмет": "Item", "Нужно": "Need", "красных": "red", "зелёных": "green", "синих": "blue",
    "Способы покраски": "Coloring methods",
    "Введи требования атрибутов предмета (или «взять требования базы»), число сокетов и сколько нужно "
    "красных/зелёных/синих.":
        "Enter the item's attribute requirements (or «use base requirements»), the socket count and how many "
        "red/green/blue you need.",
    "Рецепты": "Recipes", "групп модов": "mod groups", "вес префиксов": "prefix weight",
    "вес суффиксов": "suffix weight", "нужных модов": "wanted mods", "заблокировано": "blocked",
    "☐ — нужен мод · «до T» — худший тир · двойной клик — тиры\nправый клик — заблокировать мод (уйдёт из пула и шансов)":
        "☐ — wanted mod · «≤T» — worst tier · double click — tiers\nright click — block a mod (removed from pool and odds)",
    "Выбор изменился — нажми «Посчитать выбранное».": "Selection changed — press «Calculate selection».",
    "Эссенция:": "Essence:", "ничего не выбрано — клик по иконке": "nothing selected — click an icon",
    "Выбери базу сверху.": "Pick a base above.",
    "Кликни по эссенции или фоссилам слева — здесь будет видно, как меняются шансы нужных модов (отмечаются ☐ в "
    "«Пуле модов») и всего пула.":
        "Click an essence or fossils on the left — this shows how the odds of the wanted mods (marked ☐ in "
        "«Mod pool») and of the whole pool change.",
    "ЧАЩЕ": "MORE OFTEN", "РЕЖЕ": "LESS OFTEN", "ПРОПАЛИ ИЗ ПУЛА": "GONE FROM POOL",
    "Эссенции": "Essences", "Фоссилы": "Fossils", "Влияние": "Influence", "Звери": "Beasts", "Качество": "Quality",
    "не выбран — кликни по валюте справа": "none — click a currency on the right",
    "Клик по предмету или «Применить» — кинуть выбранное. Двойной клик по валюте — кинуть сразу.":
        "Click the item or «Apply» to use the selection. Double click a currency to use it at once.",
    "■ Стоп": "■ Stop",
    "Farric Wolf Alpha: +префикс, −суффикс": "Farric Wolf Alpha: +prefix, −suffix",
    "Farric Lynx Alpha: +суффикс, −префикс": "Farric Lynx Alpha: +suffix, −prefix",
    "Fenumal Arachnid: расколоть (Split)": "Fenumal Arachnid: split",
    "Craicic Maw: +мод влияния": "Craicic Maw: +influence mod",
    "Craicic Chimeral: отпечаток (magic)": "Craicic Chimeral: imprint (magic)",
    "Восстановить из отпечатка": "Restore from imprint", "· не распознано модов:": "· mods not recognized:",
    "крафт": "craft",
    "Пока пусто — примени валюту, и здесь будет видно, что она добавила, убрала или перекатила.":
        "Empty for now — use a currency and you'll see what it added, removed or rerolled.",
    "+ добавить": "+ add", "✎ заменить": "✎ replace", "× удалить": "× delete", "дальше": "next", "стоп": "stop",
    "Сила (Str)": "Strength (Str)", "Ловкость (Dex)": "Dexterity (Dex)", "Интеллект (Int)": "Intelligence (Int)",
    "Сокетов 1–6, а нужных цветов — от 1 до числа сокетов.": "Sockets 1–6, wanted colors from 1 to the socket count.",
    "Так не получится.": "That won't work.",
    "считаю… (Chaos-симуляция может занять несколько секунд)": "calculating… (Chaos simulation may take a few seconds)",
    "Для такого набора модов пока нет подходящих методов.": "No suitable methods for this set of mods yet.",
    "Готовлю поиск на трейде…": "Preparing the trade search…",
    "ПРЕФИКСЫ": "PREFIXES", "СУФФИКСЫ": "SUFFIXES", "вес": "weight",
    "⌕ купить базу": "⌕ buy base", "⌕ готовый предмет": "⌕ finished item", "скопировать код": "copy code",
    "сброс": "reset", "(лучший тир T": "(best tier T", "Фоссилы:": "Fossils:", "гарантирован": "guaranteed",
    "Сначала выбери базу и отметь нужные моды в «Пуле модов».": "Pick a base and mark the wanted mods in «Mod pool» first.",
    "Выбери эссенцию или фоссилы.": "Pick an essence or fossils.",
    "⇩ Предмет из игры": "⇩ Item from game", "↶ шаг назад": "↶ step back", "⟲ к началу": "⟲ to start",
    "⌕ такой на трейде": "⌕ this on trade", "▦ Прогнать": "▦ Run",
    "Сначала реши: оставить результат Hinekora's Lock или отказаться.":
        "Decide first: keep the Hinekora's Lock result or discard it.",
    "Сначала выбери метод — кликни по валюте, эссенции или фоссилам.":
        "Pick a method first — click a currency, essence or fossils.",
    "✗ отказаться": "✗ discard", "✓ оставить": "✓ keep",
    "Нужны предмет и выбранный метод (например Chaos или эссенция).":
        "Needs an item and a selected method (e.g. Chaos or an essence).",
    "Отметь нужные моды во вкладке «Пул модов» — иначе не понять, когда остановиться.":
        "Mark the wanted mods in «Mod pool» — otherwise there's no way to know when to stop.",
    "Цель уже выполнена.": "Goal already met.", "Автокрутка:": "Auto-spam:",
    "Нужны предмет, выбранный метод и отмеченные нужные моды.": "Needs an item, a selected method and marked wanted mods.",
    "Цель на предмете уже выполнена — откатись (⟲ к началу) или возьми новый предмет, тогда прогон покажет, сколько "
    "стоит дойти до цели.":
        "The item already meets the goal — rewind (⟲ to start) or take a new item, then the run shows what reaching "
        "the goal costs.",
    "Клик по иконке — лучший доступный тир этой эссенции. Нужен другой тир — выбери в списке.":
        "Click an icon for the best available tier of that essence. For another tier pick it in the list.",
    "Выбери до 4 фоссилов (клик — выбрать/снять), затем «Применить». Резонатор подберётся сам.":
        "Pick up to 4 fossils (click to toggle), then «Apply». The resonator is chosen automatically.",
    "Exalt завоевателя добавляет мод своего влияния и делает предмет влиятельным. Shaper и Elder выбираются в поле "
    "«влияние» сверху.":
        "A conqueror exalt adds a mod of its influence and makes the item influenced. Shaper and Elder are picked in "
        "the «influence» field above.",
    "Уничтожает второй предмет с другим влиянием. Этот предмет станет редким с двумя влияниями: по одному моду "
    "влияния от каждого, остальное — случайно.":
        "Destroys a second item with another influence. This item becomes rare with two influences: one influence mod "
        "from each, the rest random.",
    "Звериные крафты Менажери. Прочие рецепты (уники, валюта) на крафт модов не влияют.":
        "Menagerie beast crafts. Other recipes (uniques, currency) don't affect mod crafting.",
    "Vaal Orb оскверняет предмет: ничего / Vaal-имплицит / перекат в редкий / сокеты — по 25%. После этого работают "
    "только Tainted-валюта и верстак.":
        "Vaal Orb corrupts the item: nothing / Vaal implicit / reroll to rare / sockets — 25% each. After that only "
        "Tainted currency and the bench work.",
    "Осквернить предмет": "Corrupt item", "50%: перекат редкого, 50%: снять все моды": "50%: reroll rare, 50%: remove all mods",
    "Добавляет или снимает мод (50/50)": "Adds or removes a mod (50/50)", "Тир каждого мода ±1": "Each mod tier ±1",
    "Катализаторы (кольца, амулеты, пояса): качество до 20% усиливает моды своего тега и повышает их шанс выпасть на "
    "столько же процентов. Обычный предмет +5%, магический +2%, редкий +1% за катализатор.":
        "Catalysts (rings, amulets, belts): up to 20% quality boosts mods of their tag and raises their roll chance by "
        "the same percent. Normal item +5%, magic +2%, rare +1% per catalyst.",
    "Ember — имплицит Searing Exarch, Ichor — Eater of Worlds (только броня: шлем, перчатки, ботинки, нагрудник). "
    "Chaos/Exalt/Annul действуют на сторону доминирующего.":
        "Ember is the Searing Exarch implicit, Ichor the Eater of Worlds (armour only: helmet, gloves, boots, body). "
        "Chaos/Exalt/Annul act on the dominant side.",
    "Reforge — перекат с гарантированным модом выбранного тега. «+мод/−мод» — добавить мод тега, убрав другой.":
        "Reforge rerolls with a guaranteed mod of the chosen tag. «+mod/−mod» adds a mod of the tag, removing another.",
    "+мод / −мод": "+mod / −mod", "те же моды ↑": "same mods ↑", "те же моды ↓": "same mods ↓",
    "Veiled Chaos/Exalt дают скрытый мод, у Jun можно выбрать 1 из 3 вариантов.":
        "Veiled Chaos/Exalt give a veiled mod; at Jun you pick 1 of 3 options.",
    "★ — метакрафты. Двойной клик по строке — скрафтить.": "★ — metacrafts. Double click a row to craft.",
    "снять крафты": "remove crafts", "Скрафтить": "Craft", "Сначала выбери базу сверху.": "Pick a base above first.",
    "В буфере нет предмета — наведи на него в игре и нажми Ctrl+Alt+C.":
        "No item in the clipboard — hover it in game and press Ctrl+Alt+C.",
    "Сначала нажми «Новый белый предмет».": "Press «New white item» first.",
    "Выбери эссенцию в списке.": "Pick an essence in the list.",
    "Выбери фоссилы — клик по иконкам на вкладке «Фоссилы».": "Pick fossils — click the icons on the «Fossils» tab.",
    "Выбери крафт верстака в списке.": "Pick a bench craft in the list.", "Верстак:": "Bench:", "скрыт": "veiled",
    "предмет осквернён": "item is corrupted", "ничего не изменилось": "nothing changed",
    "Вернулся к началу.": "Back to start.", "▶ один раз в эмуляторе": "▶ once in emulator",
    "Выбери эссенцию.": "Pick an essence.", "В рецепте нет шагов.": "The recipe has no steps.",
    "Отметь нужные моды во вкладке «Пул модов».": "Mark the wanted mods in «Mod pool».",
    "Рецепт:": "Recipe:", "нет успехов": "no successes", "в среднем на попытку ≈": "average per try ≈",
    "действий": "actions", "успех": "success", "из": "of",
    "рецепт ни разу не довёл предмет до цели — проверь шаги": "the recipe never reached the goal — check the steps",
    "Формула — как в калькуляторе Siveran. Число сокетов и связи надёжнее делать верстаком: 6 сокетов — 350 "
    "Jeweller's, 6 связей — 1500 Fusing.":
        "Formula as in Siveran's calculator. Socket count and links are safer on the bench: 6 sockets — 350 "
        "Jeweller's, 6 links — 1500 Fusing.",
    "Нужны целые числа.": "Whole numbers needed.", "База сменилась — нажми «Новый белый предмет».":
        "Base changed — press «New white item».",
    "Блокировки сняты.": "Blocks cleared.", "цены:": "prices:", "Открыл трейд в браузере.": "Opened trade in the browser.",
    "Сначала выбери базу.": "Pick a base first.",
    "Не удалось загрузить список модов трейда — открыл поиск только базы.":
        "Couldn't load the trade mod list — opened a base-only search.",
    "Отметь нужные моды в «Пуле модов».": "Mark the wanted mods in «Mod pool».",
    "В эмуляторе нет модов.": "The emulator item has no mods.",
    "Сначала выбери базу и нужные моды.": "Pick a base and wanted mods first.", "Введи название крафта.": "Enter a craft name.",
    "Сохранено: goals/": "Saved: goals/", "— уже есть в списке оверлея.": "— already in the overlay list.",
    "Код скопирован.": "Code copied.", "Всегда: Alt+Aug, Alt→Regal, Chaos": "Always: Alt+Aug, Alt→Regal, Chaos",
    "Откроет официальный трейд в браузере: белая база этого ilvl или уже готовый предмет с нужными модами — сравни с "
    "ценой крафта.":
        "Opens the official trade site: a white base of this ilvl or a finished item with the wanted mods — compare "
        "with the craft cost.",
    "Максимум 4 фоссила (резонатор Prime).": "At most 4 fossils (Prime resonator).",
    "клик по шагу — откат": "click a step to rewind", "МЕТОД": "METHOD", "предметов:": "items:",
    "Hinekora's Lock: предмет показан так, как выйдет. Оставить результат?":
        "Hinekora's Lock: the item is shown as it will turn out. Keep the result?",
    "Отказался — валюта не потрачена, Lock израсходован.": "Discarded — currency not spent, Lock used up.",
    "Результат оставлен.": "Result kept.", "Прогоняю:": "Running:", "предметов…": "items…",
    "Максимум 4 фоссила.": "At most 4 fossils.",
    "Выбери влияние и мод уничтожаемого предмета (или «случайный»)":
        "Pick the influence and mod of the sacrificed item (or «random»)",
    "Maven's Orb: снимает случайный мод влияния и возвышает другой (нужно ≥2)":
        "Maven's Orb: removes a random influence mod and elevates another (needs ≥2)",
    "Звериный крафт: добавляет мод влияния предмета": "Beast craft: adds an influence mod of the item",
    "тег": "tag", "поиск": "search", "Не нашёл базу «": "Base not found «", "Выбери мод:": "Pick a mod:",
    "отпечаток сохранён": "imprint saved", "восстановлено из отпечатка": "restored from imprint",
    "Вернулся к шагу": "Back to step",
    "«если» — шаг выполняется только при условии; «повторять, пока» — кидать, пока условие не выполнится. Не вышло → "
    "«иначе»: дальше, стоп (неудача) или вернуться к шагу.":
        "«if» — the step runs only when the condition holds; «repeat until» — keep using it until the condition is "
        "met. Failed → «else»: next, stop (failure) or jump to a step.",
    "Префиксы нельзя менять": "Prefixes cannot be changed", "Суффиксы нельзя менять": "Suffixes cannot be changed",
    "Нельзя моды атаки": "No attack mods", "Нельзя моды заклинаний": "No caster mods", "До 3 крафтов": "Up to 3 crafts",
    "(выбери ещё, до 4; «очистить» в списке шагов — сброс)": "(pick more, up to 4; «clear» in the step list resets)",
    "Выбери хотя бы один фоссил.": "Pick at least one fossil.", "к шагу": "to step", "Шаблон «": "Template «",
    "». Выбери параметр в шаге": "». Pick the parameter in step",
    "(выдели шаг → параметр → «заменить»).": "(select the step → parameter → «replace»).",
    "» — можно прогнать.": "» — ready to run.", "Ошибка:": "Error:", "Готово:": "Done:", "предметов": "items",
    "(упёрлись во время)": "(hit the time limit)",
    "СКОЛЬКО РАЗ СРАБАТЫВАЕТ ШАГ (в среднем на предмет)": "HOW OFTEN EACH STEP FIRES (average per item)",
    "белые сокеты (3.29: ниже ilvl — больше белых)": "white sockets (3.29: lower ilvl — more white)",
    "шанс": "chance", "· в среднем ~": "· on average ~", "попыток · ~": "tries · ~",
    "Заблокировано модов:": "Blocked mods:",
    "— они не выпадают в эмуляторе и не учитываются в шансах. Правый клик ещё раз — разблокировать.":
        "— they don't roll in the emulator and aren't counted in odds. Right click again to unblock.",
    "— добавь вручную.": "— add it manually.", "выбери базу сверху": "pick a base above",
    "НУЖНЫЕ МОДЫ — шанс среди своего типа": "WANTED MODS — chance within their type",
    "Ошибка расчёта": "Calculation error", "Симуляция остановлена:": "Simulation stopped:",
    "Кручу… попыток": "Spamming… tries", "· потрачено ≈": "· spent ≈", "цель достигнута": "goal reached",
    "остановлено вручную": "stopped manually", "Этот метод не работает на таком предмете.": "This method doesn't work on this item.",
    "предметов: в среднем": "items: on average", "попыток (медиана": "tries (median", ", 90% — до": ", 90% — up to",
    "div) за предмет": "div) per item", "Не понял предмет:": "Couldn't read the item:", "влияние": "influence",
    "качество": "quality",
    "Отметь нужные моды во вкладке «Пул модов» (☐) — здесь появятся шансы следующего Exalt'а и что ещё не хватает.":
        "Mark the wanted mods in «Mod pool» (☐) — the odds of the next Exalt and what's still missing show up here.",
    "Создай предмет, чтобы увидеть шансы.": "Create an item to see the odds.", "фоссилы:": "fossils:",
    "Выбери крафт верстака.": "Pick a bench craft.", "Прогоняю": "Running", "шагов": "steps",
    "». Выбери из списка.": "». Pick from the list.", "· влияние": "· influence", "(◆ — его моды)": "(◆ — its mods)",
    "ничего не выбрано — клик по ☐ во вкладке «Пул модов»": "nothing selected — click ☐ in «Mod pool»",
    "Не нашёл на трейде:": "Not found on trade:", "тир:": "tier:", "Гарантирован:": "Guaranteed:",
    "Готово за": "Done in", "попыток · ≈": "tries · ≈", "Остановлено после": "Stopped after",
    "не дошли за": "didn't make it in", ": добавляет мод влияния": ": adds an influence mod", ": теги": ": tags",
    "Шанс цвета одного сокета:  R": "Color chance of one socket:  R", "блок": "block", "попыток": "tries",
    "Прогоняю…": "Running…", "белый": "white",
    # ---------------------------------------------------------------- хаб
    "Выход": "Quit", "Свернуть (оверлей продолжит работать)": "Minimize (overlay keeps running)",
    "Активная цель": "Active goal", "Недавние предметы": "Recent items",
    "Двойной клик — сделать крафт активным. Код для друзей — «Поделиться».":
        "Double click makes a craft active. A code for friends — «Share».",
    "Крафт удалён.": "Craft deleted.", "Хаб свёрнут.": "Hub minimized.", "любой класс": "any class", "Любой": "Any",
    "Сначала выбери крафт в списке.": "Pick a craft in the list first.",
    "Нажми ещё раз, чтобы удалить файл крафта.": "Press again to delete the craft file.", "Код «": "Code «",
    "» скопирован — вставь его в Discord или Telegram.": "» copied — paste it into Discord or Telegram.",
    "от": "by", "Добавлен и выбран крафт «": "Added and selected craft «", "Хаб свёрнут. Вернуть:": "Hub minimized. Bring back:",
    "⬆  Доступна версия": "⬆  Version available", "— нажми, чтобы открыть страницу загрузки": "— click to open the download page",
    "автор:": "author:", "данные": "data", "Активная цель:": "Active goal:", "Точно удалить?": "Delete for sure?",
    "оверлей": "overlay", "хаб": "hub", "Не удалось удалить:": "Couldn't delete:",
    "Скопируй код PCH1:… и нажми ещё раз.": "Copy a PCH1:… code and press again.",
    "В игре наведи на предмет и нажми": "In game hover an item and press",
    "— оверлей покажет следующий шаг.": "— the overlay shows the next step.", "Моды:": "Mods:",
    # ---------------------------------------------------------------- карточка предмета
    "Выбери базу сверху и нажми «Новый белый предмет»\nили «Предмет из игры».":
        "Pick a base above and press «New white item»\nor «Item from game».",
    "·  префиксы": "·  prefixes", "·  суффиксы": "·  suffixes", "Exalt с блоком слота": "Exalt with slot block",
    "Редкий предмет": "Rare item", "(фрактур)": "(fractured)", "· диапазон": "· range", "· ролл": "· roll",
    "Магический": "Magic", "есть отпечаток": "has imprint", "Осквернён": "Corrupted", "Качество": "Quality",
    "убран": "removed", "ИСТОРИЯ  ·  клик по шагу — вернуться к нему": "HISTORY  ·  click a step to go back to it",
    "Потрачено:": "Spent:", "не хватает:": "missing:", "модов нет": "no mods", "нужных модов": "wanted mods",
    "— всё на месте!": "— all there!", "— клик, чтобы откатиться сюда": "— click to rewind here",
    "ДЕШЕВЛЕ ВСЕГО": "CHEAPEST",
    # ---------------------------------------------------------------- настройки
    "Оверлей": "Overlay", "Цены": "Prices", "Данные игры": "Game data",
    "Показать / спрятать стартовое окно (хаб)": "Show / hide the start window (hub)",
    "Предмет под курсором → в эмулятор": "Item under cursor → emulator",
    "Настройки — PoE Craft Helper": "Settings — PoE Craft Helper",
    "Кликни по полю и нажми сочетание. Backspace — сбросить.": "Click a field and press a combo. Backspace clears it.",
    "Буфер обмена": "Clipboard",
    "Предмет в игре копируется сочетанием Ctrl+Alt+C — его задаёт сама игра. Программа ловит копирование автоматически.":
        "In game an item is copied with Ctrl+Alt+C — the game defines it. The app catches the copy automatically.",
    "Предмет → эмулятор": "Item → emulator",
    "По горячей клавише самой копировать предмет под курсором (одно нажатие Ctrl+Alt+C)":
        "On the hotkey, copy the item under the cursor itself (one Ctrl+Alt+C press)",
    "Наведи мышь на предмет в игре и нажми сочетание «Предмет под курсором → в эмулятор» — мастерская откроется с этим "
    "предметом. Программа делает ровно одно нажатие копирования на одно твоё нажатие, как Awakened PoE Trade. Если "
    "галочку снять — сначала скопируй предмет сам.":
        "Hover an item in game and press «Item under cursor → emulator» — the workshop opens with that item. The app "
        "sends exactly one copy press per press of yours, like Awakened PoE Trade. Untick it to copy the item yourself first.",
    "Маленькая панель с подсказками поверх игры.": "A small hint panel over the game.", "Вид": "Look",
    "Поведение": "Behaviour",
    "При запуске открывать стартовое окно (хаб), оверлей — только по предмету":
        "Open the start window (hub) on launch, overlay only on an item",
    "Где показывать карточку предмета": "Where to show the item card",
    "На своём месте (куда перетащил)": "In its place (where you dragged it)",
    "Рядом с курсором, как прайс-чек в APT": "Next to the cursor, like an APT price check", "Положение": "Position",
    "Не скрывать": "Don't hide", "Через 5 секунд": "After 5 seconds", "Через 10 секунд": "After 10 seconds",
    "Через 20 секунд": "After 20 seconds", "Через 40 секунд": "After 40 seconds",
    "Автоскрытие (если мышь не над карточкой)": "Auto-hide (if the mouse isn't over the card)",
    "Если оверлей не виден поверх игры — переключи игру в режим «Оконный без рамки».":
        "If the overlay isn't visible over the game, switch the game to «Windowed Fullscreen».",
    "Большое окно: пул модов, калькулятор, эмулятор, сокеты.": "The big window: mod pool, calculator, emulator, sockets.",
    "Расчёты": "Calculations", "База по умолчанию: ilvl": "Default base: ilvl",
    "Язык интерфейса меняется после перезапуска программы.": "The interface language changes after restarting the app.",
    "Русский": "Русский", "Авто (по тексту предмета)": "Auto (from item text)",
    "Цены валюты, эссенций, фоссилов и lifeforce берутся с poe.ninja.":
        "Currency, essence, fossil and lifeforce prices come from poe.ninja.",
    "Сейчас": "Now",
    "Цены обновляются автоматически раз в час. После старта новой лиги программа сама переключится на неё.":
        "Prices refresh every hour. When a new league starts the app switches to it by itself.",
    "Данные модов из файлов игры (RePoE). Обновляй после каждого патча.":
        "Mod data from the game files (RePoE). Update after every patch.",
    "Версия": "Version", "Загрузка": "Download",
    "Новые версии программы публикуются как релизы на GitHub.": "New versions are published as GitHub releases.",
    "Помощник крафта для Path of Exile 1: подсказки по предмету из буфера обмена, пул модов, калькулятор, эссенции и "
    "фоссилы, эмулятор, влияния, Eldritch, Harvest, кластеры, сокеты.":
        "A crafting helper for Path of Exile 1: hints for the copied item, mod pool, calculator, essences and "
        "fossils, emulator, influences, Eldritch, Harvest, clusters, sockets.",
    "Безопасность": "Safety",
    "Программа ничего не нажимает в игре и не читает её память — только буфер обмена. Это соответствует правилам GGG "
    "«одно действие на одно нажатие».":
        "The app presses nothing in the game and doesn't read its memory — only the clipboard. This follows GGG's "
        "«one action per keypress» rule.",
    "Источники": "Sources",
    "Path of Exile принадлежит Grinding Gear Games. Программа не связана с GGG и не одобрена ими.":
        "Path of Exile belongs to Grinding Gear Games. This app is not affiliated with or endorsed by GGG.",
    "Глобальные горячие клавиши работают только в Windows.": "Global hotkeys work on Windows only.",
    "Не забудь «Сохранить».": "Don't forget to «Save».", "Русские данные для клиента:": "Russian client data:",
    "Установлена версия": "Installed version", "Данные модов — RePoE": "Mod data — RePoE", "Цены — poe.ninja": "Prices — poe.ninja",
    "Формула сокетов — калькулятор Siveran": "Socket formula — Siveran's calculator", "загружены ✓": "loaded ✓",
    "не загружены — раздел «Данные игры» → «Обновить данные модов».": "not loaded — «Game data» → «Update mod data».",
    "Лига:": "League:", "Chaos\nИсточник:": "Chaos\nSource:", ", обновлено": ", updated",
    "Сохранено. Язык сменится после перезапуска.": "Saved. The language changes after a restart.",
    "Сохранено, но:": "Saved, but:", "версия": "version",
    "Добавь Ctrl, Alt или Shift — иначе клавиша будет мешать в игре.": "Add Ctrl, Alt or Shift — otherwise the key gets in the way in game.",
    "Данные RePoE:": "RePoE data:", "\nПапка:": "\nFolder:", "уже назначено на другое действие.": "is already bound to another action.",
    "Доступна версия": "Version available", "(у тебя": "(you have", "). Кликни, чтобы скачать.": "). Click to download.",
    "У тебя последняя версия (": "You have the latest version (", "+ русские": "+ Russian",
    "Скачиваю (≈50 МБ)… окно можно не закрывать.": "Downloading (≈50 MB)… you can keep the window open.",
    "Проверяю…": "Checking…", "Цены обновлены: лига": "Prices updated: league", "Не удалось обновить цены.": "Couldn't update prices.",
    ". Перезапусти программу, чтобы данные применились.": ". Restart the app to apply the data.",
    "Ошибка загрузки:": "Download error:",
    # ---------------------------------------------------------------- оверлей
    "Наведи курсор на предмет в игре и нажми сочетание ещё раз.": "Hover an item in game and press the combo again.",
    "Цели перезагружены.": "Goals reloaded.", "Считаю…": "Calculating…", "скопируй предмет в игре": "copy an item in game",
    "СЛЕДУЮЩИЙ ШАГ": "NEXT STEP", "⚒  Открыть в эмуляторе": "⚒  Open in emulator",
    "В буфере нет предмета — скопируй его в игре (Ctrl+Alt+C).": "No item in the clipboard — copy it in game (Ctrl+Alt+C).",
    "Крафт «": "Craft «", "» сохранён.": "» saved.", "Сначала выбери крафт.": "Pick a craft first.",
    "Код крафта «": "Craft code «", "» скопирован (": "» copied (",
    "симв.). Вставь его в Discord/Telegram — другой игрок нажмёт «импорт».":
        "chars). Paste it into Discord/Telegram — another player presses «import».",
    "Добавлен крафт «": "Added craft «", "Нет цели — выбери крафт в хабе (⌂ → Мои крафты).": "No goal — pick a craft in the hub (⌂ → My crafts).",
    "осквернён": "corrupted", "Горячие клавиши:": "Hotkeys:", "Не удалось открыть главное окно:": "Couldn't open the main window:",
    "Не удалось открыть хаб:": "Couldn't open the hub:", "Не удалось открыть в эмуляторе:": "Couldn't open in the emulator:",
    "Папка целей:": "Goals folder:", "Ошибка в цели": "Error in goal", "Импорт:": "Import:",
    "Скопируй код и нажми «импорт» ещё раз.": "Copy the code and press «import» again.", "Данные": "Data",
    ". Наведи на предмет в игре и нажми Ctrl+Alt+C.": ". Hover an item in game and press Ctrl+Alt+C.",
    "Гарантированно": "Guaranteed", "1 действие": "1 action", "Не удалось загрузить данные:": "Couldn't load data:",
    "Ошибка:\n": "Error:\n", "Шанс 0% — так не получится": "Chance 0% — this won't work", "Шанс": "Chance",
    "в среднем ~": "on average ~", "попыт.": "tries", "·  свободно": "·  free",
    # ---------------------------------------------------------------- рецепты
    "Снять крафты": "Remove crafts", "Зверь: +префикс −суффикс": "Beast: +prefix −suffix",
    "Зверь: +суффикс −префикс": "Beast: +suffix −prefix", "все нужные моды": "all wanted mods",
    "ещё не все нужные моды": "not all wanted mods yet", "хотя бы 1 нужный мод": "at least 1 wanted mod",
    "хотя бы 2 нужных мода": "at least 2 wanted mods", "хотя бы 3 нужных мода": "at least 3 wanted mods",
    "есть свободный префикс": "free prefix", "есть свободный суффикс": "free suffix",
    "нет свободного префикса": "no free prefix", "нет свободного суффикса": "no free suffix",
    "предмет обычный": "item is normal", "предмет магический": "item is magic", "предмет редкий": "item is rare",
    "Chaos до цели": "Chaos until goal", "Эссенция до цели": "Essence until goal", "Фоссилы до цели": "Fossils until goal",
    "Эссенция → блок префиксов → Exalt": "Essence → prefix block → Exalt", "есть нужный мод №": "has wanted mod #",
    "↻ пока не": "↻ until", "В шаге не выбрана эссенция.": "No essence picked in the step.",
    "В шаге не выбраны фоссилы.": "No fossils picked in the step.",
    "Такого крафта верстака нет для этой базы.": "This base has no such bench craft.",
    "· иначе дальше": "· else next", "· иначе стоп": "· else stop", "· иначе → шаг": "· else → step", "шаг": "step",
    # ---------------------------------------------------------------- движок (ошибки и журнал)
    "Transmutation → синий": "Transmutation → magic", "Regal → редкий": "Regal → rare", "Alchemy → редкий": "Alchemy → rare",
    "Divine — значения перероллены": "Divine — values rerolled",
    "Orb of Conflict: доминирующий импликит усилен, второй ослаблен": "Orb of Conflict: dominant implicit up, the other down",
    "Veiled Chaos: на предмете Veiled-мод": "Veiled Chaos: item has a veiled mod",
    "Veiled Exalt: добавлен Veiled-мод": "Veiled Exalt: veiled mod added", "Сняты крафты верстака": "Bench crafts removed",
    "Vaal-имплицит": "Vaal implicit", "Vaal-имплицит:": "Vaal implicit:",
    "Tainted Divine Teardrop: тиры сдвинуты": "Tainted Divine Teardrop: tiers shifted", "Craicic Maw: мод влияния": "Craicic Maw: influence mod",
    "Отпечаток сохранён": "Imprint saved", "Предмет восстановлен из отпечатка": "Item restored from imprint",
    "Нечего отменять.": "Nothing to undo.",
    "Предмет осквернён — на него действуют только Tainted-валюта и верстак.": "The item is corrupted — only Tainted currency and the bench work.",
    "Tainted-валюта работает только на осквернённых предметах (сначала Vaal Orb).": "Tainted currency works only on corrupted items (Vaal Orb first).",
    "Transmutation работает только на белом предмете.": "Transmutation works only on a white item.",
    "Alteration работает только на синем предмете.": "Alteration works only on a magic item.",
    "Augmentation работает только на синем предмете.": "Augmentation works only on a magic item.",
    "На синем предмете уже 2 мода.": "The magic item already has 2 mods.",
    "Regal работает только на синем предмете.": "Regal works only on a magic item.",
    "Alchemy работает только на белом предмете.": "Alchemy works only on a white item.",
    "Chaos работает только на редком предмете.": "Chaos works only on a rare item.",
    "Exalted Orb работает только на редком предмете.": "Exalted Orb works only on a rare item.",
    "Все 6 слотов заняты.": "All 6 slots are taken.", "Нечего снимать.": "Nothing to remove.",
    "Все моды защищены — Annulment ничего не снимет.": "All mods are protected — Annulment removes nothing.",
    "Annulment сняла:": "Annulment removed:", "Предмет и так белый.": "The item is already white.", "Нет модов для Divine.": "No mods for Divine.",
    "Эссенция работает на белом предмете (или на редком — Shrieking/Deafening).": "Essences work on a white item (or rare — Shrieking/Deafening).",
    "На редкий предмет можно только Shrieking/Deafening и особые эссенции.": "On a rare item only Shrieking/Deafening and special essences.",
    "Нужно от 1 до 4 фоссилов.": "Needs 1 to 4 fossils.", "Фоссилы работают на белом или редком предмете.": "Fossils work on a white or rare item.",
    "Fractured Fossil не работает на предметах с влиянием и уже расколотых (Split).": "Fractured Fossil doesn't work on influenced or split items.",
    "Hollow: добавлен абиссальный сокет": "Hollow: abyssal socket added", "Gilded: предмет дороже продаётся торговцу": "Gilded: item sells to vendors for more",
    "Неизвестное влияние.": "Unknown influence.", "Предмет уже с влиянием.": "The item is already influenced.",
    "На предмете с Eldritch-импликитами влияние добавить нельзя.": "Can't add influence to an item with Eldritch implicits.",
    "Нужен свободный слот.": "Needs a free slot.", ": влияние": ": influence",
    "Eldritch-импликиты бывают только на шлемах, перчатках, ботинках и нагрудниках.": "Eldritch implicits exist only on helmets, gloves, boots and body armours.",
    "На предмет с влиянием Eldritch-валюту применить нельзя.": "Eldritch currency can't be used on an influenced item.",
    "Для этой базы нет таких импликитов.": "This base has no such implicits.",
    "Нет доминирования: тиры импликитов Exarch и Eater равны (или их нет).": "No dominance: Exarch and Eater implicit tiers are equal (or missing).",
    "Eldritch Chaos работает только на редком предмете.": "Eldritch Chaos works only on a rare item.", "Eldritch Chaos: перероллены": "Eldritch Chaos: rerolled",
    "Eldritch Exalted Orb работает только на редком предмете.": "Eldritch Exalted Orb works only on a rare item.",
    "Нечего снимать с доминирующей стороны.": "Nothing to remove on the dominant side.", "Eldritch Annul сняла:": "Eldritch Annul removed:",
    "Нужны оба импликита: Exarch и Eater.": "Needs both implicits: Exarch and Eater.",
    "Harvest Reforge работает на редком предмете.": "Harvest Reforge works on a rare item.",
    "Этот Harvest-крафт работает на редком предмете.": "This Harvest craft works on a rare item.",
    "Для этого тега нет Harvest-крафта «добавить мод».": "No «add mod» Harvest craft for this tag.",
    "Нужен синий или редкий предмет.": "Needs a magic or rare item.",
    "Этот Harvest-крафт работает только на предметах без влияния.": "This Harvest craft works only on non-influenced items.",
    ", снят:": ", removed:", "мод (": "mod (", "(открыть у Jun)": "(unveil at Jun)",
    "Veiled Chaos Orb работает только на редком предмете.": "Veiled Chaos Orb works only on a rare item.",
    "Veiled Exalted Orb работает только на редком предмете.": "Veiled Exalted Orb works only on a rare item.",
    "На предмете уже есть Veiled-мод.": "The item already has a veiled mod.", "Нет свободного слота.": "No free slot.",
    "На предмете нет Veiled-мода.": "The item has no veiled mod.", "Для этой базы нет подходящих модов Jun.": "No suitable Jun mods for this base.",
    "Сначала открой варианты Unveil.": "Open the Unveil options first.", "Сначала сделай предмет синим или редким.": "Make the item magic or rare first.",
    "Уже есть крафт с верстака (сними его или сделай «Can have up to 3 Crafted»).": "There is already a bench craft (remove it or use «Can have up to 3 Crafted»).",
    "Мод этой группы уже есть на предмете.": "A mod of this group is already on the item.", "Нет крафтов с верстака.": "No bench crafts.",
    "Предмет уже осквернён.": "The item is already corrupted.", "Vaal: новый имплицит": "Vaal: new implicit",
    "Tainted Chaos Orb — только на осквернённом редком предмете.": "Tainted Chaos Orb — corrupted rare items only.",
    "Tainted Chaos: перекат": "Tainted Chaos: reroll", "Tainted Chaos: все моды сняты": "Tainted Chaos: all mods removed",
    "Tainted Exalted Orb — только на осквернённом редком предмете.": "Tainted Exalted Orb — corrupted rare items only.",
    "Tainted Divine Teardrop — только на осквернённом редком предмете с модами.": "Tainted Divine Teardrop — corrupted rare items with mods only.",
    "Нужен предмет ровно с одним влиянием (второе даст уничтожаемый предмет).": "Needs an item with exactly one influence (the sacrificed item gives the second).",
    "Второе влияние должно быть другим и доступным для этой базы.": "The second influence must be different and available for this base.",
    "Awakener's Orb: влияния": "Awakener's Orb: influences", "Нужно минимум 2 мода влияния.": "Needs at least 2 influence mods.",
    "Только на редком предмете.": "Rare items only.", "Нужен редкий предмет с влиянием.": "Needs an influenced rare item.",
    "Нет подходящих модов влияния.": "No suitable influence mods.", "Нужен редкий предмет минимум с 2 модами.": "Needs a rare item with at least 2 mods.",
    "Нельзя расколоть предмет с влиянием или уже расколотый.": "Can't split an influenced or already split item.",
    "Split: вторая копия —": "Split: second copy —", "мод(ов)": "mod(s)", "Аспект — на магический или редкий предмет.": "Aspects go on a magic or rare item.",
    "Нужен свободный суффикс.": "Needs a free suffix.", "На предмете уже есть крафт.": "The item already has a craft.", "Аспект:": "Aspect:",
    "Отпечаток (Craicic Chimeral) — только магического предмета.": "Imprint (Craicic Chimeral) — magic items only.",
    "Нельзя сделать отпечаток расколотого/фрактурного предмета.": "Can't imprint a split/fractured item.", "Нет отпечатка.": "No imprint.",
    "Катализаторы — только для колец, амулетов и поясов.": "Catalysts are for rings, amulets and belts only.",
    "Неизвестный катализатор.": "Unknown catalyst.", "Качество уже 20%.": "Quality is already 20%.", ": качество": ": quality",
    "В эмулятор можно положить только обычный, магический или редкий предмет.": "Only normal, magic or rare items can go into the emulator.",
    "Неизвестное действие:": "Unknown action:", "— нечего добавить": "— nothing to add", "(с защитой)": "(protected)",
    "Эта эссенция только для предметов до ilvl": "This essence is only for items up to ilvl",
    "У этого типа предметов нет влияния": "This item type has no influence", "работает только на редком предмете.": "works only on a rare item.",
    "Нет свободного": "No free", "На этой базе нет модов с тегом": "This base has no mods with tag",
    "больше шанс тех же модов": "higher chance of the same mods", "меньше шанс тех же модов": "lower chance of the same mods",
    "Нет свободного места под мод с тегом": "No free room for a mod with tag", "(или таких модов нет).": "(or no such mods).",
    "Vaal: предмет перекатился в редкий": "Vaal: item rerolled to rare", "Vaal: перекат в редкий": "Vaal: reroll to rare",
    "Tainted Exalt: снят": "Tainted Exalt: removed", "Tainted Exalt: добавлен мод": "Tainted Exalt: mod added",
    "Tainted Exalt: нечего добавить": "Tainted Exalt: nothing to add", "Dominance: снят": "Dominance: removed",
    ", возвышать нечего": ", nothing to elevate", ", возвышен": ", elevated",
    "(возвышенной версии у этого мода нет)": "(this mod has no elevated version)", "Нужен свободный": "Needs a free",
    "Зверь: +": "Beast: +", "Split: на этой копии": "Split: on this copy", "Fractured: копия предмета, «": "Fractured: item copy, «",
    "» зафрактурен (Split)": "» fractured (split)", "префиксы": "prefixes", "суффиксы": "suffixes", "префикс": "prefix",
    "суффикс": "suffix", "префикса": "prefix", "суффикса": "suffix",
    "Vaal: изменились сокеты/связи": "Vaal: sockets/links changed", "Vaal: сокеты": "Vaal: sockets", "Vaal: без изменений": "Vaal: no change",
    ", снят": ", removed", "(не распознано:": "(not recognized:",
    "создаёт копию предмета с фрактурой одного мода": "creates a copy of the item with one mod fractured",
    "повышает цену продажи вендору": "raises the vendor sell price",
    "значения модов роллятся «удачно», но тиров выпадает меньше": "mod values roll «lucky», but fewer tiers roll",
    "добавляет шанс мода от осквернённой эссенции": "adds a chance of a corrupted-essence mod",
    "добавляет гнездо для самоцвета Бездны": "adds an abyssal jewel socket", "добавляет Vaal-импликит": "adds a Vaal implicit",
    "Ни одного попадания в симуляции — так не выйдет.": "Not a single hit in the simulation — this won't work.",
    "Шанс за попытку:": "Chance per try:", "роллов) · в среднем ~": "rolls) · on average ~",
    "Эта эссенция работает только на предметах до ilvl": "This essence works only on items up to ilvl",
    "Спам:": "Spam:", "Гарантирует «": "Guarantees «", "» (как T": "» (as T", "), остальные моды случайны.": "), other mods are random.",
    "(не учитывается)": "(not counted)", "Резонатор с фоссилами:": "Resonator with fossils:", "особых модов": "special mods",
    "нет": "none", "нет цены на poe.ninja:": "no price on poe.ninja:", "Chaos Orb спам": "Chaos Orb spam",
    "Роллим редкий предмет Chaos'ом, пока не выпадут все нужные моды.": "Reroll a rare item with Chaos until all wanted mods hit.",
    "Альтаем синий предмет, аугаем, если выпал один нужный мод и свободен второй слот.":
        "Alt a magic item, aug when one wanted mod hit and the second slot is free.",
    "Собираем два нужных мода на синем предмете альтами, Regal на третий. Если Regal промахнулся — Scour, Transmute и заново.":
        "Get two wanted mods on a magic item with alts, Regal for the third. If Regal misses — Scour, Transmute and again.",
    ", симуляция": ", simulation", "Два нужных мода на синем предмете не собрать.": "Two wanted mods can't be had on a magic item.",
    "Regal не может дать недостающий мод.": "Regal can't give the missing mod.", "Шанс Regal'а:": "Regal chance:",
    "; синий с 2 нужными модами: 1 из ~": "; magic with 2 wanted mods: 1 in ~", "альтов": "alts",
    "Реролл редкого предмета с гарантированным модом тега «": "Reroll a rare item with a guaranteed mod of tag «",
    "Chromatic Orb спам": "Chromatic Orb spam", "небелых": "non-white",
    "Это оценка симуляцией: точное соотношение «1 мод / 2 мода» у синих предметов игра не раскрывает.":
        "This is a simulation estimate: the game doesn't reveal the exact «1 mod / 2 mods» ratio on magic items.",
    "Следующий шаг:": "Next step:", "\nПочему:": "\nWhy:", "Chaos Orb (или Scouring → заново)": "Chaos Orb (or Scouring → start over)",
    "Нужного мало, а свободных слотов нет. Шанс получить все нужные моды Chaos'ом:":
        "Few wanted mods and no free slots. Chance to get all wanted mods with Chaos:",
    "\nШанс: 0% — этим способом нужный мод не получить.": "\nChance: 0% — this way can't give the wanted mod.",
    "Готово": "Done", "Все нужные моды на месте. Дальше — Divine на значения или продажа.":
        "All wanted mods are there. Next — Divine for values, or sell.",
    "Orb of Transmutation, потом Alteration": "Orb of Transmutation, then Alteration",
    "Белый предмет: делаем синим и роллим альтами.": "White item: make it magic and roll alts.",
    "Оба мода нужные — делаем редким, получим третий мод.": "Both mods are wanted — make it rare to get a third mod.",
    "Редкость «": "Rarity «", "» пока не поддерживается.": "» is not supported yet.", "Orb of Annulment (риск)": "Orb of Annulment (risky)",
    "\nШанс за одну попытку:": "\nChance per try:", "Не нашёл базу предмета «": "Item base not found «", "» в данных RePoE.": "» in RePoE data.",
    "Стоп": "Stop", "Предмет осквернён — валютой его уже не изменить.": "The item is corrupted — currency can't change it anymore.",
    "Предмет — зеркальная копия, менять нельзя.": "The item is a mirrored copy and can't be changed.",
    "Не выпадает на этой базе/ilvl:": "Doesn't roll on this base/ilvl:", "Нужных модов нет — перероллить.": "No wanted mods — reroll.",
    "Сначала сними крафт верстака, если он занимает нужный тип слота.": "Remove the bench craft first if it takes the needed slot type.",
    "Заблокируй ненужный тип слота крафтом «Prefixes/Suffixes Cannot Be Changed» или любым модом верстака — шанс Exalt'а вырастет.":
        "Block the unwanted slot type with «Prefixes/Suffixes Cannot Be Changed» or any bench mod — the Exalt chance goes up.",
    ". Есть свободный слот.": ". There is a free slot.", ". Анулл снимет случайный мод — может снести и нужный.":
        ". Annul removes a random mod — it may hit a wanted one.",
    "Если шанс крошечный — дешевле начать с белой базы через Alt→Regal.": "If the chance is tiny, it's cheaper to start from a white base via Alt→Regal.",
    "(в среднем попыток: ~": "(average tries: ~", "Цель для «": "Goal for «", "», а это «": "», but this is «", "Есть «": "Has «",
    "», свободен второй слот — аугаем.": "», second slot free — aug it.",
    "Один мод нужный, второй мусорный. Шанс сразу словить два нужных за альт:": "One mod wanted, the other junk. Chance to hit two wanted per alt:",
    "Крафт на верстаке": "Bench craft", "С блоком шанс:": "With a block the chance is:", "вместо": "instead of",
    "Не хватает:": "Missing:", "Слоты заняты мусором:": "Slots taken by junk:",
    "Потом — Exalt или верстак на освободившееся место.": "Then Exalt or bench into the freed slot.",
    "Можно и Regal: оставить мусор и надеяться на крафт верстаком позже.": "Regal works too: keep the junk and hope to bench craft later.",
    "Остался только «": "Only «", "», слот свободен. Верстак:": "» left, slot free. Bench:", "(цена": "(price", "(тир ≤": "(tier ≤",
    "Значение у верстака ниже, чем у топ-тиров. Если нужен высокий тир — сначала Exalt.":
        "Bench values are lower than top tiers. If you need a high tier, Exalt first.",
    "кэш": "cache", "Все классы": "All classes",
    # ---------------------------------------------------------------- 3.30
    "Гвеннен": "Gwennen", "Уничтожен": "Destroyed", "Дважды осквернён": "Twice corrupted",
    "дважды осквернён": "twice corrupted", "Алтарь": "Altar",
    "3.30: второе осквернение (Twice Corrupted)": "3.30: second corruption (Twice Corrupted)",
    "Altar of Corruption (Храм): второе осквернение уже осквернённого предмета":
        "Altar of Corruption (Temple): corrupts an already corrupted item a second time",
    "Второе осквернение; может уничтожить предмет": "Second corruption; may destroy the item",
    "Djinn-Touched Vaal Orb: дважды оскверняет, работает и на дважды осквернённом":
        "Djinn-Touched Vaal Orb: twice corrupts, works on twice corrupted items too",
    "Если Vaal-имплицитов уже два, новый заменяет один из них. Точные шансы исходов GGG не публиковала: тут как у "
    "Vaal Orb, у Lapidary Lens риск уничтожить предмет ≈20% (оценка).":
        "With two Vaal implicits already, a new one replaces one of them. GGG hasn't published the exact odds: same "
        "as Vaal Orb here, Lapidary Lens has a ≈20% risk to destroy the item (estimate).",
    "3.30: Гвеннен за 1 Astragali предлагает на редкий предмет три пары крафтов. Выбираешь пару — монетка применяет "
    "один из двух (50/50). Выбери пару как в игре и кидай.":
        "3.30: for 1 Astragali Gwennen offers three pairs of crafts on a rare item. Pick a pair — the coin applies one "
        "of the two (50/50). Set the pair as offered in game and flip.",
    "вариант 1": "option 1", "вариант 2": "option 2", "🪙 Подбросить монетку": "🪙 Flip the coin",
    "перекатить все моды": "reroll all mods", "добавить случайный мод": "add a random mod",
    "снять случайный мод": "remove a random mod", "перекатить значения": "reroll values",
    "сдвинуть тиры ±1": "shift tiers ±1", "Гвеннен работает только с редким предметом.": "Gwennen works on rare items only.",
    "нужен уже осквернённый предмет (сначала Vaal Orb).": "needs an already corrupted item (Vaal Orb first).",
    "Предмет уже дважды осквернён.": "The item is already twice corrupted.", "предмет уничтожен": "item destroyed",
    "Предмет уничтожен — отмени шаг (↶) или возьми новый.": "The item is destroyed — undo (↶) or take a new one.",
    "новый имплицит": "new implicit", "без изменений": "no change", "перекат в редкий": "reroll to rare",
    "но": "but", "✗ предмет уничтожен": "✗ item destroyed", "предмет дважды осквернён": "item twice corrupted",
    "Создатель": "Shaper", "Древний": "Elder", "Крестоносец": "Crusader", "Избавительница": "Redeemer",
    "Охотник": "Hunter", "Вождь": "Warlord",
}
