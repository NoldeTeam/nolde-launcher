"""Visual language: near-black surfaces, deep blue actions, green play overlays.

Layout follows the reference launcher (sidebar, continue card, overlay action on
each cover). Colours and type are Nolde's own. Inter is used for body text and
Space Grotesk for headings. Both are bundled under the SIL OFL.
"""

from __future__ import annotations

from pathlib import Path

ASSETS = Path(__file__).resolve().parent / "assets"
FONT_DIR = ASSETS / "fonts"
LOGO_PATH = ASSETS / "images" / "logo.png"
APP_ICON_PATH = ASSETS / "images" / "nolde.ico"  # window, taskbar and tray icon

BODY_FONT = "Inter"
DISPLAY_FONT = "Space Grotesk"

COLORS = {
    "bg": "#0d1016",
    "sidebar": "#0d1016",
    "panel": "#141820",
    "card": "#171c26",
    "card_hover": "#1d2431",
    "border": "#232a38",
    "text": "#e9edf5",
    "muted": "#8a93a6",
    "subtle": "#5c6578",
    "accent": "#2f6fed",
    "accent_hover": "#4383ff",
    "accent_pressed": "#2558c7",
    "play": "#2fa572",
    "play_hover": "#3bbd84",
    "success": "#3aa578",
    "warning": "#d6a23b",
    "danger": "#e5534b",
}

_C = COLORS

def _base_stylesheet() -> str:
    return f"""
    QWidget {{
        background: {_C['bg']};
        color: {_C['text']};
        font-family: "{BODY_FONT}";
        font-size: 13px;
    }}
    QMainWindow, QDialog {{ background: {_C['bg']}; }}
    QLabel {{ background: transparent; }}
    QFrame {{ background: transparent; }}
    #Transparent {{ background: transparent; }}
    QToolTip {{ background: {_C['panel']}; color: {_C['text']}; border: 1px solid {_C['border']}; padding: 4px; }}
    
    #Sidebar {{ background: {_C['sidebar']}; border-right: 1px solid {_C['border']}; }}
    #SidebarSection {{
        color: {_C['subtle']}; font-size: 11px; font-weight: 600; letter-spacing: 1px;
        padding: 18px 20px 6px 20px; background: transparent;
    }}
    #Logo {{ padding: 18px 18px 14px 18px; background: transparent; }}
    
    #NavButton {{
        background: transparent; border: none; border-radius: 8px; color: {_C['muted']};
        text-align: left; padding: 9px 12px; margin: 1px 10px; font-size: 13px; font-weight: 500;
    }}
    #NavButton:hover {{ background: {_C['panel']}; color: {_C['text']}; }}
    #NavButton[active="true"] {{ background: {_C['card']}; color: {_C['text']}; }}
    #NavButton:disabled {{ color: {_C['subtle']}; }}
    
    #ContinueCard {{
        background: {_C['card']}; border: 1px solid {_C['border']}; border-radius: 10px; margin: 0 10px;
    }}
    #ContinueCard:hover {{ border-color: {_C['accent']}; }}
    #ContinueTitle {{ font-family: "{DISPLAY_FONT}"; font-size: 13px; font-weight: 700; background: transparent; }}
    #ContinueSub {{ color: {_C['muted']}; font-size: 11px; background: transparent; }}
    
    #FilterButton {{
        background: transparent; border: none; border-radius: 6px; color: {_C['muted']};
        text-align: left; padding: 6px 12px; margin: 0 10px;
    }}
    #FilterButton:hover {{ color: {_C['text']}; }}
    #FilterButton[active="true"] {{ color: {_C['text']}; background: {_C['panel']}; }}
    #FilterButton:disabled {{ color: {_C['subtle']}; }}
    
    #PageTitle {{ font-family: "{DISPLAY_FONT}"; font-size: 26px; font-weight: 700; background: transparent; }}
    #SectionTitle {{ font-family: "{DISPLAY_FONT}"; font-size: 15px; font-weight: 700; background: transparent; }}
    #Muted {{ color: {_C['muted']}; background: transparent; }}
    #Subtle {{ color: {_C['subtle']}; background: transparent; }}
    #Version {{ color: {_C['subtle']}; font-size: 12px; background: transparent; }}
    #Empty {{ color: {_C['muted']}; font-size: 14px; background: transparent; }}
    
    #Banner {{
        background: {_C['panel']}; border: 1px solid {_C['border']}; border-left: 3px solid {_C['warning']};
        border-radius: 6px; padding: 9px 12px; color: {_C['warning']};
    }}
    
    #GameCard {{
        background: {_C['card']}; border: 1px solid {_C['border']}; border-radius: 12px;
    }}
    #GameCard:hover {{ background: {_C['card_hover']}; border-color: #34405a; }}
    #GameCardTitle {{ font-family: "{DISPLAY_FONT}"; font-size: 14px; font-weight: 700; background: transparent; }}
    #GameCardSub {{ color: {_C['muted']}; font-size: 12px; background: transparent; }}
    #CoverFrame {{ background: transparent; border: none; }}
    #CoverPlaceholder {{
        background: {_C['panel']}; color: {_C['subtle']}; border-radius: 8px; border: none;
        font-family: "{DISPLAY_FONT}"; font-size: 28px; font-weight: 700;
    }}
    #OverlayPlay, #OverlayInstall {{
        border: none; border-radius: 20px; color: white;
    }}
    #OverlayPlay {{ background: {_C['play']}; }}
    #OverlayPlay:hover {{ background: {_C['play_hover']}; }}
    #OverlayInstall {{ background: {_C['accent']}; }}
    #OverlayInstall:hover {{ background: {_C['accent_hover']}; }}
    #OverlayPlay:disabled, #OverlayInstall:disabled {{ background: {_C['panel']}; }}
    #MenuButton {{ background: transparent; border: none; border-radius: 6px; padding: 4px; }}
    #MenuButton:hover {{ background: {_C['panel']}; }}
    #MenuButton::menu-indicator {{ image: none; width: 0; }}
    
    #Badge {{
        border-radius: 9px; padding: 2px 9px; font-size: 11px; background: {_C['panel']}; color: {_C['muted']};
    }}
    #BadgeSuccess {{ background: #173a2c; color: #7fd9b0; border-radius: 9px; padding: 2px 9px; font-size: 11px; }}
    #BadgeAccent {{ background: #1a2b4f; color: #8db4ff; border-radius: 9px; padding: 2px 9px; font-size: 11px; }}
    #BadgeWarning {{ background: #3a3015; color: #e8c46f; border-radius: 9px; padding: 2px 9px; font-size: 11px; }}
    #BadgeDanger {{ background: #3d1f1d; color: #f3a29d; border-radius: 9px; padding: 2px 9px; font-size: 11px; }}
    
    #Panel {{ background: {_C['card']}; border: 1px solid {_C['border']}; border-radius: 12px; }}
    #DetailHero {{ background: {_C['card']}; border: 1px solid {_C['border']}; border-radius: 14px; }}
    
    QLineEdit, QComboBox {{
        background: {_C['panel']}; border: 1px solid {_C['border']}; border-radius: 8px;
        padding: 7px 12px; selection-background-color: {_C['accent']};
    }}
    QLineEdit:focus, QComboBox:focus {{ border-color: {_C['accent']}; }}
    QComboBox {{ padding-right: 28px; min-width: 150px; }}
    QComboBox::drop-down {{ border: none; width: 24px; }}
    QComboBox QAbstractItemView {{
        background: {_C['panel']}; border: 1px solid {_C['border']}; selection-background-color: {_C['card']};
        outline: none; padding: 4px;
    }}
    
    QPushButton {{
        background: {_C['panel']}; border: 1px solid {_C['border']}; border-radius: 8px;
        padding: 7px 14px; font-weight: 500;
    }}
    QPushButton:hover {{ background: {_C['card_hover']}; border-color: #34405a; }}
    QPushButton:pressed {{ background: {_C['card']}; }}
    QPushButton:disabled {{ color: {_C['subtle']}; }}
    QPushButton#Primary {{
        background: {_C['accent']}; border: 1px solid {_C['accent']}; color: white; font-weight: 600;
        padding: 10px 22px; font-size: 14px;
    }}
    QPushButton#Primary:hover {{ background: {_C['accent_hover']}; border-color: {_C['accent_hover']}; }}
    QPushButton#Primary:pressed {{ background: {_C['accent_pressed']}; }}
    QPushButton#Play {{
        background: {_C['play']}; border: 1px solid {_C['play']}; color: white; font-weight: 600;
        padding: 10px 22px; font-size: 14px;
    }}
    QPushButton#Play:hover {{ background: {_C['play_hover']}; border-color: {_C['play_hover']}; }}
    QPushButton#Danger {{ color: {_C['danger']}; }}
    QPushButton#Ghost {{ background: transparent; border: none; color: {_C['muted']}; padding: 6px 10px; }}
    QPushButton#Ghost:hover {{ color: {_C['text']}; background: {_C['panel']}; }}
    QPushButton#Link {{ background: transparent; border: none; color: {_C['accent_hover']}; padding: 2px 4px; }}
    QPushButton#Link:hover {{ color: {_C['text']}; }}
    
    QMenu {{
        background: {_C['panel']}; border: 1px solid {_C['border']}; border-radius: 8px; padding: 4px;
    }}
    QMenu::item {{ padding: 7px 22px 7px 12px; border-radius: 5px; }}
    QMenu::item:selected {{ background: {_C['card']}; }}
    QMenu::separator {{ height: 1px; background: {_C['border']}; margin: 4px 6px; }}
    
    QScrollArea {{ border: none; background: transparent; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {_C['border']}; border-radius: 4px; min-height: 36px; }}
    QScrollBar::handle:vertical:hover {{ background: #34405a; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    
    QProgressBar {{ background: {_C['panel']}; border: none; border-radius: 4px; height: 8px; text-align: center; }}
    QProgressBar::chunk {{ background: {_C['accent']}; border-radius: 4px; }}
    QProgressBar#Done::chunk {{ background: {_C['success']}; }}
    QProgressBar#Failed::chunk {{ background: {_C['danger']}; }}
    QProgressBar#Paused::chunk {{ background: {_C['warning']}; }}
    
    QStatusBar {{ background: {_C['sidebar']}; color: {_C['muted']}; border-top: 1px solid {_C['border']}; }}
    QStatusBar::item {{ border: none; }}
    """
    

def _extra_stylesheet() -> str:
    return f"""
    #SiteButton {{ background: transparent; border: none; border-radius: 8px; padding: 6px; }}
    #SiteButton:hover {{ background: {_C['panel']}; }}
    QCheckBox {{ spacing: 10px; background: transparent; color: {_C['text']}; }}
    QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px; border: 1px solid {_C['border']}; background: {_C['panel']}; }}
    QCheckBox::indicator:checked {{ background: {_C['accent']}; border-color: {_C['accent']}; }}
    QCheckBox::indicator:hover {{ border-color: {_C['accent']}; }}
    
    #TitleBar {{ background: {_C['bg']}; border-bottom: 1px solid {_C['border']}; }}
    #TitleText {{ font-family: "{DISPLAY_FONT}"; font-size: 12px; font-weight: 700; color: {_C['muted']}; background: transparent; }}
    #WindowButton, #WindowClose {{ background: transparent; border: none; border-radius: 0px; padding: 0px; }}
    #WindowButton:hover {{ background: {_C['panel']}; }}
    #WindowClose:hover {{ background: #c4433e; }}
    #Tag {{ border: 1px solid {_C['border']}; border-radius: 9px; padding: 1px 8px; font-size: 11px; color: {_C['muted']}; background: transparent; }}
    #InfoLabel {{ color: {_C['subtle']}; font-size: 10px; font-weight: 600; background: transparent; }}
    #GameCardDesc {{ color: {_C['muted']}; font-size: 12px; background: transparent; }}
    #HeroFrame {{ background: {_C['panel']}; border: 1px solid {_C['border']}; border-radius: 14px; }}
    #HeroTitle {{ font-family: "{DISPLAY_FONT}"; font-size: 34px; font-weight: 700; color: #ffffff; background: transparent; }}
    #HeroSub {{ color: #b9c3d6; font-size: 13px; background: transparent; }}
    #LinkRow {{ background: {_C['panel']}; border: 1px solid {_C['border']}; border-radius: 8px; padding: 9px 12px; text-align: left; color: {_C['text']}; }}
    #LinkRow:hover {{ border-color: {_C['accent']}; background: {_C['card_hover']}; }}
    """
    

def build_stylesheet() -> str:
    """The full application stylesheet for the current palette in COLORS."""
    return _base_stylesheet() + _extra_stylesheet()


STYLESHEET = build_stylesheet()  # the stylesheet for the default palette
