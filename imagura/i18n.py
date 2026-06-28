"""Minimal interface localization (RU/EN).

Leaf module: imports only ``config``, ``user_settings`` and ``logging``. UI code
calls ``tr(key)`` at render time, so switching the language updates the whole
interface live. The current language is mirrored into ``config.LANGUAGE`` and
persisted to the user settings file under the ``LANGUAGE`` key.
"""

from __future__ import annotations

from . import config as cfg
from .logging import log
from .user_settings import load_user_settings, save_user_setting

LANGUAGES = ("ru", "en")

# key -> {"ru": ..., "en": ...}
STRINGS: dict[str, dict[str, str]] = {
    # --- Tabs ---
    "tab.general": {"ru": "Общие", "en": "General"},
    "tab.animation": {"ru": "Анимация", "en": "Animation"},
    "tab.interface": {"ru": "Интерфейс", "en": "Interface"},
    "tab.gallery": {"ru": "Галерея", "en": "Gallery"},
    "tab.input": {"ru": "Ввод", "en": "Input"},
    "tab.limits": {"ru": "Лимиты", "en": "Limits"},
    "tab.help": {"ru": "Справка", "en": "Help"},
    "tab.about": {"ru": "О программе", "en": "About"},

    # --- General ---
    "hdr.language": {"ru": "Язык", "en": "Language"},
    "fld.language": {"ru": "Язык интерфейса", "en": "Interface language"},
    "hdr.performance": {"ru": "Производительность", "en": "Performance"},
    "fld.target_fps": {"ru": "Целевой FPS", "en": "Target FPS"},
    "fld.async_workers": {"ru": "Асинхронные потоки", "en": "Async workers"},
    "hdr.scaling": {"ru": "Масштабирование", "en": "Scaling"},
    "fld.fit_default": {"ru": "Масштаб по умолчанию", "en": "Default scale"},
    "fld.fit_open": {"ru": "Масштаб при открытии", "en": "Open scale"},
    "fld.max_zoom": {"ru": "Макс. зум", "en": "Max zoom"},
    "fld.zoom_keys": {"ru": "Шаг зума (клавиши)", "en": "Zoom step (keys)"},
    "fld.zoom_wheel": {"ru": "Шаг зума (колесо)", "en": "Zoom step (wheel)"},

    # --- Animation ---
    "hdr.anim_times": {"ru": "Время анимации (мс)", "en": "Animation time (ms)"},
    "fld.anim_switch_keys": {"ru": "Переключение (клавиши)", "en": "Switch (keys)"},
    "fld.anim_switch_gallery": {"ru": "Переключение (галерея)", "en": "Switch (gallery)"},
    "fld.anim_open": {"ru": "Открытие изображения", "en": "Image open"},
    "fld.anim_zoom": {"ru": "Анимация зума", "en": "Zoom animation"},
    "fld.anim_toggle_zoom": {"ru": "Переключение зума", "en": "Zoom toggle"},
    "fld.gallery_slide": {"ru": "Слайд галереи", "en": "Gallery slide"},
    "fld.toolbar_slide": {"ru": "Слайд тулбара", "en": "Toolbar slide"},

    # --- Interface ---
    "hdr.font": {"ru": "Шрифт", "en": "Font"},
    "fld.font_size": {"ru": "Размер шрифта", "en": "Font size"},
    "hdr.toolbar": {"ru": "Тулбар", "en": "Toolbar"},
    "fld.toolbar_height": {"ru": "Высота тулбара", "en": "Toolbar height"},
    "fld.toolbar_btn_radius": {"ru": "Радиус кнопок", "en": "Button radius"},
    "fld.toolbar_btn_spacing": {"ru": "Отступ кнопок", "en": "Button spacing"},
    "fld.toolbar_bg_alpha": {"ru": "Прозрачность фона", "en": "Background opacity"},
    "hdr.close_btn": {"ru": "Кнопка закрытия", "en": "Close button"},
    "fld.close_btn_radius": {"ru": "Радиус кнопки", "en": "Button radius"},
    "fld.close_btn_margin": {"ru": "Отступ от края", "en": "Edge margin"},
    "hdr.overlays": {"ru": "Оверлеи", "en": "Overlays"},
    "fld.show_scale_overlay": {"ru": "Индикатор масштаба", "en": "Scale indicator"},
    "hdr.background": {"ru": "Фон", "en": "Background"},
    "fld.blur": {"ru": "Размытие фона", "en": "Background blur"},

    # --- Gallery ---
    "hdr.sizes": {"ru": "Размеры", "en": "Sizes"},
    "fld.gallery_height_frac": {"ru": "Высота (доля экрана)", "en": "Height (screen fraction)"},
    "fld.gallery_trigger_frac": {"ru": "Зона активации (доля)", "en": "Trigger zone (fraction)"},
    "fld.gallery_thumb_spacing": {"ru": "Отступ миниатюр", "en": "Thumbnail spacing"},
    "fld.gallery_min_scale": {"ru": "Мин. масштаб миниатюр", "en": "Min thumbnail scale"},
    "fld.gallery_min_alpha": {"ru": "Мин. прозрачность", "en": "Min opacity"},
    "hdr.thumbnails": {"ru": "Миниатюры", "en": "Thumbnails"},
    "fld.thumb_cache_limit": {"ru": "Лимит кэша", "en": "Cache limit"},
    "fld.thumb_padding": {"ru": "Отступ внутри", "en": "Inner padding"},
    "fld.thumb_preload": {"ru": "Предзагрузка", "en": "Preload span"},

    # --- Input ---
    "hdr.mouse": {"ru": "Мышь", "en": "Mouse"},
    "fld.double_click_ms": {"ru": "Двойной клик (мс)", "en": "Double-click (ms)"},
    "fld.idle_threshold": {"ru": "Таймаут бездействия (с)", "en": "Idle timeout (s)"},
    "hdr.keyboard": {"ru": "Клавиатура", "en": "Keyboard"},
    "fld.key_repeat_delay": {"ru": "Задержка повтора (с)", "en": "Repeat delay (s)"},
    "fld.key_repeat_interval": {"ru": "Интервал повтора (с)", "en": "Repeat interval (s)"},
    "hdr.navigation": {"ru": "Навигация", "en": "Navigation"},
    "fld.nav_btn_radius": {"ru": "Радиус кнопок навиг.", "en": "Nav button radius"},
    "fld.nav_edge_min": {"ru": "Мин. зона края (пкс)", "en": "Min edge zone (px)"},

    # --- Limits ---
    "hdr.images": {"ru": "Изображения", "en": "Images"},
    "fld.max_image_dim": {"ru": "Макс. размер (пкс)", "en": "Max size (px)"},
    "fld.max_file_size": {"ru": "Макс. размер файла (МБ)", "en": "Max file size (MB)"},
    "fld.heavy_file_size": {"ru": "Тяжёлый файл (МБ)", "en": "Heavy file (MB)"},
    "fld.heavy_min_side": {"ru": "Тяжёлый мин. сторона", "en": "Heavy min side"},
    "hdr.cache": {"ru": "Кэш", "en": "Cache"},
    "fld.full_cache_mb": {"ru": "Кэш изображений (МБ)", "en": "Full image cache (MB)"},
    "fld.full_cache_items": {"ru": "Кэш изображений (шт)", "en": "Full image cache items"},
    "fld.anim_cache_mb": {"ru": "Кэш GIF (МБ)", "en": "GIF frame cache (MB)"},
    "fld.anim_cache_items": {"ru": "Кэш GIF (шт)", "en": "GIF frame cache items"},
    "fld.gif_max_frames": {"ru": "Макс. кадров GIF", "en": "GIF max frames"},
    "fld.gif_decode_mb": {"ru": "Лимит декода GIF (МБ)", "en": "GIF decode limit (MB)"},
    "hdr.window": {"ru": "Окно", "en": "Window"},
    "fld.min_window_w": {"ru": "Мин. ширина окна", "en": "Min window width"},
    "fld.min_window_h": {"ru": "Мин. высота окна", "en": "Min window height"},
    "fld.gallery_min_h": {"ru": "Мин. высота галереи", "en": "Min gallery height"},

    # --- Settings chrome ---
    "settings.title": {"ru": "Настройки", "en": "Settings"},
    "foot.enter": {"ru": "сохранить", "en": "save"},
    "foot.cancel": {"ru": "отмена", "en": "cancel"},
    "foot.next_field": {"ru": "след. поле", "en": "next field"},
    "foot.home_end": {"ru": "начало/конец", "en": "home/end"},
    "foot.select": {"ru": "выделение", "en": "select"},
    "foot.edit": {"ru": "редактировать", "en": "edit"},
    "foot.close": {"ru": "закрыть", "en": "close"},
    "foot.scroll": {"ru": "прокрутка", "en": "scroll"},
    "lbl.click": {"ru": "Клик", "en": "Click"},
    "lbl.wheel": {"ru": "Колесо", "en": "Wheel"},

    # --- Toolbar tooltips ---
    "tip.settings": {"ru": "Настройки", "en": "Settings"},
    "tip.rotate_left": {"ru": "Повернуть влево", "en": "Rotate left"},
    "tip.rotate_right": {"ru": "Повернуть вправо", "en": "Rotate right"},
    "tip.flip": {"ru": "Отразить", "en": "Flip"},

    # --- Context menu ---
    "menu.copy": {"ru": "Копировать", "en": "Copy"},

    # --- Empty screen / dialogs / overlays ---
    "empty.no_images": {"ru": "Изображения не найдены", "en": "No images found"},
    "empty.hint": {
        "ru": "Выберите изображение, передайте путь к файлу/папке или нажмите Esc.",
        "en": "Choose an image, pass a file/folder path, or press Esc to close.",
    },
    "empty.open": {"ru": "Открыть изображение...", "en": "Open image..."},
    "empty.exit": {"ru": "Выход", "en": "Exit"},
    "dialog.open_image": {"ru": "Открыть изображение", "en": "Open image"},
    "misc.loading": {"ru": "Загрузка...", "en": "Loading..."},
    "zoom.fit": {"ru": "Вписать", "en": "Fit"},
    "zoom.custom": {"ru": "Произвольно", "en": "Custom"},
    "zoom.real": {"ru": "1:1", "en": "Real"},

    # --- Help (hotkeys) ---
    "help.section_keys": {"ru": "Клавиатура", "en": "Keyboard"},
    "help.section_mouse": {"ru": "Мышь и жесты", "en": "Mouse & gestures"},
    "help.next": {"ru": "Следующее изображение", "en": "Next image"},
    "help.prev": {"ru": "Предыдущее изображение", "en": "Previous image"},
    "help.zoom_in": {"ru": "Приблизить", "en": "Zoom in"},
    "help.zoom_out": {"ru": "Отдалить", "en": "Zoom out"},
    "help.toggle_zoom": {"ru": "Переключить зум (1:1 / Вписать)", "en": "Toggle zoom (1:1 / Fit)"},
    "help.toggle_window": {"ru": "Оконный режим", "en": "Windowed mode"},
    "help.hud": {"ru": "Показать/скрыть HUD", "en": "Toggle HUD"},
    "help.filename": {"ru": "Показать/скрыть имя файла", "en": "Toggle filename"},
    "help.bg": {"ru": "Сменить фон", "en": "Cycle background"},
    "help.delete": {"ru": "Удалить в корзину", "en": "Delete to trash"},
    "help.close": {"ru": "Закрыть", "en": "Close"},
    "help.dblclick": {"ru": "Переключить зум", "en": "Toggle zoom"},
    "help.wheel_zoom": {"ru": "Зум / прокрутка галереи", "en": "Zoom / scroll gallery"},
    "help.drag": {"ru": "Панорамирование", "en": "Pan"},
    "help.edge": {"ru": "Навигация по краям", "en": "Edge-click navigation"},
    "help.rclick": {"ru": "Контекстное меню", "en": "Context menu"},
    "key.right": {"ru": "Вправо", "en": "Right"},
    "key.left": {"ru": "Влево", "en": "Left"},
    "key.up": {"ru": "Вверх", "en": "Up"},
    "key.down": {"ru": "Вниз", "en": "Down"},
    "g.dblclick": {"ru": "Двойной клик", "en": "Double-click"},
    "g.wheel": {"ru": "Колесо", "en": "Wheel"},
    "g.drag": {"ru": "Перетаскивание ЛКМ", "en": "LMB drag"},
    "g.rclick": {"ru": "Правый клик", "en": "Right click"},
    "g.edge": {"ru": "Клик по краю", "en": "Edge click"},

    # --- About ---
    "about.tagline": {"ru": "Просмотрщик изображений", "en": "Image viewer"},
    "about.version": {"ru": "Версия", "en": "Version"},
    "about.author": {"ru": "Автор", "en": "Author"},
    "about.license": {"ru": "Лицензия", "en": "License"},
    "about.date": {"ru": "Дата", "en": "Date"},
}


def get_language() -> str:
    lang = getattr(cfg, "LANGUAGE", "ru")
    return lang if lang in LANGUAGES else "ru"


def set_language(lang: str) -> None:
    """Set the current UI language (in-memory). Does not persist."""
    if lang not in LANGUAGES:
        return
    cfg.LANGUAGE = lang


def persist_language(lang: str) -> None:
    """Set and persist the UI language to the user settings file."""
    set_language(lang)
    try:
        save_user_setting("LANGUAGE", lang)
        log(f"[I18N] Language set to {lang}")
    except Exception as exc:
        log(f"[I18N][WARN] Failed to persist language: {exc!r}")


def load_persisted_language() -> None:
    """Load the persisted UI language from user settings into config (startup)."""
    try:
        saved = load_user_settings() or {}
    except Exception:
        saved = {}
    lang = saved.get("LANGUAGE")
    if lang in LANGUAGES:
        cfg.LANGUAGE = lang


def tr(key: str) -> str:
    """Translate a key to the current language (fallback: EN, then the key)."""
    entry = STRINGS.get(key)
    if not entry:
        return key
    return entry.get(get_language()) or entry.get("en") or key
