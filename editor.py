"""Окно редактора крафта: выбираешь базу и нужные моды мышкой, без JSON."""

from __future__ import annotations

import re
import tkinter as tk
from collections import defaultdict
from tkinter import ttk

from poecraft.pool import ModPool
from poecraft.recipes import CLASS_RU, CRAFT_CLASSES, recipe_from_dict

BG, BG2, FG, MUTED, GOLD, GOOD, WARN = "#14110d", "#1f1a14", "#d9d0c1", "#8a7f70", "#e3b55b", "#7ec27a", "#e07a5f"
FONT = "Segoe UI"
NUM_RE = re.compile(r"\(?[-+]?\d+(?:\.\d+)?(?:-\d+(?:\.\d+)?)?\)?")


def text_to_pattern(text: str) -> str:
    """'+(130-144) to maximum Life' -> 'to maximum Life' (для крафтовых модов без type)."""
    first = text.split("\n")[0]
    parts = [p.strip(" +%") for p in NUM_RE.split(first)]
    parts = [re.escape(p) for p in parts if p]
    return ".*".join(parts)


def mod_label(text: str) -> str:
    first = text.split("\n")[0]
    s = NUM_RE.sub("#", first).replace("+#", "#")
    return s + (" (+гибрид)" if "\n" in text else "")


class RecipeEditor(tk.Toplevel):
    def __init__(self, master, data, on_save, recipe: dict | None = None):
        super().__init__(master)
        self.data, self.on_save = data, on_save
        self.title("Редактор крафта")
        self.configure(bg=BG)
        self.attributes("-topmost", True)
        # открываем рядом с панелью, чтобы не перекрывать её
        mx, my = master.winfo_x(), master.winfo_y()
        sw = master.winfo_screenwidth()
        x = mx + master.winfo_width() + 10
        if x + 820 > sw:
            x = max(0, mx - 830)
        self.geometry(f"820x560+{x}+{max(0, my)}")
        self.minsize(760, 500)
        self.groups: list[dict] = []      # доступные моды выбранной базы
        self.wanted: list[dict] = []      # выбранные
        self._build()
        self._fill(recipe)
        self.lift()
        self.focus_force()
        self.grab_set()

    # ------------------------------------------------------------ виджеты
    def _lbl(self, parent, text, **kw):
        return tk.Label(parent, text=text, bg=BG, fg=kw.pop("fg", MUTED), font=(FONT, 9), **kw)

    def _entry(self, parent, var, width=30):
        return tk.Entry(parent, textvariable=var, bg=BG2, fg=FG, insertbackground=FG,
                        relief="flat", font=(FONT, 10), width=width)

    def _button(self, parent, text, cmd, fg=FG):
        return tk.Button(parent, text=text, command=cmd, bg=BG2, fg=fg, activebackground="#3a3127",
                         activeforeground=GOLD, relief="flat", font=(FONT, 9), padx=10, pady=3)

    def _listbox(self, parent):
        frame = tk.Frame(parent, bg=BG)
        lb = tk.Listbox(frame, bg=BG2, fg=FG, selectbackground="#3a3127", selectforeground=GOLD,
                        relief="flat", font=(FONT, 9), activestyle="none", highlightthickness=0)
        sb = tk.Scrollbar(frame, command=lb.yview)
        lb.configure(yscrollcommand=sb.set)
        lb.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        return frame, lb

    def _build(self):
        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=12, pady=(12, 6))
        self.name_var, self.author_var = tk.StringVar(), tk.StringVar()
        self._lbl(top, "Название:").grid(row=0, column=0, sticky="w")
        self._entry(top, self.name_var, 40).grid(row=0, column=1, sticky="we", padx=6)
        self._lbl(top, "Автор:").grid(row=0, column=2, sticky="w")
        self._entry(top, self.author_var, 18).grid(row=0, column=3, sticky="we", padx=6)
        self._lbl(top, "Описание:").grid(row=1, column=0, sticky="nw", pady=(6, 0))
        self.desc = tk.Text(top, height=2, bg=BG2, fg=FG, insertbackground=FG, relief="flat",
                            font=(FONT, 9), wrap="word")
        self.desc.grid(row=1, column=1, columnspan=3, sticky="we", padx=6, pady=(6, 0))
        top.columnconfigure(1, weight=1)

        row = tk.Frame(self, bg=BG)
        row.pack(fill="x", padx=12, pady=6)
        self._lbl(row, "Тип предмета:").pack(side="left")
        self.class_box = ttk.Combobox(row, state="readonly", width=20, style="G.TCombobox",
                                      values=[CLASS_RU.get(c, c) for c in CRAFT_CLASSES])
        from mainwin import popdown_on_top
        popdown_on_top(self.class_box)
        self.class_box.pack(side="left", padx=6)
        self.class_box.bind("<<ComboboxSelected>>", lambda e: self._class_changed())
        self._lbl(row, "База:").pack(side="left", padx=(10, 0))
        self.base_box = ttk.Combobox(row, state="readonly", width=28, style="G.TCombobox")
        popdown_on_top(self.base_box)
        self.base_box.pack(side="left", padx=6)
        self.base_box.bind("<<ComboboxSelected>>", lambda e: self._refresh_mods())
        self._lbl(row, "ilvl:").pack(side="left", padx=(10, 0))
        self.ilvl_var = tk.IntVar(value=86)
        sp = tk.Spinbox(row, from_=1, to=100, textvariable=self.ilvl_var, width=4, bg=BG2, fg=FG,
                        relief="flat", buttonbackground=BG2, command=self._refresh_mods)
        sp.pack(side="left")
        sp.bind("<Return>", lambda e: self._refresh_mods())

        mid = tk.Frame(self, bg=BG)
        mid.pack(fill="both", expand=True, padx=12, pady=6)
        left = tk.Frame(mid, bg=BG)
        left.pack(side="left", fill="both", expand=True)
        right = tk.Frame(mid, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(10, 0))

        srow = tk.Frame(left, bg=BG)
        srow.pack(fill="x")
        self._lbl(srow, "Моды базы  (П — префикс, С — суффикс). Поиск:").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self._render_mods())
        self._entry(srow, self.search_var, 18).pack(side="left", padx=6, fill="x", expand=True)
        f, self.mods_lb = self._listbox(left)
        f.pack(fill="both", expand=True, pady=4)
        self.mods_lb.bind("<Double-Button-1>", lambda e: self._add())
        self._button(left, "Добавить  →", self._add, GOLD).pack(anchor="e")

        self._lbl(right, "Нужные моды  (двойной клик в левом списке — добавить)").pack(anchor="w")
        f, self.want_lb = self._listbox(right)
        f.pack(fill="both", expand=True, pady=4)
        self.want_lb.bind("<<ListboxSelect>>", lambda e: self._want_selected())
        trow = tk.Frame(right, bg=BG)
        trow.pack(fill="x")
        self._lbl(trow, "Минимальный тир (1 = лучший):").pack(side="left")
        self.tier_var = tk.IntVar(value=3)
        tsp = tk.Spinbox(trow, from_=1, to=30, textvariable=self.tier_var, width=4, bg=BG2, fg=FG,
                         relief="flat", buttonbackground=BG2, command=self._tier_changed)
        tsp.pack(side="left", padx=6)
        tsp.bind("<Return>", lambda e: self._tier_changed())
        self._button(trow, "Убрать", self._remove, WARN).pack(side="right")

        bottom = tk.Frame(self, bg=BG)
        bottom.pack(fill="x", padx=12, pady=(6, 12))
        self.err = self._lbl(bottom, "", fg=WARN)
        self.err.pack(side="left")
        self._button(bottom, "Отмена", self.destroy).pack(side="right")
        self._button(bottom, "Сохранить", self._save, GOOD).pack(side="right", padx=6)

    # ------------------------------------------------------------ данные
    def _fill(self, r):
        r = r or {}
        self.name_var.set(r.get("name", ""))
        self.author_var.set(r.get("author", ""))
        self.desc.insert("1.0", r.get("description", ""))
        if r.get("min_ilvl"):
            self.ilvl_var.set(r["min_ilvl"])
        cls = r.get("base_class") or "Belt"
        self.class_box.current(CRAFT_CLASSES.index(cls) if cls in CRAFT_CLASSES else 0)
        self._class_changed(prefer=r.get("base"))
        self.wanted = [dict(w) for w in r.get("wanted", [])]
        self._render_wanted()

    def current_class(self):
        i = self.class_box.current()
        return CRAFT_CLASSES[i] if i >= 0 else "Belt"

    def _class_changed(self, prefer=None):
        cls = self.current_class()
        bases = [b for b in self.data.bases.values() if b.item_class == cls
                 and b.domain in ("item", "flask", "abyss_jewel", "misc")]
        bases.sort(key=lambda b: b.name)
        self.bases = bases
        self.base_box["values"] = [b.name for b in bases]
        names = [b.name for b in bases]
        if bases:
            self.base_box.current(names.index(prefer) if prefer in names else 0)
        self._refresh_mods()

    def current_base(self):
        i = self.base_box.current()
        return self.bases[i] if 0 <= i < len(self.bases) else None

    def _refresh_mods(self):
        base = self.current_base()
        if not base:
            self.groups = []
            self._render_mods()
            return
        try:
            ilvl = int(self.ilvl_var.get())
        except (tk.TclError, ValueError):
            ilvl = 86
        pool = ModPool(self.data, base, ilvl)
        by = defaultdict(list)
        for e in pool.available:
            by[(e.mod.kind, e.mod.type)].append(e)
        groups = []
        for (kind, mtype), es in by.items():
            best = min(es, key=lambda e: e.tier)
            groups.append({
                "kind": kind, "mod_type": mtype, "text": best.mod.text,
                "label": mod_label(best.mod.text), "tiers": len(es), "best_tier": best.tier,
                "weight": sum(e.weight for e in es),
            })
        groups.sort(key=lambda g: (g["kind"] != "prefix", g["label"].lower()))
        self.groups = groups
        self._render_mods()

    def _render_mods(self):
        q = self.search_var.get().lower().strip()
        self.shown = [g for g in self.groups if not q or q in g["text"].lower()]
        self.mods_lb.delete(0, "end")
        for g in self.shown:
            k = "П" if g["kind"] == "prefix" else "С"
            self.mods_lb.insert("end", f"{k}  {g['label']}   [{g['tiers']} т.]")

    def _render_wanted(self):
        self.want_lb.delete(0, "end")
        for w in self.wanted:
            k = {"prefix": "П", "suffix": "С"}.get(w.get("kind", ""), "·")
            self.want_lb.insert("end", f"{k}  {w['label']}   — тир ≤ {w['max_tier']}")

    # ------------------------------------------------------------ действия
    def _add(self):
        sel = self.mods_lb.curselection()
        if not sel:
            return
        g = self.shown[sel[0]]
        if any(w.get("mod_type") == g["mod_type"] and w.get("kind") == g["kind"] for w in self.wanted):
            return
        self.wanted.append({
            "label": g["label"], "mod_type": g["mod_type"], "kind": g["kind"],
            "pattern": text_to_pattern(g["text"]), "max_tier": min(3, g["tiers"]),
        })
        self._render_wanted()
        self.want_lb.selection_clear(0, "end")
        self.want_lb.selection_set("end")
        self._want_selected()

    def _remove(self):
        sel = self.want_lb.curselection()
        if sel:
            del self.wanted[sel[0]]
            self._render_wanted()

    def _want_selected(self):
        sel = self.want_lb.curselection()
        if sel:
            self.tier_var.set(self.wanted[sel[0]]["max_tier"])

    def _tier_changed(self):
        sel = self.want_lb.curselection()
        if not sel:
            return
        try:
            self.wanted[sel[0]]["max_tier"] = max(1, int(self.tier_var.get()))
        except (tk.TclError, ValueError):
            return
        i = sel[0]
        self._render_wanted()
        self.want_lb.selection_set(i)

    def _save(self):
        base = self.current_base()
        r = {
            "name": self.name_var.get().strip(),
            "author": self.author_var.get().strip(),
            "description": self.desc.get("1.0", "end").strip(),
            "base_class": self.current_class(),
            "base": base.name if base else None,
            "min_ilvl": self.ilvl_var.get(),
            "wanted": self.wanted,
        }
        try:
            r = recipe_from_dict(r)
        except ValueError as e:
            self.err.configure(text=str(e))
            return
        self.on_save(r)
        self.destroy()
