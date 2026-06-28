<div align="center">

<img src="docs/imagura-logo.png" alt="Imagura" width="160" height="160" />

# Imagura

**Быстрый асинхронный просмотрщик изображений на Python и raylib.**

[![version](https://img.shields.io/badge/version-2.1.0-blue)](pyproject.toml)
[![python](https://img.shields.io/badge/python-%E2%89%A53.10-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![raylib](https://img.shields.io/badge/built%20with-raylib%205-white)](https://www.raylib.com/)
[![platform](https://img.shields.io/badge/platform-Windows-0078D6?logo=windows&logoColor=white)](#установка)

Русский · [English](README_EN.md)

</div>

---

## О проекте

Imagura — лёгкий просмотрщик изображений с упором на скорость и плавность. Декодирование
и загрузка идут в фоновых потоках, тяжёлые полноразмерные текстуры и кадры анимаций
кэшируются, а интерфейс (галерея, зум, оверлеи) остаётся отзывчивым даже на больших
файлах. Приложение работает в полноэкранном прозрачном режиме и в окне.

## Возможности

- **Асинхронная загрузка** — декодирование на CPU и выгрузка в GPU вынесены в фоновые
  потоки; UI не подвисает на тяжёлых картинках.
- **Форматы** — PNG, JPG/JPEG, BMP, GIF (с анимацией), TGA, QOI, WebP (с анимацией).
- **Галерея с сортировкой** — по имени, дате изменения, дате создания, размеру, типу и
  дате съёмки (EXIF); по возрастанию/убыванию, с сохранением открытого файла после
  пересортировки.
- **Зум** — колесом и клавишами, привязка к точке под курсором, переключение режимов
  1:1 / «вписать» / произвольный.
- **Кэши** — FIFO-кэш полноразмерных текстур в VRAM и кэш декодированных кадров анимаций
  в RAM; повторное открытие не показывает индикатор загрузки.
- **EXIF HUD** — оверлей с метаданными снимка.
- **Юникод** — корректные имена файлов на кириллице и других алфавитах.
- **Настройки** — модальное окно настроек; значения сохраняются в пользовательский JSON
  (`%APPDATA%\Imagura\settings.json`), а не в код.
- **Удобства** — панель инструментов, контекстное меню, удаление в корзину, работа с
  буфером обмена, локализация (i18n).
- **Прозрачный фон** — полноэкранный режим с прозрачным фреймбуфером.

## Установка

### Готовый установщик (рекомендуется)

Скачайте `Imagura-2.1.0-setup.exe` со страницы
[**Releases**](https://github.com/Barmagloth/Imagura/releases) и запустите.
Установщик создаёт ярлык в меню «Пуск», по желанию — на рабочем столе, регистрирует
ассоциации с поддерживаемыми форматами (через «Открыть с помощью», без перехвата
текущих умолчаний) и чисто удаляется.

### Запуск из исходников

Требуется Python ≥ 3.10 (Windows).

```bat
git clone https://github.com/Barmagloth/Imagura.git
cd Imagura
py -m pip install -e .[exif]
python -B imagura2.py
```

Открыть конкретный файл или папку:

```bat
python -B imagura2.py "D:\Photos\picture.png"
python -B imagura2.py "D:\Photos"
```

## Управление

| Действие | Клавиши / мышь |
| --- | --- |
| Следующее / предыдущее изображение | `→` / `←`, `D` / `A`, клик по краю экрана |
| Зум | колесо мыши, `↑` / `↓`, `W` / `S` |
| Переключить режим зума (1:1 / вписать / свой) | `Z` |
| Панорамирование | перетаскивание левой кнопкой |
| Контекстное меню | правая кнопка |
| Окно / полноэкранный режим | `F` |
| Показать/скрыть HUD | `I` |
| Показать/скрыть имя файла | `N` |
| Сменить фон | `V` |
| Удалить изображение (в корзину) | `Delete` |
| Выход | `Esc` |

## Сборка под Windows

Подробности — в [`packaging/windows/README.md`](packaging/windows/README.md).
Кратко:

```bat
py -m pip install -e .[windows-build,exif]
:: 1) собрать one-dir приложение (PyInstaller)
python -B tools\build_windows_exe.py --clean
:: 2) собрать установщик (нужен Inno Setup 6/7, ISCC)
iscc packaging\windows\imagura.iss
```

Результат: `dist\Imagura\Imagura.exe` и `dist\installer\Imagura-2.1.0-setup.exe`.

## Документация

- [`imagura/ARCHITECTURE.md`](imagura/ARCHITECTURE.md) — границы модулей и архитектура.
- [`imagura/HANDOFF.md`](imagura/HANDOFF.md) — состояние, запуск, тесты, бэклог.
- [`docs/QA_CHECKLIST.md`](docs/QA_CHECKLIST.md) — чек-лист ручного QA.
- [`docs/profiling.md`](docs/profiling.md) — профилирование и заметки по производительности.

## Тесты

```bat
python -B tools\run_smoke_tests.py --timeout 10
```

## Автор

**Barmagloth** — [github.com/Barmagloth](https://github.com/Barmagloth)
