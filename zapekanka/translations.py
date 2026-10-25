# SPDX-License-Identifier: GPL-3.0-or-later
"""Russian interface translation.

Blender shows these strings when Preferences > Interface > Language is set to
Russian.  ``tests/test_translations.py`` checks that every UI string of the
add-on has an entry here.
"""

import bpy

RU = {
    # Panels and labels
    "Zapekanka": "Zapekanka",
    "High / Low Pairs": "Пары High / Low",
    "Detection Settings": "Настройки поиска",
    "Maps": "Карты",
    "Cage & Rays": "Каж и лучи",
    "Output & Quality": "Вывод и качество",
    "Naming": "Имена файлов",
    "Pre-flight Check": "Проверка перед запеканием",
    "Export": "Экспорт",
    "Bake All": "Запечь всё",
    "Active Pair": "Активная пара",
    "Selected": "Выделенные",
    "Blender is blocked while baking": "Blender заблокирован на время запекания",
    "Baking: %s": "Запекание: %s",
    "Elapsed: %ds": "Прошло: %d с",
    "Queued: %d": "В очереди: %d",
    "Time: %.1fs": "Время: %.1f с",
    "%s: %d file(s)": "%s: файлов %d",
    "Name objects Name_low / Name_high and press Detect Pairs.":
        "Назовите объекты Имя_low / Имя_high и нажмите «Найти пары».",
    "Or select a low poly and its high polys (low poly active) and press +.":
        "Или выделите low и его high (low активный) и нажмите +.",
    "Bake All without pairs bakes the materials of the selected objects.":
        "«Запечь всё» без пар запекает материалы выделенных объектов.",
    "Scene Setting": "Как в сцене",
    "Use the Cycles device of the scene (Render Properties)": "Устройство Cycles из настроек сцены (Render Properties)",
    "Low": "Low",
    "High": "High",
    "(missing)": "(нет объекта)",
    "Material": "Материал",
    "Mesh": "Меш",
    "Full PBR": "Полный PBR",
    "Game": "Игровой",
    "Mesh Maps": "Карты меша",
    "None": "Нет",
    "Ambient Occlusion": "Ambient Occlusion",
    "Thickness": "Толщина",
    "Curvature": "Кривизна",
    "Height": "Высота",
    "ID Color": "ID-цвет",
    "Samples": "Сэмплы",
    "Distance": "Дистанция",
    "Supersampling": "Суперсэмплинг",
    "No problems found": "Проблем не найдено",
    "%d error(s), %d warning(s)": "Ошибок: %d, предупреждений: %d",
    "Fix All": "Исправить всё",
    "Fix": "Исправить",
    "Send to Unreal": "Отправить в Unreal",
    "Export and Open": "Экспорт и открыть",
    "The file changed during the bake: textures were saved, materials were not created":
        "Файл сменился во время запекания: текстуры сохранены, материалы не созданы",

    # Operators
    "Bake": "Запечь",
    "Bake the texture sets": "Запечь текстурные сеты",
    "Scope": "Область",
    "All Pairs": "Все пары",
    "All enabled pairs": "Все включённые пары",
    "Only the active pair": "Только активная пара",
    "Selected Objects": "Выделенные объекты",
    "Pairs that contain a selected object": "Пары, в которых есть выделенный объект",
    "Skip Pre-flight": "Без проверки",
    "Cancel Bake": "Отменить запекание",
    "Stop the running background bake and clear the queue": "Остановить фоновое запекание и очистить очередь",
    "Open Folder": "Открыть папку",
    "Open the output folder in the file browser": "Открыть папку с текстурами",
    "Open Log": "Открыть лог",
    "Open the log of the last background bake": "Открыть лог последнего фонового запекания",
    "Detect Pairs": "Найти пары",
    "Find high/low pairs by name suffix or collection": "Найти пары high/low по суффиксам имён или по коллекциям",
    "Replace List": "Заменить список",
    "Remove pairs that were not found again": "Удалить пары, которые не нашлись повторно",
    "Add Pair from Selection": "Пара из выделения",
    "Active object becomes the low poly, other selected objects the high polys":
        "Активный объект станет low, остальные выделенные — high",
    "Remove Pair": "Удалить пару",
    "Clear Pairs": "Очистить пары",
    "Edit Pair Objects": "Объекты пары",
    "Add selected objects to, or remove the active entry from, the active pair":
        "Добавить выделенные объекты в активную пару или убрать выбранный",
    "Add Selected": "Добавить выделенные",
    "Remove": "Удалить",
    "Select Pair Objects": "Выделить объекты пары",
    "Select the objects of the pair in the viewport": "Выделить объекты пары во вьюпорте",
    "Set Texture Set": "Задать текстурный сет",
    "Bake several pairs into one texture set (atlas) or split them again":
        "Запечь несколько пар в один текстурный сет (атлас) или разделить обратно",
    "Enabled Pairs": "Включённые пары",
    "Run Pre-flight Check": "Запустить проверку",
    "Check pairs for problems that ruin bakes (scale, UVs, normals, triangulation...)":
        "Проверить пары на проблемы, которые портят запекание (масштаб, UV, нормали, триангуляция…)",
    "Apply the suggested fix (modifies the object, can be undone)":
        "Применить исправление (меняет объект, можно отменить)",
    "Select Object": "Выделить объект",
    "Select the object this issue refers to": "Выделить объект, к которому относится проблема",
    "Update Cage Preview": "Обновить превью кажа",
    "Show the automatic cage as a wireframe (updates when the extrusion changes)":
        "Показать автоматический каж сеткой (обновляется при изменении экструзии)",
    "Estimate Extrusion": "Подобрать экструзию",
    "Measure the distance between low and high polys and set the cage extrusion":
        "Измерить расстояние между low и high и выставить экструзию кажа",
    "Set the global extrusion from all enabled pairs": "Общая экструзия по всем включённым парам",
    "Set a custom extrusion on the active pair": "Своя экструзия для активной пары",
    "Map Preset": "Набор карт",
    "Enable a typical set of maps": "Включить типовой набор карт",
    "Base Color, Roughness, Metallic, Normal, AO, Emission, Opacity":
        "Base Color, Roughness, Metallic, Normal, AO, Emission, Opacity",
    "Normal, AO, Curvature, Thickness, Position, World Normal, Height, ID":
        "Normal, AO, Curvature, Thickness, Position, World Normal, Height, ID",
    "Game Asset": "Игровой ассет",
    "Base Color, ORM, Normal": "Base Color, ORM, Normal",
    "Disable all maps": "Выключить все карты",
    "Reset to Preset": "Сбросить к пресету",
    "Re-apply naming, packing and format settings of the selected preset":
        "Заново применить имена, упаковку и формат выбранного пресета",
    "Restore Original Materials": "Вернуть исходные материалы",
    "Put back the materials the low polys had before the baked material was assigned":
        "Вернуть материалы, которые были у low до назначения запечённого",
    "Import Texture Set": "Импорт текстурного сета",
    "Build a material from a texture set (Zapekanka .json or textures named like the current preset) and "
    "assign it to the selected objects":
        "Собрать материал из текстурного сета (.json Zapekanka или текстуры с именами по пресету) и "
        "назначить выделенным объектам",
    "Name used in the file names (for textures without a .json file). Empty: guessed from the selected file":
        "Имя в названиях файлов (для текстур без .json). Пусто — определить по выбранному файлу",
    "Export low polys, textures and materials for the selected target":
        "Экспорт low-мешей, текстур и материалов для выбранной программы",
    "Open in Application": "Открыть в программе",

    # Settings
    "Preset": "Пресет",
    "Output Folder": "Папка для текстур",
    "Resolution": "Разрешение",
    "Custom": "Своё",
    "Width": "Ширина",
    "Bake at a higher resolution and downscale for anti-aliased edges":
        "Запекать в большем разрешении и уменьшать — сглаженные края",
    "Off": "Выкл",
    "Cycles samples for regular passes": "Сэмплы Cycles для обычных проходов",
    "Device": "Устройство",
    "Uses the devices enabled in Preferences > System": "Использует устройства из Настройки > Система",
    "Mode": "Режим",
    "Background": "В фоне",
    "Bake in a separate Blender process: the interface stays responsive":
        "Запекание в отдельном процессе Blender: интерфейс не зависает",
    "Foreground": "В этом окне",
    "Bake inside this Blender session (blocks the interface)": "Запекание в текущем Blender (интерфейс блокируется)",
    "Padding": "Паддинг",
    "Island padding in pixels (at output resolution)": "Расширение островов в пикселях (в итоговом разрешении)",
    "Padding Type": "Тип паддинга",
    "Adjacent Faces": "Соседние грани",
    "Continue across UV seams (seamless)": "Продолжать через швы UV (без швов)",
    "Extend": "Растянуть край",
    "Extend border pixels": "Растягивать крайние пиксели",
    "Fill Empty Space": "Заполнять пустоту",
    "Bleed colors into the whole texture (prevents seams in mip maps)":
        "Растекать цвета на всю текстуру (нет швов на мипмапах)",
    "Normal Format": "Формат нормалей",
    "OpenGL (Y+)": "OpenGL (Y+)",
    "Blender, Unity, Godot, Substance": "Blender, Unity, Godot, Substance",
    "DirectX (Y-)": "DirectX (Y-)",
    "Unreal Engine": "Unreal Engine",
    "Cage Extrusion": "Экструзия кажа",
    "Distance the automatic cage is pushed out": "На сколько автоматический каж выдавливается наружу",
    "Auto Ray Distance": "Авто-дистанция лучей",
    "Ray distance = 2x cage extrusion": "Дистанция лучей = 2 × экструзия кажа",
    "Ray Distance": "Дистанция лучей",
    "Maximum ray length from the cage": "Максимальная длина луча от кажа",
    "Exploded Bake": "Разнесённое запекание",
    "Move pairs apart while baking so their AO and rays do not interfere":
        "Разносить пары на время запекания, чтобы AO и лучи не влияли друг на друга",
    "UV Map": "UV-развёртка",
    "UV map to bake into. Empty: active UV map": "UV-развёртка для запекания. Пусто — активная",
    "Triangulate Low": "Триангулировать low",
    "Triangulate a copy of the low poly before baking (export it triangulated the same way)":
        "Триангулировать копию low перед запеканием (экспортируйте так же триангулированным)",
    "Texture Name": "Имя текстуры",
    "Tokens: {name} (texture set), {suffix}": "Токены: {name} (текстурный сет), {suffix}",
    "Material Name": "Имя материала",
    "Mesh Name": "Имя меша",
    "Packing": "Упаковка",
    "Separate Maps": "Отдельные карты",
    "Every map in its own file": "Каждая карта в своём файле",
    "ORM (R=AO, G=Rough, B=Metal)": "ORM (R=AO, G=Rough, B=Metal)",
    "Unreal Engine, Godot, glTF": "Unreal Engine, Godot, glTF",
    "Unity Metallic (R=Metal, A=Smooth)": "Unity Metallic (R=Metal, A=Smooth)",
    "Unity URP / Built-in metallic workflow": "Unity URP / Built-in, metallic-процесс",
    "Unity HDRP Mask (R=Metal, G=AO, A=Smooth)": "Unity HDRP Mask (R=Metal, G=AO, A=Smooth)",
    "Unity HDRP mask map": "Mask map для Unity HDRP",
    "Opacity in Base Color Alpha": "Непрозрачность в альфе Base Color",
    "Also Save Packed Maps": "Сохранять и упакованные карты",
    "Save AO/Roughness/Metallic separately as well": "Дополнительно сохранять AO/Roughness/Metallic отдельно",
    "Format": "Формат",
    "16-bit Normals": "16-бит нормали",
    "Skip Empty Maps": "Пропускать пустые карты",
    "Do not write emission/opacity maps that are completely black/opaque":
        "Не сохранять полностью чёрный emission и полностью непрозрачную opacity",
    "Create and Assign": "Создать и назначить",
    "Assign the baked material to the low polys (original materials can be restored)":
        "Назначить запечённый материал на low (исходные можно вернуть)",
    "Preview Copy": "Копия для превью",
    "Create a copy of the low polys with the baked material": "Создать копию low с запечённым материалом",
    "Create Only": "Только создать",
    "Create the material without assigning it": "Создать материал, не назначая",
    "Do not create a material": "Не создавать материал",
    "Detect By": "Искать по",
    "Name Suffix": "Суффиксу имени",
    "Gun_low + Gun_high, Gun_high_bolt ...": "Gun_low + Gun_high, Gun_high_bolt …",
    "Collections": "Коллекциям",
    "Collections Gun_low and Gun_high": "Коллекции Gun_low и Gun_high",
    "Low Suffixes": "Суффиксы low",
    "High Suffixes": "Суффиксы high",
    "Cage Suffix": "Суффикс кажа",
    "Selected Only": "Только выделенные",
    "Show Cage": "Показать каж",

    # Pair
    "Name": "Имя",
    "Enabled": "Включено",
    "Include this pair in 'Bake All'": "Участвует в «Запечь всё»",
    "Texture Set": "Текстурный сет",
    "Pairs with the same texture set are baked into the same textures (atlas). Empty: use the pair name":
        "Пары с одинаковым текстурным сетом запекаются в одни текстуры (атлас). Пусто — имя пары",
    "Custom Cage": "Свой каж",
    "Optional cage mesh with the same topology as the low poly. Empty: automatic cage":
        "Необязательный меш кажа с той же топологией, что у low. Пусто — автоматический каж",
    "Custom Extrusion": "Своя экструзия",
    "Override the cage extrusion for this pair": "Своя экструзия кажа для этой пары",
    "Extrusion": "Экструзия",
    "How far the automatic cage is pushed out from the low poly": "На сколько автоматический каж отстоит от low",

    # Map settings
    "Normal": "Нормали",
    "Position": "Позиция",
    "World Normal": "Мировые нормали",
    "Base Color": "Базовый цвет",
    "Roughness": "Шероховатость",
    "Metallic": "Металличность",
    "Emission": "Свечение",
    "Opacity": "Непрозрачность",
    "AO Samples": "Сэмплы AO",
    "Cycles samples for the AO and thickness pass": "Сэмплы Cycles для проходов AO и толщины",
    "AO Distance": "Дистанция AO",
    "Maximum occlusion distance": "Максимальная дистанция затенения",
    "Only Self": "Только сам объект",
    "Only the object itself occludes (ignore other parts)": "Затеняет только сам объект (другие детали игнорируются)",
    "Method": "Метод",
    "From Normal Map": "Из карты нормалей",
    "Derived from the baked normal map: matches the normal details, independent of mesh density":
        "Считается из запечённых нормалей: совпадает с деталями, не зависит от плотности меша",
    "From Mesh": "Из меша",
    "Cycles pointiness of the high poly: needs a dense mesh": "Pointiness Cycles по high: нужен плотный меш",
    "Strength": "Сила",
    "Radius": "Радиус",
    "Sampling radius (pixels at 1K)": "Радиус выборки (пикселей на 1K)",
    "Thickness Samples": "Сэмплы толщины",
    "Thickness Distance": "Дистанция толщины",
    "Range": "Диапазон",
    "Auto": "Авто",
    "Use the full 0-1 range for the largest offset": "Весь диапазон 0–1 под наибольшее смещение",
    "Manual": "Вручную",
    "Fixed range in scene units (consistent between assets)": "Фиксированный диапазон в единицах сцены (одинаково для всех ассетов)",
    "Height Range": "Диапазон высоты",
    "Offset mapped to black/white": "Смещение, которое станет чёрным/белым",
    "ID Source": "Источник ID",
    "One color per high poly material": "Свой цвет на каждый материал high",
    "Object": "Объект",
    "One color per high poly object": "Свой цвет на каждый объект high",
    "Mesh Island": "Островок меша",
    "One color per connected part of the high poly": "Свой цвет на каждую связную часть high",
    "Vertex Color": "Цвет вершин",
    "Use a color attribute of the high poly": "Взять цветовой атрибут high",
    "Attribute": "Атрибут",
    "Color attribute name (Vertex Color mode)": "Имя цветового атрибута (режим «Цвет вершин»)",

    # Export settings
    "Target": "Куда",
    "FBX + textures + material, sent live or as an import script":
        "FBX + текстуры + материал, отправка вживую или скриптом импорта",
    "Unity": "Unity",
    "FBX + textures into the project, materials created by an editor script":
        "FBX + текстуры в проект, материалы создаёт editor-скрипт",
    "Godot 4": "Godot 4",
    "glTF binary with embedded PBR material + ORMMaterial3D resource":
        "glTF (.glb) со встроенным PBR-материалом + ресурс ORMMaterial3D",
    "Substance 3D Painter": "Substance 3D Painter",
    "Low/high FBX with matching names + baked maps": "Low/high FBX с совпадающими именами + запечённые карты",
    "Marmoset Toolbag": "Marmoset Toolbag",
    "Low/high/cage FBX with bake group suffixes": "Low/high/cage FBX с суффиксами групп запекания",
    "glTF / Sketchfab": "glTF / Sketchfab",
    "Self-contained .glb": "Самодостаточный .glb",
    "Roblox": "Roblox",
    "FBX + SurfaceAppearance textures": "FBX + текстуры для SurfaceAppearance",
    "Export Folder": "Папка экспорта",
    "Content Path": "Путь в Content",
    "Destination inside the Unreal project": "Куда положить внутри проекта Unreal",
    "Send Live": "Отправлять вживую",
    "Send to a running Unreal Editor via Python remote execution; falls back to writing an import script":
        "Отправить в запущенный Unreal Editor через Python Remote Execution; иначе — записать скрипт импорта",
    "Unity Project": "Проект Unity",
    "Root folder of the Unity project": "Корневая папка проекта Unity",
    "Assets Subfolder": "Подпапка в Assets",
    "Pipeline": "Пайплайн",
    "Built-in": "Built-in",
    "Godot Project": "Проект Godot",
    "Folder containing project.godot": "Папка с файлом project.godot",
    "Subfolder": "Подпапка",
    "Include Textures": "С текстурами",
    "Include High Polys": "С high-мешами",
    "Export high polys (Substance/Marmoset)": "Экспортировать high (Substance/Marmoset)",
    "Include Cage": "С кажем",
    "Export the automatic cage (Marmoset)": "Экспортировать автоматический каж (Marmoset)",
    "Triangulate": "Триангулировать",
    "Triangulate on export so tangents match the bake": "Триангулировать при экспорте, чтобы тангенты совпали с запеканием",
    "Apply Modifiers": "Применять модификаторы",
    "Scale": "Масштаб",
    "Open the export folder when done": "Открыть папку экспорта после завершения",

    # Preferences
    "Background Baking": "Фоновое запекание",
    "Blender Executable": "Исполняемый файл Blender",
    "Blender used for background bakes. Empty: the running Blender":
        "Blender для фонового запекания. Пусто — текущий",
    "Temporary Folder": "Временная папка",
    "Where background jobs store their data. Empty: system temp folder":
        "Где фоновые задания хранят данные. Пусто — системная временная папка",
    "Keep Job Files": "Сохранять файлы заданий",
    "Keep the background job folder (scene copy, logs) after a successful bake":
        "Не удалять папку задания (копия сцены, логи) после успешного запекания",
    "Low Priority Worker": "Низкий приоритет процесса",
    "Run background bakes with lower process priority so the UI stays responsive":
        "Запускать фоновое запекание с пониженным приоритетом, чтобы интерфейс оставался отзывчивым",
    "Max Tile Size": "Макс. размер тайла",
    "Supersampled bakes larger than this are split into tiles to limit memory use":
        "Запекание больше этого размера делится на тайлы, чтобы экономить память",
    "Lowest memory use": "Минимум памяти",
    "Balanced (about 1 GB per tile buffer)": "Баланс (около 1 ГБ на буфер тайла)",
    "Fewest tiles, needs a lot of RAM": "Меньше тайлов, нужно много ОЗУ",
    "External Applications": "Внешние программы",
    "Executable used by 'Open in Substance Painter'": "Программа для «Открыть в Substance Painter»",
    "Executable used by 'Open in Marmoset Toolbag'": "Программа для «Открыть в Marmoset Toolbag»",
    "Unreal Engine Remote Execution": "Unreal Engine Remote Execution",
    "Multicast Group": "Multicast-группа",
    "Unreal Python remote execution multicast group (Project Settings > Python)":
        "Multicast-группа Python Remote Execution в Unreal (Project Settings > Python)",
    "Multicast Port": "Multicast-порт",
    "Multicast Bind Address": "Multicast Bind Address",
    "Must match 'Multicast Bind Address' in Unreal's Python plugin settings":
        "Должен совпадать с «Multicast Bind Address» в настройках Python-плагина Unreal",
    "Timeout (s)": "Таймаут (с)",

    # Pre-flight messages
    "No enabled pairs. Use 'Detect Pairs' or add one from selection":
        "Нет включённых пар. Нажмите «Найти пары» или создайте пару из выделения",
    "Output folder is relative but the file is not saved. Save the .blend or choose an absolute folder":
        "Папка вывода относительная, а файл не сохранён. Сохраните .blend или укажите абсолютный путь",
    "Output folder is not writable: %s": "Нет прав на запись в папку: %s",
    "%dx%d with %dx supersampling will be baked in tiles (needs time and RAM)":
        "%dx%d с суперсэмплингом %dx будет запекаться тайлами (нужны время и ОЗУ)",
    "Roblox accepts SurfaceAppearance textures up to 1024px": "Roblox принимает текстуры SurfaceAppearance до 1024 px",
    "Cage extrusion is 0: rays start on the low poly surface and miss details above it":
        "Экструзия кажа 0: лучи стартуют с поверхности low и пропустят детали над ней",
    "Pair has no low poly": "У пары нет low",
    "No high poly: the low poly's own materials will be baked": "Нет high: будут запечены материалы самого low",
    "Custom cage only works with a single low poly; the automatic cage will be used":
        "Свой каж работает только с одним low; будет использован автоматический",
    "Texture set '%s': UVs of different low polys overlap (%.1f%%). Arrange them in one UV layout or use "
    "separate texture sets":
        "Текстурный сет «%s»: UV разных low перекрываются (%.1f%%). Разложите их в одну развёртку или "
        "используйте разные текстурные сеты",
    "Negative scale (mirrored object)": "Отрицательный масштаб (отзеркаленный объект)",
    "Unapplied scale %.3g, %.3g, %.3g": "Неприменённый масштаб %.3g, %.3g, %.3g",
    "Low poly has no faces": "У low нет граней",
    "No UV map": "Нет UV-развёртки",
    "UV map '%s' not found, the active one is used": "UV-развёртка «%s» не найдена, берётся активная",
    "UVs outside the 0-1 range are not baked": "UV за пределами 0–1 не запекаются",
    "Overlapping UV islands (%.1f%% of the UV area). Stacked/mirrored islands are baked once":
        "Перекрывающиеся UV-острова (%.1f%% площади). Наложенные/зеркальные острова запекаются один раз",
    "%d faces are not triangles: engines may triangulate differently and break the tangent basis":
        "%d граней — не треугольники: движок может триангулировать иначе и сломать тангенты",
    "Custom normals: export them with the mesh (FBX: normals + tangents) or the bake will not match":
        "Кастомные нормали: экспортируйте их с мешем (FBX: нормали + тангенты), иначе запекание не совпадёт",
    "%d edges between faces with opposite normals": "%d рёбер между гранями с противоположными нормалями",
    "Normals point inwards": "Нормали смотрят внутрь",
    "%d non-manifold edges (3+ faces per edge)": "%d non-manifold рёбер (3+ грани на ребро)",
    "%d loose vertices/edges": "%d висящих вершин/рёбер",
    "%d duplicate vertices": "%d дублирующихся вершин",
    "%s will be converted to a mesh for baking": "%s будет сконвертирован в меш для запекания",
    "High poly has negative scale": "У high отрицательный масштаб",
    "High poly does not overlap its low poly: rays will miss": "High не пересекается со своим low: лучи промахнутся",
    "Empty material slot (baked as neutral grey)": "Пустой слот материала (запечётся нейтрально-серым)",
    "Image '%s' has unsaved changes: background bakes use the saved version":
        "Изображение «%s» не сохранено: фоновое запекание возьмёт сохранённую версию",
    "Image file not found: %s": "Файл изображения не найден: %s",
    "Apply Scale": "Применить масштаб",
    "Smart UV Project": "Smart UV Project",
    "Pack Islands": "Упаковать острова",
    "Recalculate Normals": "Пересчитать нормали",
    "Merge by Distance": "Слить по расстоянию",
    "Clear Custom Normals": "Очистить кастомные нормали",
    "Add Triangulate Modifier": "Добавить модификатор Triangulate",

    # Engine warnings
    "%s: %.1f%% of texels were not hit by rays (filled from neighbours). Increase the cage extrusion or ray "
    "distance.":
        "%s: %.1f%% текселей не получили лучей (заполнены соседями). Увеличьте экструзию кажа или дистанцию лучей.",
    "Could not write %s: %s": "Не удалось записать %s: %s",
    "High poly %s is not geometry (%s), skipped": "High %s — не геометрия (%s), пропущен",
    "UV map %s not found on %s, using %s": "UV-развёртка %s не найдена на %s, используется %s",
    "Cage %s does not match the topology of its low poly; using the automatic cage":
        "Каж %s не совпадает по топологии с low; используется автоматический",

    # Presets
    "Mask Map": "Mask Map",
    "Metallic Smoothness": "Metallic Smoothness",
    "ORM": "ORM",
    "Unreal Engine 5": "Unreal Engine 5",
    "Unity (URP / Built-in)": "Unity (URP / Built-in)",
    "Unity (HDRP)": "Unity (HDRP)",
    "DirectX normals, ORM packing, T_Name_Suffix naming": "Нормали DirectX, упаковка ORM, имена T_Имя_Суффикс",
    "OpenGL normals, metallic + smoothness in alpha": "Нормали OpenGL, metallic + smoothness в альфе",
    "OpenGL normals, HDRP mask map": "Нормали OpenGL, mask map для HDRP",
    "OpenGL normals, ORM packing": "Нормали OpenGL, упаковка ORM",
    "OpenGL normals, separate maps up to 1024px": "Нормали OpenGL, отдельные карты до 1024 px",
    "OpenGL normals, glTF occlusion-roughness-metallic packing": "Нормали OpenGL, упаковка glTF occlusion-roughness-metallic",
    "Mesh maps named for Substance 3D Painter, 16-bit normals": "Карты меша с именами для Substance 3D Painter, 16-бит нормали",
    "Mesh maps named for Marmoset Toolbag, 16-bit normals": "Карты меша с именами для Marmoset Toolbag, 16-бит нормали",
    "Keep the current naming and packing settings": "Оставить текущие имена и упаковку",
}

# Operator buttons that use bl_label are looked up in the "Operator" context.
OPERATOR_LABELS = (
    "Bake", "Cancel Bake", "Open Folder", "Open Log", "Detect Pairs", "Add Pair from Selection", "Remove Pair",
    "Clear Pairs", "Edit Pair Objects", "Select Pair Objects", "Set Texture Set", "Run Pre-flight Check", "Fix",
    "Select Object", "Update Cage Preview", "Estimate Extrusion", "Map Preset", "Reset to Preset",
    "Restore Original Materials", "Import Texture Set", "Export",
)


def _build():
    table = {}
    for en, ru in RU.items():
        table[("*", en)] = ru
    for en in OPERATOR_LABELS:
        table[("Operator", en)] = RU[en]
    return {"ru_RU": table}


translations_dict = _build()


def register():
    bpy.app.translations.register(__package__, translations_dict)


def unregister():
    bpy.app.translations.unregister(__package__)
