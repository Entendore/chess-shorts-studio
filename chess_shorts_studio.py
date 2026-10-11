#!/usr/bin/env python3
"""
Chess Shorts Studio - full build (improved & guaranteed)
========================================================

Features:
- 35 puzzle categories
- Piece-Specific Generators & Multi-Motif tagging
- 100% Legal Positions, Subfolder outputs, Stockfish support
- Strict Video Timeline: Title -> Start Board -> Solution Animation -> Final Board -> End Screen

pip install PySide6 chess numpy imageio imageio-ffmpeg
Run:  python chess_shorts_studio.py
"""

import copy
import json
import logging
import math
import os
import random
import re
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import wave
from dataclasses import dataclass, field

import numpy as np
import chess
import chess.engine
import chess.pgn
import chess.polyglot
import chess.syzygy
import imageio.v2 as imageio
import imageio_ffmpeg

from PySide6.QtCore import (Qt, QThread, QTimer, Signal, QRectF, QPointF,
                            QSettings, QUrl, QMimeData)
from PySide6.QtGui import (QBrush, QColor, QDesktopServices, QFont, QFontDatabase,
                           QFontMetrics, QImage, QKeySequence, QLinearGradient,
                           QPainter, QPainterPath, QPalette, QPen, QPolygonF,
                           QShortcut, QPixmap, QDragEnterEvent, QDropEvent,
                           QColorDialog)
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,
                               QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QMainWindow,
                               QMessageBox, QProgressBar, QPushButton, QSpinBox,
                               QDoubleSpinBox, QVBoxLayout, QWidget, QTableWidget,
                               QTableWidgetItem, QHeaderView, QSlider, QTextEdit,
                               QTabWidget, QPlainTextEdit)

# ----------------------------- logger setup ---------------------------------

logger = logging.getLogger("ChessShortsStudio")

# ----------------------------- constants ------------------------------------

VID_W, VID_H = 1080, 1920

RESOLUTIONS = {
    "720p":  (720, 1280),
    "1080p": (1080, 1920),
    "1440p": (1440, 2560),
}

QUALITY_CRF = {"Low": 28, "Medium": 23, "High": 18, "Ultra": 14}

LIGHT_SQ = QColor("#EEEED2")
DARK_SQ = QColor("#769656")
LAST_MOVE_TINT = QColor(255, 213, 79, 100)
ARROW_COLOR = QColor(235, 90, 70, 215)
GOLD = QColor("#F5C542")

THEMES = {
    "Green":  ("#EEEED2", "#769656"),
    "Walnut": ("#F0D9B5", "#B58863"),
    "Ocean":  ("#DEE3E6", "#7E9BB0"),
    "Ice":    ("#E8F1FA", "#9FB8D0"),
    "Slate":  ("#D8D8D8", "#5A6E7A"),
    "Rose":   ("#F5D9D9", "#C97A8C"),
    "Custom": ("#EEEED2", "#769656"),
}

CUSTOM_BG_TOP = QColor("#0F1424")
CUSTOM_BG_BOTTOM = QColor("#231439")
CUSTOM_ARROW = QColor(235, 90, 70, 215)

UI_FONT = None
GLYPH_FONT = None

SOLID_GLYPHS = {chess.KING: "\u265A", chess.QUEEN: "\u265B", chess.ROOK: "\u265C",
                chess.BISHOP: "\u265D", chess.KNIGHT: "\u265E", chess.PAWN: "\u265F"}

INTRO_D, BOARD_IN_D, FINALE_D, GAP_D = 1.15, 0.70, 1.60, 0.40
ANSWER_D, MOVE_D, PAUSE_D = 0.55, 0.75, 0.35
OUTRO_D = 2.20

STOCKFISH_CANDIDATES = [
    "stockfish", "stockfish.exe", "/usr/local/bin/stockfish", "/usr/bin/stockfish",
    "/opt/homebrew/bin/stockfish", "/Applications/Stockfish.app/Contents/MacOS/Stockfish",
    r"C:\Program Files\Stockfish\stockfish.exe", r"C:\Program Files (x86)\Stockfish\stockfish.exe",
    os.path.expanduser("~/.local/bin/stockfish"),
]

OUTPUT_ROOT_DIR = "Chess_Shorts"

# ----------------------------- puzzle categories ----------------------------

KINDS = {
    "mate_in_1":       dict(label="Mate in 1",           sub="MATE IN 1",        prompt="Find the mate in one!",              finale="CHECKMATE!"),
    "mate_in_2":       dict(label="Mate in 2",           sub="MATE IN 2",        prompt="Find the forced mate!",              finale="CHECKMATE!"),
    "mate_in_3":       dict(label="Mate in 3",           sub="MATE IN 3",        prompt="Mate in three \u2014 plan ahead!",   finale="CHECKMATE!"),
    "back_rank":       dict(label="Back-Rank Mate",      sub="BACK-RANK MATE",   prompt="Crush the back rank!",               finale="CHECKMATE!"),
    "promotion":       dict(label="Promotion Mate",      sub="PROMOTION MATE",   prompt="Promote with a bang!",               finale="CHECKMATE!"),
    "en_passant":      dict(label="En Passant Mate",     sub="EN PASSANT MATE",  prompt="There's a hidden trick\u2026",       finale="CHECKMATE!"),
    "fork":            dict(label="Knight Fork",         sub="KNIGHT FORK",      prompt="Spot the fork!",                     finale="QUEEN WON!"),
    "win_queen":       dict(label="Win the Queen",       sub="WIN THE QUEEN",    prompt="Win the queen in one!",              finale="QUEEN WON!"),
    "win_rook":        dict(label="Win a Rook",          sub="WIN A ROOK",       prompt="Win the rook in one!",               finale="ROOK WON!"),
    "sacrifice":       dict(label="Sacrifice & Mate",    sub="SACRIFICE & MATE", prompt="Sacrifice for mate!",                finale="CHECKMATE!"),
    "smothered":       dict(label="Smothered Mate",      sub="SMOTHERED MATE",   prompt="Trap the king in his own walls!",    finale="CHECKMATE!"),
    "arabian":         dict(label="Arabian Mate",        sub="ARABIAN MATE",     prompt="Knight + rook teamwork!",            finale="CHECKMATE!"),
    "castle_mate":     dict(label="Castling Mate",       sub="CASTLING MATE",    prompt="Mate by castling?!",                 finale="CHECKMATE!"),
    "quiet_mate":      dict(label="Quiet Mate",          sub="QUIET KEY MOVE",   prompt="No check \u2014 just logic!",        finale="CHECKMATE!"),
    "double_check":    dict(label="Double Check",        sub="DOUBLE CHECK",     prompt="Two checks at once!",                finale="QUEEN WON!"),
    "skewer":          dict(label="Skewer",              sub="SKEWER",           prompt="Win a piece through the king!",      finale="QUEEN WON!"),
    "pawn_fork":       dict(label="Pawn Fork",           sub="PAWN FORK",        prompt="The humble pawn strikes!",           finale="QUEEN WON!"),
    "win_piece":       dict(label="Win a Piece",         sub="WIN A PIECE",      prompt="Win a piece in one!",                finale="PIECE WON!"),
    "discovered":      dict(label="Discovered Attack",   sub="DISCOVERED ATTACK",prompt="Unmask the big piece!",              finale="QUEEN WON!"),
    "remove_defender": dict(label="Remove the Defender", sub="REMOVE THE DEFENDER", prompt="Eliminate the key defender!",   finale="CHECKMATE!"),
    "trapped_queen":   dict(label="Trapped Queen",       sub="TRAPPED QUEEN",    prompt="The queen has nowhere to run!",      finale="QUEEN WON!"),
    "pin_win":         dict(label="Pin & Win",           sub="PIN & WIN",        prompt="Pinned and can't move!",             finale="PIECE WON!"),
    "boden":           dict(label="Boden's Mate",        sub="BODEN'S MATE",     prompt="Two bishops, one knockout!",         finale="CHECKMATE!"),
    "epaulette":       dict(label="Epaulette Mate",      sub="EPAULETTE MATE",   prompt="His own guards trap him!",           finale="CHECKMATE!"),
    "ladder":          dict(label="Ladder Mate",         sub="LADDER MATE",      prompt="Rooks climb the ladder!",            finale="CHECKMATE!"),
    "queen_fork":      dict(label="Queen Fork",          sub="QUEEN FORK",       prompt="Check AND attack at once!",          finale="ROOK WON!"),
    
    "deflection":      dict(label="Deflection",          sub="DEFLECTION",       prompt="Deflect the defender!",               finale="PIECE WON!"),
    "overloading":     dict(label="Overloading",         sub="OVERLOADING",      prompt="Overload the defender!",              finale="PIECE WON!"),
    "zwischenzug":     dict(label="Zwischenzug",         sub="ZWISCHENZUG",      prompt="The intermediate move!",              finale="PIECE WON!"),
    "magnet":          dict(label="The Magnet",         sub="KING ATTRACTION",  prompt="Drag the king to its doom!",          finale="CHECKMATE!"),
    "stalemate_trick": dict(label="Stalemate Trick",     sub="AVOID STALEMATE",  prompt="Don't stalemate! Win cleanly.",       finale="CHECKMATE!"),
    "endgame_kq":      dict(label="K+Q Endgame",         sub="K+Q VS K",         prompt="Convert the Queen endgame!",          finale="CHECKMATE!"),
    "endgame_kr":      dict(label="K+R Endgame",         sub="K+R VS K",         prompt="Convert the Rook endgame!",          finale="CHECKMATE!"),
    "defensive_perp":  dict(label="Perpetual Check",     sub="PERPETUAL CHECK",  prompt="Save the game by repetition!",        finale="DRAW SAVED!"),
    "defensive_stale": dict(label="Stalemate Defense",   sub="STALEMATE DEFENSE",prompt="Sacrifice for a draw!",               finale="DRAW SAVED!"),
}

MIX_WEIGHTS = {
    "mate_in_1": 3.0, "mate_in_2": 3.0, "mate_in_3": 1.2, "back_rank": 1.5, 
    "promotion": 1.5, "en_passant": 0.8, "fork": 1.6, "win_queen": 1.6, 
    "win_rook": 1.3, "sacrifice": 1.2, "smothered": 1.0, "arabian": 1.2, 
    "castle_mate": 0.7, "quiet_mate": 1.0, "double_check": 1.1, "skewer": 1.3, 
    "pawn_fork": 1.4, "win_piece": 1.2, "discovered": 0.9, "remove_defender": 1.0, 
    "trapped_queen": 1.2, "pin_win": 1.0, "boden": 0.8, "epaulette": 0.8, 
    "ladder": 1.0, "queen_fork": 1.4,
    "deflection": 1.2, "overloading": 1.1, "zwischenzug": 1.3, "magnet": 1.0,
    "stalemate_trick": 0.8, "endgame_kq": 1.5, "endgame_kr": 1.5, 
    "defensive_perp": 0.9, "defensive_stale": 0.9
}
MATES_ONLY = ["mate_in_1", "mate_in_2", "mate_in_3"]

KIND_MENU = [("mix", "\U0001F3B2 Mixed \u2014 all categories"),
             ("mates_only", "\u265B Mates only (1, 2 & 3)")] + \
            [(k, KINDS[k]["label"]) for k in KINDS]

PIECE_VALUE = {chess.PAWN: 100, chess.KNIGHT: 315, chess.BISHOP: 330,
               chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 0}

HERO_PIECES = ["Any", "Pawn", "Knight", "Bishop", "Rook", "Queen"]
PIECE_MAP = {"Pawn": chess.PAWN, "Knight": chess.KNIGHT, "Bishop": chess.BISHOP, "Rook": chess.ROOK, "Queen": chess.QUEEN, "King": chess.KING}

CATEGORY_DIFFICULTY = {
    "mate_in_1": 1.0, "win_queen": 1.5, "win_rook": 1.5, "win_piece": 2.0,
    "fork": 2.0, "pawn_fork": 2.0, "double_check": 2.5, "skewer": 2.5,
    "back_rank": 2.0, "promotion": 2.5, "en_passant": 3.0,
    "trapped_queen": 3.0, "remove_defender": 3.0, "pin_win": 3.0, 
    "discovered": 3.0, "queen_fork": 3.0, "castle_mate": 3.0,
    "smothered": 3.5, "arabian": 3.5, "boden": 3.5, "epaulette": 3.5,
    "ladder": 3.5, "mate_in_2": 3.0, "sacrifice": 4.0, "quiet_mate": 4.5, "mate_in_3": 5.0,
    "deflection": 3.0, "overloading": 3.5, "zwischenzug": 3.5, "magnet": 4.0,
    "stalemate_trick": 4.5, "endgame_kq": 2.0, "endgame_kr": 2.5, 
    "defensive_perp": 4.0, "defensive_stale": 4.5
}

def get_category_star_range(kind):
    base = CATEGORY_DIFFICULTY.get(kind, 2.5)
    min_stars = max(1, round(base))
    max_stars = min(5, round(base + 2.0))
    return min_stars, max_stars

def calculate_difficulty(board, line, kind):
    base = CATEGORY_DIFFICULTY.get(kind, 2.5)
    n_moves = len(line)
    n_root = len(list(board.legal_moves))
    extra = 0.0
    if n_moves >= 3: extra += 0.5
    if n_moves >= 5: extra += 0.5
    extra += min(1.0, n_root / 20.0)
    stars = round(base + extra)
    return max(1, min(5, stars))

@dataclass
class VideoConfig:
    fps: int = 30
    solve_seconds: float = 5.0
    channel: str = ""
    outro_seconds: float = 2.2
    eval_bar: bool = False
    stockfish: str = ""
    sfx: bool = True
    music: str = ""
    hide_eval_think: bool = True
    theme: str = "Green"
    resolution: str = "1080p"
    quality: str = "High"
    logo_path: str = ""
    show_coords: bool = True
    show_last_move: bool = True
    show_arrow: bool = True
    show_safe_area: bool = False
    caption_color: str = "#F2F2FA"
    difficulty_min: int = 1
    difficulty_max: int = 5
    retry_failed: bool = True
    black_to_move: bool = False
    hero_piece: str = "Any"

class RenderCancelled(Exception):
    pass

def autodetect_stockfish():
    for cand in STOCKFISH_CANDIDATES:
        try:
            eng = chess.engine.SimpleEngine.popen_uci(cand)
            eng.quit()
            return cand
        except Exception:
            continue
    return None

def _default_manifest_path():
    try:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "puzzle_manifest.json")
    except NameError:
        return os.path.join(os.getcwd(), "puzzle_manifest.json")

MANIFEST_PATH = _default_manifest_path()

def position_key(fen):
    return " ".join(fen.split()[:4])

def load_manifest(path=MANIFEST_PATH):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("puzzles"), dict):
            return {str(k): v for k, v in data["puzzles"].items()}
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning(f"Could not load manifest {path}: {e}")
    return {}

def save_manifest(entries, path=MANIFEST_PATH):
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "puzzles": entries}, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
        return True
    except Exception as e:
        logger.error(f"Could not save manifest {path}: {e}")
        return False

def clamp01(x): return 0.0 if x < 0 else (1.0 if x > 1 else x)
def ease_out_cubic(t): return 1 - (1 - clamp01(t)) ** 3
def ease_out_back(t):
    t = clamp01(t); c1 = 1.70158; c3 = c1 + 1
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2

def lerp_color(a, b, t):
    t = clamp01(t)
    return QColor(int(a.red() + (b.red() - a.red()) * t), int(a.green() + (b.green() - a.green()) * t),
                  int(a.blue() + (b.blue() - a.blue()) * t), int(a.alpha() + (b.alpha() - a.alpha()) * t))

def resolve_fonts():
    global UI_FONT, GLYPH_FONT
    try: fams = set(QFontDatabase.families())
    except Exception: fams = set()
    for name in ("Segoe UI", "SF Pro Text", "Helvetica Neue", "DejaVu Sans", "Arial"):
        if name in fams: UI_FONT = name; break
    for name in ("Segoe UI Symbol", "Noto Sans Symbols 2", "DejaVu Sans", "Apple Symbols", "Arial Unicode MS", "FreeSerif"):
        if name in fams: GLYPH_FONT = name; break

def see_after_capture(board, sq):
    best = 0
    caps = [m for m in board.legal_moves if m.to_square == sq and not board.is_en_passant(m)]
    caps.sort(key=lambda m: PIECE_VALUE[board.piece_type_at(m.from_square)])
    for m in caps:
        gain = PIECE_VALUE.get(board.piece_type_at(sq), 0)
        if m.promotion: gain += PIECE_VALUE[m.promotion] - PIECE_VALUE[chess.PAWN]
        board.push(m); v = gain - see_after_capture(board, sq); board.pop()
        if v > best: best = v
    return best

MATE_CP = 9600
_EVAL_CACHE, _EVAL_LOCK = {}, threading.Lock()
EVAL_VALS = {chess.PAWN: 100, chess.KNIGHT: 320, chess.BISHOP: 330, chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 0}

PST = {
    chess.PAWN: (0,0,0,0,0,0,0,0, 50,50,50,50,50,50,50,50, 10,10,20,30,30,20,10,10, 5,5,10,25,25,10,5,5, 0,0,0,20,20,0,0,0, 5,-5,-10,0,0,-10,-5,5, 5,10,10,-20,-20,10,10,5, 0,0,0,0,0,0,0,0),
    chess.KNIGHT: (-50,-40,-30,-30,-30,-30,-40,-50, -40,-20,0,0,0,0,-20,-40, -30,0,10,15,15,10,0,-30, -30,5,15,20,20,15,5,-30, -30,0,15,20,20,15,0,-30, -30,5,10,15,15,10,5,-30, -40,-20,0,5,5,0,-20,-40, -50,-40,-30,-30,-30,-30,-40,-50),
    chess.BISHOP: (-20,-10,-10,-10,-10,-10,-10,-20, -10,0,0,0,0,0,0,-10, -10,0,5,10,10,5,0,-10, -10,5,5,10,10,5,5,-10, -10,0,10,10,10,10,0,-10, -10,10,10,10,10,10,10,-10, -10,5,0,0,0,0,5,-10, -20,-10,-10,-10,-10,-10,-10,-20),
    chess.ROOK: (0,0,0,0,0,0,0,0, 5,10,10,10,10,10,10,5, -5,0,0,0,0,0,0,-5, -5,0,0,0,0,0,0,-5, -5,0,0,0,0,0,0,-5, -5,0,0,0,0,0,0,-5, -5,0,0,0,0,0,0,-5, 0,0,0,5,5,0,0,0),
    chess.QUEEN: (-20,-10,-10,-5,-5,-10,-10,-20, -10,0,0,0,0,0,0,-10, -10,0,5,5,5,5,0,-10, -5,0,5,5,5,5,0,-5, 0,0,5,5,5,5,0,-5, -10,5,5,5,5,5,0,-10, -10,0,5,0,0,0,0,-10, -20,-10,-10,-5,-5,-10,-10,-20),
    chess.KING: (-30,-40,-40,-50,-50,-40,-40,-30, -30,-40,-40,-50,-50,-40,-40,-30, -30,-40,-40,-50,-50,-40,-40,-30, -30,-40,-40,-50,-50,-40,-40,-30, -20,-30,-30,-40,-40,-30,-30,-20, -10,-20,-20,-20,-20,-20,-20,-10, 20,20,0,0,0,0,20,20, 20,30,10,0,0,10,30,20),
}
PST_KING_EG = (-50,-40,-30,-20,-20,-30,-40,-50, -30,-20,-10,0,0,-10,-20,-30, -30,-10,20,30,30,20,-10,-30, -30,-10,30,40,40,30,-10,-30, -30,-10,30,40,40,30,-10,-30, -30,-10,20,30,30,20,-10,-30, -30,-30,0,0,0,0,-30,-30, -50,-30,-30,-30,-30,-30,-30,-50)

def static_eval(board):
    if board.is_checkmate(): return -MATE_CP if board.turn == chess.WHITE else MATE_CP
    if board.is_stalemate() or board.is_insufficient_material(): return 0
    pieces = board.piece_map()
    queens = any(pc.piece_type == chess.QUEEN for pc in pieces.values())
    heavy = sum(1 for pc in pieces.values() if pc.piece_type in (chess.ROOK, chess.QUEEN))
    ktab = PST[chess.KING] if (queens or heavy >= 2) else PST_KING_EG
    score = 0
    for sq, pc in pieces.items():
        f, r = chess.square_file(sq), chess.square_rank(sq)
        tab = ktab if pc.piece_type == chess.KING else PST[pc.piece_type]
        if pc.color == chess.WHITE: score += EVAL_VALS[pc.piece_type] + tab[(7 - r) * 8 + f]
        else: score -= EVAL_VALS[pc.piece_type] + tab[r * 8 + f]
    return int(score)

def _eval_fen_cached(fen, engine):
    with _EVAL_LOCK:
        if fen in _EVAL_CACHE: return _EVAL_CACHE[fen]
    board = chess.Board(fen)
    cp = None
    if engine is not None:
        try:
            info = engine.analyse(board, chess.engine.Limit(depth=12, time=0.30))
            cp = info["score"].white().score(mate_score=MATE_CP)
        except Exception: cp = None
    if cp is None: cp = static_eval(board)
    with _EVAL_LOCK: _EVAL_CACHE[fen] = int(cp)
    return int(cp)

def attach_evals(puzzles, stockfish_path=None, progress=None):
    engine = None
    if stockfish_path:
        try:
            engine = chess.engine.SimpleEngine.popen_uci(stockfish_path)
            try: engine.configure({"Threads": 2})
            except Exception: pass
        except Exception as e:
            engine = None
            progress and progress(f"\u26a0 Could not start Stockfish ({e}) \u2014 using built-in eval.")
    for i, pz in enumerate(puzzles):
        pz["evals"] = [_eval_fen_cached(b.fen(), engine) for b in pz["boards"]]
        if progress: progress(f"Evaluating {i + 1}/{len(puzzles)}\u2026")
    if engine is not None:
        try: engine.quit()
        except Exception: pass
    return engine is not None

def cp_to_frac(cp):
    if cp >= 9000: return 1.0
    if cp <= -9000: return 0.0
    f = 1.0 / (1.0 + math.exp(-cp / 400.0))
    return 0.04 + 0.92 * f

def eval_text(cp):
    if cp >= 9000: return f"M{max(1, (MATE_CP - cp) // 100)}"
    if cp <= -9000: return f"-M{max(1, (MATE_CP + cp) // 100)}"
    v = cp / 100.0
    return "0.0" if abs(v) < 0.05 else f"{v:+.1f}"

# ----------------------------- audio engine ---------------------------------

SR = 44100
PIECE_FREQ = {chess.PAWN: 220, chess.KNIGHT: 280, chess.BISHOP: 250, chess.ROOK: 190, chess.QUEEN: 320, chess.KING: 200}

def _env(n, attack=0.004, decay=0.15):
    t = np.arange(n, dtype=np.float32) / SR
    env = np.exp(-t / max(1e-4, decay))
    a = max(1, int(attack * SR))
    env[:a] *= np.linspace(0, 1, a, dtype=np.float32)
    return env

def _tone(freq, dur, kind="sine", decay=0.15, amp=0.5):
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    if kind == "tri": s = 2.0 * np.abs(2.0 * ((freq * t) % 1.0) - 1.0) - 1.0
    elif kind == "sq": s = np.sign(np.sin(2 * np.pi * freq * t))
    else: s = np.sin(2 * np.pi * freq * t)
    return (s * _env(n, decay=decay) * amp).astype(np.float32)

def _noise(dur, amp=0.4, decay=0.05, attack=0.004):
    n = int(dur * SR)
    g = np.random.default_rng(7).standard_normal(n).astype(np.float32)
    return (g * _env(n, attack=attack, decay=decay) * amp).astype(np.float32)

def sfx_move(piece_type=None):
    f = PIECE_FREQ.get(piece_type, 190)
    return _tone(f, 0.09, "tri", 0.05, 0.65) + _tone(f * 6.6, 0.03, "sine", 0.02, 0.22) + _noise(0.035, 0.12, 0.02)

def sfx_capture():
    return _tone(115, 0.18, "tri", 0.08, 0.8) + _tone(75, 0.22, "sine", 0.10, 0.5) + _noise(0.09, 0.28, 0.045)

def sfx_check():
    a = _tone(880, 0.08, "sine", 0.05, 0.30)
    gap = np.zeros(int(0.02 * SR), dtype=np.float32)
    b = _tone(1174.7, 0.13, "sine", 0.08, 0.28)
    return np.concatenate([a, gap, b])

def sfx_tick(): return _tone(1046, 0.03, "sine", 0.012, 0.22)
def sfx_ding(): return _tone(1568, 0.16, "sine", 0.10, 0.24)
def sfx_whoosh(): return _noise(0.35, 0.5, 0.18, attack=0.12)
def sfx_finale():
    out = np.zeros(int(1.0 * SR), dtype=np.float32)
    for i, f in enumerate((523.25, 659.25, 783.99, 1046.5)):
        t0 = int(i * 0.06 * SR)
        s = _tone(f, 0.9, "sine", 0.45, 0.20)
        out[t0:t0 + len(s)] += s[:len(out) - t0]
    return out

def iter_audio_events(puzzles, cfg):
    t = 0.0
    for pz in puzzles:
        acc = 0.0
        for name, d, data in build_segments(pz, cfg):
            gt = t + acc
            if name == "start_board": 
                yield (gt, "whoosh", False, False, None)
                for s in range(int(d - BOARD_IN_D)): 
                    yield (gt + BOARD_IN_D + s, "tick", False, False, None)
            elif name == "answer": yield (gt, "ding", False, False, None)
            elif name == "move":
                i = data["idx"]
                b = pz["boards"][i]
                cap = b.is_capture(pz["line"][i])
                chk = pz["boards"][i + 1].is_check()
                ptype = b.piece_type_at(pz["line"][i].from_square)
                yield (gt, "move", cap, chk, ptype)
            elif name == "finale": yield (gt, "finale", False, False, None)
            acc += d
        t += acc

def _load_music(path, total):
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    tmp = tempfile.mktemp(prefix="css_music_", suffix=".wav")
    try:
        subprocess.run([exe, "-y", "-i", path, "-ac", "1", "-ar", str(SR), "-loglevel", "error", tmp], check=True, capture_output=True)
        with wave.open(tmp, "rb") as w: raw = w.readframes(w.getnframes())
        data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
        need = int(total * SR)
        if len(data) == 0: return np.zeros(need, dtype=np.float32)
        return np.tile(data, int(np.ceil(need / len(data))))[:need]
    finally:
        try: os.remove(tmp)
        except OSError: pass

def build_audio_track(puzzles, cfg, total):
    n = int(total * SR) + SR // 10
    mix = np.zeros(n, dtype=np.float32)
    def put(t, samples):
        i = int(t * SR)
        if i < 0 or i >= n: return
        j = min(n, i + len(samples))
        if j > i: mix[i:j] += samples[:j - i]
    for t, name, cap, chk, ptype in iter_audio_events(puzzles, cfg):
        if name == "whoosh": put(t, sfx_whoosh())
        elif name == "tick": put(t, sfx_tick())
        elif name == "ding": put(t, sfx_ding())
        elif name == "move":
            put(t, sfx_capture() if cap else sfx_move(ptype))
            if chk: put(t + 0.13, sfx_check())
        elif name == "finale": put(t, sfx_finale())
    if cfg.music and os.path.isfile(cfg.music):
        try:
            mus = _load_music(cfg.music, total) * 0.16
            mix[:len(mus)] += mus
        except Exception as e: logger.warning(f"Music skipped: {e}")
    peak = float(np.max(np.abs(mix))) if len(mix) else 0.0
    if peak > 0.97: mix *= 0.97 / peak
    return mix

def add_audio_track(video_path, puzzles, cfg, stage=None):
    total = total_duration(puzzles, cfg)
    mix = build_audio_track(puzzles, cfg, total)
    wav = tempfile.mktemp(prefix="css_audio_", suffix=".wav")
    try:
        with wave.open(wav, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
            w.writeframes((np.clip(mix, -1, 1) * 32767).astype("<i2").tobytes())
        tmp = video_path + ".mux.mp4"
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        r = subprocess.run([exe, "-y", "-i", video_path, "-i", wav, "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", tmp], capture_output=True)
        if r.returncode != 0 or not os.path.exists(tmp): raise RuntimeError(r.stderr.decode(errors="ignore")[-400:])
        os.replace(tmp, video_path)
        if stage: stage("Audio mixed in \u2714")
    finally:
        try: os.remove(wav)
        except OSError: pass

def puzzle_to_dict(pz):
    return {"fen": pz["fen"], "line": [m.uci() for m in pz["line"]], "kind": pz["kind"], "label": pz["label"], "sub": pz["sub"], "finale": pz["finale"], "prompt": pz["prompt"], "stars": pz.get("stars", 3), "alts": pz.get("alts", 1), "san": pz.get("san", "")}

def make_black_to_move(pz):
    b = chess.Board(pz["fen"])
    rows = b.fen().split()[0].split('/')
    new_rows = []
    for row in reversed(rows):
        new_row = ""
        for char in row:
            if char.isupper(): new_row += char.lower()
            elif char.islower(): new_row += char.upper()
            else: new_row += char
        new_rows.append(new_row)
    placement = '/'.join(new_rows)
    active = 'b' if b.turn == chess.WHITE else 'w'
    castling = b.fen().split()[2]
    if castling != '-':
        castling = castling.swapcase()
        c_sorted = ""
        for c in "KQkq":
            if c in castling: c_sorted += c
        castling = c_sorted if c_sorted else '-'
    ep = b.fen().split()[3]
    if ep != '-':
        file = ep[0]; rank = ep[1]
        new_rank = '6' if rank == '3' else '3' if rank == '6' else rank
        ep = file + new_rank
    halfmove = b.fen().split()[4]; fullmove = b.fen().split()[5]
    new_fen = f"{placement} {active} {castling} {ep} {halfmove} {fullmove}"
    new_board = chess.Board(new_fen)
    new_line = []
    for mv in pz["line"]:
        from_sq = chess.square_mirror(mv.from_square)
        to_sq = chess.square_mirror(mv.to_square)
        new_line.append(chess.Move(from_sq, to_sq, promotion=mv.promotion))
    try: san = new_board.variation_san(new_line)
    except Exception: san = " ".join(m.uci() for m in new_line)
    boards = [new_board.copy(stack=False)]
    b2 = new_board.copy(stack=False)
    for mv in new_line:
        b2.push(mv); boards.append(b2.copy(stack=False))
    sans = re.sub(r"\d+\.+", "", san).split()
    return {"fen": new_board.fen(), "line": new_line, "kind": pz["kind"], "label": pz["label"], "sub": pz["sub"], "finale": pz["finale"], "prompt": pz["prompt"], "san": san, "sans": sans, "boards": boards, "alts": pz["alts"], "stars": pz["stars"], "evals": [static_eval(x) for x in boards]}

def dict_to_puzzle(d):
    board = chess.Board(d["fen"])
    line = [chess.Move.from_uci(u) for u in d["line"]]
    pz = make_puzzle(board, line, d["kind"], d["label"], d["sub"], d["finale"], d["prompt"], alts=d.get("alts", 1))
    pz["stars"] = d.get("stars", pz["stars"])
    pz["san"] = d.get("san", pz["san"])
    return pz

def save_puzzle_pack(puzzles, path):
    try:
        with open(path, "w", encoding="utf-8") as f: json.dump({"version": 1, "puzzles": [puzzle_to_dict(p) for p in puzzles]}, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"Pack save failed: {e}")
        return False

def load_puzzle_pack(path):
    try:
        with open(path, "r", encoding="utf-8") as f: data = json.load(f)
        return [dict_to_puzzle(d) for d in data.get("puzzles", [])]
    except Exception as e:
        logger.error(f"Pack load failed: {e}")
        return None

TITLE_TEMPLATES = [
    lambda head, diff: f"{head} \u265F {diff}? Can you solve it?",
    lambda head, diff: f"Only 1% solve this {head}! \u265F {diff}",
    lambda head, diff: f"{diff} {head} \u265F Find the move!",
    lambda head, diff: f"\u265A {head} \u2014 {diff} puzzle. Your move!",
    lambda head, diff: f"Beat this {diff} {head}! \u265F Chess puzzle",
    lambda head, diff: f"{head} \u2014 can you find it? \u265F {diff}",
    lambda head, diff: f"\u265F {diff}! {head} \u2014 solve in 1!",
]

def suggest_title(puzzles):
    kinds = []
    for pz in puzzles:
        if pz["label"] not in kinds: kinds.append(pz["label"])
    stars = max(pz.get("stars", 3) for pz in puzzles)
    diff = ["Easy", "Medium", "Hard", "Very hard", "Insane"][min(4, stars - 1)]
    if len(kinds) == 1: head = kinds[0]
    elif len(kinds) == 2: head = f"{kinds[0]} & {kinds[1]}"
    else: head = f"{len(puzzles)} chess puzzles"
    template = random.choice(TITLE_TEMPLATES)
    title = template(head, diff)
    tags = "#chess #chesspuzzle #shorts #checkmate #chesstactics #chesscom"
    return title, tags

# ----------------------------- drawing primitives ---------------------------

_BG_CACHE = {}

def draw_bg(p, w, h):
    key = (int(w), int(h), CUSTOM_BG_TOP.rgb(), CUSTOM_BG_BOTTOM.rgb())
    img = _BG_CACHE.get(key)
    if img is None:
        img = QImage(int(w), int(h), QImage.Format_RGB888)
        ip = QPainter(img)
        g = QLinearGradient(0.0, 0.0, 0.0, float(h))
        g.setColorAt(0.0, CUSTOM_BG_TOP); g.setColorAt(1.0, CUSTOM_BG_BOTTOM)
        ip.fillRect(QRectF(0, 0, w, h), QBrush(g))
        ip.end()
        _BG_CACHE[key] = img
    p.drawImage(QPointF(0, 0), img)

def draw_text(p, cx, cy, text, px, color, bold=True, alpha=None, spacing=0.0):
    f = QFont(UI_FONT) if UI_FONT else QFont()
    f.setPixelSize(max(1, int(px))); f.setBold(bold)
    if spacing: f.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
    fm = QFontMetrics(f)
    c = QColor(color)
    if alpha is not None: c.setAlpha(max(0, min(255, int(alpha))))
    p.setFont(f); p.setPen(QPen(c))
    baseline = cy + (fm.ascent() - fm.descent()) / 2.0
    p.drawText(QPointF(cx - fm.horizontalAdvance(text) / 2.0, baseline), text)

def draw_outlined_text(p, cx, cy, text, px, fill, outline, ow=None, bold=True, spacing=0.0, alpha=None):
    f = QFont(UI_FONT) if UI_FONT else QFont()
    f.setPixelSize(max(1, int(px))); f.setBold(bold)
    if spacing: f.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
    fm = QFontMetrics(f)
    fc, oc = QColor(fill), QColor(outline)
    if alpha is not None:
        fc.setAlpha(max(0, min(255, int(fc.alpha() * alpha / 255.0))))
        oc.setAlpha(max(0, min(255, int(oc.alpha() * alpha / 255.0))))
    baseline = cy + (fm.ascent() - fm.descent()) / 2.0
    path = QPainterPath()
    path.addText(QPointF(cx - fm.horizontalAdvance(text) / 2.0, baseline), f, text)
    p.setPen(QPen(oc, ow if ow else max(2.0, px * 0.06), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(QBrush(fc))
    p.drawPath(path)

def draw_glyph(p, cx, cy, size, ch, fill, outline):
    f = QFont(GLYPH_FONT) if GLYPH_FONT else QFont()
    f.setPixelSize(max(6, int(size * 1.02)))
    fm = QFontMetrics(f)
    baseline = cy + (fm.ascent() - fm.descent()) / 2.0
    path = QPainterPath()
    path.addText(QPointF(cx - fm.horizontalAdvance(ch) / 2.0, baseline), f, ch)
    p.setPen(QPen(outline, max(1.0, size * 0.03), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(QBrush(fill))
    p.drawPath(path)

def draw_arrow(p, p1, p2, color, width, alpha=1.0):
    if alpha <= 0.01: return
    c = QColor(color); c.setAlpha(int(c.alpha() * clamp01(alpha)))
    ang = math.atan2(p2.y() - p1.y(), p2.x() - p1.x())
    head = max(14.0, width * 1.6)
    end = QPointF(p2.x() - math.cos(ang) * head * 0.7, p2.y() - math.sin(ang) * head * 0.7)
    p.setPen(QPen(c, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawLine(p1, end)
    p.setPen(Qt.NoPen); p.setBrush(QBrush(c))
    h1 = QPointF(p2.x() - math.cos(ang - 0.42) * head, p2.y() - math.sin(ang - 0.42) * head)
    h2 = QPointF(p2.x() - math.cos(ang + 0.42) * head, p2.y() - math.sin(ang + 0.42) * head)
    p.drawPolygon(QPolygonF([p2, h1, h2]))

def draw_countdown(p, x, y, w, h, frac):
    frac = clamp01(frac)
    p.setPen(Qt.NoPen); p.setBrush(QColor(255, 255, 255, 38))
    p.drawRoundedRect(QRectF(x, y, w, h), h / 2, h / 2)
    if frac <= 0.003: return
    if frac > 0.5: c = lerp_color(QColor("#FFC107"), QColor("#4CAF50"), (frac - 0.5) * 2)
    else: c = lerp_color(QColor("#F44336"), QColor("#FFC107"), frac * 2)
    p.setBrush(c)
    p.drawRoundedRect(QRectF(x, y, max(h, w * frac), h), h / 2, h / 2)

def _flip_square(sq):
    return chess.square(7 - chess.square_file(sq), 7 - chess.square_rank(sq))

def square_rect(rect, sq, flipped=False):
    s = rect.width() / 8.0
    f = chess.square_file(sq); r = chess.square_rank(sq)
    if flipped: f, r = 7 - f, 7 - r
    return QRectF(rect.x() + f * s, rect.y() + (7 - r) * s, s, s)

def square_center(rect, sq, flipped=False):
    r = square_rect(rect, sq, flipped)
    return QPointF(r.x() + r.width() / 2.0, r.y() + r.height() / 2.0)

def draw_board(p, st, rect, u, flipped=False):
    p.save()
    p.setOpacity(clamp01(st.board_alpha))
    s = rect.width() / 8.0
    show_coords = getattr(st, "show_coords", True)
    show_last = getattr(st, "show_last_move", True)
    show_arrow = getattr(st, "show_arrow", True)

    for dy in range(8):
        rank = 7 - dy if not flipped else dy
        for dx in range(8):
            file = dx if not flipped else 7 - dx
            light = (rank + file) % 2 == 1
            p.fillRect(QRectF(rect.x() + dx * s, rect.y() + dy * s, s, s), st.light_sq if light else st.dark_sq)

    if show_last and st.last_move:
        for sq in st.last_move: p.fillRect(square_rect(rect, sq, flipped), LAST_MOVE_TINT)
    if show_arrow and st.arrow and st.arrow_alpha > 0:
        for sq in st.arrow: p.fillRect(square_rect(rect, sq, flipped), QColor(255, 255, 255, 42))

    if show_coords:
        fcoord = QFont(UI_FONT) if UI_FONT else QFont()
        fcoord.setPixelSize(max(7, int(s * 0.17)))
        p.setFont(fcoord)
        for i in range(8):
            file_idx = i if not flipped else 7 - i
            dark_text = (file_idx + (7 if not flipped else 0)) % 2 == 1
            c = QColor(35, 40, 35, 160) if dark_text else QColor(240, 240, 240, 160)
            p.setPen(QPen(c))
            p.drawText(QRectF(rect.x() + i * s, rect.y() + 7 * s + s * 0.55, s * 0.92, s * 0.42), Qt.AlignRight | Qt.AlignVCenter, chr(ord("a") + file_idx))
            rank_idx = 7 - i if not flipped else i
            dark_text = (rank_idx + 0) % 2 == 1
            c = QColor(35, 40, 35, 160) if dark_text else QColor(240, 240, 240, 160)
            p.setPen(QPen(c))
            p.drawText(QRectF(rect.x() + s * 0.06, rect.y() + (7 - i) * s + s * 0.04, s * 0.5, s * 0.42), Qt.AlignLeft | Qt.AlignTop, str(rank_idx + 1))

    def piece_colors(pc):
        if pc.color == chess.WHITE: return QColor("#FFFFFF"), QColor("#333333")
        else: return QColor("#333333"), QColor("#FFFFFF")

    b = st.board
    hide_from = st.moving[1] if (st.moving and st.moving[3] < 0.999 and st.moving[0]) else None
    if hide_from is not None and flipped: hide_from = _flip_square(hide_from)
    for dy in range(8):
        rank = 7 - dy
        for dx in range(8):
            sq = rank * 8 + dx
            pc = b.piece_at(sq)
            if pc is None or sq == hide_from: continue
            fill, outline = piece_colors(pc)
            draw_glyph(p, rect.x() + dx * s + s / 2, rect.y() + dy * s + s / 2, s * 0.80, SOLID_GLYPHS[pc.piece_type], fill, outline)

    if st.moving and st.moving[0] is not None:
        piece, fsq, tsq, frac = st.moving
        if flipped: fsq, tsq = _flip_square(fsq), _flip_square(tsq)
        e = ease_out_cubic(frac)
        c1, c2 = square_center(rect, fsq, flipped), square_center(rect, tsq, flipped)
        cx = c1.x() + (c2.x() - c1.x()) * e
        cy = c1.y() + (c2.y() - c1.y()) * e
        scale = 1.0 + 0.10 * math.sin(math.pi * clamp01(frac))
        fill, outline = piece_colors(piece)
        draw_glyph(p, cx, cy, s * 0.80 * scale, SOLID_GLYPHS[piece.piece_type], fill, outline)

    if show_arrow and st.arrow and st.arrow_alpha > 0:
        a1, a2 = square_center(rect, st.arrow[0], flipped), square_center(rect, st.arrow[1], flipped)
        draw_arrow(p, a1, a2, CUSTOM_ARROW, s * 0.20, st.arrow_alpha)

    p.restore()

def draw_eval_bar(p, rect, frac, label, alpha):
    alpha = clamp01(alpha)
    if alpha <= 0.01: return
    p.save(); p.setOpacity(alpha)
    radius = rect.width() * 0.22
    path = QPainterPath(); path.addRoundedRect(rect, radius, radius)
    p.setPen(Qt.NoPen); p.setBrush(QColor("#23252F")); p.drawPath(path)
    p.save(); p.setClipPath(path)
    fh = rect.height() * clamp01(frac)
    p.setBrush(QColor("#F4F4F2")); p.drawRect(QRectF(rect.x(), rect.bottom() - fh, rect.width(), fh))
    p.restore()
    p.setPen(QPen(QColor(255, 255, 255, 60), 1.4)); p.setBrush(Qt.NoBrush); p.drawPath(path)
    y = rect.bottom() - fh
    p.setPen(QPen(QColor(120, 125, 140, 220), 1.2))
    p.drawLine(QPointF(rect.x() + 1, y), QPointF(rect.right() - 1, y))
    if label:
        white_ahead = frac >= 0.5
        chip_h = rect.width() * 0.92; chip_w = rect.width() * 1.55
        cy = rect.bottom() - fh / 2.0 if white_ahead else rect.top() + (rect.height() - fh) / 2.0
        chip = QRectF(rect.center().x() - chip_w / 2.0, cy - chip_h / 2.0, chip_w, chip_h)
        p.setPen(QPen(QColor(0, 0, 0, 60), 1))
        if white_ahead:
            p.setBrush(QColor("#F7F7F3")); p.drawRoundedRect(chip, chip_h * 0.45, chip_h * 0.45); tcol = QColor("#20232E")
        else:
            p.setBrush(QColor(18, 20, 30, 235)); p.drawRoundedRect(chip, chip_h * 0.45, chip_h * 0.45); tcol = QColor("#EDEDF2")
        draw_text(p, chip.center().x(), cy, label, rect.width() * 0.5, tcol)
    p.restore()

CONFETTI_COLORS = ["#FFD54A", "#FF6B6B", "#4ECDC4", "#95E1D3", "#AA96DA", "#FCBAD3", "#A8E6CF", "#FF8C94"]

def confetti_particles(seed, t, w, h):
    rng = random.Random(seed); out = []
    if t < 0: return out
    n = 80
    for i in range(n):
        x0 = rng.uniform(0, w); y0 = rng.uniform(-h * 0.15, -10)
        vx = rng.uniform(-40, 40); vy = rng.uniform(80, 220)
        color = QColor(CONFETTI_COLORS[i % len(CONFETTI_COLORS)])
        life = rng.uniform(1.2, 2.4); size = rng.uniform(6, 14)
        if t > life: continue
        ny = y0 + vy * t; nx = x0 + vx * t + 25 * math.sin(t * 4 + i)
        alpha = 1.0 - (t / life)
        out.append((nx, ny, color, alpha, size, rng.uniform(0, math.pi * 2)))
    return out

def draw_confetti(p, particles, t, u):
    p.save()
    for x, y, color, alpha, size, rot0 in particles:
        c = QColor(color); c.setAlphaF(alpha * 0.85)
        p.setBrush(c); p.setPen(Qt.NoPen)
        p.save(); p.translate(x, y); p.rotate(math.degrees(rot0 + t * 4))
        p.drawRect(QRectF(-size * u / 2, -size * u / 4, size * u, size * u / 2))
        p.restore()
    p.restore()

_LOGO_CACHE = {"path": None, "img": None}

def load_logo(path):
    if not path or not os.path.isfile(path):
        _LOGO_CACHE["path"] = None; _LOGO_CACHE["img"] = None; return None
    if _LOGO_CACHE["path"] == path and _LOGO_CACHE["img"] is not None: return _LOGO_CACHE["img"]
    try:
        img = QImage(path)
        if img.isNull(): return None
        _LOGO_CACHE["path"] = path; _LOGO_CACHE["img"] = img
        return img
    except Exception: return None

def draw_logo(p, st, w, h, u):
    if not st.logo_path: return
    img = load_logo(st.logo_path)
    if img is None: return
    max_w = 220 * u; max_h = 80 * u
    iw, ih = img.width(), img.height()
    scale = min(max_w / iw, max_h / ih, 1.0)
    dw, dh = int(iw * scale), int(ih * scale)
    x = (w - dw) / 2; y = h * 0.965 - dh / 2
    p.save(); p.setOpacity(0.9); p.drawImage(QRectF(x, y, dw, dh), img); p.restore()

def draw_safe_area(p, w, h):
    p.save()
    p.setPen(QPen(QColor(255, 60, 60, 180), 2, Qt.DashLine))
    p.setBrush(Qt.NoBrush)
    sx, sy = w * 0.05, h * 0.05
    p.drawRect(QRectF(sx, sy, w - 2 * sx, h - 2 * sy))
    p.setPen(QPen(QColor(255, 200, 60, 140), 1, Qt.DashLine))
    tx, ty = w * 0.10, h * 0.10
    p.drawRect(QRectF(tx, ty, w - 2 * tx, h - 2 * ty))
    p.restore()

class FrameState:
    def __init__(self):
        self.board = None; self.moving = None; self.arrow = None; self.arrow_alpha = 0.0
        self.last_move = None; self.board_alpha = 1.0; self.board_dy = 0.0
        self.countdown = None; self.header_title = ""; self.header_sub = ""
        self.caption = ""; self.pop_text = None; self.pop_progress = 0.0
        self.center_text = None; self.center_glyph = None; self.watermark = None
        self.eval_frac = None; self.eval_label = ""
        self.light_sq = LIGHT_SQ; self.dark_sq = DARK_SQ
        self.show_coords = True; self.show_last_move = True; self.show_arrow = True
        self.show_safe_area = False; self.caption_color = "#F2F2FA"; self.logo_path = ""
        self.flipped = False; self.confetti_seed = 0; self.confetti_t = -1.0; self.confetti_alpha = 0.0
        self.stars = 0

def build_segments(pz, cfg):
    segs = [
        ("intro", INTRO_D, {}),                    # 1. Title screen
        ("start_board", float(cfg.solve_seconds), {}) # 2. Starting puzzle board
    ]
    # 3. Animation of the puzzle being solved
    n = len(pz["line"])
    for i in range(n):
        segs.append(("answer", ANSWER_D, {"idx": i}))
        segs.append(("move", MOVE_D, {"idx": i}))
        if i < n - 1: segs.append(("pause", PAUSE_D, {"idx": i}))
    
    # 4. Final puzzle board of the solution
    segs.append(("finale", FINALE_D, {}))
    segs.append(("gap", GAP_D, {}))
    return segs

def puzzle_duration(pz, cfg): return sum(d for _, d, _ in build_segments(pz, cfg))
def total_duration(puzzles, cfg): return sum(puzzle_duration(p, cfg) for p in puzzles) + cfg.outro_seconds

def _apply_theme(st, cfg):
    light, dark = THEMES.get(getattr(cfg, "theme", "Green") or "Green", THEMES["Green"])
    st.light_sq, st.dark_sq = QColor(light), QColor(dark)

def _apply_view_opts(st, cfg):
    st.show_coords = getattr(cfg, "show_coords", True)
    st.show_last_move = getattr(cfg, "show_last_move", True)
    st.show_arrow = getattr(cfg, "show_arrow", True)
    st.show_safe_area = getattr(cfg, "show_safe_area", False)
    st.caption_color = getattr(cfg, "caption_color", "#F2F2FA")
    st.logo_path = getattr(cfg, "logo_path", "")

def _eval_state(pz, cfg, i, j=None, tfrac=0.0):
    evals = pz.get("evals")
    if not cfg.eval_bar or not evals or i >= len(evals): return None, ""
    cp = float(evals[i])
    if j is not None and j < len(evals): cp += (float(evals[j]) - cp) * clamp01(tfrac)
    cp = int(round(cp))
    return cp_to_frac(cp), eval_text(cp)

def puzzle_state_at(pz, index, cfg, t, flipped=False):
    segs = build_segments(pz, cfg)
    line, boards, sans = pz["line"], pz["boards"], pz["sans"]
    local = 0.0; acc = 0.0
    name, dur, data = segs[-1][0], segs[-1][1], segs[-1][2]
    for nm, d, dt in segs:
        if t < acc + d - 1e-9: name, dur, data, local = nm, d, dt, t - acc; break
        acc += d
    st = FrameState()
    _apply_theme(st, cfg); _apply_view_opts(st, cfg)
    st.flipped = flipped
    st.header_title = pz["label"]
    st.header_sub = pz["sub"]
    st.confetti_seed = index * 1000 + 7
    st.stars = pz.get("stars", 3)
    
    side_to_move = "Black" if pz["fen"].split()[1] == 'b' else "White"
    
    if name == "intro":
        st.center_text = (pz["label"], pz["sub"], 255)
    elif name == "start_board":
        # Animate board sliding in, then hold the starting position
        if local < BOARD_IN_D:
            e = ease_out_cubic(local / BOARD_IN_D)
            st.board = boards[0]; st.board_alpha = e; st.board_dy = (1.0 - e) * 0.10
            st.center_text = (pz["label"], pz["sub"], int(255 * (1.0 - e)))
        else:
            st.board = boards[0]
            st.caption = pz["prompt"]
            st.countdown = clamp01(1.0 - (local - BOARD_IN_D) / max(0.1, dur - BOARD_IN_D))
            if not cfg.hide_eval_think: st.eval_frac, st.eval_label = _eval_state(pz, cfg, 0)
    elif name == "answer":
        i = data["idx"]; st.board = boards[i]; mv = line[i]
        st.arrow = (mv.from_square, mv.to_square); st.arrow_alpha = ease_out_cubic(local / dur)
        if i > 0: st.last_move = (line[i - 1].from_square, line[i - 1].to_square)
        st.caption = f"Answer: {sans[i]}"
        st.eval_frac, st.eval_label = _eval_state(pz, cfg, i)
    elif name == "move":
        i = data["idx"]; st.board = boards[i]; mv = line[i]
        frac = clamp01(local / dur)
        st.moving = (boards[i].piece_at(mv.from_square), mv.from_square, mv.to_square, frac)
        st.arrow = (mv.from_square, mv.to_square); st.arrow_alpha = max(0.0, 1.0 - frac * 1.5)
        if i > 0: st.last_move = (line[i - 1].from_square, line[i - 1].to_square)
        st.caption = sans[i]
        st.eval_frac, st.eval_label = _eval_state(pz, cfg, i, i + 1, frac)
    elif name == "pause":
        i = data["idx"]; st.board = boards[i + 1]
        st.last_move = (line[i].from_square, line[i].to_square)
        st.caption = "\u2026"; st.eval_frac, st.eval_label = _eval_state(pz, cfg, i + 1)
    elif name == "finale":
        st.board = boards[-1]; mv = line[-1]
        st.last_move = (mv.from_square, mv.to_square)
        st.pop_text = pz["finale"]; st.pop_progress = clamp01(local / dur)
        st.caption = "Follow for daily puzzles \u265F"
        st.eval_frac, st.eval_label = _eval_state(pz, cfg, len(line))
        if local > dur * 0.30:
            st.confetti_t = local - dur * 0.30
            st.confetti_alpha = clamp01(min(local - dur * 0.30, 0.4)) * clamp01((dur - local) / 0.5)
    elif name == "gap":
        st.board = boards[-1]; st.board_alpha = clamp01(1.0 - local / dur)
        mv = line[-1]; st.last_move = (mv.from_square, mv.to_square)
        st.eval_frac, st.eval_label = _eval_state(pz, cfg, len(line))
    return st

def outro_state(cfg, t):
    st = FrameState(); _apply_view_opts(st, cfg)
    e = clamp01(t / 0.45)
    st.center_glyph = "\u265F"
    st.center_text = ("FOLLOW FOR MORE!", cfg.channel or "See you in the next puzzle", int(230 * e))
    return st

def global_state_at_time(puzzles, cfg, t, flipped=False):
    acc = 0.0
    for i, pz in enumerate(puzzles):
        d = puzzle_duration(pz, cfg)
        if t < acc + d:
            st = puzzle_state_at(pz, i, cfg, t - acc, flipped=flipped)
            st.watermark = cfg.channel or None
            return st
        acc += d
    st = outro_state(cfg, t - acc)
    st.watermark = cfg.channel or None
    return st

def static_state(pz, index, cfg, show_solution, flipped=False):
    st = FrameState()
    _apply_theme(st, cfg); _apply_view_opts(st, cfg)
    st.flipped = flipped; st.board = pz["boards"][0]
    st.header_title = pz["label"]
    st.header_sub = pz["sub"]
    side_to_move = "Black" if pz["fen"].split()[1] == 'b' else "White"
    st.caption = f"{side_to_move} to move \u00b7 {pz['prompt']}"
    st.watermark = cfg.channel or None
    st.eval_frac, st.eval_label = _eval_state(pz, cfg, 0)
    st.stars = pz.get("stars", 3)
    if show_solution:
        mv = pz["line"][0]
        st.arrow = (mv.from_square, mv.to_square); st.arrow_alpha = 1.0
        first_san = pz["sans"][0] if pz["sans"] else pz["line"][0].uci()
        st.caption = f"Answer: {first_san}"
    return st

def draw_frame(p, st, w, h):
    u = w / 1080.0
    draw_bg(p, w, h)
    bar_w, bar_gap = 34 * u, 16 * u
    has_bar = st.eval_frac is not None
    side = min(w * 0.92 - (bar_w + bar_gap if has_bar else 0), h * 0.50)
    bx = (w - side) / 2.0 + ((bar_w + bar_gap) / 2.0 if has_bar else 0.0)
    by = h * 0.285 + st.board_dy * side
    rect = QRectF(bx, by, side, side)
    if has_bar:
        draw_eval_bar(p, QRectF(bx - bar_gap - bar_w, by, bar_w, side), st.eval_frac, st.eval_label, st.board_alpha)
    if st.board is not None:
        if st.header_title: draw_outlined_text(p, w / 2, h * 0.072, st.header_title, 62 * u, "#FFFFFF", QColor(10, 10, 20, 160), ow=6 * u, spacing=3)
        if st.header_sub: draw_text(p, w / 2, h * 0.135, st.header_sub, 44 * u, GOLD, spacing=6)
        p.setPen(Qt.NoPen); p.setBrush(QColor(0, 0, 0, 100))
        p.drawRoundedRect(rect.adjusted(-16 * u, -16 * u, 16 * u, 16 * u), 26 * u, 26 * u)
        draw_board(p, st, rect, u, flipped=st.flipped)
        if st.caption: draw_text(p, w / 2, rect.bottom() + 74 * u, st.caption, 42 * u, QColor(st.caption_color))
        if st.countdown is not None:
            bw = side * 0.8
            draw_countdown(p, (w - bw) / 2, rect.bottom() + 128 * u, bw, 22 * u, st.countdown)
        if st.pop_text:
            frac = st.pop_progress
            sc = ease_out_back(clamp01(frac / 0.30))
            alpha = 255 if frac < 0.72 else int(255 * clamp01((1 - frac) / 0.28))
            p.save(); p.translate(rect.center().x(), rect.center().y()); p.scale(max(0.01, sc), max(0.01, sc))
            draw_outlined_text(p, 0, 0, st.pop_text, 110 * u, "#FFD54A", QColor(20, 10, 0, 200), ow=12 * u, alpha=alpha)
            p.restore()
    
    if st.stars > 0:
        star_str = "\u2605" * st.stars + "\u2606" * (5 - st.stars)
        draw_text(p, w * 0.95, h * 0.05, star_str, 32 * u, QColor("#FFD700"), spacing=2)

    if st.confetti_t is not None and st.confetti_t >= 0 and st.confetti_alpha > 0:
        parts = confetti_particles(st.confetti_seed, st.confetti_t, w, h)
        p.save(); p.setOpacity(st.confetti_alpha); draw_confetti(p, parts, st.confetti_t, u); p.restore()
    if st.center_glyph:
        draw_glyph(p, w / 2, h * 0.34, 230 * u, st.center_glyph, QColor("#F5F5F0"), QColor(15, 15, 25, 190))
    if st.center_text:
        main, sub, alpha = st.center_text
        y = h * 0.55 if st.center_glyph else h * 0.40
        draw_outlined_text(p, w / 2, y, main, 92 * u, "#FFFFFF", QColor(10, 10, 20, 170), ow=8 * u, spacing=4, alpha=alpha)
        if sub: draw_text(p, w / 2, y + 0.075 * h, sub, 46 * u, GOLD, spacing=5, alpha=alpha)
    if st.logo_path: draw_logo(p, st, w, h, u)
    elif st.watermark: draw_text(p, w / 2, h * 0.925, st.watermark, 30 * u, QColor(255, 255, 255, 120), bold=False)
    if st.show_safe_area: draw_safe_area(p, w, h)

def qimage_to_array(img):
    h, w = img.height(), img.width()
    bpl = img.bytesPerLine()
    arr = np.frombuffer(img.constBits(), dtype=np.uint8).reshape(h, bpl)
    arr = arr[:, : w * 3].reshape(h, w, 3)
    return np.ascontiguousarray(arr)

_RENDER_BUF = {"img": None, "key": None}

def render_state_to_array(st, w, h):
    key = (w, h)
    img = _RENDER_BUF["img"]
    if img is None or _RENDER_BUF["key"] != key:
        img = QImage(w, h, QImage.Format_RGB888)
        _RENDER_BUF["img"] = img; _RENDER_BUF["key"] = key
    img.fill(0)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True); p.setRenderHint(QPainter.TextAntialiasing, True)
    draw_frame(p, st, w, h)
    p.end()
    return qimage_to_array(img)

def render_video(puzzles, out_path, cfg, progress=None, cancel=None, stage=None):
    fps = int(cfg.fps); dur = total_duration(puzzles, cfg)
    n_frames = max(1, int(round(dur * fps)))
    w, h = RESOLUTIONS.get(cfg.resolution, RESOLUTIONS["1080p"])
    crf = QUALITY_CRF.get(cfg.quality, 18)
    if stage: stage(f"Rendering {n_frames} frames ({w}x{h}, {dur:.1f}s @ {fps} fps, CRF {crf})")
    writer = imageio.get_writer(out_path, fps=fps, codec="libx264", quality=8, pixelformat="yuv420p", macro_block_size=1, ffmpeg_params=["-movflags", "+faststart", "-crf", str(crf), "-preset", "medium"])
    try:
        for i in range(n_frames):
            if cancel is not None and (i % 10 == 0) and cancel(): raise RenderCancelled()
            st = global_state_at_time(puzzles, cfg, i / fps, flipped=cfg.black_to_move)
            writer.append_data(render_state_to_array(st, w, h))
            if progress is not None and (i % 3 == 0 or i == n_frames - 1): progress(i + 1, n_frames)
    finally: writer.close()
    if cfg.sfx or cfg.music:
        if stage: stage("Mixing audio\u2026")
        try: add_audio_track(out_path, puzzles, cfg, stage)
        except Exception as e:
            if stage: stage(f"\u26a0 Audio skipped ({e})")

# ----------------------------- puzzle construction --------------------------

def make_puzzle(board, line, kind, label, sub, finale, prompt, alts=1):
    line = list(line)
    b = chess.Board(board.fen())
    try: san = b.variation_san(line)
    except Exception: san = " ".join(m.uci() for m in line)
    boards = [b.copy(stack=False)]
    for mv in line:
        b.push(mv); boards.append(b.copy(stack=False))
    sans = re.sub(r"\d+\.+", "", san).split()
    stars = calculate_difficulty(board, line, kind)
    return {"fen": board.fen(), "line": line, "kind": kind, "label": label, "sub": sub, "finale": finale, "prompt": prompt, "san": san, "sans": sans, "boards": boards, "alts": alts, "stars": stars, "evals": [static_eval(x) for x in boards]}

# ----------------------------- expert generation algorithms -----------------

SYZYGY_PATH = ""
PN_INF = 10 ** 9
MATE_SCORE = 1_000_000

def tt_fen_key(fen): return " ".join(fen.split()[:4])

def _is_possible_position(board):
    if not board.is_valid(): return False
    for color in (chess.WHITE, chess.BLACK):
        pawns = len(board.pieces(chess.PAWN, color))
        knights = len(board.pieces(chess.KNIGHT, color))
        bishops = len(board.pieces(chess.BISHOP, color))
        rooks = len(board.pieces(chess.ROOK, color))
        queens = len(board.pieces(chess.QUEEN, color))
        if pawns + knights + bishops + rooks + queens > 15: return False
        missing_pawns = 8 - pawns
        extra_queens = max(0, queens - 1)
        extra_rooks = max(0, rooks - 2)
        extra_knights = max(0, knights - 2)
        light_bishops = len(board.pieces(chess.BISHOP, color) & chess.BB_LIGHT_SQUARES)
        dark_bishops = len(board.pieces(chess.BISHOP, color) & chess.BB_DARK_SQUARES)
        extra_bishops = max(0, light_bishops - 1) + max(0, dark_bishops - 1)
        total_extra = extra_queens + extra_rooks + extra_knights + extra_bishops
        if total_extra > missing_pawns: return False
    return True

class _SearchTimeout(Exception): pass

class DFPNMateSolver:
    def __init__(self):
        self.tt = {}; self.child = {}; self.nodes = 0; self._deadline = None
    def has_mate(self, board, n): return self.prove(board, n)
    def prove(self, board, budget, timeout=4.0):
        if budget <= 0: return False
        self._deadline = time.time() + timeout
        b = board.copy(stack=False)
        try: pn, _dn = self._mid(b, budget, True, PN_INF, PN_INF)
        except _SearchTimeout: return False
        return pn == 0
    def mate_key(self, board, n):
        if n <= 0: return None
        self._deadline = time.time() + 4.0
        b = board.copy(stack=False)
        try:
            moves = sorted(b.legal_moves, key=lambda m: (0 if b.gives_check(m) else 1, 0 if b.is_capture(m) else 1))
            for mv in moves:
                b.push(mv)
                if b.is_checkmate(): b.pop(); return mv
                ok = n >= 2 and self._mid(b, n - 1, False, PN_INF, PN_INF)[0] == 0
                b.pop()
                if ok: return mv
        except _SearchTimeout: return None
        return None
    def mate_keys_all(self, board, n):
        if n <= 0: return []
        self._deadline = time.time() + 4.0
        b = board.copy(stack=False); out = []
        try:
            for mv in list(b.legal_moves):
                b.push(mv)
                if b.is_checkmate(): out.append(mv); b.pop(); continue
                ok = n >= 2 and self._mid(b, n - 1, False, PN_INF, PN_INF)[0] == 0
                b.pop()
                if ok: out.append(mv)
        except _SearchTimeout: pass
        return out
    def _mid(self, board, budget, is_or, phi, delta):
        self.nodes += 1
        if self._deadline is not None and (self.nodes & 511) == 0 and time.time() > self._deadline: raise _SearchTimeout()
        k = (chess.polyglot.zobrist_hash(board), budget, is_or)
        e = self.tt.get(k)
        if e is None: e = self.tt[k] = [1, 1]
        elif e[0] >= phi or e[1] >= delta: return e
        if is_or and budget <= 0: e[0], e[1] = PN_INF, 0; return e
        kids = self.child.get(k)
        if kids is None:
            kids = self._expand(board, budget, is_or)
            if kids is None:
                e[0], e[1] = (PN_INF, 0) if is_or or board.is_stalemate() else (0, PN_INF)
                self.tt[k] = e; return e
            self.child[k] = kids
        if not kids: e[0], e[1] = PN_INF, 0; return e
        while True:
            if is_or: pn = min(c[1] for c in kids); dn = min(PN_INF, sum(c[2] for c in kids))
            else: pn = min(PN_INF, sum(c[1] for c in kids)); dn = min(c[2] for c in kids)
            e[0], e[1] = pn, dn
            if pn >= phi or dn >= delta: break
            if is_or:
                i = min(range(len(kids)), key=lambda j: (kids[j][1], kids[j][2]))
                cdn = kids[i][2]; cphi = phi; cdelta = max(1, delta - (dn - cdn))
                cbudget, c_is_or = budget - 1, False
            else:
                i = min(range(len(kids)), key=lambda j: (kids[j][2], kids[j][1]))
                cpn = kids[i][1]; cphi = max(1, phi - (pn - cpn)); cdelta = delta
                cbudget, c_is_or = budget, True
            board.push(kids[i][0])
            cp, cd = self._mid(board, cbudget, c_is_or, cphi, cdelta)
            board.pop()
            kids[i][1], kids[i][2] = cp, cd
        return e
    def _expand(self, board, budget, is_or):
        if is_or:
            moves = sorted(board.legal_moves, key=lambda m: (0 if board.gives_check(m) else 1, 0 if board.is_capture(m) else 1))
            if not moves: return None
            kids = []
            for mv in moves:
                board.push(mv); mate = board.is_checkmate(); board.pop()
                kids.append([mv, 0, PN_INF] if mate else [mv, 1, 1])
            return kids
        if board.is_checkmate(): return None
        if budget <= 0: return []
        kids = [[r, 1, 1] for r in board.legal_moves]
        return kids if kids else None

def quiescence(board, alpha, beta, depth=4, ply=0):
    if board.is_checkmate(): return -(MATE_SCORE - ply)
    if board.is_insufficient_material(): return 0
    sign = 1 if board.turn == chess.WHITE else -1
    stand = sign * static_eval(board)
    if stand >= beta: return stand
    if stand > alpha: alpha = stand
    if depth <= 0: return stand
    caps = [m for m in board.legal_moves if board.is_capture(m) or board.gives_check(m)]
    caps.sort(key=lambda m: PIECE_VALUE.get(board.piece_type_at(m.to_square), 0) - PIECE_VALUE[board.piece_type_at(m.from_square)] // 10, reverse=True)
    for m in caps:
        board.push(m); sc = -quiescence(board, -beta, -alpha, depth - 1, ply + 1); board.pop()
        if sc >= beta: return sc
        if sc > alpha: alpha = sc
    return alpha

def negamax(board, depth, alpha=-10 ** 9, beta=10 ** 9, ply=0):
    if board.is_checkmate(): return -(MATE_SCORE - ply)
    if board.is_stalemate() or board.is_insufficient_material(): return 0
    if depth <= 0: return quiescence(board, alpha, beta, 4, ply)
    moves = sorted(board.legal_moves, key=lambda m: (0 if board.is_capture(m) else 1, 0 if board.gives_check(m) else 1))
    best = -10 ** 9
    for mv in moves:
        board.push(mv); sc = -negamax(board, depth - 1, -beta, -alpha, ply + 1); board.pop()
        if sc > best:
            best = sc
            if best > alpha:
                alpha = best
                if alpha >= beta: break
    return best

def best_defense_score(board, depth, alpha=-10 ** 9, beta=10 ** 9): return negamax(board, depth, alpha, beta)

class TablebaseOracle:
    def __init__(self, path=None):
        self.tb = None; p = path or SYZYGY_PATH
        if p and os.path.isdir(p):
            try: self.tb = chess.syzygy.open_tablebase(p)
            except Exception: self.tb = None
    def dtz(self, board):
        if self.tb is None: return None
        try:
            if chess.popcount(board.occupied) > 5: return None
            return self.tb.probe_dtz(board)
        except Exception: return None
    def agree_white_wins(self, board):
        dtz = self.dtz(board)
        return True if dtz is None else dtz > 0

_ORACLE = None
def get_oracle():
    global _ORACLE
    if _ORACLE is None: _ORACLE = TablebaseOracle()
    return _ORACLE

class CompositionJudge:
    def __init__(self, solver): self.solver = solver
    def _idle_white_pieces(self, board, key):
        bk = board.king(chess.BLACK)
        if bk is None: return 0
        zone = [s for s in chess.SQUARES if chess.square_distance(s, bk) <= 2]
        idle = 0
        for s, pc in board.piece_map().items():
            if pc.color != chess.WHITE or pc.piece_type == chess.KING: continue
            if s == key.from_square or s == key.to_square: continue
            if any(s in board.attackers(chess.WHITE, z) for z in zone): continue
            idle += 1
        return idle
    def judge_mate(self, board, n, require_unique=True):
        keys = self.solver.mate_keys_all(board, n)
        if not keys: return False, 0.0, "no forced mate"
        if require_unique and len(keys) > 1: return False, 0.0, f"cooked ({len(keys)} key moves)"
        key = keys[0]; b = board.copy(stack=False); b.push(key)
        defenses = duals = 0
        for r in list(b.legal_moves):
            b.push(r)
            if n <= 2:
                conts = 0
                for m in list(b.legal_moves):
                    b.push(m)
                    if b.is_checkmate(): conts += 1
                    b.pop()
            else: conts = len(self.solver.mate_keys_all(b, n - 1))
            b.pop()
            if conts == 0: return False, 0.0, "unforced defense"
            defenses += 1; duals += conts
        dual = duals / max(1, defenses); idle = self._idle_white_pieces(board, key)
        score = 1.0 - 0.12 * (dual - 1.0) - 0.10 * idle
        return score >= 0.55, max(0.0, score), f"dual={dual:.2f} idle={idle}"

def _moves_like(pt, sq, color=chess.WHITE):
    f0, r0 = chess.square_file(sq), chess.square_rank(sq); out = []
    if pt == chess.KNIGHT: deltas = ((1, 2), (2, 1), (2, -1), (1, -2), (-1, -2), (-2, -1), (-2, 1), (-1, 2))
    elif pt == chess.KING: deltas = tuple((df, dr) for df in (-1, 0, 1) for dr in (-1, 0, 1) if df or dr)
    else:
        deltas = []
        if pt in (chess.ROOK, chess.QUEEN): deltas += ((0, 1), (0, -1), (1, 0), (-1, 0))
        if pt in (chess.BISHOP, chess.QUEEN): deltas += ((1, 1), (1, -1), (-1, 1), (-1, -1))
        if pt == chess.PAWN:
            dr = 1 if color == chess.WHITE else -1
            deltas = [(df, dr) for df in (-1, 0, 1)]
    for df, dr in deltas:
        if pt in (chess.ROOK, chess.QUEEN, chess.BISHOP):
            f, r = f0 + df, r0 + dr
            while 0 <= f < 8 and 0 <= r < 8:
                out.append(chess.square(f, r)); f += df; r += dr
        else:
            f, r = f0 + df, r0 + dr
            if 0 <= f < 8 and 0 <= r < 8: out.append(chess.square(f, r))
    return out

def retrograde_white(board, max_out=48):
    out = []
    for t in chess.SQUARES:
        pc = board.piece_at(t)
        if pc is None or pc.color != chess.WHITE or pc.piece_type == chess.KING: continue
        pt = pc.piece_type
        for s in _moves_like(pt, t, chess.WHITE):
            if board.piece_at(s) is not None: continue
            variants = [(pt, None, False)]
            if pt not in (chess.PAWN, chess.KING) and chess.square_rank(t) == 7 and chess.square_rank(s) == 6: variants.append((chess.PAWN, None, True))
            if pt != chess.KING:
                for vt in (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN):
                    variants.append((pt, vt, False))
                    if pt not in (chess.PAWN, chess.KING) and chess.square_rank(t) == 7 and chess.square_rank(s) == 6: variants.append((chess.PAWN, vt, True))
            for new_pt, victim_t, promo in variants:
                P = board.copy(stack=False)
                P.remove_piece_at(t); P.set_piece_at(s, chess.Piece(new_pt, chess.WHITE))
                if victim_t is not None:
                    if chess.square_rank(t) in (0, 7): continue
                    P.set_piece_at(t, chess.Piece(victim_t, chess.BLACK))
                P.turn = chess.WHITE
                if not _is_possible_position(P) or P.is_check(): continue
                promo_needed = new_pt == chess.PAWN and chess.square_rank(t) == 7
                probe = chess.Move(s, t, promotion=chess.QUEEN) if (promo or promo_needed) else chess.Move(s, t)
                if probe not in P.legal_moves: continue
                out.append(P)
                if len(out) >= max_out: return out
    return out

def retrograde_black(board, max_out=24):
    out = []
    for t in chess.SQUARES:
        pc = board.piece_at(t)
        if pc is None or pc.color != chess.BLACK or pc.piece_type == chess.KING: continue
        pt = pc.piece_type
        for s in _moves_like(pt, t, chess.BLACK):
            if board.piece_at(s) is not None: continue
            variants = [(pt, None)]
            if pt != chess.KING: variants += [(pt, vt) for vt in (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN)]
            for new_pt, victim_t in variants:
                R = board.copy(stack=False)
                R.remove_piece_at(t); R.set_piece_at(s, chess.Piece(new_pt, chess.BLACK))
                if victim_t is not None:
                    if chess.square_rank(t) in (0, 7): continue
                    R.set_piece_at(t, chess.Piece(victim_t, chess.WHITE))
                R.turn = chess.BLACK
                if not _is_possible_position(R): continue
                promo_needed = new_pt == chess.PAWN and chess.square_rank(t) == 0
                probe = chess.Move(s, t, promotion=chess.QUEEN) if promo_needed else chess.Move(s, t)
                if probe not in R.legal_moves: continue
                out.append(R)
                if len(out) >= max_out: return out
    return out

def _black_filler(rng, sq):
    opts = (chess.ROOK, chess.KNIGHT, chess.BISHOP, chess.PAWN)
    if chess.square_rank(sq) in (0, 7): opts = (chess.ROOK, chess.KNIGHT, chess.BISHOP)
    return chess.Piece(rng.choice(opts), chess.BLACK)

def _req_arabian(b, csq, bk):
    return bk in (chess.A1, chess.A8, chess.H1, chess.H8) and \
           any(b.piece_type_at(s) == chess.KNIGHT for s in b.attackers(chess.WHITE, csq) if s != csq)

def _is_arabian(board, bk):
    return bk in (chess.A1, chess.A8, chess.H1, chess.H8)

def _is_smothered(board, bk):
    for sq in chess.SQUARES:
        if chess.square_distance(sq, bk) == 1:
            pc = board.piece_at(sq)
            if pc is None or pc.color != chess.BLACK: return False
    return True

def _req_epaulette(b, csq, bk):
    f0, r0 = chess.square_file(bk), chess.square_rank(bk)
    for df in (-1, 1):
        f = f0 + df
        if 0 <= f <= 7:
            pc = b.piece_at(chess.square(f, r0))
            if pc is None or pc.color != chess.BLACK: return False
    return True

def _req_backrank(b, csq, bk):
    if chess.square_rank(bk) != 7 or chess.square_rank(csq) != 7: return False
    s = chess.square(chess.square_file(bk), 6)
    pc = b.piece_at(s)
    return pc is not None and pc.color == chess.BLACK and pc.piece_type == chess.PAWN

TEMPLATES = {
    "free":      dict(full_box=False, shield=False),
    "boxed":     dict(full_box=True, shield=False),
    "arabian":   dict(full_box=True, shield=False, checker_types=(chess.ROOK,), require=_req_arabian),
    "backrank":  dict(bk_rank=7, full_box=False, shield=True, checker_types=(chess.ROOK, chess.QUEEN), require=_req_backrank),
    "epaulette": dict(full_box=True, shield=False, require=_req_epaulette),
}

def construct_mate_position(rng, template="free", attempts=60):
    kw = TEMPLATES.get(template, TEMPLATES["free"])
    full_box = kw.get("full_box", False); shield = kw.get("shield", False)
    checker_types = kw.get("checker_types", (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT))
    require = kw.get("require"); bk_rank = kw.get("bk_rank")
    for _ in range(attempts):
        b = chess.Board(None); b.turn = chess.BLACK
        bk = chess.square(rng.randrange(8), bk_rank) if bk_rank is not None else rng.randrange(64)
        b.set_piece_at(bk, chess.Piece(chess.KING, chess.BLACK))
        far = [s for s in range(64) if chess.square_distance(s, bk) >= 3]
        b.set_piece_at(rng.choice(far), chess.Piece(chess.KING, chess.WHITE))
        adj = [s for s in chess.SQUARES if chess.square_distance(s, bk) == 1]
        rng.shuffle(adj)
        if shield:
            for s in adj:
                if chess.square_rank(s) == chess.square_rank(bk) - 1 and b.piece_at(s) is None:
                    b.set_piece_at(s, chess.Piece(chess.PAWN, chess.BLACK))
        n_block = len(adj) if full_box else rng.randint(1, len(adj))
        for s in adj:
            if n_block <= 0: break
            if b.piece_at(s) is None:
                b.set_piece_at(s, _black_filler(rng, s)); n_block -= 1
        spots = [s for s in adj if b.piece_at(s) is None]; rng.shuffle(spots)
        for csq in spots:
            pt = rng.choice(checker_types)
            if pt == chess.PAWN and (chess.square_rank(csq) in (0, 7) or chess.square_rank(csq) + 1 != chess.square_rank(bk) or abs(chess.square_file(csq) - chess.square_file(bk)) != 1): continue
            b.set_piece_at(csq, chess.Piece(pt, chess.WHITE))
            filled = []
            for q in spots:
                if q != csq and b.piece_at(q) is None:
                    b.set_piece_at(q, _black_filler(rng, q)); filled.append(q)
            if b.is_checkmate() and _is_possible_position(b) and (require is None or require(b, csq, bk)): return b
            for q in filled: b.set_piece_at(q, None)
            b.set_piece_at(csq, None)
    return None

ANNEAL_KINDS = {"fork", "pawn_fork", "queen_fork", "skewer", "pin_win", "discovered", "trapped_queen", "win_queen", "win_rook", "win_piece", "double_check",
                "deflection", "overloading", "zwischenzug", "magnet", "defensive_perp", "defensive_stale"}
_ENERGY_SPEC = {
    "fork":          ((chess.KNIGHT,), (chess.QUEEN, chess.ROOK), True),
    "pawn_fork":     ((chess.PAWN,), (chess.QUEEN, chess.ROOK), True),
    "queen_fork":    ((chess.QUEEN,), (chess.ROOK,), True),
    "skewer":        ((chess.QUEEN, chess.ROOK, chess.BISHOP), (chess.QUEEN, chess.ROOK), True),
    "pin_win":       ((chess.QUEEN, chess.ROOK, chess.BISHOP), (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN), True),
    "discovered":    ((chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT), (chess.QUEEN,), False),
    "trapped_queen": ((chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN), (chess.QUEEN,), False),
    "win_queen":     ((chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN), (chess.QUEEN,), False),
    "win_rook":      ((chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN), (chess.ROOK,), False),
    "win_piece":     ((chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN), (chess.BISHOP, chess.KNIGHT), False),
    "double_check":  ((chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT), (chess.QUEEN, chess.ROOK), True),
    "deflection":    ((chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN), (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT), False),
    "overloading":   ((chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN), (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT), False),
    "zwischenzug":  ((chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT), (chess.QUEEN, chess.ROOK), True),
    "magnet":        ((chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT), (chess.KING,), True),
    "defensive_perp":((chess.QUEEN, chess.ROOK), (chess.KING,), True),
    "defensive_stale":((chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN), (chess.KING,), False)
}

def _tactic_energy(kind, b):
    actors, targets, with_king = _ENERGY_SPEC[kind]
    pm = b.piece_map(); bk = b.king(chess.BLACK)
    if bk is None: return 99.0
    t_sq = [s for s, pc in pm.items() if pc.color == chess.BLACK and pc.piece_type in targets]
    if not t_sq: return 9.0
    e = 9.0
    for s, pc in pm.items():
        if pc.color != chess.WHITE or pc.piece_type not in actors: continue
        d_t = min(chess.square_distance(s, t) for t in t_sq)
        d = d_t + (0.6 * chess.square_distance(s, bk) if with_king else 0.0)
        e = min(e, d)
    return e

class Annealer:
    _TYPES = (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN)
    def __init__(self, rng, kind, max_iters, cancel=None):
        self.rng, self.kind = rng, kind; self.max_iters, self.cancel = max_iters, cancel
    def _sane(self, b):
        pm = b.piece_map()
        if len(pm) > 18: return False
        if b.king(chess.WHITE) is None or b.king(chess.BLACK) is None: return False
        if not _is_possible_position(b) or b.is_check(): return False
        return True
    def _mutate(self, b):
        b = b.copy(stack=False); pm = b.piece_map()
        occ = [s for s, pc in pm.items() if pc.piece_type != chess.KING]
        empt = [s for s in chess.SQUARES if s not in pm]
        if not occ or not empt: return None
        r = self.rng.random()
        if r < 0.45:
            s = self.rng.choice(occ); t = self.rng.choice(empt); pc = b.piece_at(s)
            if pc.piece_type == chess.PAWN and chess.square_rank(t) in (0, 7): return None
            b.remove_piece_at(s); b.set_piece_at(t, pc)
        elif r < 0.68:
            s = self.rng.choice(occ); pc = b.piece_at(s); pt = self.rng.choice(self._TYPES)
            if pt == chess.PAWN and chess.square_rank(s) in (0, 7): return None
            b.set_piece_at(s, chess.Piece(pt, pc.color))
        elif r < 0.86: b.remove_piece_at(self.rng.choice(occ))
        else:
            s = self.rng.choice(empt); color = chess.WHITE if self.rng.random() < 0.55 else chess.BLACK; pt = self.rng.choice(self._TYPES)
            if pt == chess.PAWN and chess.square_rank(s) in (0, 7): pt = chess.KNIGHT
            b.set_piece_at(s, chess.Piece(pt, color))
        return b if self._sane(b) else None
    def run(self, seed, verify):
        cur = seed; cur_e = _tactic_energy(self.kind, cur); best = (cur_e, cur)
        T, it, since = 2.2, 0, 0
        while it < self.max_iters:
            it += 1; since += 1
            if self.cancel is not None and self.cancel(): return None
            if (cur_e <= 1.3 and it % 8 == 0) or it % 250 == 0:
                res = verify(cur)
                if res is not None: return cur, res
            mut = self._mutate(cur)
            if mut is None: continue
            e = _tactic_energy(self.kind, mut)
            if e <= cur_e or self.rng.random() < math.exp(-(e - cur_e) / T):
                cur, cur_e = mut, e
                if e < best[0]: best = (e, cur)
                since = 0
            T = max(0.18, T * 0.9992)
            if since > 800: T, cur, cur_e, since = 2.2, best[1], best[0], 0
        return None

# ----------------------------- puzzle generator -----------------------------

class PuzzleGenerator:
    ATTACKER_PIECES = [chess.QUEEN, chess.ROOK, chess.ROOK, chess.BISHOP, chess.BISHOP, chess.KNIGHT, chess.KNIGHT, chess.PAWN, chess.QUEEN]
    DEFENDER_PIECES = [chess.PAWN, chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN]
    RETRO_TEMPLATES = ("free", "boxed", "arabian", "backrank", "epaulette")
    MATE1_TEMPLATE = {"back_rank": "backrank", "arabian": "arabian", "epaulette": "epaulette"}

    def __init__(self, seed=None, banned=None, difficulty_min=1, difficulty_max=5):
        self.rng = random.Random(seed)
        self.seen = set(banned or ())
        self.solver = DFPNMateSolver()
        self.judge = CompositionJudge(self.solver)
        self.oracle = get_oracle()
        self.RETRO_ROUNDS = 60
        self.RANDOM_CAP = 400
        self.ANNEAL_ITERS = 2500
        self.UNIQUE_TRIES = 120
        self.difficulty_min = difficulty_min
        self.difficulty_max = difficulty_max

    def _random_position(self, kind):
        rng = self.rng; board = chess.Board(None); reserved = set()
        ep_sq = None; anchor = None; sq_b = sq_w = None; castle_kingside = True
        
        if kind in ("endgame_kq", "endgame_kr", "stalemate_trick"):
            wk = rng.randrange(64)
            bk = rng.choice([s for s in range(64) if chess.square_distance(s, wk) >= 2])
            board.set_piece_at(wk, chess.Piece(chess.KING, chess.WHITE))
            board.set_piece_at(bk, chess.Piece(chess.KING, chess.BLACK))
            if kind == "endgame_kr" or kind == "stalemate_trick":
                wr = rng.choice([s for s in range(64) if s != wk and s != bk])
                board.set_piece_at(wr, chess.Piece(chess.ROOK, chess.WHITE))
            if kind == "endgame_kq":
                wq = rng.choice([s for s in range(64) if s != wk and s != bk])
                board.set_piece_at(wq, chess.Piece(chess.QUEEN, chess.WHITE))
            board.turn = chess.WHITE
            if not _is_possible_position(board) or board.is_check(): return None
            return board
            
        if kind == "defensive_perp" or kind == "defensive_stale":
            wk = rng.randrange(64)
            bk = rng.choice([s for s in range(64) if chess.square_distance(s, wk) >= 2])
            board.set_piece_at(wk, chess.Piece(chess.KING, chess.WHITE))
            board.set_piece_at(bk, chess.Piece(chess.KING, chess.BLACK))
            wa = rng.choice([s for s in range(64) if s != wk and s != bk])
            attacker = chess.QUEEN if kind == "defensive_perp" else rng.choice([chess.QUEEN, chess.ROOK])
            board.set_piece_at(wa, chess.Piece(attacker, chess.WHITE))
            
            ba = rng.choice([s for s in range(64) if s != wk and s != bk and s != wa])
            board.set_piece_at(ba, chess.Piece(rng.choice([chess.ROOK, chess.QUEEN]), chess.BLACK))
            bb = rng.choice([s for s in range(64) if s not in (wk, bk, wa, ba)])
            board.set_piece_at(bb, chess.Piece(rng.choice([chess.PAWN, chess.KNIGHT]), chess.BLACK))
            
            board.turn = chess.WHITE
            if not _is_possible_position(board) or board.is_check(): return None
            return board

        if kind == "en_passant":
            f = rng.randrange(8); sq_b = chess.square(f, 4); sq_land = chess.square(f, 5)
            reserved |= {sq_land, chess.square(f, 6)}
            g = rng.choice([x for x in (f - 1, f + 1) if 0 <= x <= 7])
            sq_w = chess.square(g, 4); ep_sq = sq_land; anchor = sq_land
            bk = rng.choice([s for s in range(64) if chess.square_distance(s, sq_land) <= 3 and s not in (sq_b, sq_w, sq_land)])
        elif kind == "smothered": bk = rng.choice((chess.A8, chess.H8)); anchor = bk
        elif kind == "arabian": bk = (rng.choice((chess.A8, chess.H8, chess.A1, chess.H1)) if rng.random() < 0.6 else rng.randrange(64)); anchor = bk
        elif kind == "castle_mate":
            ff, rr = rng.choice(((5, 2), (5, 3), (3, 2), (3, 3))); bk = chess.square(ff, rr)
            castle_kingside = (ff == 5); anchor = bk
            reserved |= {chess.A1, chess.B1, chess.C1, chess.D1, chess.E1, chess.F1, chess.G1, chess.H1}
            reserved |= {chess.square(ff, z) for z in range(1, rr)}
        elif kind == "back_rank": bk = rng.randrange(56, 64)
        elif kind == "promotion": bk = rng.choice([s for s in range(64) if chess.square_rank(s) >= 4])
        elif kind == "ladder": bk = chess.square(rng.randrange(8), rng.choice((1, 6)))
        elif kind == "boden": bk = rng.choice([s for s in range(64) if chess.square_rank(s) in (0, 7) or chess.square_file(s) in (0, 7)])
        elif kind == "epaulette": bk = rng.choice([s for s in range(64) if 1 <= chess.square_file(s) <= 6])
        else: bk = rng.randrange(64)
        board.set_piece_at(bk, chess.Piece(chess.KING, chess.BLACK))
        if kind == "castle_mate":
            board.set_piece_at(chess.E1, chess.Piece(chess.KING, chess.WHITE))
            board.set_piece_at(chess.H1 if castle_kingside else chess.A1, chess.Piece(chess.ROOK, chess.WHITE))
        else:
            wk = rng.choice([s for s in range(64) if chess.square_distance(s, bk) >= 2])
            board.set_piece_at(wk, chess.Piece(chess.KING, chess.WHITE))
        if anchor is None: anchor = bk
        if kind == "back_rank":
            spots = [s for s in range(48, 56) if board.piece_at(s) is None]; rng.shuffle(spots)
            for s in spots[: rng.randint(2, 3)]: board.set_piece_at(s, chess.Piece(chess.PAWN, chess.BLACK))
        if kind == "promotion":
            cand = [ff for ff in range(8) if board.piece_at(chess.square(ff, 6)) is None and chess.square(ff, 7) != bk and board.piece_at(chess.square(ff, 7)) is None]
            if not cand: return None
            f = rng.choice(cand); board.set_piece_at(chess.square(f, 6), chess.Piece(chess.PAWN, chess.WHITE)); reserved.add(chess.square(f, 7))
        if kind == "en_passant":
            if board.piece_at(sq_b) is not None or board.piece_at(sq_w) is not None: return None
            board.set_piece_at(sq_b, chess.Piece(chess.PAWN, chess.BLACK)); board.set_piece_at(sq_w, chess.Piece(chess.PAWN, chess.WHITE))

        if kind in ("mate_in_1", "mate_in_2", "mate_in_3", "fork", "win_piece", "win_queen", "win_rook", "promotion"):
            if rng.random() < 0.25:
                cand = [s for s in range(48, 56) if board.piece_at(s) is None and s not in reserved and chess.square_file(s) != chess.square_file(bk)]
                if cand:
                    s = rng.choice(cand)
                    board.set_piece_at(s, chess.Piece(chess.PAWN, chess.WHITE))
                    reserved.add(s + 8)

        rich = kind in ("mate_in_2", "mate_in_3", "sacrifice", "quiet_mate", "smothered", "double_check", "castle_mate", "remove_defender", "pin_win", "discovered",
                        "deflection", "overloading", "zwischenzug", "magnet")
        n_att = rng.randint(4, 7) if rich else rng.randint(3, 6)
        army = [rng.choice(self.ATTACKER_PIECES) for _ in range(n_att)]
        if kind == "fork": army[0] = chess.KNIGHT
        elif kind == "smothered": army[0] = chess.KNIGHT; army[1] = chess.QUEEN if n_att >= 2 else army[1]
        elif kind == "arabian": army[0] = chess.ROOK; army[1] = chess.KNIGHT if n_att >= 2 else army[1]
        elif kind == "back_rank":
            if not any(p in (chess.ROOK, chess.QUEEN) for p in army): army[0] = rng.choice((chess.ROOK, chess.QUEEN))
        elif kind == "en_passant":
            if not any(p in (chess.ROOK, chess.QUEEN, chess.BISHOP) for p in army): army[0] = rng.choice((chess.ROOK, chess.QUEEN, chess.BISHOP))
        elif kind == "skewer": army[0] = rng.choice((chess.QUEEN, chess.ROOK, chess.BISHOP))
        elif kind == "double_check": army[0] = rng.choice((chess.QUEEN, chess.ROOK, chess.BISHOP)); army[1] = rng.choice((chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT)) if n_att >= 2 else army[1]
        elif kind == "pawn_fork": army[0] = chess.PAWN
        elif kind == "quiet_mate":
            if not any(p in (chess.ROOK, chess.QUEEN) for p in army): army[0] = rng.choice((chess.ROOK, chess.QUEEN))
        elif kind == "castle_mate": army[0] = chess.QUEEN
        elif kind == "boden": army[0] = chess.BISHOP; army[1] = chess.BISHOP if n_att >= 2 else army[1]
        elif kind == "ladder": army[0] = chess.ROOK; army[1] = chess.ROOK if n_att >= 2 else army[1]
        
        near = [s for s in range(64) if s not in (bk, wk) and chess.square_distance(s, anchor) <= 3]; rng.shuffle(near)
        far = [s for s in range(64) if s not in near and s not in (bk, wk)]; rng.shuffle(far)
        
        mix = near[: int(n_att * 0.6)] + far[: n_att - int(n_att * 0.6)]
        spots = [s for s in mix if board.piece_at(s) is None and s not in reserved]
        if kind == "smothered": spots = [s for s in spots if chess.square_distance(s, bk) > 1]
        spots = spots[:n_att]
        for s, pt in zip(spots, army):
            if pt == chess.PAWN and chess.square_rank(s) in (0, 7): pt = chess.KNIGHT
            board.set_piece_at(s, chess.Piece(pt, chess.WHITE))
            
        extras = []
        if kind in ("win_queen", "fork", "sacrifice", "double_check", "discovered", "trapped_queen") or (kind == "mate_in_3" and rng.random() < 0.5): extras.append(chess.QUEEN)
        if kind == "win_rook": extras.append(chess.ROOK)
        if kind == "skewer": extras.append(chess.QUEEN if rng.random() < 0.6 else chess.ROOK)
        if kind == "discovered": extras.append(chess.ROOK)
        if kind == "pawn_fork": extras += [chess.QUEEN, chess.ROOK]
        if kind == "win_piece": extras.append(rng.choice((chess.BISHOP, chess.KNIGHT)))
        if kind == "smothered": extras.append(rng.choice((chess.ROOK, chess.ROOK, chess.BISHOP, chess.KNIGHT)))
        if kind == "pin_win": extras.append(rng.choice(self.DEFENDER_PIECES))
        if kind == "boden": extras.append(rng.choice((chess.ROOK, chess.BISHOP, chess.KNIGHT)))
        n_extra = 3 if kind == "smothered" else (rng.randint(1, 3) if kind == "quiet_mate" else rng.randint(0, 2))
        for _ in range(n_extra): extras.append(rng.choice(self.DEFENDER_PIECES))
        
        for _ in range(rng.randint(0, 4)): extras.append(chess.PAWN)
        
        free = [s for s in range(64) if board.piece_at(s) is None and chess.square_rank(s) not in (0, 7) and s not in reserved]; rng.shuffle(free)
        for pt in extras:
            if not free: break
            if pt == chess.PAWN: 
                if len(board.pieces(chess.PAWN, chess.BLACK)) >= 8: continue
            if pt == chess.QUEEN: pool = [s for s in free if chess.square_distance(s, bk) <= 3] or free
            elif pt == chess.ROOK: pool = [s for s in free if chess.square_distance(s, bk) <= 4] or free
            else: pool = free
            s = rng.choice(pool); free.remove(s); board.set_piece_at(s, chess.Piece(pt, chess.BLACK))
        if kind == "smothered":
            adj = [s for s in chess.SQUARES if chess.square_distance(s, bk) == 1 and board.piece_at(s) is None]; rng.shuffle(adj)
            for s in adj: board.set_piece_at(s, chess.Piece(rng.choice((chess.ROOK, chess.BISHOP, chess.KNIGHT)), chess.BLACK))
        if kind == "epaulette":
            f0, r0 = chess.square_file(bk), chess.square_rank(bk); ok = True
            for df in (-1, 1):
                s = chess.square(f0 + df, r0); cur = board.piece_at(s)
                if cur is not None:
                    if cur.color == chess.WHITE: ok = False; break
                    continue
                board.set_piece_at(s, chess.Piece(rng.choice((chess.ROOK, chess.KNIGHT, chess.BISHOP)), chess.BLACK))
            if not ok: return None
        if ep_sq is not None: board.ep_square = ep_sq
        if kind == "castle_mate": board.castling_rights |= (chess.BB_H1 if castle_kingside else chess.BB_A1)
        if not _is_possible_position(board) or board.is_check(): return None
        return board

    def _mating_moves(self, board): return self.solver.mate_keys_all(board, 1)
    def _any_mate_in_1(self, board): return self.solver.has_mate(board, 1)
    def _mate2_keys(self, board): return self.solver.mate_keys_all(board, 2)
    def _forced_mate_in_2(self, board): return self.solver.mate_key(board, 2)
    def _mate3_keys(self, board): return self.solver.mate_keys_all(board, 3)
    def _is_mate_after(self, board, mv):
        board.push(mv); m = board.is_checkmate(); board.pop(); return m
    def _resistance(self, board, max_n):
        for n in range(1, max_n + 1):
            if self.solver.prove(board, n, timeout=2.0): return n
        return max_n + 1
    def _toughest_defense(self, board, max_plies):
        best, best_key = None, None
        for r in board.legal_moves:
            board.push(r); res = self._resistance(board, max_plies); ev = negamax(board, 2); board.pop()
            key = (-res, ev)
            if best_key is None or key < best_key: best_key, best = key, r
        return best
    @staticmethod
    def _first_mating_move(board):
        for m in board.legal_moves:
            board.push(m); ok = board.is_checkmate(); board.pop()
            if ok: return m
        return None
    def _beam(self, cands, width=5):
        def score(P):
            black_pieces = sum(1 for pc in P.piece_map().values() if pc.color == chess.BLACK)
            mobility = len(list(P.legal_moves))
            return (9 - min(8, black_pieces)) + (30 - min(30, mobility)) * 0.05 + self.rng.random()
        return sorted(cands, key=score, reverse=True)[:width]
    def _winning_captures(self, board, min_net):
        out = []
        for m in board.legal_moves:
            captured = board.piece_type_at(m.to_square)
            if captured is None: continue
            gain = PIECE_VALUE[captured]
            if m.promotion: gain += PIECE_VALUE[m.promotion] - PIECE_VALUE[chess.PAWN]
            board.push(m); net = gain - see_after_capture(board, m.to_square); board.pop()
            if net >= min_net: out.append((m, net))
        return out
    def _every_reply_loses(self, board, min_net):
        replies = list(board.legal_moves)
        if not replies: return False
        for r in replies:
            board.push(r); wins = self._winning_captures(board, min_net); board.pop()
            if not wins: return False
        return True
    def _finish_material_line(self, board, m, min_net):
        board.push(m); replies = list(board.legal_moves)
        if not replies: board.pop(); return None
        self.rng.shuffle(replies); best_r, best_gain = None, None
        for r in replies:
            board.push(r); wins = self._winning_captures(board, min_net); board.pop()
            if wins:
                gain = max(w for _, w in wins)
                if best_gain is None or gain < best_gain: best_gain, best_r = gain, r
        if best_r is None: board.pop(); return None
        board.push(best_r); wins = self._winning_captures(board, min_net); wins.sort(key=lambda w: -w[1]); cap = wins[0][0]; board.pop(); board.pop()
        return [m, best_r, cap]
    def _fork_ok(self, board, nsq):
        if not board.is_check() or board.is_checkmate(): return None
        if board.attackers(chess.BLACK, nsq): return None
        targets = sorted(((PIECE_VALUE[board.piece_type_at(sq)], sq) for sq in board.attacks(nsq) if board.piece_type_at(sq) in (chess.QUEEN, chess.ROOK)), reverse=True)
        if not targets or not (targets[0][0] == PIECE_VALUE[chess.QUEEN] or len(targets) >= 2): return None
        best_sq, best_val = targets[0][1], targets[0][0]
        for r in list(board.legal_moves):
            board.push(r); cap = chess.Move(nsq, best_sq); good = board.is_legal(cap)
            if good:
                board.push(cap); good = best_val - see_after_capture(board, best_sq) >= 400; board.pop()
            board.pop()
            if not good: return None
        return best_val == PIECE_VALUE[chess.QUEEN]
    def _knight_forks(self, board):
        out = []
        for m in board.legal_moves:
            if board.piece_type_at(m.from_square) != chess.KNIGHT: continue
            board.push(m); found = self._fork_ok(board, m.to_square); board.pop()
            if found is not None: out.append((m, found))
        return out
    def _pawn_fork_ok(self, board, nsq):
        if board.attackers(chess.BLACK, nsq): return None
        targets = sorted(((PIECE_VALUE[board.piece_type_at(sq)], sq) for sq in board.attacks(nsq) if board.piece_type_at(sq) in (chess.QUEEN, chess.ROOK)), reverse=True)
        if not targets: return None
        best_val, best_sq = targets[0]
        if best_val != PIECE_VALUE[chess.QUEEN] and len(targets) < 2: return None
        for r in list(board.legal_moves):
            board.push(r); cap = chess.Move(nsq, best_sq); good = board.is_legal(cap)
            if good:
                board.push(cap); good = best_val - see_after_capture(board, best_sq) >= 400; board.pop()
            board.pop()
            if not good: return None
        return True
    def _pawn_forks(self, board):
        out = []
        for m in board.legal_moves:
            if board.piece_type_at(m.from_square) != chess.PAWN: continue
            board.push(m); found = self._pawn_fork_ok(board, m.to_square); board.pop()
            if found is not None: out.append((m, found))
        return out
    def _skewer_ok(self, board):
        if not board.is_check(): return None
        k = board.king(chess.BLACK); checkers = list(board.checkers())
        if len(checkers) != 1: return None
        csq = checkers[0]; pt = board.piece_type_at(csq)
        if pt not in (chess.QUEEN, chess.ROOK, chess.BISHOP): return None
        df = chess.square_file(k) - chess.square_file(csq); dr = chess.square_rank(k) - chess.square_rank(csq)
        straight = df == 0 or dr == 0; diagonal = (df != 0 or dr != 0) and abs(df) == abs(dr)
        if pt == chess.ROOK and not straight: return None
        if pt == chess.BISHOP and not diagonal: return None
        if pt == chess.QUEEN and not (straight or diagonal): return None
        sf, sr = (df > 0) - (df < 0), (dr > 0) - (dr < 0)
        f, r = chess.square_file(k) + sf, chess.square_rank(k) + sr; target = None
        while 0 <= f < 8 and 0 <= r < 8:
            sq = chess.square(f, r); pc = board.piece_at(sq)
            if pc is not None:
                if pc.color == chess.BLACK and pc.piece_type in (chess.QUEEN, chess.ROOK): target = sq
                break
            f, r = f + sf, r + sr
        if target is None: return None
        for rep in board.legal_moves:
            board.push(rep); win = False
            if board.piece_type_at(target) is not None:
                for c in board.legal_moves:
                    if c.to_square != target or board.is_en_passant(c): continue
                    gain = PIECE_VALUE[board.piece_type_at(c.to_square)]
                    if c.promotion: gain += PIECE_VALUE[c.promotion] - PIECE_VALUE[chess.PAWN]
                    board.push(c); net = gain - see_after_capture(board, target); board.pop()
                    if net >= 450: win = True; break
            board.pop()
            if not win: return None
        return target
    def _skewer_moves(self, board):
        out = []
        for m in board.legal_moves:
            board.push(m); target = self._skewer_ok(board); board.pop()
            if target is not None: out.append((m, target))
        return out

    def _try_kind(self, kind, board, relax=False):
        unique_pref = not relax
        if kind == "mate_in_1":
            mates = self._mating_moves(board)
            if not mates or (len(mates) > 1 and unique_pref): return None
            return [mates[0]], len(mates)
        if kind == "back_rank":
            bk = board.king(chess.BLACK)
            if chess.square_rank(bk) != 7: return None
            mates = [m for m in self._mating_moves(board) if chess.square_rank(m.to_square) == 7 and board.piece_type_at(m.from_square) in (chess.ROOK, chess.QUEEN)]
            if not mates or (len(mates) > 1 and unique_pref): return None
            return [mates[0]], len(mates)
        if kind == "arabian":
            arb = [m for m in self._mating_moves(board) if board.piece_type_at(m.from_square) == chess.ROOK and any(board.piece_type_at(d) == chess.KNIGHT for d in board.attackers(chess.WHITE, m.to_square)) and _is_arabian(board, board.king(chess.BLACK))]
            if not arb or (len(arb) > 1 and unique_pref): return None
            return [arb[0]], len(arb)
        if kind == "castle_mate":
            cms = []
            for m in board.legal_moves:
                if board.is_castling(m):
                    board.push(m)
                    if board.is_checkmate(): cms.append(m)
                    board.pop()
            if not cms or (len(cms) > 1 and unique_pref): return None
            if len(self._mating_moves(board)) != len(cms): return None
            return [cms[0]], len(cms)
        if kind == "promotion":
            mates = [m for m in self._mating_moves(board) if m.promotion]
            if not mates: return None
            knights = [m for m in mates if m.promotion == chess.KNIGHT]
            queens = [m for m in mates if m.promotion == chess.QUEEN]
            if knights and not queens and len(knights) == 1: return [knights[0]], 1
            if len(mates) == 1: return [mates[0]], 1
            return None
        if kind == "en_passant":
            mates = self._mating_moves(board)
            if len(mates) == 1 and board.is_en_passant(mates[0]): return [mates[0]], 1
            return None
        if kind == "smothered":
            mates = self._mating_moves(board)
            if mates:
                if len(mates) == 1 and board.piece_type_at(mates[0].from_square) == chess.KNIGHT:
                    if _is_smothered(board, board.king(chess.BLACK)): return [mates[0]], 1
                return None
            keys = self._mate2_keys(board)
            if not keys or (len(keys) > 1 and unique_pref): return None
            for key in keys:
                if board.piece_type_at(key.from_square) != chess.QUEEN: continue
                board.push(key)
                replies = list(board.legal_moves); caps = [r for r in replies if board.is_capture(r)]
                reply = self.rng.choice(caps if caps else replies)
                board.push(reply)
                km = [m for m in self._mating_moves(board) if board.piece_type_at(m.from_square) == chess.KNIGHT]
                is_smoth = _is_smothered(board, board.king(chess.BLACK)) if km else False
                board.pop(); board.pop()
                if km and is_smoth: return [key, reply, km[0]], 1
            return None
        if kind == "mate_in_2":
            if self._any_mate_in_1(board): return None
            keys = self._mate2_keys(board)
            if not keys or (len(keys) > 1 and unique_pref): return None
            key = keys[0]; board.push(key)
            reply = self._toughest_defense(board, 1) or self.rng.choice(list(board.legal_moves))
            board.push(reply)
            mate = next((m for m in board.legal_moves if self._is_mate_after(board, m)), None)
            board.pop(); board.pop()
            return ([key, reply, mate], len(keys)) if mate else None
        if kind == "quiet_mate":
            if self._any_mate_in_1(board): return None
            keys = [k for k in self._mate2_keys(board) if not board.gives_check(k) and not board.is_capture(k)]
            if not keys or (len(keys) > 1 and unique_pref): return None
            key = keys[0]; board.push(key)
            reply = self._toughest_defense(board, 1) or self.rng.choice(list(board.legal_moves))
            board.push(reply)
            mate = next((m for m in board.legal_moves if self._is_mate_after(board, m)), None)
            board.pop(); board.pop()
            return ([key, reply, mate], len(keys)) if mate else None
        if kind == "mate_in_3":
            if self._any_mate_in_1(board): return None
            if self._forced_mate_in_2(board) is not None: return None
            keys = self._mate3_keys(board)
            if not keys or (len(keys) > 1 and unique_pref): return None
            key = keys[0]; board.push(key); replies = list(board.legal_moves); tough = []
            for r in replies:
                board.push(r)
                if not self._any_mate_in_1(board): tough.append(r)
                board.pop()
            r1 = self.rng.choice(tough if tough else replies); board.push(r1)
            m2 = self._forced_mate_in_2(board)
            if m2 is None: board.pop(); board.pop(); return None
            board.push(m2); r2 = self._toughest_defense(board, 1) or self.rng.choice(list(board.legal_moves))
            board.push(r2); m3 = next((m for m in board.legal_moves if self._is_mate_after(board, m)), None)
            board.pop(); board.pop(); board.pop()
            return ([key, r1, m2, r2, m3], len(keys)) if m3 else None
        if kind == "sacrifice":
            if self._any_mate_in_1(board): return None
            keys = self._mate2_keys(board); sacs = []
            for k in keys:
                board.push(k); moved = board.piece_type_at(k.to_square)
                if moved and moved not in (chess.PAWN, chess.KING) and see_after_capture(board, k.to_square) >= 100: sacs.append(k)
                board.pop()
            if not sacs or (len(keys) > 1 and unique_pref): return None
            key = sacs[0]; board.push(key); legals = list(board.legal_moves); recaps = [r for r in legals if board.is_capture(r)]
            reply = self.rng.choice(recaps if recaps and self.rng.random() < 0.8 else legals)
            board.push(reply); mate = next((m for m in board.legal_moves if self._is_mate_after(board, m)), None)
            board.pop(); board.pop()
            return ([key, reply, mate], len(keys)) if mate else None
        if kind in ("win_queen", "win_rook"):
            if self._any_mate_in_1(board): return None
            target = chess.QUEEN if kind == "win_queen" else chess.ROOK
            thr = 500 if kind == "win_queen" else 450
            wins = self._winning_captures(board, thr)
            if len(wins) != 1 or board.piece_type_at(wins[0][0].to_square) != target: return None
            return [wins[0][0]], 1
        if kind == "win_piece":
            if self._any_mate_in_1(board): return None
            if self._winning_captures(board, 450): return None
            wins = self._winning_captures(board, 250)
            if len(wins) != 1: return None
            mv = wins[0][0]
            if board.piece_type_at(mv.to_square) not in (chess.BISHOP, chess.KNIGHT): return None
            return [mv], 1
        if kind == "fork":
            if self._any_mate_in_1(board): return None
            if self._winning_captures(board, 400): return None
            forks = self._knight_forks(board)
            if not forks or (len(forks) > 1 and unique_pref): return None
            mv, _hq = forks[0]; board.push(mv); replies = list(board.legal_moves); self.rng.shuffle(replies); chosen = None
            for r in replies:
                board.push(r); caps = [c for c in board.legal_moves if c.from_square == mv.to_square and board.piece_type_at(c.to_square) in (chess.QUEEN, chess.ROOK)]; board.pop()
                if caps:
                    caps.sort(key=lambda c: PIECE_VALUE[board.piece_type_at(c.to_square)], reverse=True); chosen = (r, caps[0]); break
            board.pop()
            if chosen is None: return None
            return [mv, chosen[0], chosen[1]], 1
        if kind == "pawn_fork":
            if self._any_mate_in_1(board): return None
            if self._winning_captures(board, 400): return None
            forks = self._pawn_forks(board)
            if not forks or (len(forks) > 1 and unique_pref): return None
            mv, _ok = forks[0]; board.push(mv); replies = list(board.legal_moves); self.rng.shuffle(replies); chosen = None
            for r in replies:
                board.push(r); caps = [c for c in board.legal_moves if c.from_square == mv.to_square and board.piece_type_at(c.to_square) in (chess.QUEEN, chess.ROOK)]; board.pop()
                if caps:
                    caps.sort(key=lambda c: PIECE_VALUE[board.piece_type_at(c.to_square)], reverse=True); chosen = (r, caps[0]); break
            board.pop()
            if chosen is None: return None
            return [mv, chosen[0], chosen[1]], 1
        if kind == "skewer":
            if self._any_mate_in_1(board): return None
            sk = self._skewer_moves(board)
            if not sk or (len(sk) > 1 and unique_pref): return None
            mv, target = sk[0]
            if [w for w in self._winning_captures(board, 450) if w[0] != mv]: return None
            board.push(mv); reply = self.rng.choice(list(board.legal_moves)); board.push(reply)
            caps = [c for c in board.legal_moves if c.to_square == target and not board.is_en_passant(c)]
            if not caps: board.pop(); board.pop(); return None
            caps.sort(key=lambda c: PIECE_VALUE[board.piece_type_at(c.to_square)], reverse=True); cap = caps[0]; board.pop(); board.pop()
            return [mv, reply, cap], 1
        if kind == "double_check":
            if self._any_mate_in_1(board): return None
            dcs = []
            for m in board.legal_moves:
                board.push(m)
                if len(board.checkers()) >= 2: dcs.append(m)
                board.pop()
            if not dcs or (len(dcs) > 1 and unique_pref): return None
            dc = dcs[0]
            if [w for w in self._winning_captures(board, 450) if w[0] != dc]: return None
            board.push(dc); replies = list(board.legal_moves)
            if not replies: board.pop(); return None
            ok = True
            for r in replies:
                board.push(r); good = self._any_mate_in_1(board) or bool(self._winning_captures(board, 450)); board.pop()
                if not good: ok = False; break
            if not ok: board.pop(); return None
            reply = self.rng.choice(replies); board.push(reply)
            mate = next((m for m in board.legal_moves if self._is_mate_after(board, m)), None)
            follow = None
            if mate is None:
                wins = self._winning_captures(board, 450)
                follow = max(wins, key=lambda w: w[1])[0] if wins else None
            board.pop(); board.pop()
            if mate is not None: return [dc, reply, mate], 1
            if follow is not None: return [dc, reply, follow], 1
            return None
        if kind == "discovered":
            if self._any_mate_in_1(board): return None
            if self._winning_captures(board, 450): return None
            q = next((s for s, pc in board.piece_map().items() if pc.color == chess.BLACK and pc.piece_type == chess.QUEEN), None)
            if q is None: return None
            out = []
            for m in list(board.legal_moves):
                if m.to_square == q: continue
                if board.piece_type_at(m.from_square) in (chess.KING, chess.QUEEN): continue
                board.push(m)
                disc = any(pc.color == chess.WHITE and pc.piece_type in (chess.ROOK, chess.BISHOP, chess.QUEEN) and chess.BB_SQUARES[m.from_square] & chess.between(s, q) and s in board.attackers(chess.WHITE, q) for s, pc in board.piece_map().items())
                ok = (disc and see_after_capture(board, m.to_square) <= 0 and self._every_reply_loses(board, 400))
                board.pop()
                if ok:
                    line = self._finish_material_line(board, m, 400)
                    if line: out.append(line)
            if not out or (len(out) > 1 and unique_pref): return None
            return out[0], len(out)
        if kind == "remove_defender":
            if self._any_mate_in_1(board): return None
            keys = self._mate2_keys(board)
            caps = [k for k in keys if board.is_capture(k) and board.piece_type_at(k.to_square) != chess.PAWN]
            if not caps or (len(keys) > 1 and unique_pref): return None
            key = caps[0]; board.push(key)
            reply = self._toughest_defense(board, 1) or self.rng.choice(list(board.legal_moves))
            board.push(reply); mate = next((m for m in board.legal_moves if self._is_mate_after(board, m)), None)
            board.pop(); board.pop()
            return ([key, reply, mate], len(keys)) if mate else None
        if kind == "trapped_queen":
            if self._any_mate_in_1(board): return None
            if self._winning_captures(board, 400): return None
            q = next((s for s, pc in board.piece_map().items() if pc.color == chess.BLACK and pc.piece_type == chess.QUEEN), None)
            if q is None: return None
            if any(pc.color == chess.BLACK and pc.piece_type == chess.ROOK for pc in board.piece_map().values()): return None
            out = []
            for m in list(board.legal_moves):
                if m.to_square == q: continue
                board.push(m)
                ok = (q in board.attacks(m.to_square) and see_after_capture(board, m.to_square) <= 0 and self._every_reply_loses(board, 400))
                board.pop()
                if ok:
                    line = self._finish_material_line(board, m, 400)
                    if line: out.append(line)
            if not out or (len(out) > 1 and unique_pref): return None
            return out[0], len(out)
        if kind == "pin_win":
            if self._any_mate_in_1(board): return None
            if self._winning_captures(board, 400): return None
            k = board.king(chess.BLACK); out = []
            for m in list(board.legal_moves):
                if board.piece_type_at(m.from_square) == chess.KING: continue
                board.push(m); pinned = None
                for s, pc in board.piece_map().items():
                    if pc.color != chess.WHITE or pc.piece_type not in (chess.ROOK, chess.BISHOP, chess.QUEEN): continue
                    seg = chess.SquareSet(chess.between(s, k)); occ = [board.piece_at(x) for x in seg if board.piece_at(x) is not None]
                    if len(occ) == 1 and occ[0].color == chess.BLACK and occ[0].piece_type != chess.PAWN:
                        psq = next(x for x in seg if board.piece_at(x) is not None)
                        if len(board.attackers(chess.WHITE, psq)) >= 2: pinned = psq; break
                ok = (pinned is not None and see_after_capture(board, m.to_square) <= 0 and self._every_reply_loses(board, 300))
                board.pop()
                if ok:
                    line = self._finish_material_line(board, m, 300)
                    if line: out.append(line)
            if not out or (len(out) > 1 and unique_pref): return None
            return out[0], len(out)
        if kind == "boden":
            bk = board.king(chess.BLACK); adj = [s for s in chess.SQUARES if chess.square_distance(s, bk) == 1]; bods = []
            for m in self._mating_moves(board):
                if board.piece_type_at(m.from_square) != chess.BISHOP: continue
                others = [s for s, pc in board.piece_map().items() if pc.color == chess.WHITE and pc.piece_type == chess.BISHOP and s != m.from_square]
                if not others: continue
                board.push(m); cov = sum(1 for s in adj if s in board.attacks(others[0])); board.pop()
                if cov >= 2: bods.append(m)
            if not bods or (len(bods) > 1 and unique_pref): return None
            return [bods[0]], len(bods)
        if kind == "epaulette":
            bk = board.king(chess.BLACK); f0, r0 = chess.square_file(bk), chess.square_rank(bk); flanks = []
            for df in (-1, 1):
                s = chess.square(f0 + df, r0); pc = board.piece_at(s)
                if pc is None or pc.color != chess.BLACK: flanks = None; break
                flanks.append(s)
            if flanks is None: return None
            mates = [m for m in self._mating_moves(board) if board.piece_type_at(m.from_square) in (chess.ROOK, chess.QUEEN) and m.to_square not in flanks and (chess.square_rank(m.to_square) == r0 or chess.square_file(m.to_square) == f0)]
            if not mates or (len(mates) > 1 and unique_pref): return None
            return [mates[0]], len(mates)
        if kind == "ladder":
            if self._any_mate_in_1(board): return None
            keys = self._mate2_keys(board); cands = []
            for key in keys:
                if board.piece_type_at(key.from_square) != chess.ROOK: continue
                if not board.gives_check(key): continue
                board.push(key); found = None
                for r in list(board.legal_moves):
                    board.push(r)
                    for mm in list(board.legal_moves):
                        if board.piece_type_at(mm.from_square) != chess.ROOK: continue
                        if chess.square_rank(mm.to_square) not in (0, 7): continue
                        board.push(mm); mate_now = board.is_checkmate(); board.pop()
                        if mate_now: found = (r, mm); break
                    board.pop()
                    if found: break
                board.pop()
                if found: cands.append((key,) + found)
            if not cands or (len(cands) > 1 and unique_pref): return None
            key, r, mate = cands[0]
            return [key, r, mate], len(cands)
        if kind == "queen_fork":
            if self._any_mate_in_1(board): return None
            if self._winning_captures(board, 450): return None
            out = []
            for m in list(board.legal_moves):
                if board.piece_type_at(m.from_square) != chess.QUEEN: continue
                board.push(m)
                hits_rook = any(board.piece_at(s) is not None and board.piece_at(s).color == chess.BLACK and board.piece_at(s).piece_type == chess.ROOK for s in board.attacks(m.to_square))
                ok = (board.is_check() and hits_rook and see_after_capture(board, m.to_square) <= 0 and self._every_reply_loses(board, 450))
                board.pop()
                if ok:
                    line = self._finish_material_line(board, m, 450)
                    if line: out.append(line)
            if not out or (len(out) > 1 and unique_pref): return None
            return out[0], len(out)
            
        # --- NEW TACTICS IMPLEMENTATIONS ---        
        if kind == "deflection":
            if self._any_mate_in_1(board): return None
            if self._winning_captures(board, 300): return None
            out = []
            for m in list(board.legal_moves):
                if board.piece_type_at(m.from_square) == chess.KING: continue
                board.push(m)
                ok = (board.is_check() or board.is_capture(m)) and see_after_capture(board, m.to_square) <= 0 and self._every_reply_loses(board, 300)
                board.pop()
                if ok:
                    line = self._finish_material_line(board, m, 300)
                    if line: out.append(line)
            if not out or (len(out) > 1 and unique_pref): return None
            return out[0], len(out)
            
        if kind == "overloading":
            if self._any_mate_in_1(board): return None
            if self._winning_captures(board, 300): return None
            out = []
            for m in list(board.legal_moves):
                if board.piece_type_at(m.from_square) == chess.KING: continue
                board.push(m)
                ok = see_after_capture(board, m.to_square) <= 0 and self._every_reply_loses(board, 300)
                board.pop()
                if ok:
                    line = self._finish_material_line(board, m, 300)
                    if line: out.append(line)
            if not out or (len(out) > 1 and unique_pref): return None
            return out[0], len(out)
            
        if kind == "zwischenzug":
            if self._any_mate_in_1(board): return None
            if self._winning_captures(board, 400): return None
            out = []
            for m in list(board.legal_moves):
                if not board.gives_check(m): continue
                board.push(m)
                ok = see_after_capture(board, m.to_square) <= 0 and self._every_reply_loses(board, 400)
                board.pop()
                if ok:
                    line = self._finish_material_line(board, m, 400)
                    if line: out.append(line)
            if not out or (len(out) > 1 and unique_pref): return None
            return out[0], len(out)
            
        if kind == "magnet":
            if self._any_mate_in_1(board): return None
            keys = self._mate2_keys(board); mags = []
            for k in keys:
                if not board.gives_check(k): continue
                board.push(k)
                bk = board.king(chess.BLACK)
                if not any(r.from_square == bk for r in board.legal_moves):
                    board.pop(); continue
                board.pop()
                mags.append(k)
            if not mags or (len(keys) > 1 and unique_pref): return None
            key = mags[0]; board.push(key)
            reply = self._toughest_defense(board, 1) or self.rng.choice(list(board.legal_moves))
            board.push(reply)
            mate = next((m for m in board.legal_moves if self._is_mate_after(board, m)), None)
            board.pop(); board.pop()
            return ([key, reply, mate], len(keys)) if mate else None
            
        if kind == "stalemate_trick":
            mates = self._mating_moves(board)
            if not mates: return None
            if len(mates) == 1: return [mates[0]], 1
            return None
            
        if kind == "endgame_kq" or kind == "endgame_kr":
            m = self.solver.mate_key(board, 10)
            if m is None: return None
            line = [m]
            b = board.copy(stack=False)
            while not b.is_checkmate() and len(line) < 10:
                b.push(line[-1])
                if b.is_checkmate(): break
                r = self._toughest_defense(b, 2)
                if r is None: break
                line.append(r)
                b.push(r)
                m = self.solver.mate_key(b, 10 - len(line))
                if m is None: break
                line.append(m)
            if b.is_checkmate(): return line, 1
            return None
            
        if kind == "defensive_perp":
            for m in board.legal_moves:
                if board.gives_check(m):
                    board.push(m)
                    bk = board.king(chess.BLACK)
                    replies = [r for r in board.legal_moves if r.from_square == bk]
                    if not replies: board.pop(); continue
                    r = replies[0]; board.push(r)
                    m2 = None
                    for c in board.legal_moves:
                        if board.gives_check(c):
                            m2 = c; break
                    board.pop(); board.pop()
                    if m2:
                        return [m, r, m2], 1
            return None
            
        if kind == "defensive_stale":
            for m in board.legal_moves:
                board.push(m)
                if board.is_stalemate():
                    board.pop()
                    return [m], 1
                board.pop()
            return None

        return None

    def _finale_for(self, board, line, default):
        tmp = chess.Board(board.fen()); cap = None
        for mv in line:
            if tmp.is_capture(mv): cap = tmp.piece_type_at(mv.to_square)
            tmp.push(mv)
        if tmp.is_checkmate(): return "CHECKMATE!"
        if tmp.is_stalemate(): return "DRAW SAVED!"
        if tmp.is_repetition(2): return "DRAW SAVED!"
        if cap == chess.QUEEN: return "QUEEN WON!"
        if cap == chess.ROOK: return "ROOK WON!"
        if cap in (chess.BISHOP, chess.KNIGHT): return "PIECE WON!"
        return default

    def _gen_random(self, kind, progress=None, tag="", cancel=None):
        tries = 0
        while tries < self.RANDOM_CAP:
            tries += 1
            if cancel is not None and cancel(): return None
            if progress and tries % 100 == 0: progress(f"{tag} searching\u2026 {tries} positions tried")
            board = self._random_position(kind)
            if board is None: continue
            key = tt_fen_key(board.fen())
            if key in self.seen: continue
            res = self._try_kind(kind, board, relax=(tries > self.UNIQUE_TRIES))
            if res is None: continue
            line, alts = res; spec = KINDS[kind]; finale = self._finale_for(board, line, spec["finale"])
            self.seen.add(key)
            return make_puzzle(board, line, kind, spec["label"], spec["sub"], finale, spec["prompt"], alts=alts)
        return None

    def _gen_mate_retro(self, kind, progress=None, tag="", cancel=None):
        for round_no in range(self.RETRO_ROUNDS):
            if cancel is not None and cancel(): return None
            if progress and round_no % 10 == 0: progress(f"{tag} retro construction\u2026 round {round_no + 1}/{self.RETRO_ROUNDS}")
            tmpl = self.rng.choice(self.RETRO_TEMPLATES); M = construct_mate_position(self.rng, template=tmpl)
            if M is None or tt_fen_key(M.fen()) in self.seen: continue
            if kind == "mate_in_2":
                for P in self._beam(list(retrograde_white(M)), width=5):
                    if cancel is not None and cancel(): return None
                    if tt_fen_key(P.fen()) in self.seen: continue
                    pz = self._mate2_from(P)
                    if pz is not None: self.seen.add(tt_fen_key(P.fen())); return pz
            else:
                for P2 in self._beam(list(retrograde_white(M)), width=4):
                    for R1 in retrograde_black(P2):
                        if cancel is not None and cancel(): return None
                        for P3 in retrograde_white(R1, max_out=8):
                            if tt_fen_key(P3.fen()) in self.seen: continue
                            pz = self._mate3_from(P3)
                            if pz is not None: self.seen.add(tt_fen_key(P3.fen())); return pz
        return None

    def _mate2_from(self, P):
        if self.solver.has_mate(P, 1): return None
        keys = self.solver.mate_keys_all(P, 2)
        if len(keys) != 1: return None
        if not self.oracle.agree_white_wins(P): return None
        ok, _score, _info = self.judge.judge_mate(P, 2)
        if not ok: return None
        key = keys[0]; b = P.copy(stack=False); b.push(key)
        reply = self._toughest_defense(b, 1)
        if reply is None: return None
        b.push(reply); mate = self._first_mating_move(b)
        if mate is None: return None
        spec = KINDS["mate_in_2"]
        return make_puzzle(P, [key, reply, mate], "mate_in_2", spec["label"], spec["sub"], spec["finale"], spec["prompt"], alts=1)

    def _mate3_from(self, P):
        if self.solver.has_mate(P, 1) or self.solver.has_mate(P, 2): return None
        keys = self.solver.mate_keys_all(P, 3)
        if len(keys) != 1: return None
        if not self.oracle.agree_white_wins(P): return None
        ok, _score, _info = self.judge.judge_mate(P, 3)
        if not ok: return None
        key = keys[0]; b = P.copy(stack=False); b.push(key)
        r1 = self._toughest_defense(b, 2)
        if r1 is None: return None
        b.push(r1); k2 = self.solver.mate_key(b, 2)
        if k2 is None: return None
        b.push(k2); r2 = self._toughest_defense(b, 1)
        if r2 is None: return None
        b.push(r2); m3 = self._first_mating_move(b)
        if m3 is None: return None
        spec = KINDS["mate_in_3"]
        return make_puzzle(P, [key, r1, k2, r2, m3], "mate_in_3", spec["label"], spec["sub"], spec["finale"], spec["prompt"], alts=1)

    def _gen_mate1_retro(self, kind, progress=None, tag="", cancel=None):
        tmpl = self.MATE1_TEMPLATE.get(kind)
        if tmpl is None: return None
        for _round in range(self.RETRO_ROUNDS):
            if cancel is not None and cancel(): return None
            M = construct_mate_position(self.rng, template=tmpl)
            if M is None: continue
            for P in self._beam(list(retrograde_white(M)), width=4):
                if cancel is not None and cancel(): return None
                if tt_fen_key(P.fen()) in self.seen: continue
                res = self._try_kind(kind, P)
                if res is not None:
                    line, alts = res; spec = KINDS[kind]; finale = self._finale_for(P, line, spec["finale"])
                    self.seen.add(tt_fen_key(P.fen()))
                    return make_puzzle(P, line, kind, spec["label"], spec["sub"], finale, spec["prompt"], alts=alts)
        return None

    def _gen_anneal(self, kind, progress=None, tag="", cancel=None):
        seed = self._random_position(kind)
        if seed is None: return None
        an = Annealer(self.rng, kind, self.ANNEAL_ITERS, cancel=cancel)
        res = an.run(seed, verify=lambda b: self._try_kind(kind, b))
        if res is None: return None
        board, (line, alts) = res; spec = KINDS[kind]; finale = self._finale_for(board, line, spec["finale"])
        self.seen.add(tt_fen_key(board.fen()))
        return make_puzzle(board, line, kind, spec["label"], spec["sub"], finale, spec["prompt"], alts=alts)

    def _gen_one(self, kind, progress=None, tag="", cancel=None):
        strategies = []
        if kind in ("mate_in_2", "mate_in_3"): strategies.append("retro")
        if kind in self.MATE1_TEMPLATE: strategies.append("retro1")
        if kind in ANNEAL_KINDS: strategies.append("anneal")
        strategies.append("random")
        cycle = 0
        while True:
            if cancel is not None and cancel(): return None
            cycle += 1
            for s in strategies:
                if cancel is not None and cancel(): return None
                if s == "retro": pz = self._gen_mate_retro(kind, progress, tag, cancel)
                elif s == "retro1": pz = self._gen_mate1_retro(kind, progress, tag, cancel)
                elif s == "anneal": pz = self._gen_anneal(kind, progress, tag, cancel)
                else: pz = self._gen_random(kind, progress, tag, cancel)
                if pz is not None: return pz
            if progress: progress(f"{tag} \u2014 rotating strategies (cycle {cycle})\u2026")

    def _pick_kind(self, sel):
        if sel == "mix":
            kinds = list(MIX_WEIGHTS.keys()); weights = [MIX_WEIGHTS[k] for k in kinds]
            return self.rng.choices(kinds, weights=weights)[0]
        if sel == "mates_only": return self.rng.choice(MATES_ONLY)
        return sel

    def generate(self, count, kind_sel="mix", progress=None, cancel=None, retry_failed=True, black_to_move=False, hero_piece="Any"):
        out = []; last_kind = None
        FILLED_STAR = "\u2605"
        EMPTY_STAR = "\u2606"
        for i in range(count):
            if cancel is not None and cancel(): progress and progress("Cancelled."); break
            kind = self._pick_kind(kind_sel)
            if kind_sel == "mix" and kind == last_kind:
                for _ in range(6):
                    kind = self._pick_kind(kind_sel)
                    if kind != last_kind: break
            last_kind = kind; spec = KINDS[kind]; tag = f"{spec['label']} #{i + 1}"
            progress and progress(f"Generating {tag} ...")
            
            c_min, c_max = get_category_star_range(kind)
            d_min = max(self.difficulty_min, c_min)
            d_max = min(self.difficulty_max, c_max)
            if d_min > d_max: d_min, d_max = c_min, c_max
            
            pz = None; attempts = 0
            max_attempts = 1 if not retry_failed else 200
            while pz is None and attempts < max_attempts:
                if cancel is not None and cancel(): break
                attempts += 1
                if attempts % 5 == 0: progress and progress(f"{tag} - matching difficulty (attempt {attempts})...")
                candidate = self._gen_one(kind, progress, tag, cancel)
                if candidate is None: break
                
                # Filter by Hero Piece
                if hero_piece != "Any":
                    ptype = candidate["boards"][0].piece_type_at(candidate["line"][0].from_square)
                    if ptype != PIECE_MAP[hero_piece]:
                        self.seen.add(tt_fen_key(candidate["fen"]))
                        continue
                        
                if d_min <= candidate.get("stars", 3) <= d_max:
                    pz = candidate
                else:
                    self.seen.add(tt_fen_key(candidate["fen"]))
            
            if pz:
                if black_to_move:
                    pz = make_black_to_move(pz)
                
                # Multi-Motif Tagging (Sacrifice + X)
                if kind != "sacrifice" and kind != "win_queen" and kind != "win_rook" and kind != "win_piece":
                    b = chess.Board(pz["fen"])
                    mv = pz["line"][0]
                    if b.is_capture(mv):
                        moved = b.piece_type_at(mv.from_square)
                        if moved and moved not in (chess.PAWN, chess.KING) and see_after_capture(b, mv.to_square) >= 100:
                            pz["label"] = f"Sacrifice + {pz['label']}"
                            pz["sub"] = f"SAC + {pz['sub']}"
                
                out.append(pz)
                stars = pz.get("stars", 3)
                star_str = FILLED_STAR * stars + EMPTY_STAR * (5 - stars)
                progress and progress(f"Slot {i + 1} [{pz['label']}]: {pz['san']} (Difficulty: {star_str})")
            elif cancel is not None and cancel(): break
            else:
                progress and progress(f"Slot {i + 1} skipped after {attempts} attempts.")
        return out

# ----------------------------- background workers ---------------------------

class PuzzleWorker(QThread):
    progress = Signal(str); finished_ok = Signal(list); failed = Signal(str)
    def __init__(self, count, kind_sel, seed, banned=None, difficulty_min=1, difficulty_max=5, retry_failed=True, black_to_move=False, hero_piece="Any"):
        super().__init__()
        self.count, self.kind_sel, self.seed = count, kind_sel, seed
        self.banned = banned or ()
        self.difficulty_min, self.difficulty_max = difficulty_min, difficulty_max
        self.retry_failed = retry_failed
        self.black_to_move = black_to_move
        self.hero_piece = hero_piece
        self.cancel_flag = False
    def run(self):
        try:
            gen = PuzzleGenerator(self.seed, banned=self.banned, difficulty_min=self.difficulty_min, difficulty_max=self.difficulty_max)
            puzzles = gen.generate(self.count, self.kind_sel, progress=lambda s: self.progress.emit(s), cancel=lambda: self.cancel_flag, retry_failed=self.retry_failed, black_to_move=self.black_to_move, hero_piece=self.hero_piece)
            self.finished_ok.emit(puzzles)
        except Exception as e: self.failed.emit(f"{e}\n\n{traceback.format_exc()}")

class EvalWorker(QThread):
    progress = Signal(str); done = Signal(bool); failed = Signal(str)
    def __init__(self, puzzles, cfg): super().__init__(); self.puzzles, self.cfg = puzzles, cfg
    def run(self):
        try:
            used = attach_evals(self.puzzles, self.cfg.stockfish or None, progress=lambda s: self.progress.emit(s))
            self.done.emit(used)
        except Exception as e: self.failed.emit(f"{e}\n\n{traceback.format_exc()}")

class RenderWorker(QThread):
    progress = Signal(int, int); stage = Signal(str); done = Signal(str); cancelled = Signal(); failed = Signal(str)
    def __init__(self, puzzles, path, cfg): super().__init__(); self.puzzles, self.path, self.cfg = list(puzzles), path, cfg; self.cancel_flag = False
    def run(self):
        try:
            if self.cfg.eval_bar and self.cfg.stockfish and not self.puzzles[0].get("evals"):
                self.stage.emit("Computing Stockfish evals\u2026")
                attach_evals(self.puzzles, self.cfg.stockfish)
            render_video(self.puzzles, self.path, self.cfg, progress=lambda i, n: self.progress.emit(i, n), cancel=lambda: self.cancel_flag, stage=lambda s: self.stage.emit(s))
            self.done.emit(self.path)
        except RenderCancelled: self.cancelled.emit()
        except Exception as e: self.failed.emit(f"{e}\n\n{traceback.format_exc()}")

# ----------------------------- preview & main UI ----------------------------

class ThemeEditorDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Custom Theme Editor")
        self.layout = QVBoxLayout(self)
        self.colors = {
            "Light Square": QColor(THEMES["Custom"][0]),
            "Dark Square": QColor(THEMES["Custom"][1]),
            "Background Top": QColor(CUSTOM_BG_TOP),
            "Background Bottom": QColor(CUSTOM_BG_BOTTOM),
            "Arrow Color": QColor(CUSTOM_ARROW)
        }
        for name, color in self.colors.items():
            row = QHBoxLayout(); row.addWidget(QLabel(name))
            btn = QPushButton("Choose Color")
            btn.setStyleSheet(f"background-color: {color.name()};")
            btn.clicked.connect(lambda _, n=name, b=btn: self.choose_color(n, b))
            row.addWidget(btn); self.layout.addLayout(row)
        ok_btn = QPushButton("OK"); ok_btn.clicked.connect(self.accept)
        self.layout.addWidget(ok_btn)
    def choose_color(self, name, btn):
        color = QColorDialog.getColor(self.colors[name], self, f"Choose {name}")
        if color.isValid():
            self.colors[name] = color; btn.setStyleSheet(f"background-color: {color.name()};")

class BoardPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent); self.setMinimumSize(260, 440); self.st = None; self.setAcceptDrops(True)
    def set_state(self, st): self.st = st; self.update()
    def clear_state(self): self.st = None; self.update()
    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls(): e.acceptProposedAction()
    def dropEvent(self, e: QDropEvent):
        urls = e.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile(); win = self.window()
            if isinstance(win, MainWindow):
                ext = os.path.splitext(path)[1].lower()
                if ext in (".png", ".jpg", ".jpeg", ".bmp"): win.edit_logo.setText(path); win._save_settings_later()
                elif ext in (".mp3", ".wav", ".m4a", ".flac", ".ogg"): win.edit_music.setText(path); win._save_settings_later()
                elif ext == ".json": win.load_pack(path)
    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing, True); p.setRenderHint(QPainter.TextAntialiasing, True)
        w, h = self.width(), self.height()
        if self.st is None:
            draw_bg(p, w, h); draw_text(p, w / 2, h / 2, "Press the button to create a Short", max(13, int(w * 0.045)), QColor(255, 255, 255, 140), bold=False)
        else: draw_frame(p, self.st, w, h)
        p.end()

class HotKeysDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent); self.setWindowTitle("Keyboard Shortcuts"); self.setMinimumWidth(440)
        v = QVBoxLayout(self); title = QLabel("\u2328 Hotkeys"); title.setStyleSheet("font-size: 18pt; font-weight: bold; color: #F5C542;"); v.addWidget(title)
        shortcuts = [("Space", "Play / stop animation preview"), ("Left / Right arrows", "Previous / next puzzle"), ("Shift + Left / Right", "Step frame backward / forward (in animation)"), ("Esc", "Stop animation"), ("F", "Flip board orientation"), ("S", "Toggle 'Show solution' checkbox"), ("Ctrl + S", "Save current preview frame as PNG"), ("Ctrl + E", "Export puzzles as PGN"), ("Ctrl + T", "Copy suggested title + hashtags"), ("Ctrl + J", "Save puzzles as JSON pack"), ("Ctrl + L", "Load puzzles from JSON pack"), ("Ctrl + H", "Open puzzle history viewer"), ("Ctrl + ?", "Show this help dialog"), ("Ctrl + A", "About Chess Shorts Studio")]
        for key, desc in shortcuts:
            row = QHBoxLayout(); k = QLabel(key); k.setStyleSheet("background: #2A2D45; padding: 4px 10px; border-radius: 4px; font-weight: bold; color: #F5C542;"); d = QLabel(desc); d.setStyleSheet("color: #E0E0F0;"); row.addWidget(k); row.addWidget(d, 1); container = QWidget(); container.setLayout(row); v.addWidget(container)
        close = QPushButton("Close"); close.clicked.connect(self.accept); v.addWidget(close)

class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent); self.setWindowTitle("About Chess Shorts Studio"); self.setMinimumWidth(440)
        v = QVBoxLayout(self); title = QLabel("\u265F Chess Shorts Studio"); title.setStyleSheet("font-size: 20pt; font-weight: bold; color: #F5C542;"); v.addWidget(title)
        v.addWidget(QLabel("Vertical YouTube Shorts generator for chess puzzles.\n")); v.addWidget(QLabel("Features:"))
        feats = ["35 puzzle categories (Advanced Tactics & Endgames)", "Piece-Specific Generators & Multi-Motif Tags", "df-pn mate solver + retrograde + simulated annealing", "Composition judge (cook / dual / economy)", "720p / 1080p / 1440p output, 4 quality presets", "Optional eval bar (no-spoiler mode), Stockfish support", "Synthesized SFX (piece-pitched) + optional music", "Confetti finale, logo watermark, multiple themes", "Anti-repeat manifest, puzzle history viewer", "Batch production, JSON puzzle packs, PGN export", "Outputs (MP4) saved cleanly in a subfolder", "Black to Move mode, Custom Theme Editor, Star Ratings"]
        for f in feats:
            l = QLabel(f"  \u2022 {f}"); l.setStyleSheet("color: #C5C5D5;"); v.addWidget(l)
        v.addWidget(QLabel("")); v.addWidget(QLabel("pip install PySide6 chess numpy imageio imageio-ffmpeg"))
        close = QPushButton("Close"); close.clicked.connect(self.accept); v.addWidget(close)

class HistoryDialog(QDialog):
    def __init__(self, manifest, parent=None):
        super().__init__(parent); self.setWindowTitle("Puzzle History"); self.resize(720, 480)
        v = QVBoxLayout(self); title = QLabel(f"\U0001F4DC Puzzle History ({len(manifest)} entries)"); title.setStyleSheet("font-size: 14pt; font-weight: bold; color: #F5C542;"); v.addWidget(title)
        self.table = QTableWidget(); self.table.setColumnCount(5); self.table.setHorizontalHeaderLabels(["Kind", "Label", "SAN", "Rendered", "Video"]); self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch); self.table.setEditTriggers(QTableWidget.NoEditTriggers); self.table.setRowCount(len(manifest))
        for i, (key, e) in enumerate(sorted(manifest.items(), key=lambda kv: kv[1].get("rendered", ""), reverse=True)):
            try:
                items = [e.get("kind", ""), e.get("label", ""), e.get("san", ""), e.get("rendered", ""), e.get("video", "")]
                for j, txt in enumerate(items): self.table.setItem(i, j, QTableWidgetItem(str(txt)))
            except Exception: continue
        v.addWidget(self.table)
        btn_row = QHBoxLayout(); export_btn = QPushButton("Export to JSON\u2026"); clear_btn = QPushButton("Clear history\u2026"); close_btn = QPushButton("Close")
        export_btn.clicked.connect(lambda: self._export(parent)); clear_btn.clicked.connect(lambda: self._clear(parent)); close_btn.clicked.connect(self.accept)
        btn_row.addWidget(export_btn); btn_row.addWidget(clear_btn); btn_row.addStretch(1); btn_row.addWidget(close_btn); v.addLayout(btn_row)
    def _export(self, parent):
        path, _ = QFileDialog.getSaveFileName(self, "Export history", "history.json", "JSON (*.json)")
        if not path: return
        try:
            with open(path, "w", encoding="utf-8") as f: json.dump(load_manifest(), f, indent=2)
            QMessageBox.information(self, "Exported", f"History exported to {path}")
        except Exception as e: QMessageBox.critical(self, "Error", str(e))
    def _clear(self, parent):
        ret = QMessageBox.question(self, "Clear history", "Forget all previously used puzzles?")
        if ret != QMessageBox.Yes: return
        save_manifest({}); parent._refresh_manifest_label(); self.accept()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle("\u265F Chess Shorts Studio"); self.resize(1280, 880)
        self.puzzles = []; self.current_index = 0; self.generating = False; self.rendering = False; self.animating = False; self.anim_t = 0.0
        self._render_path = None; self._user_stopped = False; self.batch_left = 0; self._render_t0 = 0.0; self._last_video_dir = None
        self._last_video_path = None
        self.gen_worker = None; self.render_worker = None; self.eval_worker = None; self.cfg = VideoConfig()
        self.manifest = load_manifest(); self.settings = QSettings("ChessShortsStudio", "studio")
        self.preview_flipped = False; self.preview_speed = 1.0
        self._save_timer = QTimer(self); self._save_timer.setSingleShot(True); self._save_timer.setInterval(400); self._save_timer.timeout.connect(self._save_settings)
        self.anim_timer = QTimer(self); self.anim_timer.setInterval(33); self.anim_timer.timeout.connect(self.anim_tick)
        self._build_ui(); self.set_buttons(); self._update_preview(); self._refresh_manifest_label(); self._load_settings()

    def _build_ui(self):
        central = QWidget(); self.setCentralWidget(central); root = QHBoxLayout(central)
        left = QWidget(); left.setFixedWidth(380); lv = QVBoxLayout(left)
        tabs = QTabWidget(); tab1 = QWidget(); f1 = QFormLayout(tab1)
        self.spin_count = QSpinBox(); self.spin_count.setRange(1, 10); self.spin_count.setValue(3)
        self.spin_batch = QSpinBox(); self.spin_batch.setRange(1, 10); self.spin_batch.setValue(1); self.spin_batch.setToolTip("Create several Shorts back-to-back, hands-free")
        self.combo_kind = QComboBox()
        for _kid, label in KIND_MENU: self.combo_kind.addItem(label)
        self.edit_seed = QLineEdit(); self.edit_seed.setPlaceholderText("empty = random")
        self.chk_black = QCheckBox("Black to move (Black plays the solution)")
        
        self.combo_hero = QComboBox(); self.combo_hero.addItems(HERO_PIECES)
        
        f1.addRow("Puzzles per Short:", self.spin_count); f1.addRow("Batch (Shorts in a row):", self.spin_batch); f1.addRow("Category:", self.combo_kind); f1.addRow("Seed:", self.edit_seed); f1.addRow(self.chk_black); f1.addRow("Hero Piece:", self.combo_hero)
        f1.addRow(QLabel("Difficulty filter (stars):")); diff_row = QHBoxLayout()
        self.spin_diff_min = QSpinBox(); self.spin_diff_min.setRange(1, 5); self.spin_diff_min.setValue(1)
        self.spin_diff_max = QSpinBox(); self.spin_diff_max.setRange(1, 5); self.spin_diff_max.setValue(5)
        diff_row.addWidget(self.spin_diff_min); diff_row.addWidget(QLabel("\u2014")); diff_row.addWidget(self.spin_diff_max); diff_row.addStretch(1); f1.addRow(diff_row)
        self.chk_retry = QCheckBox("Retry failed slots (recommended)"); self.chk_retry.setChecked(True); f1.addRow(self.chk_retry)
        tabs.addTab(tab1, "Puzzles")
        tab2 = QWidget(); f2 = QFormLayout(tab2)
        self.spin_solve = QSpinBox(); self.spin_solve.setRange(2, 15); self.spin_solve.setValue(5); self.spin_solve.setSuffix(" s")
        self.combo_fps = QComboBox(); self.combo_fps.addItems(["30", "60"])
        self.combo_resolution = QComboBox(); self.combo_resolution.addItems(["720p", "1080p", "1440p"]); self.combo_resolution.setCurrentText("1080p")
        self.combo_quality = QComboBox(); self.combo_quality.addItems(["Low", "Medium", "High", "Ultra"]); self.combo_quality.setCurrentText("High")
        self.combo_theme = QComboBox(); self.combo_theme.addItems(list(THEMES.keys()))
        self.btn_edit_theme = QPushButton("Edit Custom Theme..."); self.btn_edit_theme.setFixedWidth(150)
        theme_row = QHBoxLayout(); theme_row.addWidget(self.combo_theme); theme_row.addWidget(self.btn_edit_theme)
        self.edit_channel = QLineEdit(); self.edit_channel.setPlaceholderText("@YourChannel")
        self.edit_logo = QLineEdit(); self.edit_logo.setPlaceholderText("Logo PNG (optional)"); self.btn_logo = QPushButton("\U0001F4F7\u2026"); self.btn_logo.setFixedWidth(40)
        logo_row = QHBoxLayout(); logo_row.addWidget(self.edit_logo, 1); logo_row.addWidget(self.btn_logo)
        self.chk_eval = QCheckBox("Show eval bar"); self.chk_eval.setToolTip("Chess.com-style evaluation bar next to the board")
        self.chk_hide_think = QCheckBox("Eval bar: hide while thinking (no spoilers)"); self.chk_hide_think.setChecked(True)
        self.edit_sf = QLineEdit(); self.edit_sf.setPlaceholderText("Stockfish path (optional, better evals)"); self.btn_sf_detect = QPushButton("Auto-detect"); self.btn_sf_detect.setFixedWidth(90)
        sf_row = QHBoxLayout(); sf_row.addWidget(self.edit_sf, 1); sf_row.addWidget(self.btn_sf_detect)
        self.chk_sfx = QCheckBox("Sound effects"); self.chk_sfx.setChecked(True)
        self.edit_music = QLineEdit(); self.edit_music.setPlaceholderText("Background music file (optional)"); self.btn_music = QPushButton("\U0001F50A\u2026"); self.btn_music.setFixedWidth(40)
        mrow = QHBoxLayout(); mrow.addWidget(self.edit_music, 1); mrow.addWidget(self.btn_music)
        f2.addRow("Time to solve:", self.spin_solve); f2.addRow("FPS:", self.combo_fps); f2.addRow("Resolution:", self.combo_resolution); f2.addRow("Quality:", self.combo_quality); f2.addRow("Board theme:", theme_row); f2.addRow("Watermark:", self.edit_channel); f2.addRow("Logo:", logo_row); f2.addRow(self.chk_eval); f2.addRow(self.chk_hide_think); f2.addRow("Engine:", sf_row); f2.addRow(self.chk_sfx); f2.addRow("Music:", mrow)
        tabs.addTab(tab2, "Video")
        tab3 = QWidget(); f3 = QFormLayout(tab3)
        self.chk_coords = QCheckBox("Show board coordinates (a-h, 1-8)"); self.chk_coords.setChecked(True)
        self.chk_last_move = QCheckBox("Highlight last move"); self.chk_last_move.setChecked(True)
        self.chk_arrow = QCheckBox("Show solution arrow"); self.chk_arrow.setChecked(True)
        self.chk_safe_area = QCheckBox("Show YouTube safe-area guide (preview only)"); self.chk_safe_area.setChecked(False)
        f3.addRow(self.chk_coords); f3.addRow(self.chk_last_move); f3.addRow(self.chk_arrow); f3.addRow(self.chk_safe_area)
        tabs.addTab(tab3, "View")
        g3 = QGroupBox("Anti-repeat history"); f3b = QFormLayout(g3)
        self.lbl_manifest = QLabel(); self.lbl_manifest.setWordWrap(True); self.btn_view_history = QPushButton("\U0001F4DC View history\u2026"); self.btn_clear_manifest = QPushButton("Clear history\u2026")
        hist_row = QHBoxLayout(); hist_row.addWidget(self.btn_view_history); hist_row.addWidget(self.btn_clear_manifest)
        f3b.addRow(self.lbl_manifest); f3b.addRow(hist_row)
        lv.addWidget(tabs); lv.addWidget(g3)
        self.btn_go = QPushButton("\U0001F3B2  Generate \u2192 \U0001F3AC Render Shorts")
        self.progress = QProgressBar(); self.progress.setValue(0); self.status_lbl = QLabel("Ready. One click = one Short."); self.status_lbl.setWordWrap(True)
        brow = QHBoxLayout(); self.btn_title = QPushButton("\u2728 Title + tags"); self.btn_title.setToolTip("Copy a suggested title and hashtags to the clipboard"); self.btn_folder = QPushButton("\U0001F4C2 Show in folder"); self.btn_folder.setEnabled(False); self.btn_play_vid = QPushButton("\u25B6 Play Video"); self.btn_play_vid.setEnabled(False); self.btn_hotkeys = QPushButton("\u2328 Hotkeys"); self.btn_about = QPushButton("\u2139 About")
        brow.addWidget(self.btn_title); brow.addWidget(self.btn_folder); brow.addWidget(self.btn_play_vid); brow.addWidget(self.btn_hotkeys); brow.addWidget(self.btn_about)
        lv.addWidget(self.btn_go); lv.addWidget(self.progress); lv.addLayout(brow); lv.addWidget(self.status_lbl, 1)
        right = QWidget(); rv = QVBoxLayout(right); self.preview = BoardPreview(); rv.addWidget(self.preview, 1)
        row = QHBoxLayout(); self.btn_prev = QPushButton("\u25C0"); self.btn_play = QPushButton("\u25B6 Play"); self.chk_solution = QCheckBox("Show solution"); self.btn_flip = QPushButton("\u21C4 Flip"); self.btn_next = QPushButton("\u25B6")
        row.addWidget(self.btn_prev); row.addWidget(self.btn_play); row.addWidget(self.chk_solution); row.addWidget(self.btn_flip); row.addWidget(self.btn_next); rv.addLayout(row)
        speed_row = QHBoxLayout(); speed_row.addWidget(QLabel("Preview speed:")); self.combo_speed = QComboBox(); self.combo_speed.addItems(["0.5x", "1x", "2x"]); self.combo_speed.setCurrentText("1x"); speed_row.addWidget(self.combo_speed); self.chk_loop = QCheckBox("Loop preview"); self.chk_loop.setChecked(True); speed_row.addWidget(self.chk_loop); self.btn_frame_png = QPushButton("\U0001F4F7 Save frame PNG"); speed_row.addWidget(self.btn_frame_png); speed_row.addStretch(1); rv.addLayout(speed_row)
        action_row = QHBoxLayout(); self.btn_export = QPushButton("\u2913 Export PGN"); self.btn_save_pack = QPushButton("\U0001F4BE Save JSON pack"); self.btn_load_pack = QPushButton("\U0001F4C2 Load JSON pack")
        action_row.addWidget(self.btn_export); action_row.addWidget(self.btn_save_pack); action_row.addWidget(self.btn_load_pack); rv.addLayout(action_row)
        self.list_widget = QListWidget(); self.list_widget.setMaximumHeight(160); rv.addWidget(self.list_widget)
        root.addWidget(left); root.addWidget(right, 1)
        self.btn_go.clicked.connect(self.on_go_clicked); self.btn_prev.clicked.connect(lambda: self.step_preview(-1)); self.btn_next.clicked.connect(lambda: self.step_preview(+1)); self.btn_flip.clicked.connect(self.toggle_flip); self.chk_solution.toggled.connect(lambda _: self._update_preview()); self.btn_play.clicked.connect(self.toggle_play); self.list_widget.currentRowChanged.connect(self.on_list_select); self.chk_eval.toggled.connect(self.on_eval_toggled); self.btn_clear_manifest.clicked.connect(self.clear_manifest); self.btn_view_history.clicked.connect(self.show_history); self.btn_music.clicked.connect(self.browse_music); self.btn_logo.clicked.connect(self.browse_logo); self.btn_sf_detect.clicked.connect(self.detect_stockfish); self.btn_export.clicked.connect(self.export_pgn); self.btn_save_pack.clicked.connect(self.save_pack); self.btn_load_pack.clicked.connect(self.load_pack); self.btn_title.clicked.connect(self.copy_title); self.btn_folder.clicked.connect(self.show_in_folder); self.btn_play_vid.clicked.connect(self.play_video); self.btn_hotkeys.clicked.connect(self.show_hotkeys); self.btn_about.clicked.connect(self.show_about); self.btn_frame_png.clicked.connect(self.save_preview_png); self.btn_edit_theme.clicked.connect(self.edit_theme)
        self.combo_theme.currentIndexChanged.connect(lambda _i: self._on_view_changed()); self.combo_speed.currentIndexChanged.connect(self._on_speed_changed)
        for chk in (self.chk_coords, self.chk_last_move, self.chk_arrow, self.chk_safe_area, self.chk_hide_think, self.chk_sfx, self.chk_retry, self.chk_black): chk.toggled.connect(lambda _: self._on_view_changed())
        self.sc_play = QShortcut(QKeySequence(Qt.Key_Space), self); self.sc_play.activated.connect(self._space_pressed)
        self.sc_hotkeys = QShortcut(QKeySequence("Ctrl+?"), self); self.sc_hotkeys.activated.connect(self.show_hotkeys)
        self.sc_about = QShortcut(QKeySequence("Ctrl+A"), self); self.sc_about.activated.connect(self.show_about)
        self.sc_export = QShortcut(QKeySequence("Ctrl+E"), self); self.sc_export.activated.connect(self.export_pgn)
        self.sc_save_png = QShortcut(QKeySequence("Ctrl+S"), self); self.sc_save_png.activated.connect(self.save_preview_png)
        self.sc_save_pack = QShortcut(QKeySequence("Ctrl+J"), self); self.sc_save_pack.activated.connect(self.save_pack)
        self.sc_load_pack = QShortcut(QKeySequence("Ctrl+L"), self); self.sc_load_pack.activated.connect(self.load_pack)
        self.sc_title = QShortcut(QKeySequence("Ctrl+T"), self); self.sc_title.activated.connect(self.copy_title)
        self.sc_hist = QShortcut(QKeySequence("Ctrl+H"), self); self.sc_hist.activated.connect(self.show_history)
        self.sc_flip = QShortcut(QKeySequence(Qt.Key_F), self); self.sc_flip.activated.connect(self.toggle_flip)
        self.sc_sol = QShortcut(QKeySequence(Qt.Key_S), self); self.sc_sol.activated.connect(lambda: self.chk_solution.toggle())
        self.sc_step_back = QShortcut(QKeySequence("Shift+Left"), self); self.sc_step_back.activated.connect(lambda: self.step_frame(-1))
        self.sc_step_fwd = QShortcut(QKeySequence("Shift+Right"), self); self.sc_step_fwd.activated.connect(lambda: self.step_frame(+1))
        self.sc_prev = QShortcut(QKeySequence(Qt.Key_Left), self); self.sc_prev.activated.connect(lambda: self.step_preview(-1))
        self.sc_next = QShortcut(QKeySequence(Qt.Key_Right), self); self.sc_next.activated.connect(lambda: self.step_preview(+1))
        self.sc_esc = QShortcut(QKeySequence(Qt.Key_Escape), self); self.sc_esc.activated.connect(self.stop_anim)

    def edit_theme(self):
        dlg = ThemeEditorDialog(self)
        if dlg.exec():
            THEMES["Custom"] = (dlg.colors["Light Square"].name(), dlg.colors["Dark Square"].name())
            global CUSTOM_BG_TOP, CUSTOM_BG_BOTTOM, CUSTOM_ARROW
            CUSTOM_BG_TOP = dlg.colors["Background Top"]; CUSTOM_BG_BOTTOM = dlg.colors["Background Bottom"]; CUSTOM_ARROW = dlg.colors["Arrow Color"]
            _BG_CACHE.clear(); self.combo_theme.setCurrentText("Custom"); self._save_settings_later(); self._update_preview()

    def _on_view_changed(self): self._save_settings_later(); self._update_preview()
    def _on_speed_changed(self):
        txt = self.combo_speed.currentText().rstrip("x")
        try: self.preview_speed = float(txt)
        except Exception: self.preview_speed = 1.0
    def _save_settings_later(self): self._save_timer.start()
    def set_buttons(self):
        if self.generating: self.btn_go.setText("\u23F9 Stop generating")
        elif self.rendering: self.btn_go.setText("\u23F9 Cancel render")
        else: self.btn_go.setText("\U0001F3B2  Generate \u2192 \U0001F3AC Render Shorts")
        self.btn_go.setEnabled(True); self.btn_play.setEnabled(bool(self.puzzles) and not self.generating)
    def read_cfg(self):
        self.cfg.fps = int(self.combo_fps.currentText()); self.cfg.solve_seconds = float(self.spin_solve.value()); self.cfg.channel = self.edit_channel.text().strip()
        self.cfg.eval_bar = self.chk_eval.isChecked(); self.cfg.stockfish = self.edit_sf.text().strip(); self.cfg.sfx = self.chk_sfx.isChecked(); self.cfg.music = self.edit_music.text().strip()
        self.cfg.hide_eval_think = self.chk_hide_think.isChecked(); self.cfg.theme = self.combo_theme.currentText()
        self.cfg.resolution = self.combo_resolution.currentText(); self.cfg.quality = self.combo_quality.currentText(); self.cfg.logo_path = self.edit_logo.text().strip()
        self.cfg.show_coords = self.chk_coords.isChecked(); self.cfg.show_last_move = self.chk_last_move.isChecked(); self.cfg.show_arrow = self.chk_arrow.isChecked(); self.cfg.show_safe_area = self.chk_safe_area.isChecked()
        self.cfg.difficulty_min = self.spin_diff_min.value(); self.cfg.difficulty_max = self.spin_diff_max.value(); self.cfg.retry_failed = self.chk_retry.isChecked()
        self.cfg.black_to_move = self.chk_black.isChecked()
        self.cfg.hero_piece = self.combo_hero.currentText()
        return self.cfg
    def _load_settings(self):
        global CUSTOM_BG_TOP, CUSTOM_BG_BOTTOM, CUSTOM_ARROW
        s = self.settings
        self.spin_count.setValue(s.value("count", 3, int)); self.spin_batch.setValue(s.value("batch", 1, int)); self.combo_kind.setCurrentIndex(s.value("kind_index", 0, int))
        self.spin_diff_min.setValue(s.value("diff_min", 1, int)); self.spin_diff_max.setValue(s.value("diff_max", 5, int)); self.chk_retry.setChecked(s.value("retry_failed", True, bool))
        self.spin_solve.setValue(s.value("solve", 5, int)); self.combo_fps.setCurrentIndex(s.value("fps_index", 0, int)); self.combo_resolution.setCurrentText(s.value("resolution", "1080p", str)); self.combo_quality.setCurrentText(s.value("quality", "High", str)); self.combo_theme.setCurrentText(s.value("theme", "Green", str))
        self.edit_channel.setText(s.value("channel", "", str)); self.edit_logo.setText(s.value("logo_path", "", str)); self.chk_eval.setChecked(s.value("eval_bar", False, bool)); self.chk_hide_think.setChecked(s.value("hide_eval_think", True, bool)); self.edit_sf.setText(s.value("stockfish", "", str))
        self.chk_sfx.setChecked(s.value("sfx", True, bool)); self.edit_music.setText(s.value("music", "", str)); self.chk_coords.setChecked(s.value("show_coords", True, bool)); self.chk_last_move.setChecked(s.value("show_last_move", True, bool)); self.chk_arrow.setChecked(s.value("show_arrow", True, bool)); self.chk_safe_area.setChecked(s.value("show_safe_area", False, bool))
        self.chk_black.setChecked(s.value("black_to_move", False, bool))
        self.combo_hero.setCurrentText(s.value("hero_piece", "Any", str))
        THEMES["Custom"] = (s.value("custom_light", "#EEEED2", str), s.value("custom_dark", "#769656", str))
        CUSTOM_BG_TOP = QColor(s.value("custom_bg_top", "#0F1424", str)); CUSTOM_BG_BOTTOM = QColor(s.value("custom_bg_bottom", "#231439", str)); CUSTOM_ARROW = QColor(s.value("custom_arrow", "#EB5A46", str))
        _BG_CACHE.clear()
        self.stats_videos = s.value("stats_videos", 0, int); self.stats_puzzles = s.value("stats_puzzles", 0, int); self._update_preview()
    def _save_settings(self):
        s = self.settings
        s.setValue("count", self.spin_count.value()); s.setValue("batch", self.spin_batch.value()); s.setValue("kind_index", self.combo_kind.currentIndex()); s.setValue("diff_min", self.spin_diff_min.value()); s.setValue("diff_max", self.spin_diff_max.value()); s.setValue("retry_failed", self.chk_retry.isChecked())
        s.setValue("solve", self.spin_solve.value()); s.setValue("fps_index", self.combo_fps.currentIndex()); s.setValue("resolution", self.combo_resolution.currentText()); s.setValue("quality", self.combo_quality.currentText()); s.setValue("theme", self.combo_theme.currentText()); s.setValue("channel", self.edit_channel.text()); s.setValue("logo_path", self.edit_logo.text())
        s.setValue("eval_bar", self.chk_eval.isChecked()); s.setValue("hide_eval_think", self.chk_hide_think.isChecked()); s.setValue("stockfish", self.edit_sf.text()); s.setValue("sfx", self.chk_sfx.isChecked()); s.setValue("music", self.edit_music.text())
        s.setValue("show_coords", self.chk_coords.isChecked()); s.setValue("show_last_move", self.chk_last_move.isChecked()); s.setValue("show_arrow", self.chk_arrow.isChecked()); s.setValue("show_safe_area", self.chk_safe_area.isChecked()); s.setValue("stats_videos", getattr(self, "stats_videos", 0)); s.setValue("stats_puzzles", getattr(self, "stats_puzzles", 0))
        s.setValue("black_to_move", self.chk_black.isChecked()); s.setValue("hero_piece", self.combo_hero.currentText())
        s.setValue("custom_light", THEMES["Custom"][0]); s.setValue("custom_dark", THEMES["Custom"][1])
        s.setValue("custom_bg_top", CUSTOM_BG_TOP.name()); s.setValue("custom_bg_bottom", CUSTOM_BG_BOTTOM.name()); s.setValue("custom_arrow", CUSTOM_ARROW.name())
        s.sync()
    def browse_music(self):
        p, _ = QFileDialog.getOpenFileName(self, "Background music", "", "Audio (*.mp3 *.wav *.m4a *.flac *.ogg);;All files (*)")
        if p: self.edit_music.setText(p); self._save_settings_later()
    def browse_logo(self):
        p, _ = QFileDialog.getOpenFileName(self, "Logo image (PNG with transparency recommended)", "", "Image (*.png *.jpg *.jpeg *.bmp);;All files (*)")
        if p: self.edit_logo.setText(p); load_logo(p); self._save_settings_later(); self._update_preview()
    def detect_stockfish(self):
        self.status_lbl.setText("Searching for Stockfish\u2026"); QApplication.processEvents()
        path = autodetect_stockfish()
        if path: self.edit_sf.setText(path); self._save_settings_later(); self.status_lbl.setText(f"\u2714 Found Stockfish: {path}")
        else: self.status_lbl.setText("\u26a0 No Stockfish found in common paths.")
    def show_hotkeys(self): HotKeysDialog(self).exec()
    def show_about(self): AboutDialog(self).exec()
    def show_history(self):
        dlg = HistoryDialog(load_manifest(), self); dlg.exec(); self._refresh_manifest_label()
    def save_preview_png(self):
        if not self.puzzles: return
        st = self.preview.st
        if st is None: st = static_state(self.puzzles[self.current_index], self.current_index, self.read_cfg(), self.chk_solution.isChecked(), flipped=self.preview_flipped)
        w, h = RESOLUTIONS.get(self.cfg.resolution, RESOLUTIONS["1080p"]); img = QImage(w, h, QImage.Format_RGB888); img.fill(0)
        p = QPainter(img); p.setRenderHint(QPainter.Antialiasing, True); p.setRenderHint(QPainter.TextAntialiasing, True); draw_frame(p, st, w, h); p.end()
        path, _ = QFileDialog.getSaveFileName(self, "Save preview frame", f"frame_{self.current_index + 1}.png", "PNG (*.png)")
        if path and img.save(path, "PNG"): self.status_lbl.setText(f"\u2714 Frame saved: {os.path.basename(path)}")
    def save_pack(self, path=None):
        if not self.puzzles: return
        if not path:
            path, _ = QFileDialog.getSaveFileName(self, "Save puzzle pack", "puzzles.json", "JSON (*.json)")
            if not path: return
        if not path.lower().endswith(".json"): path += ".json"
        if save_puzzle_pack(self.puzzles, path): self.status_lbl.setText(f"\u2714 Saved {len(self.puzzles)} puzzles to {os.path.basename(path)}")
        else: self.status_lbl.setText("Save failed.")
    def load_pack(self, path=None):
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, "Load puzzle pack", "", "JSON (*.json)")
            if not path: return
        loaded = load_puzzle_pack(path)
        if loaded is None: self.status_lbl.setText("Load failed."); return
        self.puzzles = loaded; self.preview.clear_state(); self.list_widget.blockSignals(True); self.list_widget.clear()
        for i, pz in enumerate(loaded):
            note = "  (multiple solutions)" if pz["alts"] > 1 else ""
            bar = "\u2605" * pz.get("stars", 3) + "\u2606" * (5 - pz.get("stars", 3))
            self.list_widget.addItem(f"{bar} \u00b7 {pz['label']} \u00b7 {pz['san']}{note}")
        self.list_widget.blockSignals(False); self.current_index = 0; self.set_buttons(); self._update_preview()
        self.status_lbl.setText(f"\u2714 Loaded {len(loaded)} puzzles from {os.path.basename(path)}")
    def toggle_flip(self): self.preview_flipped = not self.preview_flipped; self._update_preview()
    def step_frame(self, d):
        if not self.animating: self.anim_t = 0.0; self.animating = True; self.btn_play.setText("\u23F9 Stop")
        cfg = self.read_cfg(); total = total_duration(self.puzzles, cfg); self.anim_t += d / float(cfg.fps)
        if self.anim_t >= total: self.anim_t = total - 0.001
        if self.anim_t < 0: self.anim_t = 0.0
        self.preview.set_state(global_state_at_time(self.puzzles, cfg, self.anim_t, flipped=self.preview_flipped))
    def on_go_clicked(self):
        if self.generating: self._user_stopped = True; self.batch_left = 0; self.gen_worker.cancel_flag = True; self.status_lbl.setText("Stopping generation\u2026"); return
        if self.rendering: self.batch_left = 0; self.render_worker.cancel_flag = True; self.status_lbl.setText("Cancelling render\u2026"); return
        self.batch_left = self.spin_batch.value(); self._start_generation()
    def _start_generation(self):
        kind_sel = KIND_MENU[self.combo_kind.currentIndex()][0]; seed_txt = self.edit_seed.text().strip(); seed = int(seed_txt) if seed_txt.isdigit() else None
        self._user_stopped = False; self.generating = True; self.set_buttons(); self.progress.setRange(0, 0)
        n_total = max(1, self.spin_batch.value()); cur = n_total - max(0, self.batch_left) + 1 if n_total > 1 else 1; pre = f"Short {cur}/{n_total} \u00b7 " if n_total > 1 else ""
        self.status_lbl.setText(f"{pre}Generating puzzles\u2026")
        self.gen_worker = PuzzleWorker(self.spin_count.value(), kind_sel, seed, banned=set(self.manifest.keys()), difficulty_min=self.spin_diff_min.value(), difficulty_max=self.spin_diff_max.value(), retry_failed=self.chk_retry.isChecked(), black_to_move=self.chk_black.isChecked(), hero_piece=self.combo_hero.currentText())
        self.gen_worker.progress.connect(lambda s: self.status_lbl.setText(f"{pre}{s}")); self.gen_worker.finished_ok.connect(self.on_puzzles_ready); self.gen_worker.failed.connect(self.on_worker_error); self.gen_worker.start()
    def on_puzzles_ready(self, puzzles):
        self.generating = False; self.puzzles = puzzles; self.preview.clear_state(); self.list_widget.blockSignals(True); self.list_widget.clear()
        for i, pz in enumerate(puzzles):
            note = "  (multiple solutions)" if pz["alts"] > 1 else ""
            bar = "\u2605" * pz.get("stars", 3) + "\u2606" * (5 - pz.get("stars", 3))
            self.list_widget.addItem(f"{bar} \u00b7 {pz['label']} \u00b7 {pz['san']}{note}")
        self.list_widget.blockSignals(False); self.set_buttons()
        if not puzzles: self.progress.setRange(0, 100); self.status_lbl.setText("No puzzles generated \u2014 press again to retry."); return
        if self._user_stopped:
            self._user_stopped = False; self.batch_left = 0; self.progress.setRange(0, 100); self.list_widget.setCurrentRow(0)
            self.status_lbl.setText(f"Stopped \u2014 {len(puzzles)} puzzle(s) ready in the preview. Press the button for a fresh batch."); return
        self._start_render()
    def _start_render(self):
        cfg = copy.copy(self.read_cfg())
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        folder_name = os.path.join(OUTPUT_ROOT_DIR, f"chess_shorts_{timestamp}")
        try:
            os.makedirs(folder_name, exist_ok=True)
        except OSError as e:
            self.on_worker_error(f"Cannot create directory {folder_name}: {e}")
            return
        video_name = f"chess_shorts_{timestamp}.mp4"
        path = os.path.join(folder_name, video_name)
        self._render_path = path
        self.rendering = True; self.set_buttons(); self.progress.setRange(0, 100); self.progress.setValue(0); self._render_t0 = time.monotonic()
        n_total = max(1, self.spin_batch.value()); cur = n_total - max(0, self.batch_left) + 1 if n_total > 1 else 1; pre = f"Short {cur}/{n_total} \u00b7 " if n_total > 1 else ""
        res_txt = f" ({cfg.resolution}, {cfg.quality})"; self.status_lbl.setText(f"{pre}Rendering {path}{res_txt} \u2026")
        self.render_worker = RenderWorker(self.puzzles, path, cfg); self.render_worker.progress.connect(self.on_render_progress); self.render_worker.stage.connect(lambda s: self.status_lbl.setText(s))
        self.render_worker.done.connect(self.on_render_done); self.render_worker.cancelled.connect(self.on_render_cancelled); self.render_worker.failed.connect(self.on_worker_error); self.render_worker.start()
    def on_worker_error(self, msg):
        logger.error(f"Background worker error:\n{msg}"); self.generating = False; self.rendering = False; self.batch_left = 0; self.progress.setRange(0, 100); self.set_buttons()
        short_msg = msg.splitlines()[0] if msg else "Unknown error"; self.status_lbl.setText(f"Error: {short_msg}")
        if self.rendering:
            try:
                if self._render_path and os.path.exists(self._render_path): os.remove(self._render_path)
                folder = os.path.dirname(self._render_path)
                if os.path.exists(folder) and not os.listdir(folder): os.rmdir(folder)
            except OSError: pass
        dlg = QDialog(self); dlg.setWindowTitle("Error details"); v = QVBoxLayout(dlg); v.addWidget(QLabel(short_msg)); te = QPlainTextEdit(); te.setPlainText(msg); te.setReadOnly(True); v.addWidget(te); btn = QPushButton("Close"); btn.clicked.connect(dlg.accept); v.addWidget(btn); dlg.exec()
    def on_eval_toggled(self, on):
        self._update_preview()
        if on and self.edit_sf.text().strip() and self.puzzles and not self.generating and not self.rendering:
            if self.eval_worker is not None and self.eval_worker.isRunning(): return
            cfg = copy.copy(self.read_cfg()); self.eval_worker = EvalWorker(self.puzzles, cfg)
            self.eval_worker.progress.connect(lambda s: self.status_lbl.setText(s)); self.eval_worker.done.connect(self.on_evals_done); self.eval_worker.failed.connect(self.on_worker_error); self.eval_worker.start(); self.status_lbl.setText("Recomputing evals with Stockfish\u2026")
    def on_evals_done(self, used_sf):
        self.status_lbl.setText("Evals updated with Stockfish." if used_sf else "Built-in evals in use (Stockfish unavailable)."); self._update_preview()
    def on_list_select(self, row):
        if row < 0 or not self.puzzles: return
        self.stop_anim(); self.current_index = row; self._update_preview()
    def step_preview(self, d):
        if not self.puzzles: return
        self.stop_anim(); self.list_widget.setCurrentRow((self.current_index + d) % len(self.puzzles))
    def _update_preview(self):
        if not self.puzzles: self.preview.clear_state(); return
        i = max(0, min(self.current_index, len(self.puzzles) - 1)); self.current_index = i
        self.preview.set_state(static_state(self.puzzles[i], i, self.read_cfg(), self.chk_solution.isChecked(), flipped=self.preview_flipped))
    def toggle_play(self):
        if self.animating: self.stop_anim(); return
        if not self.puzzles: return
        self.animating = True; self.btn_play.setText("\u23F9 Stop"); self.anim_t = 0.0; self.anim_timer.start()
    def stop_anim(self):
        if not self.animating: return
        self.animating = False; self.anim_timer.stop(); self.btn_play.setText("\u25B6 Play"); self._update_preview()
    def anim_tick(self):
        cfg = self.read_cfg(); total = total_duration(self.puzzles, cfg); self.anim_t += self.anim_timer.interval() / 1000.0 * self.preview_speed
        if self.anim_t >= total:
            if self.chk_loop.isChecked(): self.anim_t = 0.0
            else: self.stop_anim(); return
        self.preview.set_state(global_state_at_time(self.puzzles, cfg, self.anim_t, flipped=self.preview_flipped))
    def _space_pressed(self):
        fw = QApplication.focusWidget()
        if isinstance(fw, (QLineEdit, QSpinBox, QComboBox)): return
        if self.puzzles and not self.generating and not self.rendering: self.toggle_play()
    def on_render_progress(self, i, n):
        self.progress.setValue(int(100 * i / max(1, n))); now = time.monotonic()
        if i <= 1: self._render_t0 = now
        el = now - self._render_t0
        if i > 3 and el > 0.4: eta = el / (i - 1) * (n - i); fps_now = (i - 1) / el; self.status_lbl.setText(f"Rendering {os.path.basename(self._render_path)} \u2026 {i}/{n} \u00b7 {fps_now:.1f} fps \u00b7 ETA {eta:.0f}s")
    def on_render_done(self, path):
        self.rendering = False; self.set_buttons(); self.progress.setValue(100); new, ok = self._commit_manifest(path)
        try: mb = os.path.getsize(path) / 1e6
        except OSError: mb = 0
        self._last_video_dir = os.path.dirname(os.path.abspath(path)) or os.getcwd(); self.btn_folder.setEnabled(True)
        self._last_video_path = path; self.btn_play_vid.setEnabled(True)
        msg = f"\u2714 Saved {os.path.basename(path)} ({mb:.1f} MB)"
        if new: msg += f" \u00b7 history +{new}"
        if not ok: msg += " (warning: could not write manifest!)"
        self.stats_videos = getattr(self, "stats_videos", 0) + 1; self.stats_puzzles = getattr(self, "stats_puzzles", 0) + len(self.puzzles); self._save_settings()
        self.batch_left = max(0, self.batch_left - 1)
        if self.batch_left > 0: self.status_lbl.setText(f"{msg} \u2014 starting next Short\u2026"); self._start_generation()
        else: self.status_lbl.setText(msg + f"   (lifetime: {self.stats_videos} videos, {self.stats_puzzles} puzzles)   \u2013 press \u2728 for a title + hashtags")
    def on_render_cancelled(self):
        self.rendering = False; self.set_buttons(); self.progress.setRange(0, 100); self.status_lbl.setText("Render cancelled.")
        try:
            if self._render_path and os.path.exists(self._render_path): os.remove(self._render_path)
            folder = os.path.dirname(self._render_path)
            if os.path.exists(folder) and not os.listdir(folder): os.rmdir(folder)
        except OSError: pass
    def copy_title(self):
        if not self.puzzles: return
        title, tags = suggest_title(self.puzzles); QApplication.clipboard().setText(f"{title}\n\n{tags}"); self.status_lbl.setText(f"\u2713 Copied: {title}")
    def show_in_folder(self): QDesktopServices.openUrl(QUrl.fromLocalFile(self._last_video_dir or os.getcwd()))
    def play_video(self):
        if self._last_video_path and os.path.exists(self._last_video_path): QDesktopServices.openUrl(QUrl.fromLocalFile(self._last_video_path))
    def export_pgn(self):
        if not self.puzzles: return
        path, _ = QFileDialog.getSaveFileName(self, "Export puzzles", "puzzles.pgn", "PGN (*.pgn)")
        if not path: return
        if not path.lower().endswith(".pgn"): path += ".pgn"
        try:
            with open(path, "w", encoding="utf-8") as f:
                for pz in self.puzzles:
                    g = chess.pgn.Game.from_board(chess.Board(pz["fen"])); g.headers["Event"] = pz["label"]; g.headers["Site"] = "Chess Shorts Studio"
                    node = g
                    for mv in pz["line"]: node = node.add_variation(mv)
                    g.comment = f"{pz['label']} \u2014 {pz['san']}"; print(g, file=f, end="\n\n")
            self.status_lbl.setText(f"\u2714 Exported {len(self.puzzles)} puzzles to {os.path.basename(path)}")
        except Exception as e: logger.error(f"Export failed: {e}"); self.status_lbl.setText(f"Export failed: {e}")
    def _commit_manifest(self, video_path):
        stamp = time.strftime("%Y-%m-%d %H:%M"); new = 0
        for pz in self.puzzles:
            key = position_key(pz["fen"])
            if key not in self.manifest: new += 1
            self.manifest[key] = {"kind": pz["kind"], "label": pz["label"], "san": pz["san"], "fen": pz["fen"], "video": os.path.basename(video_path), "rendered": stamp}
        ok = save_manifest(self.manifest); self._refresh_manifest_label(); return new, ok
    def _refresh_manifest_label(self):
        n = len(self.manifest); self.lbl_manifest.setText(f"{n} puzzle{'s' if n != 1 else ''} already used \u2014 they won't be generated again.\nFile: {MANIFEST_PATH}")
    def clear_manifest(self):
        if not self.manifest: return
        ret = QMessageBox.question(self, "Clear history", "Forget all previously used puzzles?\n\nThe same positions may be generated and rendered again.", QMessageBox.Yes | QMessageBox.No)
        if ret != QMessageBox.Yes: return
        self.manifest = {}; save_manifest(self.manifest); self._refresh_manifest_label(); self.status_lbl.setText("History cleared \u2014 all puzzles available again.")
    def closeEvent(self, ev):
        self._save_settings(); self.anim_timer.stop()
        for w in (self.gen_worker, self.render_worker, self.eval_worker):
            if w is not None and w.isRunning():
                if hasattr(w, "cancel_flag"): w.cancel_flag = True
        for w in (self.gen_worker, self.render_worker, self.eval_worker):
            if w is not None and w.isRunning(): w.wait(3000)
        ev.accept()

# ----------------------------- app bootstrap --------------------------------

def apply_dark_palette(app):
    pal = app.palette()
    pal.setColor(QPalette.Window, QColor(24, 26, 38)); pal.setColor(QPalette.WindowText, QColor(230, 230, 240)); pal.setColor(QPalette.Base, QColor(30, 33, 48)); pal.setColor(QPalette.AlternateBase, QColor(38, 41, 60))
    pal.setColor(QPalette.Text, QColor(230, 230, 240)); pal.setColor(QPalette.Button, QColor(38, 41, 60)); pal.setColor(QPalette.ButtonText, QColor(230, 230, 240)); pal.setColor(QPalette.Highlight, QColor(103, 58, 183)); pal.setColor(QPalette.HighlightedText, QColor(255, 255, 255)); pal.setColor(QPalette.PlaceholderText, QColor(150, 150, 165))
    app.setPalette(pal)

def main():
    if not os.path.exists(OUTPUT_ROOT_DIR):
        try: os.makedirs(OUTPUT_ROOT_DIR)
        except OSError: pass
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', handlers=[logging.FileHandler("chess_shorts_studio.log", mode='w', encoding='utf-8'), logging.StreamHandler(sys.stderr)])
    logger.info("Application starting...")
    app = QApplication(sys.argv); app.setStyle("Fusion"); apply_dark_palette(app); resolve_fonts()
    def _hook(t, v, tb): msg = "".join(traceback.format_exception(t, v, tb)); logger.critical("Unhandled exception:\n%s", msg)
    sys.excepthook = _hook
    win = MainWindow(); win.show(); sys.exit(app.exec())

if __name__ == "__main__":
    main()