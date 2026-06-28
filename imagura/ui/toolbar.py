"""Top toolbar hit-testing, input update, and drawing."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Optional

from ..config import (
    TOOLBAR_BG_ALPHA,
    TOOLBAR_BTN_RADIUS,
    TOOLBAR_BTN_SPACING,
    TOOLBAR_HEIGHT,
    TOOLBAR_SLIDE_MS,
    TOOLBAR_TRIGGER_FRAC,
    TOOLBAR_TRIGGER_MIN_PX,
)
from ..rl_compat import make_color as RL_Color
from ..rl_compat import make_vec2 as RL_V2
from ..rl_compat import rl
from ..state.ui import ToolbarButton, ToolbarButtonId

if TYPE_CHECKING:
    from ..state import AppState


def update_toolbar_alpha(state: "AppState") -> None:
    """Animate toolbar visibility toward its target alpha."""
    toolbar = state.ui.toolbar
    if abs(toolbar.alpha - toolbar.target_alpha) > 0.01:
        speed = 1000.0 / TOOLBAR_SLIDE_MS
        dt = rl.GetFrameTime()
        if toolbar.target_alpha > toolbar.alpha:
            toolbar.alpha = min(toolbar.target_alpha, toolbar.alpha + speed * dt)
        else:
            toolbar.alpha = max(toolbar.target_alpha, toolbar.alpha - speed * dt)
    else:
        toolbar.alpha = toolbar.target_alpha


def update_toolbar_input(state: "AppState", mouse, blocked: bool) -> Optional[ToolbarButton]:
    """Update visibility/hover state and return the clicked toolbar button."""
    toolbar = state.ui.toolbar

    if is_in_toolbar_zone(state, mouse.x, mouse.y):
        toolbar.target_alpha = 1.0
    else:
        toolbar.target_alpha = 0.0

    if toolbar.alpha > 0.1:
        toolbar.hover_index = get_toolbar_button_at(state, mouse.x, mouse.y)
    else:
        toolbar.hover_index = -1

    if blocked:
        return None
    if not rl.IsMouseButtonPressed(rl.MOUSE_BUTTON_LEFT):
        return None
    if toolbar.hover_index < 0:
        return None
    return toolbar.buttons[toolbar.hover_index]


def get_toolbar_panel_bounds(state: "AppState") -> tuple[int, int]:
    """Return toolbar panel `(x, width)`."""
    sw = state.screenW
    buttons_width = _buttons_width(state)
    min_panel_width = buttons_width + TOOLBAR_BTN_RADIUS * 2 * 2
    panel_width = max(min_panel_width, int(sw * 0.6))
    panel_x = (sw - panel_width) // 2
    return panel_x, panel_width


def is_in_toolbar_zone(state: "AppState", mouse_x: float, mouse_y: float) -> bool:
    """Check if the pointer is in the toolbar trigger zone."""
    trigger_height = max(state.screenH * TOOLBAR_TRIGGER_FRAC, TOOLBAR_TRIGGER_MIN_PX)
    if mouse_y >= trigger_height:
        return False
    panel_x, panel_width = get_toolbar_panel_bounds(state)
    return panel_x <= mouse_x <= panel_x + panel_width


def get_toolbar_button_at(state: "AppState", mx: float, my: float) -> int:
    """Return toolbar button index at pointer position, or `-1`."""
    toolbar = state.ui.toolbar
    if toolbar.alpha < 0.5:
        return -1

    separator_width = TOOLBAR_BTN_SPACING
    start_x = (state.screenW - _buttons_width(state)) // 2 + TOOLBAR_BTN_RADIUS
    cy = TOOLBAR_HEIGHT // 2

    current_x = start_x
    for i, btn in enumerate(toolbar.buttons):
        dx = mx - current_x
        dy = my - cy
        if (dx * dx + dy * dy) <= (TOOLBAR_BTN_RADIUS * TOOLBAR_BTN_RADIUS):
            return i

        current_x += TOOLBAR_BTN_RADIUS * 2 + TOOLBAR_BTN_SPACING
        if btn.separator_after:
            current_x += separator_width

    return -1


def draw_toolbar(state: "AppState") -> None:
    """Draw top toolbar with action buttons."""
    toolbar = state.ui.toolbar
    if toolbar.alpha < 0.01:
        return

    sw = state.screenW
    alpha = toolbar.alpha
    n_buttons = len(toolbar.buttons)
    separator_width = TOOLBAR_BTN_SPACING
    buttons_width = _buttons_width(state)
    min_panel_width = buttons_width + TOOLBAR_BTN_RADIUS * 2 * 2
    panel_width = max(min_panel_width, int(sw * 0.6))
    panel_x = (sw - panel_width) // 2
    fade_width = 40
    bg_alpha_max = int(255 * TOOLBAR_BG_ALPHA * alpha)

    step = 4
    for i in range(0, fade_width, step):
        fade_alpha = int(bg_alpha_max * (i / fade_width))
        rl.DrawRectangle(panel_x + i, 0, step, TOOLBAR_HEIGHT, RL_Color(0, 0, 0, fade_alpha))

    rl.DrawRectangle(
        panel_x + fade_width,
        0,
        panel_width - fade_width * 2,
        TOOLBAR_HEIGHT,
        RL_Color(0, 0, 0, bg_alpha_max),
    )

    for i in range(0, fade_width, step):
        fade_alpha = int(bg_alpha_max * (1.0 - i / fade_width))
        rl.DrawRectangle(
            panel_x + panel_width - fade_width + i,
            0,
            step,
            TOOLBAR_HEIGHT,
            RL_Color(0, 0, 0, fade_alpha),
        )

    current_x = (sw - buttons_width) // 2 + TOOLBAR_BTN_RADIUS
    cy = TOOLBAR_HEIGHT // 2

    for i, btn in enumerate(toolbar.buttons):
        cx = current_x
        is_hover = i == toolbar.hover_index

        btn_alpha = int(255 * alpha)
        bg_btn_alpha = int(128 * alpha) if is_hover else int(80 * alpha)
        rl.DrawCircle(cx, cy, TOOLBAR_BTN_RADIUS, RL_Color(0, 0, 0, bg_btn_alpha))
        rl.DrawCircleLines(cx, cy, TOOLBAR_BTN_RADIUS, RL_Color(255, 255, 255, btn_alpha))

        icon_r = TOOLBAR_BTN_RADIUS * 0.45
        icon_color = RL_Color(255, 255, 255, btn_alpha)
        if btn.id == ToolbarButtonId.SETTINGS:
            draw_gear_icon(cx, cy, icon_r, icon_color)
        elif btn.id == ToolbarButtonId.ROTATE_CW:
            draw_rotate_icon(cx, cy, icon_r, clockwise=True, color=icon_color)
        elif btn.id == ToolbarButtonId.ROTATE_CCW:
            draw_rotate_icon(cx, cy, icon_r, clockwise=False, color=icon_color)
        elif btn.id == ToolbarButtonId.FLIP_H:
            draw_flip_icon(cx, cy, icon_r, icon_color)

        current_x += TOOLBAR_BTN_RADIUS * 2 + TOOLBAR_BTN_SPACING

        if btn.separator_after and i < n_buttons - 1:
            current_x += separator_width
            sep_x = current_x - TOOLBAR_BTN_RADIUS - (separator_width + TOOLBAR_BTN_SPACING) // 2
            sep_alpha = int(150 * alpha)
            rl.DrawLineEx(
                RL_V2(sep_x, cy - TOOLBAR_BTN_RADIUS * 0.7),
                RL_V2(sep_x, cy + TOOLBAR_BTN_RADIUS * 0.7),
                2.0,
                RL_Color(255, 255, 255, sep_alpha),
            )


def draw_rotate_icon(cx: int, cy: int, r: float, clockwise: bool, color) -> None:
    """Draw rotation arrow icon."""
    segments = 8

    if clockwise:
        start_angle = -120
        arc_span = 270
        points = []
        for i in range(segments + 1):
            angle = math.radians(start_angle + (arc_span * i / segments))
            points.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))

        for i in range(len(points) - 1):
            rl.DrawLineEx(RL_V2(points[i][0], points[i][1]), RL_V2(points[i + 1][0], points[i + 1][1]), 2.0, color)

        end_angle = math.radians(start_angle + arc_span)
        end_x, end_y = points[-1]
        arrow_size = r * 0.5
        tangent_angle = end_angle + math.pi / 2
    else:
        start_angle = -60
        arc_span = 270
        points = []
        for i in range(segments + 1):
            angle = math.radians(start_angle - (arc_span * i / segments))
            points.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))

        for i in range(len(points) - 1):
            rl.DrawLineEx(RL_V2(points[i][0], points[i][1]), RL_V2(points[i + 1][0], points[i + 1][1]), 2.0, color)

        end_angle = math.radians(start_angle - arc_span)
        end_x, end_y = points[-1]
        arrow_size = r * 0.5
        tangent_angle = end_angle - math.pi / 2

    arr_angle1 = tangent_angle + math.radians(150)
    arr_angle2 = tangent_angle - math.radians(150)
    rl.DrawLineEx(
        RL_V2(end_x, end_y),
        RL_V2(end_x + arrow_size * math.cos(arr_angle1), end_y + arrow_size * math.sin(arr_angle1)),
        2.0,
        color,
    )
    rl.DrawLineEx(
        RL_V2(end_x, end_y),
        RL_V2(end_x + arrow_size * math.cos(arr_angle2), end_y + arrow_size * math.sin(arr_angle2)),
        2.0,
        color,
    )


def draw_flip_icon(cx: int, cy: int, r: float, color) -> None:
    """Draw horizontal flip icon."""
    arrow_w = r * 0.6
    arrow_h = r * 0.8
    gap = r * 0.15

    rl.DrawLineEx(RL_V2(cx - gap - arrow_w, cy), RL_V2(cx - gap, cy - arrow_h), 2.0, color)
    rl.DrawLineEx(RL_V2(cx - gap - arrow_w, cy), RL_V2(cx - gap, cy + arrow_h), 2.0, color)
    rl.DrawLineEx(RL_V2(cx - gap, cy - arrow_h), RL_V2(cx - gap, cy + arrow_h), 2.0, color)
    rl.DrawLineEx(RL_V2(cx + gap + arrow_w, cy), RL_V2(cx + gap, cy - arrow_h), 2.0, color)
    rl.DrawLineEx(RL_V2(cx + gap + arrow_w, cy), RL_V2(cx + gap, cy + arrow_h), 2.0, color)
    rl.DrawLineEx(RL_V2(cx + gap, cy - arrow_h), RL_V2(cx + gap, cy + arrow_h), 2.0, color)


def draw_gear_icon(cx: int, cy: int, r: float, color) -> None:
    """Draw gear/settings icon."""
    teeth = 8
    outer_r = r
    inner_r = r * 0.6
    tooth_depth = r * 0.25

    for i in range(teeth):
        angle = 2 * math.pi * i / teeth
        next_angle = 2 * math.pi * (i + 0.5) / teeth
        x1 = cx + (outer_r + tooth_depth) * math.cos(angle - math.pi / teeth / 2)
        y1 = cy + (outer_r + tooth_depth) * math.sin(angle - math.pi / teeth / 2)
        x2 = cx + (outer_r + tooth_depth) * math.cos(angle + math.pi / teeth / 2)
        y2 = cy + (outer_r + tooth_depth) * math.sin(angle + math.pi / teeth / 2)
        x3 = cx + outer_r * math.cos(angle + math.pi / teeth / 2)
        y3 = cy + outer_r * math.sin(angle + math.pi / teeth / 2)
        x4 = cx + outer_r * math.cos(next_angle - math.pi / teeth / 2)
        y4 = cy + outer_r * math.sin(next_angle - math.pi / teeth / 2)

        rl.DrawLineEx(RL_V2(x1, y1), RL_V2(x2, y2), 2.0, color)
        rl.DrawLineEx(RL_V2(x2, y2), RL_V2(x3, y3), 2.0, color)
        rl.DrawLineEx(RL_V2(x3, y3), RL_V2(x4, y4), 2.0, color)

    segments = 16
    for i in range(segments):
        angle1 = 2 * math.pi * i / segments
        angle2 = 2 * math.pi * (i + 1) / segments
        x1 = cx + inner_r * math.cos(angle1)
        y1 = cy + inner_r * math.sin(angle1)
        x2 = cx + inner_r * math.cos(angle2)
        y2 = cy + inner_r * math.sin(angle2)
        rl.DrawLineEx(RL_V2(x1, y1), RL_V2(x2, y2), 2.0, color)


def _buttons_width(state: "AppState") -> int:
    toolbar = state.ui.toolbar
    n_buttons = len(toolbar.buttons)
    n_separators = sum(1 for btn in toolbar.buttons if btn.separator_after)
    separator_width = TOOLBAR_BTN_SPACING
    return (
        n_buttons * (TOOLBAR_BTN_RADIUS * 2)
        + (n_buttons - 1) * TOOLBAR_BTN_SPACING
        + n_separators * separator_width
    )
