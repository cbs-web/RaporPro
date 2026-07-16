# Dosya: RaporPro/arayuz_temel.py
import datetime
import threading
import tkinter as tk
from tkinter import ttk

from sabitler import *
from ui_icons import IconManager


class ArayuzTemelMixin:
    def setup_styles(self):
        self.bootstrap_theme_active = False
        self.bootstrap_theme_name = "classic"
        self._bootstrap_module = None
        self.ui_icons = IconManager(getattr(self, "root", None))
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
        style.configure("Surface.TFrame", background=COLOR_SURFACE)
        style.configure("SurfaceAlt.TFrame", background=COLOR_SURFACE_ALT)
        style.configure("PageTitle.TLabel", background=COLOR_BG, foreground=COLOR_PRIMARY, font=FONT_UI_PAGE)
        style.configure("SectionTitle.TLabel", background=COLOR_BG, foreground=COLOR_PRIMARY, font=FONT_UI_SECTION)
        style.configure("Muted.TLabel", background=COLOR_BG, foreground=COLOR_TEXT_MUTED, font=FONT_UI_BODY)
        style.configure(
            "Dashboard.Horizontal.TProgressbar",
            troughcolor="#E8EDF2",
            background=COLOR_ACCENT,
            bordercolor="#E8EDF2",
            lightcolor=COLOR_ACCENT,
            darkcolor=COLOR_ACCENT,
            thickness=8,
        )
        for name, color in (
            ("Success", COLOR_SUCCESS),
            ("Warning", COLOR_WARNING),
            ("Danger", COLOR_DANGER),
        ):
            style.configure(
                f"{name}.Horizontal.TProgressbar",
                troughcolor="#E8EDF2",
                background=color,
                bordercolor="#E8EDF2",
                lightcolor=color,
                darkcolor=color,
                thickness=8,
            )

    def scrollable_page(self, parent, padding=12):
        """İçeriği görünür genişliğe sabitleyen dikey kaydırılabilir sayfa oluştur."""
        shell = ttk.Frame(parent)
        shell.pack(fill="both", expand=True)
        canvas = tk.Canvas(shell, bg=COLOR_BG, highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(shell, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = ttk.Frame(canvas, padding=padding)
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def update_region(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def update_width(event):
            canvas.itemconfigure(window_id, width=max(1, event.width))

        def is_page_child(widget):
            while widget is not None:
                if widget in (canvas, inner):
                    return True
                widget = getattr(widget, "master", None)
            return False

        def on_mousewheel(event):
            try:
                if not canvas.winfo_exists():
                    return None
                widget = self.root.winfo_containing(*self.root.winfo_pointerxy())
                if not is_page_child(widget):
                    return None
                if widget is not canvas and isinstance(widget, (tk.Text, tk.Listbox, ttk.Treeview)):
                    return None
                steps = -int(event.delta / 120) if event.delta else 0
                if steps == 0 and event.delta:
                    steps = -1 if event.delta > 0 else 1
                if steps:
                    canvas.yview_scroll(steps, "units")
                    return "break"
            except tk.TclError:
                return None
            return None

        inner.bind("<Configure>", update_region)
        canvas.bind("<Configure>", update_width)
        self.root.bind_all("<MouseWheel>", on_mousewheel, add="+")
        return inner, canvas

    def ui_surface_frame(self, parent, padding=12, background=COLOR_SURFACE):
        """İnce kenarlıklı, nötr içerik yüzeyi oluştur."""
        return tk.Frame(
            parent,
            bg=background,
            bd=0,
            highlightthickness=1,
            highlightbackground=COLOR_BORDER,
            highlightcolor=COLOR_BORDER_STRONG,
            padx=padding,
            pady=padding,
        )

    def ui_section_title(self, parent, text):
        """Sayfa içindeki bölüm başlıklarını tek tip üret."""
        return ttk.Label(parent, text=text, style="SectionTitle.TLabel")

    def ui_status_palette(self, state="neutral"):
        """Durum göstergelerinde kullanılacak vurgu ve yumuşak yüzey rengini döndür."""
        palettes = {
            "success": (COLOR_SUCCESS, COLOR_SUCCESS_SOFT),
            "warning": (COLOR_WARNING, COLOR_WARNING_SOFT),
            "danger": (COLOR_DANGER, COLOR_DANGER_SOFT),
            "accent": (COLOR_ACCENT, COLOR_ACCENT_SOFT),
            "neutral": (COLOR_TEXT_MUTED, COLOR_SURFACE_ALT),
        }
        return palettes.get(state, palettes["neutral"])

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

    def _button_icon_color(self, role="neutral", outline=False):
        if outline or role in ("neutral", "secondary", None):
            return "#111111"
        return "white"

    def _button_icon_image(self, text, role="neutral", outline=False, icon=None, size=16):
        if icon is False:
            return None
        manager = getattr(self, "ui_icons", None)
        if manager is None:
            return None
        key = icon or manager.guess_key(text)
        if not key:
            return None
        color = self._button_icon_color(role, outline)
        return manager.get(key, color=color, size=size)

    def _attach_button_icon(self, widget, image):
        if image is None:
            return widget
        try:
            widget.configure(image=image, compound="left")
            widget._ui_icon_image = image
        except Exception:
            pass
        return widget

    def configure_modern_button(self, widget, text=None, command=None, role=None, outline=False, icon=None):
        options = {}
        if text is not None:
            options["text"] = text
        if command is not None:
            options["command"] = command
        if options:
            try:
                widget.configure(**options)
            except Exception:
                pass
        if role is not None:
            if getattr(self, "bootstrap_theme_active", False) and self._bootstrap_module is not None:
                try:
                    widget.configure(bootstyle=self._button_bootstyle(role, outline))
                except Exception:
                    pass
            else:
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
                try:
                    widget.configure(bg=bg, fg=fg)
                except Exception:
                    pass
        label = text
        if label is None:
            try:
                label = widget.cget("text")
            except Exception:
                label = ""
        image = self._button_icon_image(label, role=role or "neutral", outline=outline, icon=icon, size=16)
        return self._attach_button_icon(widget, image)

    def modern_button(self, parent, text, command=None, role="neutral", outline=False, **kwargs):
        icon = kwargs.pop("icon", None)
        icon_size = kwargs.pop("icon_size", 16)
        image = self._button_icon_image(text, role=role, outline=outline, icon=icon, size=icon_size)
        if getattr(self, "bootstrap_theme_active", False) and self._bootstrap_module is not None:
            tb_kwargs = {"text": text, "command": command, "bootstyle": self._button_bootstyle(role, outline)}
            for key in ("width", "state", "takefocus"):
                if key in kwargs:
                    tb_kwargs[key] = kwargs[key]
            if image is not None:
                tb_kwargs["image"] = image
                tb_kwargs["compound"] = "left"
            padx = kwargs.get("padx", 10)
            pady = kwargs.get("pady", 5)
            tb_kwargs.setdefault("padding", (padx, pady))
            try:
                return self._attach_button_icon(self._bootstrap_module.Button(parent, **tb_kwargs), image)
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
        if image is not None:
            kwargs["image"] = image
            kwargs["compound"] = "left"
        return self._attach_button_icon(tk.Button(parent, text=text, command=command, **kwargs), image)

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

    def _task_engine_state_changed(self, snapshot):
        if getattr(self, "_closing", False):
            return
        try:
            active = int(getattr(snapshot, "active_count", 0))
        except Exception:
            active = 0
        if hasattr(self, "task_status_var"):
            if active:
                tasks = getattr(snapshot, "active_tasks", ()) or ()
                first = tasks[0] if tasks else None
                detail = ""
                if first is not None:
                    if getattr(first, "total", 0):
                        detail = f" · {first.name} {first.completed:g}/{first.total:g}"
                    else:
                        detail = f" · {first.name}"
                self.task_status_var.set(f"İşlem: {active} görev{detail}")
            else:
                self.task_status_var.set("İşlem: hazır")
        if hasattr(self, "task_status_label"):
            self.task_status_label.config(fg=COLOR_WARNING if active else "#333333")

    def arka_plan_gorevi_baslat(self, ad, func, *args, **kwargs):
        engine = getattr(self, "task_engine", None)
        if engine is None:
            on_success = kwargs.pop("on_success", None)
            on_error = kwargs.pop("on_error", None)
            kwargs.pop("on_cancel", None)
            on_done = kwargs.pop("on_done", None)
            status_start = kwargs.pop("status_start", None)
            status_success = kwargs.pop("status_success", None)
            status_error = kwargs.pop("status_error", None)
            kwargs.pop("status_cancel", None)
            with_context = bool(kwargs.pop("with_context", False))
            kwargs.pop("cancellable", None)
            kwargs.pop("resource", None)
            if status_start:
                self.set_status(status_start)
            try:
                if with_context:
                    from task_engine import TaskContext

                    context = TaskContext(0, lambda *_args, **_kwargs: None, cancellable=False)
                    result = func(*args, task_context=context, **kwargs)
                else:
                    result = func(*args, **kwargs)
            except Exception as exc:
                if status_error:
                    self.set_status(status_error.format(error=exc), level="error")
                if on_error:
                    on_error(exc)
                if on_done:
                    on_done()
                return None
            if status_success:
                self.set_status(status_success, level="success")
            if on_success:
                on_success(result)
            if on_done:
                on_done()
            return result
        return engine.run(ad, func, *args, **kwargs)

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
        widget._tooltip_text = text
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
            current_text = getattr(widget, "_tooltip_text", text)
            if not current_text:
                tip.destroy()
                return
            label = tk.Label(
                tip,
                text=current_text,
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
        image = self._button_icon_image(title, role=role, outline=True, size=16)
        menu_images = []
        if getattr(self, "bootstrap_theme_active", False) and self._bootstrap_module is not None:
            try:
                kwargs = {
                    "text": f"{title} ▾",
                    "bootstyle": self._button_bootstyle(role, outline=True),
                    "padding": (10, 4),
                }
                if image is not None:
                    kwargs["image"] = image
                    kwargs["compound"] = "left"
                btn = self._bootstrap_module.Menubutton(parent, **kwargs)
            except Exception:
                btn = tk.Menubutton(parent, text=f"{title} ▾", bg=bg, fg=fg, font=FONT_BOLD, relief="raised", padx=10, pady=3)
        else:
            btn = tk.Menubutton(parent, text=f"{title} ▾", bg=bg, fg=fg, font=FONT_BOLD, relief="raised", padx=10, pady=3)
        self._attach_button_icon(btn, image)
        menu = tk.Menu(btn, tearoff=0)
        btn.configure(menu=menu)
        for item in commands:
            if item is None:
                menu.add_separator()
                continue
            label, command = item
            item_image = self._button_icon_image(label, role="secondary", outline=True, size=16)
            if item_image is not None:
                menu_images.append(item_image)
                try:
                    menu.add_command(label=label, image=item_image, compound="left", command=command)
                except Exception:
                    menu.add_command(label=label, command=command)
            else:
                menu.add_command(label=label, command=command)
        btn.pack(side="left", padx=3, pady=5)
        btn._ui_icon_image = image
        btn._ui_menu_icon_images = menu_images
        self.tooltip_ekle(btn, tooltip or f"{title} komutları")
        return btn
