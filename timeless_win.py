"""Окно прайс-чека Timeless Jewel: появляется у курсора, когда скопирован таймлесс.

Показывает сид и завоевателя, ищет тот же сид на официальном трейде (у любого завоевателя
серии или только у своего), выводит самые дешёвые лоты, минимум и медиану.
Кнопки открывают тот же поиск в браузере и калькулятор Vilsol с этим сидом.
"""

from __future__ import annotations

import threading
import tkinter as tk
import webbrowser
from datetime import datetime, timezone

from poecraft import timeless as tl
from poecraft import fonts as _fonts

BG = "#14110d"
BG2 = "#1f1a14"
ROW = "#1a1611"
FG = "#d9d0c1"
MUTED = "#8a7f70"
DIM = "#5a5248"
GOLD = "#e3b55b"
GOOD = "#7ec27a"
WARN = "#e07a5f"
LINE = "#3a3127"
UNIQUE = ("#2a1a0e", "#c87c3c")
FONT = _fonts.UI
TFONT = _fonts.TITLE
WIDTH = 440


def _ago(iso: str) -> str:
    try:
        t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        d = (datetime.now(timezone.utc) - t).total_seconds()
    except Exception:
        return ""
    if d < 3600:
        return f"{int(d // 60)} мин"
    if d < 86400:
        return f"{int(d // 3600)} ч"
    return f"{int(d // 86400)} дн"


class TimelessWindow(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.withdraw()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", app.settings.get("alpha", 0.95))
        self.configure(bg=BG, highlightthickness=1, highlightbackground=UNIQUE[1])
        self.bind("<Escape>", lambda e: self.hide())
        self.jewel: tl.TimelessJewel | None = None
        self.any_conq = app.settings.get("timeless_any_conqueror", True)
        self.result: tl.Result | None = None
        self.busy = False
        self._req = 0
        self._drag = None
        self._prices = None
        self._league = None

    # ------------------------------------------------------------ данные
    @property
    def prices(self):
        if self._prices is None:
            main = getattr(self.app, "main_win", None)
            self._prices = getattr(main, "prices", None)
            if self._prices is None:
                from poecraft.prices import Prices
                self._prices = Prices()
        return self._prices

    def _resolve_league(self) -> str:
        """Лига для трейда: из настроек, иначе текущая лига poe.ninja, сверенная с трейдом."""
        want = self.app.settings.get("timeless_league", "")
        if want:
            return want
        if self._league:
            return self._league
        self.prices.refresh()
        league = self.prices.league if self.prices.league not in ("?", "") else ""
        try:
            leagues = tl.trade_leagues()
            if league not in leagues:
                bad = ("Standard", "Hardcore", "SSF", "HC", "Ruthless")
                league = next((l for l in leagues if not any(b in l for b in bad)), "Standard")
        except tl.TradeError:
            league = league or "Standard"
        self._league = league
        return league

    def _lang(self) -> str:
        lang = self.app.settings.get("game_lang", "auto")
        if lang == "auto":
            from poecraft import i18n
            lang = "ru" if i18n.lang() == "ru" else "en"
        return lang

    # ------------------------------------------------------------ поток
    def check(self, jewel: tl.TimelessJewel):
        self.jewel = jewel
        self.result = None
        self._search()

    def _search(self):
        self._req += 1
        req = self._req
        self.busy = True
        self._render(loading=True)
        any_conq = self.any_conq or not self.jewel.conqueror_known
        threading.Thread(target=self._work, args=(req, self.jewel, any_conq), daemon=True).start()

    def _work(self, req, jewel, any_conq):
        try:
            league = self._resolve_league()
            res = tl.search(jewel, league, any_conq, count=20,
                            status=self.app.settings.get("timeless_status", "online"))
            out = ("ok", res)
        except tl.TradeError as e:
            out = ("err", str(e))
        except Exception as e:
            out = ("err", f"Ошибка: {e}")
        self.after(0, lambda: self._done(req, out))

    def _done(self, req, out):
        if req != self._req or not self.winfo_exists():
            return
        self.busy = False
        if out[0] == "ok":
            self.result = out[1]
            self._render()
        else:
            self._render(error=out[1])

    def _set_mode(self, any_conq: bool):
        if any_conq == self.any_conq or self.busy:
            return
        self.any_conq = any_conq
        self.app.settings["timeless_any_conqueror"] = any_conq
        self.app.save_settings(self.app.settings)
        self._search()

    # ------------------------------------------------------------ отрисовка
    def _lbl(self, parent, text, fg=FG, size=10, bold=False, bg=None, **kw):
        return tk.Label(parent, text=text, fg=fg, bg=bg or parent["bg"],
                        font=(FONT, size, "bold") if bold else (FONT, size), **kw)

    def _button(self, parent, text, cmd, active=False):
        b = tk.Label(parent, text=text, font=(FONT, 9), padx=9, pady=3, cursor="hand2",
                     fg=BG if active else FG, bg=GOLD if active else BG2,
                     highlightthickness=1, highlightbackground=GOLD if active else LINE)
        b.bind("<Button-1>", lambda e: cmd())
        if not active:
            b.bind("<Enter>", lambda e: b.configure(fg=GOLD))
            b.bind("<Leave>", lambda e: b.configure(fg=FG))
        return b

    def _render(self, loading=False, error=None):
        for w in self.winfo_children():
            w.destroy()
        j = self.jewel
        hb, hf = UNIQUE
        head = tk.Frame(self, bg=hb)
        head.pack(fill="x")
        txt = tk.Frame(head, bg=hb)
        txt.pack(side="left", fill="x", expand=True, padx=10, pady=5)
        t1 = self._lbl(txt, j.jewel, hf, 13, anchor="w")
        t1.configure(font=(TFONT, 13))
        t1.pack(fill="x")
        sub = f"сид {j.seed} · {j.conqueror}" + (" · осквернён" if j.corrupted else "")
        t2 = self._lbl(txt, sub, FG, 9, anchor="w")
        t2.pack(fill="x")
        close = self._lbl(head, "✕", MUTED, 10, cursor="hand2", padx=8)
        close.pack(side="right", anchor="n", pady=5)
        close.bind("<Button-1>", lambda e: self.hide())
        for w in (head, txt, t1, t2):
            w.bind("<ButtonPress-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)
        tk.Frame(self, bg=LINE, height=1).pack(fill="x")

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=10, pady=8)
        for ex in j.extra:
            self._lbl(body, ex, MUTED, 9, anchor="w").pack(fill="x")

        modes = tk.Frame(body, bg=BG)
        modes.pack(fill="x", pady=(2, 8))
        any_now = self.any_conq or not j.conqueror_known
        self._button(modes, "Любой завоеватель", lambda: self._set_mode(True), any_now).pack(side="left")
        if j.conqueror_known:
            self._button(modes, f"Только {j.conqueror}", lambda: self._set_mode(False),
                         not self.any_conq).pack(side="left", padx=(6, 0))

        if loading:
            self._lbl(body, "Ищу этот сид на трейде…", MUTED, 10, anchor="w").pack(fill="x", pady=4)
        elif error:
            self._lbl(body, error, WARN, 10, anchor="w", justify="left",
                      wraplength=WIDTH - 30).pack(fill="x", pady=4)
            self._lbl(body, "Поиск можно открыть в браузере кнопкой «Трейд ↗».", MUTED, 9,
                      anchor="w").pack(fill="x")
        elif self.result:
            self._render_result(body)

        foot = tk.Frame(body, bg=BG)
        foot.pack(fill="x", pady=(10, 0))
        self._button(foot, "Калькулятор Vilsol ↗", lambda: webbrowser.open(j.vilsol_url())).pack(side="right")
        if not loading:
            self._button(foot, "Трейд ↗", self._open_trade).pack(side="right", padx=(0, 6))
        info = []
        if self.result:
            info.append(self.result.league)
        if self.prices.divine:
            info.append(f"1 div ≈ {self.prices.divine:.0f}c")
        self._lbl(foot, " · ".join(info), DIM, 8, anchor="w").pack(side="left")
        self._place()

    def _chaos_str(self, v: float) -> str:
        d = self.prices.divine
        return f"{v / d:.1f} div" if d and v >= d else f"{v:.0f}c"

    def _render_result(self, body):
        res, j = self.result, self.jewel
        d = self.prices.divine
        s = tl.summary(res.listings, d)
        line = f"Найдено: {res.total}"
        if s:
            line += f"     мин {self._chaos_str(s[0])}     медиана {self._chaos_str(s[1])}"
        self._lbl(body, line, GOOD if res.listings else MUTED, 10, True, anchor="w").pack(fill="x")
        if not res.listings:
            tip = ("Своего завоевателя никто не продаёт — посмотри «Любой завоеватель»."
                   if not self.any_conq else
                   "Этот сид никто не продаёт. Ценность смотри по нодам в калькуляторе Vilsol.")
            self._lbl(body, tip, MUTED, 9, anchor="w", justify="left",
                      wraplength=WIDTH - 30).pack(fill="x", pady=(4, 0))
            return
        tbl = tk.Frame(body, bg=BG)
        tbl.pack(fill="x", pady=(6, 0))
        for i, l in enumerate(res.listings):
            bg = ROW if i % 2 == 0 else BG
            price = l.price_text()
            ch = tl.to_chaos(l, d)
            if l.currency == "divine" and ch:
                price += f"  ({ch:.0f}c)"
            cells = [(price, 16, FG),
                     (l.conqueror + (" ⚠" if l.corrupted else ""), 10, GOLD if l.conqueror == j.conqueror else MUTED),
                     (_ago(l.indexed), 7, DIM),
                     (("● " if l.online else "○ ") + l.seller[:16], 18, GOOD if l.online else DIM)]
            for c, (text, w, fg) in enumerate(cells):
                tk.Label(tbl, text=text, width=w, anchor="w", fg=fg, bg=bg,
                         font=(FONT, 9)).grid(row=i, column=c, sticky="we")

    def _open_trade(self):
        """Поиск в браузере. Работает и тогда, когда запрос программы не прошёл."""
        if self.result:
            league, query = self.result.league, self.result.query
        else:
            league = (self.app.settings.get("timeless_league") or self._league
                      or (self.prices.league if self.prices.league not in ("?", "") else "Standard"))
            query = tl.build_query(self.jewel, self.any_conq or not self.jewel.conqueror_known,
                                   self.app.settings.get("timeless_status", "online"))
        webbrowser.open(tl.trade_url(league, query, self._lang()))

    # ------------------------------------------------------------ окно
    def _place(self):
        first = self.state() == "withdrawn"
        self.update_idletasks()
        if first:
            w, h = WIDTH, self.winfo_reqheight()
            px, py = self.winfo_pointerxy()
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            x = px - w - 24 if px > sw // 2 else px + 24
            y = min(max(0, py - 60), max(0, sh - h - 40))
            self.geometry(f"{w}x{h}+{max(0, x)}+{y}")
            self.deiconify()
        else:
            self.geometry(f"{WIDTH}x{self.winfo_reqheight()}")
        self.lift()
        self.attributes("-topmost", True)

    def _drag_start(self, e):
        self._drag = (e.x_root - self.winfo_x(), e.y_root - self.winfo_y())

    def _drag_move(self, e):
        if self._drag:
            self.geometry(f"+{e.x_root - self._drag[0]}+{e.y_root - self._drag[1]}")

    def hide(self):
        self._req += 1
        self.busy = False
        self.withdraw()
