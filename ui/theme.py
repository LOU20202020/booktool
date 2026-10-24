"""视觉规范：颜色、字体、全局样式表。与设计稿 ui-3-spec 对应。"""

PAPER = "#F4F1EA"
SURFACE = "#FFFFFF"
INK = "#1E1B18"
INK2 = "#6B6459"
INK3 = "#7E7568"
LINE = "#E4DDD1"
LINE2 = "#EFE9DE"
RED = "#B23A2E"
RED_SOFT = "#F3E3DF"
RAIL = "#26221D"

FONT_HEAD = "SimSun"
FONT_BODY = "Microsoft YaHei"

QSS = f"""
QWidget {{
    background: transparent;
    color: {INK};
    font-family: "{FONT_BODY}";
    font-size: 12px;
}}
QMainWindow, #Root {{ background: {PAPER}; }}

/* 左侧导航 */
#Rail {{ background: {RAIL}; }}
QToolButton#RailAvatar {{
    background: transparent; border: 0; padding: 0;
}}
QToolButton#RailAvatar:hover {{ border: 2px solid {RED}; border-radius: 12px; }}
QToolButton#RailLogo {{
    background: {RED}; color: #FBF7F0; border: 0; border-radius: 8px;
    font-family: "{FONT_HEAD}"; font-size: 26px; padding: 0;
}}
QToolButton#RailLogo:hover {{ background: #A3332A; }}
QToolButton#NavBtn {{
    background: transparent; border: 0; border-left: 3px solid transparent;
    color: #BEB4A5; font-size: 9pt; padding: 7px 0 6px 0;
}}
QToolButton#NavBtn:hover {{ background: #2C2822; color: #EAE2D4; }}
QToolButton#NavBtn:checked {{
    background: #2E2A24; color: #F6F1E7; border-left: 3px solid {RED};
}}
QListWidget#NavList {{ background: transparent; border: 0; outline: 0; }}
QListWidget#NavList::item {{
    color: #A79D8F; border-radius: 8px; margin: 3px 10px; padding: 7px 0;
}}
QListWidget#NavList::item:selected {{
    background: #2E2A24; color: #F6F1E7;
}}

/* 顶栏 */
#TopBar {{ background: {PAPER}; border-bottom: 1px solid {LINE}; }}
#Crumb {{ color: {INK3}; font-size: 10px; letter-spacing: 1px; }}
#Title {{ font-family: "{FONT_HEAD}"; font-size: 20px; letter-spacing: 2px; }}
#ProjChip {{
    background: {SURFACE}; border: 1px solid {LINE}; border-radius: 6px; padding: 5px 12px; color: {INK2};
}}

/* 卡片/面板 */
#Panel, #Card {{
    background: {SURFACE}; border: 1px solid {LINE}; border-radius: 10px;
}}
#SectionLabel {{ color: {INK3}; font-size: 10px; letter-spacing: 2px; }}
#Hint {{ color: {INK2}; font-size: 11px; }}
#Kv {{ color: {INK2}; font-size: 12px; }}
#BigNum {{ font-family: Georgia; font-size: 22px; }}
#NumLabel {{ color: {INK2}; font-size: 10px; }}

/* 按钮 */
QPushButton {{
    background: #FCFAF5; border: 1px solid {LINE}; border-radius: 6px;
    padding: 6px 12px; color: {INK};
}}
QPushButton:hover {{ border-color: #CFC6B6; }}
QPushButton:pressed {{ background: #F3EEE4; }}
QLineEdit#StepEdit {{
    background: {SURFACE}; border: 1px solid {LINE}; border-radius: 0;
    color: {INK}; font-size: 13px; font-weight: 600; padding: 3px 4px;
}}
QLineEdit#StepEdit:focus {{ border: 1px solid {RED}; background: #FFFDFC; }}
QSpinBox#StepSpin, QDoubleSpinBox#StepSpin {{
    background: {SURFACE}; border: 1px solid {LINE}; border-radius: 0;
    color: {INK}; font-size: 13px; font-weight: 600; padding: 3px 4px;
}}
QSpinBox#StepSpin:focus, QDoubleSpinBox#StepSpin:focus {{
    border: 1px solid {RED}; background: #FFFDFC;
}}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 0; height: 0; border: 0; }}
QToolButton#BiliBtn {{
    background: transparent; border: 2px solid {LINE}; border-radius: 21px; padding: 0;
}}
QToolButton#BiliBtn:hover {{ border-color: {RED}; }}
QPushButton#ClearBtn {{
    background: #FCFAF5; border: 1px solid {LINE}; border-radius: 11px;
    color: {INK2}; font-size: 13px; padding: 0;
}}
QPushButton#ClearBtn:hover {{ border-color: {RED}; color: {RED}; background: #FFF3F1; }}
QPushButton#AddBtn {{
    background: {INK}; border: 0; color: #F6F1E7; font-weight: 600;
}}
QPushButton#AddBtn:hover {{ background: #33302A; }}
QPushButton#StepBtn {{
    background: #FCFAF5; border: 1px solid {LINE}; color: {INK};
    font-size: 15px; font-weight: 600; padding: 0; border-radius: 0;
}}
QPushButton#StepBtn:hover {{ background: #F3EEE4; }}
QPushButton#StepBtn:pressed {{ background: #EAE3D6; }}
QPushButton#Primary {{
    background: {RED}; border: 0; border-radius: 7px; color: #FBF7F0;
    font-size: 13px; font-weight: 600; padding: 0 22px;
}}
QPushButton#Primary:hover {{ background: #A3332A; }}
QPushButton#Primary:disabled {{ background: #D9CFC8; color: #FBEDE9; }}
QPushButton#CollapseHead {{
    background: transparent; border: 0; text-align: left;
}}
QPushButton#CollapseHead:hover {{ background: #FBFAF6; }}
QToolButton#ArrBtn {{
    background: #FCFAF5; border: 1px solid {LINE}; border-radius: 8px;
    color: {INK2}; font-size: 11px; padding: 4px;
}}
QToolButton#ArrBtn:hover {{ border-color: #CFC6B6; }}
QToolButton#ArrBtn:checked {{
    border: 1px solid {RED}; background: #FFF8F6; color: {RED}; font-weight: 600;
}}
QPushButton#Chip {{
    border-radius: 999px; padding: 5px 12px; font-size: 11px; color: {INK2}; background: #FCFAF5;
}}
QPushButton#Chip:checked {{
    border-color: {RED}; color: {RED}; background: #FFF8F6;
}}
QPushButton#Seg {{
    border: 1px solid {LINE}; border-radius: 0; padding: 4px 14px; color: {INK2}; background: {SURFACE};
}}
QPushButton#Seg:checked {{ background: {INK}; color: #F6F1E7; border-color: {INK}; }}

/* 输入 */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: #FCFAF5; border: 1px solid {LINE}; border-radius: 6px;
    padding: 4px 8px; min-height: 22px; selection-background-color: {RED};
}}
QComboBox::drop-down {{ border: 0; width: 18px; }}
QScrollArea {{ border: 0; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #DCD5C8; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}

/* 底部操作条 */
#ActionBar {{ background: {SURFACE}; border-top: 1px solid {LINE}; }}
#Status {{ color: {INK2}; font-size: 12px; }}
#StatusRed {{ color: {RED}; font-size: 12px; }}

QToolTip {{ background: {INK}; color: #F6F1E7; border: 0; padding: 6px; }}

/* 分组标题 */
#GroupTitle {{ font-family: "{FONT_HEAD}"; font-size: 13px; letter-spacing: 1px; color: {INK}; }}
QCheckBox {{ color: {INK2}; }}

/* 系统消息框：不写就会被透明背景+深色文字吞掉 */
QMessageBox {{ background: {SURFACE}; }}
QMessageBox QLabel {{ color: {INK}; background: transparent; }}
QMessageBox QTextEdit, QMessageBox QPlainTextEdit, QMessageBox QTextBrowser {{
    background: {SURFACE}; color: {INK}; border: 1px solid {LINE};
}}
QMessageBox QPushButton {{
    background: #FCFAF5; border: 1px solid {LINE}; border-radius: 6px;
    color: {INK}; padding: 6px 18px; min-width: 68px;
}}
QMessageBox QPushButton:hover {{ border-color: {RED}; color: {RED}; }}
QMessageBox QPushButton:default {{ background: {RED}; color: #FBF7F0; border: 0; }}
"""
