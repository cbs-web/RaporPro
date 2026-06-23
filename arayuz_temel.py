# Dosya: RaporPro/arayuz_temel.py
import datetime
import threading
import tkinter as tk
from tkinter import ttk

from sabitler import *


class ArayuzTemelMixin:
    def setup_styles(self):
        self.bootstrap_theme_active = False
        self.bootstrap_theme_name = "classic"
        self._bootstrap_module = None
        try:
            import ttkbootstrap as tb
            self._bootstrap_module = tb
            try:
                style = tb.Style(theme="flatly")
            except TypeError:
                style = tb.Style(themename="flatly")
            self.bootstrap_theme_active = True
            self.bootstrap_theme_name = "flatly"
        except Exception:
            style = ttk.Style()
            try:
                style.theme_use('clam')
            except Exception:
                pass
        style.configure("TFrame", background=COLOR_BG)
        style.configure("TLabelframe", background=COLOR_BG, relief="solid", borderwidth=1)
        style.configure("TLabelframe.Label", font=FONT_HEADER, background=COLOR_BG, foreground=COLOR_PRIMARY)
        style.configure("TLabel", background=COLOR_BG, font=FONT_MAIN, foreground="#333333")
        style.configure("TButton", font=FONT_MAIN, padding=6)
        style.configure("TEntry", font=FONT_MAIN, padding=5)
        style.configure("TNotebook", background=COLOR_BG, borderwidth=0)
        style.configure("TNotebook.Tab", font=FONT_BOLD, padding=(12, 7))
        style.configure("Treeview", rowheight=26, font=FONT_MAIN)
        style.configure("Treeview.Heading", font=FONT_BOLD)
        style.configure("TCombobox", font=FONT_MAIN, padding=4)
        style.configure("Valid.TEntry", fieldbackground="#FFFFFF")
        style.configure("Warning.TEntry", fieldbackground="#FCF3CF")
        style.configure("Invalid.TEntry", fieldbackground="#FADBD8")

    def _role_from_color(self, color, default="neutral"):
        color = str(color or "").lower()
        role_map = {
            COLOR_PRIMARY.lower(): "primary",
            COLOR_ACCENT.lower(): "accent",
            COLOR_SUCCESS.lower(): "success",
            COLOR_WARNING.lower(): "warning",
            COLOR_DANGER.lower(): "danger",
            "#2e86c1": "primary",
            "#1e8449": "success",
            "#148f77": "success",
            "#117864": "success",
            "#5dade2": "accent",
            "#f5b041": "warning",
            "#f9e79f": "warning",
            "#fad7a0": "warning",
            "#d6eaf8": "accent",
            "#d5f5e3": "success",
            "#fadbd8": "warning",
        }
        return role_map.get(color, default)

    def _button_bootstyle(self, role="neutral", outline=False):
        role_map = {
            "primary": "primary",
            "success": "success",
            "warning": "warning",
            "danger": "danger",
            "accent": "info",
            "info": "info",
            "neutral": "secondary",
            "secondary": "secondary",
        }
        style = role_map.get(role, "secondary")
        return f"{style}-outline" if outline else style

    def modern_button(self, parent, text, command=None, role="neutral", outline=False, **kwargs):
        if getattr(self, "bootstrap_theme_active", False) and self._bootstrap_module is not None:
            tb_kwargs = {"text": text, "command": command, "bootstyle": self._button_bootstyle(role, outline)}
            for key in ("width", "state", "takefocus"):
                if key in kwargs:
                    tb_kwargs[key] = kwargs[key]
            padx = kwargs.get("padx", 10)
            pady = kwargs.get("pady", 5)
            tb_kwargs.setdefault("padding", (padx, pady))
            try:
                return self._bootstrap_module.Button(parent, **tb_kwargs)
            except Exception:
                pass
        palette = {
            "primary": (COLOR_PRIMARY, "white"),
            "success": (COLOR_SUCCESS, "white"),
            "warning": (COLOR_WARNING, "white"),
            "danger": (COLOR_DANGER, "white"),
            "accent": (COLOR_ACCENT, "white"),
            "neutral": ("#ECF0F1", "#111111"),
            "secondary": ("#ECF0F1", "#111111"),
        }
        bg, fg = palette.get(role, palette["neutral"])
        kwargs.setdefault("bg", bg)
        kwargs.setdefault("fg", fg)
        kwargs.setdefault("font", FONT_BOLD)
        kwargs.setdefault("relief", "flat")
        return tk.Button(parent, text=text, command=command, **kwargs)

    def set_status(self, msg, level="info"):
        if getattr(self, "_closing", False):
            return
        if threading.current_thread() is not threading.main_thread():
            try:
                self.root.after(0, lambda m=msg, l=level: self.set_status(m, l))
            except Exception:
                pass
            return
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        color_tag = "normal"
        if level == "error": color_tag = "error"
        elif level == "warning": color_tag = "warning"
        elif level == "success": color_tag = "success"
        self.log_text.config(state="normal")
        self.log_text.insert("end", f"> [{timestamp}] {msg}\n", color_tag)
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def set_save_indicator(self, text, level="info"):
        if getattr(self, "_closing", False):
            return
        if threading.current_thread() is not threading.main_thread():
            try:
                self.root.after(0, lambda: self.set_save_indicator(text, level))
            except Exception:
                pass
            return
        if hasattr(self, "autosave_status_var"):
            self.autosave_status_var.set(text)
        if hasattr(self, "autosave_status_label"):
            color = {
                "success": COLOR_SUCCESS,
                "warning": COLOR_WARNING,
                "error": COLOR_DANGER,
            }.get(level, "#333333")
            self.autosave_status_label.config(fg=color)

    def _geometry_parcala(self, geometry):
        if not geometry:
            return None
        try:
            size = str(geometry).split("+", 1)[0].lower()
            w, h = size.split("x", 1)
            return int(float(w)), int(float(h))
        except Exception:
            return None

    def _ekran_limitleri(self, width_ratio=0.94, height_ratio=0.90):
        try:
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
        except Exception:
            sw, sh = 1366, 768
        max_w = max(640, int(sw * width_ratio))
        max_h = max(520, int(sh * height_ratio))
        return max_w, max_h

    def pencere_ekrana_sigdir(self, win, geometry=None, minsize=None, width_ratio=0.94, height_ratio=0.90):
        parsed = self._geometry_parcala(geometry)
        max_w, max_h = self._ekran_limitleri(width_ratio, height_ratio)
        if parsed:
            desired_w, desired_h = parsed
            final_w = min(desired_w, max_w)
            final_h = min(desired_h, max_h)
            win.geometry(f"{final_w}x{final_h}")
        if minsize:
            min_w = min(int(minsize[0]), max_w)
            min_h = min(int(minsize[1]), max_h)
            try:
                win.minsize(min_w, min_h)
            except Exception:
                pass

    def ana_pencere_tam_ekran_yap(self):
        try:
            self.root.state("zoomed")
            return
        except Exception:
            pass
        try:
            self.root.attributes("-zoomed", True)
            return
        except Exception:
            pass
        try:
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            self.root.geometry(f"{sw}x{sh}+0+0")
        except Exception:
            pass

    def responsive_widget_grid(self, parent, widgets, min_width=160, max_cols=None, padx=4, pady=4):
        state = {"cols": 0}

        def relayout(_event=None):
            if not widgets:
                return
            width = parent.winfo_width()
            if width <= 1:
                try:
                    width = parent.master.winfo_width()
                except Exception:
                    width = self.root.winfo_width()
            cols = max(1, width // max(min_width, 1))
            if max_cols:
                cols = min(cols, max_cols)
            cols = min(cols, len(widgets))
            if cols == state["cols"]:
                return
            for widget in widgets:
                try:
                    if widget.winfo_exists():
                        widget.grid_forget()
                except tk.TclError:
                    continue
            for c in range(max(len(widgets), state["cols"], cols)):
                parent.columnconfigure(c, weight=0)
            for idx, widget in enumerate(widgets):
                try:
                    if widget.winfo_exists():
                        widget.grid(row=idx // cols, column=idx % cols, sticky="ew", padx=padx, pady=pady)
                except tk.TclError:
                    continue
            for c in range(cols):
                parent.columnconfigure(c, weight=1)
            state["cols"] = cols

        parent.bind("<Configure>", relayout)
        try:
            self.root.after_idle(relayout)
        except Exception:
            relayout()

    def responsive_button_row(self, parent, button_specs, min_width=130, max_cols=None, padx=4, pady=3):
        buttons = []
        for spec in button_specs:
            if len(spec) == 3:
                text, command, bg = spec
                fg = "#111111"
                tip = f"{text} işlemini başlatır"
            elif len(spec) == 4:
                text, command, bg, tip = spec
                fg = "white"
            else:
                text, command, bg, fg, tip = spec
            btn = self.modern_button(parent, text, command=command, role=self._role_from_color(bg), bg=bg, fg=fg, font=FONT_BOLD, relief="flat", padx=8)
            buttons.append(btn)
            self.tooltip_ekle(btn, tip)
        self.responsive_widget_grid(parent, buttons, min_width=min_width, max_cols=max_cols, padx=padx, pady=pady)
        return buttons

    def pencere_hazirla(self, win, title, geometry=None, minsize=None, modal=False):
        win.title(title)
        self.pencere_ekrana_sigdir(win, geometry, minsize)
        try:
            win.configure(bg=COLOR_BG)
        except Exception:
            pass
        if modal:
            try:
                win.transient(self.root)
            except Exception:
                pass
        return win

    def arayuz_butonu(self, parent, text, command=None, role="neutral", **kwargs):
        return self.modern_button(parent, text, command=command, role=role, **kwargs)

    def tooltip_ekle(self, widget, text, delay=550):
        if not text:
            return widget
        state = {"after": None, "tip": None}

        def show_tip():
            if state["tip"] is not None:
                return
            try:
                x = widget.winfo_rootx() + 18
                y = widget.winfo_rooty() + widget.winfo_height() + 8
            except Exception:
                return
            tip = tk.Toplevel(widget)
            tip.wm_overrideredirect(True)
            tip.wm_geometry(f"+{x}+{y}")
            label = tk.Label(
                tip,
                text=text,
                bg="#FFF8DC",
                fg="#111111",
                relief="solid",
                bd=1,
                padx=7,
                pady=4,
                font=("Segoe UI", 8),
                justify="left",
                wraplength=280,
            )
            label.pack()
            state["tip"] = tip

        def schedule(_event=None):
            cancel()
            try:
                state["after"] = widget.after(delay, show_tip)
            except Exception:
                state["after"] = None

        def cancel(_event=None):
            after_id = state.get("after")
            if after_id is not None:
                try:
                    widget.after_cancel(after_id)
                except Exception:
                    pass
                state["after"] = None
            tip = state.get("tip")
            if tip is not None:
                try:
                    tip.destroy()
                except Exception:
                    pass
                state["tip"] = None

        widget.bind("<Enter>", schedule, add="+")
        widget.bind("<Leave>", cancel, add="+")
        widget.bind("<ButtonPress>", cancel, add="+")
        return widget

    def toolbar_menu(self, parent, title, commands, bg="#ECF0F1", fg="#111111", tooltip=None, role=None):
        role = role or self._role_from_color(bg)
        if getattr(self, "bootstrap_theme_active", False) and self._bootstrap_module is not None:
            try:
                btn = self._bootstrap_module.Menubutton(
                    parent,
                    text=f"{title} ▾",
                    bootstyle=self._button_bootstyle(role, outline=True),
                    padding=(10, 4),
                )
            except Exception:
                btn = tk.Menubutton(parent, text=f"{title} ▾", bg=bg, fg=fg, font=FONT_BOLD, relief="raised", padx=10, pady=3)
        else:
            btn = tk.Menubutton(parent, text=f"{title} ▾", bg=bg, fg=fg, font=FONT_BOLD, relief="raised", padx=10, pady=3)
        menu = tk.Menu(btn, tearoff=0)
        btn.configure(menu=menu)
        for item in commands:
            if item is None:
                menu.add_separator()
                continue
            label, command = item
            menu.add_command(label=label, command=command)
        btn.pack(side="left", padx=3, pady=5)
        self.tooltip_ekle(btn, tooltip or f"{title} komutları")
        return btn

