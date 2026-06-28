"""Settings modal: input handling and rendering (with i18n + Help/About tabs)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .. import config as cfg
from ..config import (
    SETTINGS_CONTENT_BORDER_MARGIN,
    SETTINGS_CONTENT_FOOTER_HEIGHT,
    SETTINGS_CONTENT_ITEM_HEIGHT,
    SETTINGS_CONTENT_PADDING_X,
    SETTINGS_CONTENT_SUB_INDENT,
    SETTINGS_CONTENT_VALUE_MARGIN,
    SETTINGS_CONTENT_VALUE_WIDTH,
    SETTINGS_MODAL_CLOSE_MARGIN,
    SETTINGS_MODAL_CLOSE_SIZE,
    SETTINGS_MODAL_COLORS_DARK,
    SETTINGS_MODAL_COLORS_LIGHT,
    SETTINGS_MODAL_COLORS_TRANSPARENT,
    SETTINGS_MODAL_HEIGHT,
    SETTINGS_MODAL_SHADOW_OFFSET,
    SETTINGS_MODAL_TITLE_Y,
    SETTINGS_MODAL_WIDTH,
    SETTINGS_TAB_GAP,
    SETTINGS_TAB_HEIGHT,
    SETTINGS_TAB_PADDING,
    SETTINGS_TAB_START_X,
    SETTINGS_TAB_TOP_Y,
)
from ..i18n import LANGUAGES, get_language, persist_language, tr
from ..logging import log, now
from ..rl_compat import draw_text as RL_DrawText
from ..rl_compat import make_color as RL_Color
from ..rl_compat import make_vec2 as RL_V2
from ..rl_compat import rl
from ..settings_persistence import (
    SETTINGS_TABS,
    is_editable_item,
    save_config_value_impl,
    validate_settings_value,
)

if TYPE_CHECKING:
    from ..state import AppState


def _save_config_value(config_key: str, value, val_type: type, state: "AppState") -> bool:
    """Save through imagura2's shim when available so runtime globals stay mirrored.

    Falls back to the pure persistence impl if imagura2 has not been imported
    (e.g. when the UI module is exercised in isolation).
    """
    import sys

    shim = getattr(sys.modules.get("imagura2"), "save_config_value", None)
    if shim is not None:
        return shim(config_key, value, val_type, state)
    return save_config_value_impl(config_key, value, val_type, state)


def get_settings_color_scheme(state: "AppState") -> dict:
    """Get color scheme based on current background mode. Colors defined in config.py."""
    bg_color = state.ui.bg_color
    opacity = state.ui.bg_current_opacity

    is_transparent = opacity < 1.0
    is_light_bg = sum(bg_color) > 380  # White is 765, black is 0

    if is_transparent:
        return SETTINGS_MODAL_COLORS_TRANSPARENT
    elif is_light_bg:
        return SETTINGS_MODAL_COLORS_LIGHT
    else:
        return SETTINGS_MODAL_COLORS_DARK


# ──────────────────────────────────────────────────────────────────────────────
# Layout helpers
# ──────────────────────────────────────────────────────────────────────────────

def _modal_rect(state: "AppState"):
    win_w = SETTINGS_MODAL_WIDTH
    win_h = SETTINGS_MODAL_HEIGHT
    win_x = (state.screenW - win_w) // 2
    win_y = (state.screenH - win_h) // 2
    return win_x, win_y, win_w, win_h


def _text_w(state: "AppState", text: str, size: int) -> int:
    if state.unicode_font:
        try:
            return int(rl.MeasureTextEx(state.unicode_font, text.encode("utf-8"), size, 1.0).x)
        except Exception:
            pass
    return len(text) * (size // 2)


def _tab_font(state: "AppState") -> int:
    font_size = max(16, min(22, cfg.FONT_DISPLAY_SIZE - 4))
    return max(14, font_size - 2)


def _tab_layout(state: "AppState"):
    """Lay out the tab strip, wrapping to new rows when tabs exceed the modal
    width (Russian labels + Help/About overflow a single row). Returns
    (positions, content_y) where positions[i] = (x, y, w) for SETTINGS_TABS[i]
    and content_y is the top of the content area (below the last tab row)."""
    win_x, win_y, win_w, _win_h = _modal_rect(state)
    tab_font = _tab_font(state)
    tab_h = SETTINGS_TAB_HEIGHT
    row_gap = 2
    start_x = win_x + SETTINGS_TAB_START_X
    max_right = win_x + win_w - SETTINGS_TAB_START_X
    top_y = win_y + SETTINGS_TAB_TOP_Y

    positions = []
    x = start_x
    y = top_y
    for tab in SETTINGS_TABS:
        tw = int(_text_w(state, tr(tab["name"]), tab_font)) + SETTINGS_TAB_PADDING * 2
        if x != start_x and x + tw > max_right:
            x = start_x
            y += tab_h + row_gap
        positions.append((x, y, tw))
        x += tw + SETTINGS_TAB_GAP

    last_y = positions[-1][1] if positions else top_y
    content_y = last_y + tab_h
    return positions, content_y


def _draw_backdrop_dim(state: "AppState", color) -> None:
    """Dim everything behind the modal WITHOUT punching the transparent
    framebuffer's alpha. A plain translucent rect (BLEND_ALPHA) lowers the
    destination alpha, so the opaque image would turn see-through to the desktop.
    Use separate blend factors: normal alpha-blend for RGB, but keep the
    destination alpha (src=ZERO, dst=ONE). Falls back to a plain rect."""
    sw, sh = state.screenW, state.screenH
    GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA = 0x0302, 0x0303
    GL_ZERO, GL_ONE, GL_FUNC_ADD = 0, 1, 0x8006
    try:
        rl.rlSetBlendFactorsSeparate(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA,
                                     GL_ZERO, GL_ONE, GL_FUNC_ADD, GL_FUNC_ADD)
        rl.BeginBlendMode(rl.BLEND_CUSTOM_SEPARATE)
        rl.DrawRectangle(0, 0, sw, sh, RL_Color(*color))
        rl.EndBlendMode()
    except Exception:
        rl.DrawRectangle(0, 0, sw, sh, RL_Color(*color))


def _pt_in(mouse, rect) -> bool:
    x, y, w, h = rect
    return x <= mouse.x <= x + w and y <= mouse.y <= y + h


def _lang_row_rects(state: "AppState"):
    """RU/EN segment rects for the language selector row, or None if not visible."""
    settings = state.ui.settings
    tab = SETTINGS_TABS[settings.active_tab]
    if tab.get("type") == "info":
        return None
    win_x, win_y, win_w, win_h = _modal_rect(state)
    _positions, content_y = _tab_layout(state)
    item_h = SETTINGS_CONTENT_ITEM_HEIGHT
    val_w = SETTINGS_CONTENT_VALUE_WIDTH
    val_x = win_x + win_w - val_w - SETTINGS_CONTENT_VALUE_MARGIN

    item_y = content_y + 5 - settings.scroll_offset
    for item in tab["items"]:
        if item[2] == "lang":
            seg_w = val_w // 2
            ru = (val_x, item_y + 4, seg_w, item_h - 8)
            en = (val_x + seg_w, item_y + 4, val_w - seg_w, item_h - 8)
            return ru, en, item_y, item_h
        item_y += item_h
    return None


def _content_row_count(tab) -> int:
    if tab.get("type") == "info":
        return len(_info_rows(tab))
    return len(tab["items"])


# ──────────────────────────────────────────────────────────────────────────────
# Info-tab content (Help / About)
# ──────────────────────────────────────────────────────────────────────────────

def _help_rows():
    """Rows for the Help tab. ('h', header_key) | ('k', action_key, keys) | ('g', action_key, gesture_key)."""
    return [
        ("h", "help.section_keys"),
        ("k", "help.next", f"{tr('key.right')} / D"),
        ("k", "help.prev", f"{tr('key.left')} / A"),
        ("k", "help.zoom_in", f"{tr('key.up')} / W"),
        ("k", "help.zoom_out", f"{tr('key.down')} / S"),
        ("k", "help.toggle_zoom", "Z"),
        ("k", "help.toggle_window", "F"),
        ("k", "help.hud", "I"),
        ("k", "help.filename", "N"),
        ("k", "help.bg", "V"),
        ("k", "help.delete", "Del"),
        ("k", "help.close", "Esc"),
        ("h", "help.section_mouse"),
        ("g", "help.dblclick", "g.dblclick"),
        ("g", "help.wheel_zoom", "g.wheel"),
        ("g", "help.drag", "g.drag"),
        ("g", "help.edge", "g.edge"),
        ("g", "help.rclick", "g.rclick"),
    ]


def _about_rows():
    """Rows for the About tab. ('title', text) | ('sub', key) | ('kv', key, value) | ('gap',)."""
    return [
        ("title", cfg.APP_NAME),
        ("sub", "about.tagline"),
        ("gap",),
        ("kv", "about.version", cfg.APP_VERSION),
        ("kv", "about.author", cfg.APP_AUTHOR),
        ("kv", "about.license", cfg.APP_LICENSE),
        ("kv", "about.date", cfg.APP_YEAR),
    ]


def _info_rows(tab):
    content = tab.get("content")
    if content == "help":
        return _help_rows()
    if content == "about":
        return _about_rows()
    return []


# ──────────────────────────────────────────────────────────────────────────────
# Input
# ──────────────────────────────────────────────────────────────────────────────

def handle_settings_input(state: "AppState") -> bool:
    """Handle input for settings window with full text editing support."""
    settings = state.ui.settings
    if not settings.visible:
        return False

    mouse = rl.GetMousePosition()

    win_x, win_y, win_w, win_h = _modal_rect(state)

    font_size = max(16, min(22, cfg.FONT_DISPLAY_SIZE - 4))
    small_font = max(14, font_size - 2)

    tab_positions, content_y = _tab_layout(state)
    tab_h = SETTINGS_TAB_HEIGHT

    item_h = SETTINGS_CONTENT_ITEM_HEIGHT
    val_w = SETTINGS_CONTENT_VALUE_WIDTH
    val_x = win_x + win_w - val_w - SETTINGS_CONTENT_VALUE_MARGIN

    close_x = win_x + win_w - SETTINGS_MODAL_CLOSE_SIZE - SETTINGS_MODAL_CLOSE_MARGIN
    close_y_btn = win_y + SETTINGS_MODAL_TITLE_Y

    if rl.IsMouseButtonPressed(rl.MOUSE_BUTTON_LEFT):
        # Close button
        if (close_x <= mouse.x <= close_x + SETTINGS_MODAL_CLOSE_SIZE and
                close_y_btn <= mouse.y <= close_y_btn + SETTINGS_MODAL_CLOSE_SIZE):
            settings.hide()
            return True

        # Tab clicks - wrapped tab positions (x, y, w per tab, multi-row aware)
        for i, (tx, ty, tw) in enumerate(tab_positions):
            if tx <= mouse.x <= tx + tw and ty <= mouse.y <= ty + tab_h:
                if i != settings.active_tab:
                    if settings.editing_item >= 0:
                        _save_current_edit_for_tab(state, settings.active_tab)
                    settings.active_tab = i
                    settings.editing_item = -1
                    settings.edit_state.reset()
                    settings.scroll_offset = 0
                return True

        # Language selector row (RU/EN segments)
        lang_rects = _lang_row_rects(state)
        if lang_rects:
            ru_rect, en_rect, _ry, _ih = lang_rects
            target = None
            if _pt_in(mouse, ru_rect):
                target = "ru"
            elif _pt_in(mouse, en_rect):
                target = "en"
            if target is not None:
                if target != get_language():
                    if settings.editing_item >= 0:
                        _save_current_edit_for_tab(state, settings.active_tab)
                        settings.editing_item = -1
                        settings.edit_state.reset()
                    persist_language(target)
                return True

    current_tab = SETTINGS_TABS[settings.active_tab]

    # Info tabs (Help/About): only scroll, ESC and tab switching apply.
    if current_tab.get("type") == "info":
        if rl.IsKeyPressed(rl.KEY_ESCAPE):
            settings.hide()
            return True
        content_h = win_h - (content_y - win_y) - SETTINGS_CONTENT_FOOTER_HEIGHT
        wheel = rl.GetMouseWheelMove()
        if wheel != 0:
            max_scroll = max(0, _content_row_count(current_tab) * item_h - content_h)
            settings.scroll_offset = max(0, min(max_scroll, settings.scroll_offset - int(wheel * 40)))
        return True

    tab_items = current_tab["items"]

    # Count editable items in current tab
    total_editable = sum(1 for item in tab_items if is_editable_item(item))

    shift_held = rl.IsKeyDown(rl.KEY_LEFT_SHIFT) or rl.IsKeyDown(rl.KEY_RIGHT_SHIFT)
    ctrl_held = rl.IsKeyDown(rl.KEY_LEFT_CONTROL) or rl.IsKeyDown(rl.KEY_RIGHT_CONTROL)

    # Handle editing mode
    if settings.editing_item >= 0:
        edit = settings.edit_state

        if rl.IsMouseButtonPressed(rl.MOUSE_BUTTON_LEFT):
            item_y = content_y - settings.scroll_offset
            editable_idx = 0

            clicked_field = -1
            clicked_bool = False
            for item in tab_items:
                if is_editable_item(item):
                    if (val_x - 5 <= mouse.x <= val_x + val_w + 10 and
                            item_y + 2 <= mouse.y <= item_y + item_h - 2):
                        clicked_field = editable_idx
                        clicked_bool = (item[2] == bool)
                        break
                    editable_idx += 1
                item_y += item_h

            if clicked_bool and clicked_field >= 0:
                if _save_current_edit_for_tab(state, settings.active_tab):
                    settings.editing_item = -1
                    edit.reset()
                    _editable = 0
                    for _item in tab_items:
                        if is_editable_item(_item):
                            if _editable == clicked_field:
                                _cur = getattr(cfg, _item[1], False)
                                _save_config_value(_item[1], not _cur, bool, state)
                                break
                            _editable += 1
                return True
            elif clicked_field == settings.editing_item:
                edit.clear_selection()
            elif clicked_field >= 0:
                if _save_current_edit_for_tab(state, settings.active_tab):
                    _start_editing_field(state, settings.active_tab, clicked_field)
                return True
            else:
                if _save_current_edit_for_tab(state, settings.active_tab):
                    settings.editing_item = -1
                    edit.reset()
                return True

        if rl.IsKeyPressed(rl.KEY_LEFT):
            edit.move_cursor_left(shift_held)
            return True
        if rl.IsKeyPressed(rl.KEY_RIGHT):
            edit.move_cursor_right(shift_held)
            return True
        if rl.IsKeyPressed(rl.KEY_HOME):
            edit.move_cursor_home(shift_held)
            return True
        if rl.IsKeyPressed(rl.KEY_END):
            edit.move_cursor_end(shift_held)
            return True
        if ctrl_held and rl.IsKeyPressed(rl.KEY_A):
            edit.select_all()
            return True
        if rl.IsKeyPressed(rl.KEY_TAB):
            if _save_current_edit_for_tab(state, settings.active_tab):
                if total_editable > 0:
                    if shift_held:
                        new_idx = (settings.editing_item - 1) % total_editable
                    else:
                        new_idx = (settings.editing_item + 1) % total_editable
                    _start_editing_field(state, settings.active_tab, new_idx)
            return True

        # Text input
        key = rl.GetCharPressed()
        while key > 0:
            if (48 <= key <= 57) or key == 46 or key == 45:
                edit.insert_text(chr(key))
            key = rl.GetCharPressed()

        if rl.IsKeyPressed(rl.KEY_BACKSPACE):
            edit.delete_char_before()
            return True
        if rl.IsKeyPressed(rl.KEY_DELETE):
            edit.delete_char_after()
            return True
        if rl.IsKeyPressed(rl.KEY_ENTER):
            if _save_current_edit_for_tab(state, settings.active_tab):
                settings.editing_item = -1
                edit.reset()
            return True
        if rl.IsKeyPressed(rl.KEY_ESCAPE):
            settings.editing_item = -1
            edit.reset()
            return True

        return True  # Consume all input while editing

    # ESC closes settings when not editing
    if rl.IsKeyPressed(rl.KEY_ESCAPE):
        settings.hide()
        return True

    # Mouse wheel scrolling
    content_h = win_h - (content_y - win_y) - SETTINGS_CONTENT_FOOTER_HEIGHT
    wheel = rl.GetMouseWheelMove()
    if wheel != 0:
        max_scroll = max(0, _content_row_count(current_tab) * item_h - content_h)
        settings.scroll_offset = max(0, min(max_scroll, settings.scroll_offset - int(wheel * 40)))
        return True

    # Click to start editing
    if rl.IsMouseButtonPressed(rl.MOUSE_BUTTON_LEFT):
        item_y = content_y - settings.scroll_offset
        editable_idx = 0

        for item in tab_items:
            label, config_key, val_type, min_val, max_val = item

            if is_editable_item(item):
                in_row = (item_y + 2 <= mouse.y <= item_y + item_h - 2 and
                          content_y <= mouse.y <= content_y + content_h)
                if val_type == bool:
                    label_x = win_x + SETTINGS_CONTENT_PADDING_X + SETTINGS_CONTENT_SUB_INDENT
                    if in_row and label_x <= mouse.x <= val_x + val_w + 10:
                        current_val = getattr(cfg, config_key, False)
                        _save_config_value(config_key, not current_val, bool, state)
                        return True
                else:
                    if (val_x - 5 <= mouse.x <= val_x + val_w + 10 and in_row):
                        _start_editing_field(state, settings.active_tab, editable_idx)
                        return True
                editable_idx += 1

            item_y += item_h

    return False


def _save_current_edit_for_tab(state: "AppState", tab_idx: int) -> bool:
    """Save current edit value for a specific tab. Returns True if successful."""
    settings = state.ui.settings
    if settings.editing_item < 0:
        return True

    tab = SETTINGS_TABS[tab_idx]
    if tab.get("type") == "info":
        return True
    tab_items = tab["items"]
    editable_idx = 0

    for item in tab_items:
        if is_editable_item(item):
            if editable_idx == settings.editing_item:
                label, config_key, val_type, min_val, max_val = item
                is_valid, parsed_val, error = validate_settings_value(
                    settings.edit_state.text, val_type, min_val, max_val
                )
                if is_valid:
                    _save_config_value(config_key, parsed_val, val_type, state)
                    log(f"[SETTINGS] Updated {config_key} = {parsed_val}")
                    return True
                else:
                    log(f"[SETTINGS] Validation failed: {error}")
                    return False
            editable_idx += 1
    return True


def _start_editing_field(state: "AppState", tab_idx: int, field_idx: int) -> None:
    """Start editing a specific field."""
    settings = state.ui.settings
    tab = SETTINGS_TABS[tab_idx]
    if tab.get("type") == "info":
        return
    tab_items = tab["items"]
    editable_idx = 0

    for item in tab_items:
        if is_editable_item(item):
            if editable_idx == field_idx:
                config_key = item[1]
                current_val = getattr(cfg, config_key, 0)
                settings.editing_item = field_idx
                settings.edit_state.set_text(str(current_val))
                return
            editable_idx += 1


# ──────────────────────────────────────────────────────────────────────────────
# Rendering
# ──────────────────────────────────────────────────────────────────────────────

def _draw_info_tab(state: "AppState", tab, win_x: int, win_y: int, win_w: int,
                   content_y: int, content_h: int, item_h: int, padding_x: int,
                   small_font: int, font_size: int, colors: dict) -> None:
    """Render a read-only info tab (Help / About) as text rows."""
    rows = _info_rows(tab)
    right_edge = win_x + win_w - SETTINGS_CONTENT_BORDER_MARGIN - 12
    item_y = content_y + 5 - state.ui.settings.scroll_offset

    for row in rows:
        kind = row[0]
        if not (item_y + item_h >= content_y and item_y <= content_y + content_h):
            item_y += item_h
            continue
        ty = item_y + (item_h - small_font) // 2

        if kind == "gap":
            pass
        elif kind == "h":
            _draw_settings_text(state, tr(row[1]), win_x + padding_x, ty, small_font, colors["header_text"])
        elif kind == "title":
            _draw_settings_text(state, row[1], win_x + padding_x,
                                item_y + (item_h - (font_size + 4)) // 2, font_size + 4, colors["title_color"])
        elif kind == "sub":
            _draw_settings_text(state, tr(row[1]), win_x + padding_x, ty, small_font, colors["hint_color"])
        elif kind in ("k", "g", "kv"):
            left = tr(row[1])
            # gesture rights are tr keys; key/kv rights are literal strings
            if kind == "g":
                right = tr(row[2])
            else:
                right = str(row[2])
            _draw_settings_text(state, left, win_x + padding_x + SETTINGS_CONTENT_SUB_INDENT,
                                ty, small_font, colors["text_color"])
            rw = _text_w(state, right, small_font)
            _draw_settings_text(state, right, right_edge - rw, ty, small_font, colors["value_color"])
        item_y += item_h


def draw_settings_window(state: "AppState"):
    """Draw settings window overlay with tabs and adaptive colors."""
    settings = state.ui.settings
    if not settings.visible:
        return

    colors = get_settings_color_scheme(state)

    win_x, win_y, win_w, win_h = _modal_rect(state)

    font_size = max(16, min(22, cfg.FONT_DISPLAY_SIZE - 4))
    small_font = max(14, font_size - 2)
    tab_font = small_font

    _draw_backdrop_dim(state, colors["overlay"])
    rl.DrawRectangle(win_x + SETTINGS_MODAL_SHADOW_OFFSET, win_y + SETTINGS_MODAL_SHADOW_OFFSET,
                     win_w, win_h, RL_Color(0, 0, 0, 40))
    rl.DrawRectangle(win_x, win_y, win_w, win_h, RL_Color(*colors["window_bg"]))
    rl.DrawRectangleLines(win_x, win_y, win_w, win_h, RL_Color(*colors["window_border"]))

    # Title
    _draw_settings_text(state, tr("settings.title"), win_x + 20, win_y + SETTINGS_MODAL_TITLE_Y,
                        font_size + 2, colors["title_color"])

    # Close button
    close_x = win_x + win_w - SETTINGS_MODAL_CLOSE_SIZE - SETTINGS_MODAL_CLOSE_MARGIN
    close_y = win_y + SETTINGS_MODAL_TITLE_Y
    mouse = rl.GetMousePosition()
    close_hover = (close_x <= mouse.x <= close_x + SETTINGS_MODAL_CLOSE_SIZE and
                   close_y <= mouse.y <= close_y + SETTINGS_MODAL_CLOSE_SIZE)
    close_color = colors["close_btn_hover"] if close_hover else colors["close_btn"]
    _draw_settings_text(state, "X", close_x + 8, close_y + 2, font_size + 4, close_color)

    tab_h = SETTINGS_TAB_HEIGHT
    tab_positions, content_y = _tab_layout(state)

    border_color = RL_Color(120, 120, 125, 255)
    content_h = win_h - (content_y - win_y) - SETTINGS_CONTENT_FOOTER_HEIGHT

    content_border_x = win_x + SETTINGS_CONTENT_BORDER_MARGIN
    content_border_w = win_w - SETTINGS_CONTENT_BORDER_MARGIN * 2
    # Content box border (left, right, bottom, top)
    rl.DrawLine(content_border_x, content_y, content_border_x, content_y + content_h, border_color)
    rl.DrawLine(content_border_x + content_border_w, content_y,
                content_border_x + content_border_w, content_y + content_h, border_color)
    rl.DrawLine(content_border_x, content_y + content_h,
                content_border_x + content_border_w, content_y + content_h, border_color)
    rl.DrawLine(content_border_x, content_y,
                content_border_x + content_border_w, content_y, border_color)

    # Draw tabs (wrapped into rows; the active tab is highlighted)
    for i, tab in enumerate(SETTINGS_TABS):
        tx, ty, tw = tab_positions[i]
        is_active = (i == settings.active_tab)
        if is_active:
            rl.DrawRectangle(tx, ty, tw, tab_h, RL_Color(*colors["tab_active"]))
            rl.DrawRectangleLines(tx, ty, tw, tab_h, border_color)
        tab_text_color = colors["tab_text_active"] if is_active else colors["tab_text"]
        text_y = ty + (tab_h - tab_font) // 2
        _draw_settings_text(state, tr(tab["name"]), tx + SETTINGS_TAB_PADDING, text_y, tab_font, tab_text_color)

    # Content layout
    item_h = SETTINGS_CONTENT_ITEM_HEIGHT
    padding_x = SETTINGS_CONTENT_PADDING_X
    sub_item_padding = SETTINGS_CONTENT_SUB_INDENT
    val_w = SETTINGS_CONTENT_VALUE_WIDTH
    val_x = win_x + win_w - val_w - SETTINGS_CONTENT_VALUE_MARGIN

    rl.BeginScissorMode(win_x + SETTINGS_CONTENT_BORDER_MARGIN + 1, content_y + 1,
                        win_w - SETTINGS_CONTENT_BORDER_MARGIN * 2 - 2, content_h - 2)

    current_tab = SETTINGS_TABS[settings.active_tab]

    if current_tab.get("type") == "info":
        _draw_info_tab(state, current_tab, win_x, win_y, win_w, content_y, content_h,
                       item_h, padding_x, small_font, font_size, colors)
        rl.EndScissorMode()
    else:
        tab_items = current_tab["items"]
        item_y = content_y + 5 - settings.scroll_offset
        editable_idx = 0

        for item in tab_items:
            label, config_key, val_type, min_val, max_val = item

            if item_y + item_h < content_y or item_y > content_y + content_h:
                if is_editable_item(item):
                    editable_idx += 1
                item_y += item_h
                continue

            if config_key is None:
                # Section header
                _draw_settings_text(state, tr(label), win_x + padding_x, item_y + (item_h - small_font) // 2,
                                    small_font, colors["header_text"])
            elif val_type == "lang":
                # Language selector row: label + RU/EN segments
                label_x = win_x + padding_x + sub_item_padding
                _draw_settings_text(state, tr(label), label_x, item_y + (item_h - small_font) // 2,
                                    small_font, colors["text_color"])
                seg_w = val_w // 2
                cur = get_language()
                for si, code in enumerate(LANGUAGES):
                    sx = val_x + si * seg_w
                    sw = seg_w if si == 0 else (val_w - seg_w)
                    sy = item_y + 4
                    sh = item_h - 8
                    active = (code == cur)
                    seg_hover = (sx <= mouse.x <= sx + sw and sy <= mouse.y <= sy + sh)
                    if active:
                        rl.DrawRectangle(sx, sy, sw, sh, RL_Color(*colors["input_active_bg"]))
                        rl.DrawRectangleLines(sx, sy, sw, sh, RL_Color(*colors["input_active_border"]))
                    else:
                        bg = colors["hover_bg"] if seg_hover else colors["input_bg"]
                        rl.DrawRectangle(sx, sy, sw, sh, RL_Color(*bg))
                        rl.DrawRectangleLines(sx, sy, sw, sh, RL_Color(*colors["input_border"]))
                    txt = code.upper()
                    tw2 = _text_w(state, txt, small_font)
                    tcol = colors["value_color"] if active else colors["input_text"]
                    _draw_settings_text(state, txt, sx + (sw - tw2) // 2, item_y + (item_h - small_font) // 2,
                                        small_font, tcol)
            else:
                current_val = getattr(cfg, config_key, "?")
                is_editing = (settings.editing_item == editable_idx)

                is_out_of_range = False
                try:
                    val = val_type(current_val) if val_type else current_val
                    if min_val is not None and val < min_val:
                        is_out_of_range = True
                    if max_val is not None and val > max_val:
                        is_out_of_range = True
                except (ValueError, TypeError):
                    pass

                label_x = win_x + padding_x + sub_item_padding
                _draw_settings_text(state, tr(label), label_x, item_y + (item_h - small_font) // 2,
                                    small_font, colors["text_color"])

                if val_type == bool:
                    cb_size = 16
                    cb_x = val_x + (val_w - cb_size) // 2
                    cb_y = item_y + (item_h - cb_size) // 2
                    is_hover = (label_x <= mouse.x <= val_x + val_w + 10 and
                                item_y + 2 <= mouse.y <= item_y + item_h - 2)
                    bg_color = colors["hover_bg"] if is_hover else colors["input_bg"]
                    rl.DrawRectangle(cb_x, cb_y, cb_size, cb_size, RL_Color(*bg_color))
                    rl.DrawRectangleLines(cb_x, cb_y, cb_size, cb_size, RL_Color(*colors["input_border"]))
                    if current_val:
                        rl.DrawLine(cb_x + 3, cb_y + 8, cb_x + 6, cb_y + 12, RL_Color(*colors["value_color"]))
                        rl.DrawLine(cb_x + 6, cb_y + 12, cb_x + 13, cb_y + 3, RL_Color(*colors["value_color"]))
                else:
                    field_x = val_x - 5
                    field_w = val_w + 10
                    field_y = item_y + 4
                    field_h = item_h - 8

                    if is_editing:
                        rl.DrawRectangle(field_x, field_y, field_w, field_h, RL_Color(*colors["input_active_bg"]))
                        rl.DrawRectangleLines(field_x, field_y, field_w, field_h, RL_Color(*colors["input_active_border"]))

                        edit = settings.edit_state
                        text = edit.text

                        edit_out_of_range = False
                        try:
                            if text.strip():
                                test_val = val_type(text) if val_type else text
                                if min_val is not None and test_val < min_val:
                                    edit_out_of_range = True
                                if max_val is not None and test_val > max_val:
                                    edit_out_of_range = True
                        except (ValueError, TypeError):
                            edit_out_of_range = True

                        if edit.has_selection():
                            sel_start, sel_end = edit.get_selection_range()
                            text_before_sel = text[:sel_start]
                            text_sel = text[sel_start:sel_end]
                            start_x = val_x + (_text_w(state, text_before_sel, small_font) if text_before_sel else 0)
                            sel_width = _text_w(state, text_sel, small_font) if text_sel else 0
                            rl.DrawRectangle(int(start_x), field_y + 2, int(sel_width), field_h - 4,
                                             RL_Color(*colors["selection_bg"]))

                        text_color = (200, 60, 60, 255) if edit_out_of_range else colors["input_text"]
                        _draw_settings_text(state, text, val_x, item_y + (item_h - small_font) // 2,
                                            small_font, text_color)

                        if int(now() * 2) % 2 == 0:
                            text_before_cursor = text[:edit.cursor_pos]
                            cursor_x = val_x + (_text_w(state, text_before_cursor, small_font) if text_before_cursor else 0)
                            rl.DrawRectangle(int(cursor_x), field_y + 4, 2, field_h - 8,
                                             RL_Color(*colors["input_text"]))
                    else:
                        is_hover = (field_x <= mouse.x <= field_x + field_w and
                                    field_y <= mouse.y <= field_y + field_h)
                        if is_hover:
                            rl.DrawRectangle(field_x, field_y, field_w, field_h, RL_Color(*colors["hover_bg"]))
                        else:
                            rl.DrawRectangle(field_x, field_y, field_w, field_h, RL_Color(*colors["input_bg"]))
                        rl.DrawRectangleLines(field_x, field_y, field_w, field_h, RL_Color(*colors["input_border"]))

                        val_str = str(current_val)
                        val_color = (200, 60, 60, 255) if is_out_of_range else colors["value_color"]
                        _draw_settings_text(state, val_str, val_x, item_y + (item_h - small_font) // 2,
                                            small_font, val_color)

                editable_idx += 1

            item_y += item_h

        rl.EndScissorMode()

    # Scroll indicator
    n_rows = _content_row_count(current_tab)
    max_scroll = max(0, n_rows * item_h - content_h)
    if max_scroll > 0:
        scroll_bar_h = max(20, content_h * content_h // (n_rows * item_h))
        scroll_bar_y = content_y + (settings.scroll_offset / max_scroll) * (content_h - scroll_bar_h)
        rl.DrawRectangle(win_x + win_w - 12, int(scroll_bar_y), 4, int(scroll_bar_h),
                         RL_Color(*colors["input_border"]))

    # Footer hints
    hint_y = win_y + win_h - 35
    if settings.editing_item >= 0:
        hints = [("Enter", tr("foot.enter")), ("Esc", tr("foot.cancel")), ("Tab", tr("foot.next_field")),
                 ("Home/End", tr("foot.home_end")), ("Shift", tr("foot.select"))]
    else:
        hints = [(tr("lbl.click"), tr("foot.edit")), ("Esc", tr("foot.close")), (tr("lbl.wheel"), tr("foot.scroll"))]

    hint_x = win_x + SETTINGS_TAB_START_X
    for key, desc in hints:
        hint_text = f"{key}: {desc}"
        _draw_settings_text(state, hint_text, hint_x, hint_y, small_font - 2, colors["hint_color"])
        hint_x += int(_text_w(state, hint_text, small_font - 2)) + 20
        if hint_x > win_x + win_w - 100:
            break


def _draw_settings_text(state: "AppState", text: str, x: int, y: int, size: int, color: tuple):
    """Helper to draw text with unicode support."""
    color_rl = RL_Color(*color)
    if state.unicode_font:
        try:
            rl.DrawTextEx(state.unicode_font, text.encode('utf-8'),
                          RL_V2(x, y), size, 1.0, color_rl)
            return
        except Exception:
            pass
    RL_DrawText(text, x, y, size, color_rl)
