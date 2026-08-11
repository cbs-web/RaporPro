# Dosya: RaporPro/arayuz_temel.py
import datetime
import threading
import tkinter as tk
from tkinter import ttk

from sabitler import *
from ui_icons import IconManager
from ui_motion import MOTION_FAST_MS, MOTION_NORMAL_MS, UIMotionMixin, blend_hex


class ArayuzTemelMixin(UIMotionMixin):
    def setup_styles(self):
        self.ui_motion_setup(enabled=True)
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
        style.configure("TButton", font=FONT_MAIN, padding=(9, 6))
        style.configure("TEntry", font=FONT_MAIN, padding=6)
        style.configure("TNotebook", background=COLOR_BG, borderwidth=0)
        style.configure("TNotebook.Tab", font=FONT_BOLD, padding=(12, 7))
        style.configure("Main.TNotebook", background=COLOR_BG, borderwidth=0, tabmargins=0)
        style.layout("Main.TNotebook.Tab", [])
        style.configure("Treeview", rowheight=28, font=FONT_MAIN, background=COLOR_SURFACE, fieldbackground=COLOR_SURFACE)
        style.configure("Treeview.Heading", font=FONT_BOLD)
        style.configure("TCombobox", font=FONT_MAIN, padding=5)
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

    def ana_navigasyon_kur(self, parent):
        """Ana Notebook sayfaları için daraltılabilir sol navigasyonu oluştur."""
        self.ana_nav_expanded = True
        self.ana_nav_manual = False
        self.ana_nav_items = []
        self.ana_nav_full_width = 184
        self.ana_nav_compact_width = 58

        nav = tk.Frame(parent, bg=COLOR_PRIMARY, width=self.ana_nav_full_width, bd=0, highlightthickness=0)
        nav.grid(row=0, column=0, sticky="ns")
        nav.grid_propagate(False)
        nav.grid_columnconfigure(0, weight=1)
        self.ana_nav_frame = nav

        header = tk.Frame(nav, bg=COLOR_PRIMARY, height=56)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        header.grid_columnconfigure(0, weight=1)
        self.ana_nav_title = tk.Label(
            header,
            text="RaporPro",
            bg=COLOR_PRIMARY,
            fg="white",
            font=FONT_UI_SECTION,
            anchor="w",
        )
        self.ana_nav_title.grid(row=0, column=0, sticky="nsew", padx=(14, 4))
        self.ana_nav_toggle = tk.Button(
            header,
            text="\u2039",
            command=lambda: self.ana_navigasyon_daralt(not self.ana_nav_expanded, manual=True),
            bg=COLOR_PRIMARY,
            activebackground="#34495E",
            fg="white",
            activeforeground="white",
            relief="flat",
            bd=0,
            width=3,
            font=("Segoe UI", 14),
            cursor="hand2",
            takefocus=True,
        )
        self.ana_nav_toggle.grid(row=0, column=1, sticky="ns")
        self.tooltip_ekle(self.ana_nav_toggle, "Sol menüyü daralt veya genişlet")

        nav_specs = (
            ("0", "Özet", "project", self.tab_ozet),
            ("1", "Künye", "tag", self.tab_kunye),
            ("2", "Bina", "project", self.tab_bina),
            ("3", "Arazi", "map", self.tab_arazi),
            ("4", "Sondaj", "borehole", self.tab_sondaj),
            ("5", "Jeofizik", "gauge", self.tab_jeofizik),
            ("6", "Haritalar", "map", self.tab_haritalar),
            ("7", "Rapor", "report", self.tab_rapor),
        )
        for row, (number, label, icon_key, tab) in enumerate(nav_specs, start=1):
            item_frame = tk.Frame(nav, bg=COLOR_PRIMARY, height=46)
            item_frame.grid(row=row, column=0, sticky="ew")
            item_frame.grid_propagate(False)
            item_frame.grid_columnconfigure(1, weight=1)
            indicator = tk.Frame(item_frame, bg=COLOR_PRIMARY, width=4)
            indicator.grid(row=0, column=0, sticky="ns")
            inactive_image = self.ui_icons.get(icon_key, color="#D8E1E8", size=18)
            active_image = self.ui_icons.get(icon_key, color="white", size=18)
            button = tk.Button(
                item_frame,
                text=f"{number}.  {label}",
                image=inactive_image,
                compound="left",
                command=lambda target=tab: self.nb.select(target),
                bg=COLOR_PRIMARY,
                activebackground="#34495E",
                fg="#E8EDF2",
                activeforeground="white",
                relief="flat",
                bd=0,
                padx=13,
                pady=9,
                anchor="w",
                font=FONT_UI_BODY_BOLD,
                cursor="hand2",
                takefocus=True,
            )
            button.grid(row=0, column=1, sticky="nsew")
            self.tooltip_ekle(button, f"{number}. {label} sekmesine git")
            item = {
                "number": number,
                "label": label,
                "tab": tab,
                "frame": item_frame,
                "indicator": indicator,
                "button": button,
                "inactive_image": inactive_image,
                "active_image": active_image,
                "active": False,
            }
            self.ana_nav_items.append(item)
            button.bind("<Enter>", lambda _event, target=item: self._ana_nav_hover(target, True), add="+")
            button.bind("<Leave>", lambda _event, target=item: self._ana_nav_hover(target, False), add="+")

        self.root.bind("<Configure>", self.ana_navigasyon_pencere_degisti, add="+")
        self.root.after_idle(self.ana_navigasyon_ilk_boyut)
        self.root.after_idle(self.ana_navigasyon_secimi_guncelle)

    def ana_navigasyon_daralt(self, expanded, manual=False):
        """Sol navigasyonu geniş veya kompakt görünüme geçir."""
        self.ana_nav_expanded = bool(expanded)
        if manual:
            self.ana_nav_manual = True
        target_width = self.ana_nav_full_width if self.ana_nav_expanded else self.ana_nav_compact_width
        try:
            current_width = int(self.ana_nav_frame.cget("width"))
        except Exception:
            current_width = target_width

        if not self.ana_nav_expanded:
            self._ana_nav_icerik_ayarla(False)

        shown = {"value": not self.ana_nav_expanded}

        def update(value):
            self.ana_nav_frame.configure(width=max(self.ana_nav_compact_width, round(value)))
            if self.ana_nav_expanded and not shown["value"] and value >= target_width - 36:
                shown["value"] = True
                self._ana_nav_icerik_ayarla(True)

        def complete():
            self._ana_nav_icerik_ayarla(self.ana_nav_expanded)
            self.ana_navigasyon_secimi_guncelle()

        self.ui_motion_tween(
            "main-nav-width",
            current_width,
            target_width,
            update,
            duration=MOTION_NORMAL_MS,
            complete=complete,
        )

    def _ana_nav_icerik_ayarla(self, expanded):
        self.ana_nav_title.configure(text="RaporPro" if expanded else "")
        self.ana_nav_toggle.configure(text="\u2039" if expanded else "\u203a")
        for item in self.ana_nav_items:
            button = item["button"]
            if expanded:
                button.configure(
                    text=f"{item['number']}.  {item['label']}",
                    compound="left",
                    anchor="w",
                    padx=13,
                )
            else:
                button.configure(text="", compound="none", anchor="center", padx=0)

    def _ana_nav_hover(self, item, hovered):
        if item.get("active"):
            return
        target = "#34495E" if hovered else COLOR_PRIMARY
        self.ui_motion_color(
            item["button"],
            "background",
            target,
            key=f"nav-button:{id(item['button'])}",
            duration=MOTION_FAST_MS,
        )

    def ana_navigasyon_ilk_boyut(self):
        """İlk gerçek pencere boyutuna göre menünün başlangıç görünümünü seç."""
        try:
            expanded = self.root.winfo_width() >= 1280
        except tk.TclError:
            return
        self.ana_navigasyon_daralt(expanded, manual=False)

    def ana_navigasyon_pencere_degisti(self, event):
        """Dar pencerelerde içerik alanını korumak için menüyü otomatik daralt."""
        if event.widget is not self.root or self.ana_nav_manual:
            return
        if event.width < 1180 and self.ana_nav_expanded:
            self.ana_navigasyon_daralt(False)
        elif event.width >= 1280 and not self.ana_nav_expanded:
            self.ana_navigasyon_daralt(True)

    def ana_navigasyon_secimi_guncelle(self):
        """Notebook seçimini sol menünün aktif görünümüyle eşitle."""
        if not hasattr(self, "nb") or not hasattr(self, "ana_nav_items"):
            return
        try:
            selected = self.nb.select()
        except tk.TclError:
            return
        for item in self.ana_nav_items:
            active = selected == str(item["tab"])
            item["active"] = active
            background = COLOR_ACCENT if active else COLOR_PRIMARY
            self.ui_motion_color(
                item["frame"],
                "background",
                background,
                key=f"nav-frame:{id(item['frame'])}",
                duration=MOTION_FAST_MS,
            )
            self.ui_motion_color(
                item["indicator"],
                "background",
                "#FFFFFF" if active else COLOR_PRIMARY,
                key=f"nav-indicator:{id(item['indicator'])}",
                duration=MOTION_FAST_MS,
            )
            self.ui_motion_color(
                item["button"],
                "background",
                background,
                key=f"nav-button:{id(item['button'])}",
                duration=MOTION_FAST_MS,
            )
            item["button"].configure(
                activebackground=COLOR_ACCENT if active else "#34495E",
                fg="white" if active else "#E8EDF2",
                image=item["active_image"] if active else item["inactive_image"],
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
        scroll_state = {"target": None}

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
                    bbox = canvas.bbox("all")
                    content_height = max(1, (bbox[3] - bbox[1]) if bbox else 1)
                    viewport_height = max(1, canvas.winfo_height())
                    if content_height <= viewport_height:
                        return "break"
                    current = float(canvas.yview()[0])
                    base = scroll_state["target"] if scroll_state["target"] is not None else current
                    maximum = max(0.0, 1.0 - viewport_height / content_height)
                    target = max(0.0, min(maximum, base + (steps * 62.0 / content_height)))
                    scroll_state["target"] = target

                    def finished():
                        scroll_state["target"] = None

                    self.ui_motion_tween(
                        f"scroll:{id(canvas)}",
                        current,
                        target,
                        canvas.yview_moveto,
                        duration=140,
                        complete=finished,
                    )
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
            options["command"] = self.ui_motion_close_command(command)
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
        command = self.ui_motion_close_command(command)
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
        button = self._attach_button_icon(tk.Button(parent, text=text, command=command, **kwargs), image)
        try:
            hover = blend_hex(bg, "#FFFFFF", 0.12 if role not in {"neutral", "secondary"} else 0.35)
            self.ui_motion_bind_hover(button, bg, hover)
        except ValueError:
            pass
        return button

    def bildirim_seridi_kur(self, parent, row=1, column=0, columnspan=2):
        """Ana pencere içinde modal olmayan ortak bildirim şeridini oluştur."""
        self._bildirim_after_id = None
        self._bildirim_action = None
        self._bildirim_title_var = tk.StringVar(value="")
        self._bildirim_message_var = tk.StringVar(value="")

        frame = tk.Frame(
            parent,
            bg=COLOR_ACCENT_SOFT,
            bd=0,
            highlightthickness=1,
            highlightbackground=COLOR_ACCENT,
            height=42,
        )
        frame.grid(row=row, column=column, columnspan=columnspan, sticky="ew")
        frame.grid_columnconfigure(2, weight=1)
        frame.grid_propagate(False)
        self._bildirim_frame = frame

        self._bildirim_indicator = tk.Frame(frame, width=5, bg=COLOR_ACCENT)
        self._bildirim_indicator.grid(row=0, column=0, sticky="ns")
        self._bildirim_indicator.grid_propagate(False)
        self._bildirim_title = tk.Label(
            frame,
            textvariable=self._bildirim_title_var,
            bg=COLOR_ACCENT_SOFT,
            fg=COLOR_PRIMARY,
            font=FONT_UI_BODY_BOLD,
            anchor="w",
        )
        self._bildirim_title.grid(row=0, column=1, sticky="w", padx=(10, 8))
        self._bildirim_message = tk.Label(
            frame,
            textvariable=self._bildirim_message_var,
            bg=COLOR_ACCENT_SOFT,
            fg=COLOR_TEXT,
            font=FONT_UI_BODY,
            anchor="w",
            width=1,
        )
        self._bildirim_message.grid(row=0, column=2, sticky="ew", pady=6)
        self._bildirim_action_button = tk.Button(
            frame,
            text="",
            command=self._bildirim_action_calistir,
            bg=COLOR_ACCENT_SOFT,
            fg=COLOR_PRIMARY,
            activebackground=COLOR_SURFACE,
            activeforeground=COLOR_PRIMARY,
            relief="flat",
            bd=0,
            font=FONT_UI_BODY_BOLD,
            cursor="hand2",
        )
        self._bildirim_action_button.grid(row=0, column=3, padx=(8, 2), pady=3)
        self._bildirim_action_button.grid_remove()
        close_button = tk.Button(
            frame,
            text="×",
            command=self.bildirim_gizle,
            bg=COLOR_ACCENT_SOFT,
            fg=COLOR_TEXT_MUTED,
            activebackground=COLOR_SURFACE,
            activeforeground=COLOR_PRIMARY,
            relief="flat",
            bd=0,
            width=3,
            font=("Segoe UI", 12),
            cursor="hand2",
        )
        close_button.grid(row=0, column=4, padx=(2, 4), pady=2)
        self._bildirim_close_button = close_button
        self.tooltip_ekle(close_button, "Bildirimi kapat")
        frame.grid_remove()

    def _bildirim_action_calistir(self):
        action = getattr(self, "_bildirim_action", None)
        self.bildirim_gizle()
        if callable(action):
            try:
                action()
            except Exception as exc:
                self.set_status(f"Bildirim işlemi çalıştırılamadı: {exc}", level="error")

    def bildirim_gizle(self, immediate=False):
        after_id = getattr(self, "_bildirim_after_id", None)
        if after_id:
            try:
                self.root.after_cancel(after_id)
            except Exception:
                pass
        self._bildirim_after_id = None
        self._bildirim_action = None
        frame = getattr(self, "_bildirim_frame", None)
        if frame is not None:
            def remove_frame():
                try:
                    frame.grid_remove()
                    frame.configure(height=42)
                except Exception:
                    pass

            try:
                visible = bool(frame.winfo_ismapped())
            except Exception:
                visible = False
            if immediate or not visible or not getattr(self, "ui_motion_enabled", True):
                self.ui_motion_cancel("notification-height")
                remove_frame()
                return
            try:
                frame.update_idletasks()
                start_height = max(1, int(frame.winfo_height()))
            except Exception:
                start_height = 42
            self.ui_motion_tween(
                "notification-height",
                start_height,
                1,
                lambda value: frame.configure(height=max(1, round(value))),
                duration=MOTION_FAST_MS,
                complete=remove_frame,
            )

    def bildirim_goster(
        self,
        message,
        level="info",
        title=None,
        duration=None,
        action_text=None,
        action=None,
        log=True,
    ):
        """Kullanıcıya akışı kesmeden ortak bildirim şeridinde geri bildirim ver."""
        if getattr(self, "_closing", False):
            return
        if threading.current_thread() is not threading.main_thread():
            try:
                self.root.after(
                    0,
                    lambda: self.bildirim_goster(
                        message,
                        level=level,
                        title=title,
                        duration=duration,
                        action_text=action_text,
                        action=action,
                        log=log,
                    ),
                )
            except Exception:
                pass
            return

        text = " ".join(str(message or "").split())
        if len(text) > 240:
            text = text[:237].rstrip() + "..."
        if log:
            self.set_status(text, level=level)

        frame = getattr(self, "_bildirim_frame", None)
        if frame is None:
            return
        palette = {
            "success": ("Tamamlandı", COLOR_SUCCESS, COLOR_SUCCESS_SOFT),
            "warning": ("Dikkat", COLOR_WARNING, COLOR_WARNING_SOFT),
            "error": ("Hata", COLOR_DANGER, COLOR_DANGER_SOFT),
            "info": ("Bilgi", COLOR_ACCENT, COLOR_ACCENT_SOFT),
        }
        default_title, color, background = palette.get(level, palette["info"])
        self._bildirim_title_var.set(title or default_title)
        self._bildirim_message_var.set(text)
        frame.configure(bg=background, highlightbackground=color)
        self._bildirim_indicator.configure(bg=color)
        self._bildirim_title.configure(bg=background, fg=color)
        self._bildirim_message.configure(bg=background)
        self._bildirim_action_button.configure(bg=background, activebackground=COLOR_SURFACE)
        self._bildirim_close_button.configure(bg=background, activebackground=COLOR_SURFACE)
        self._bildirim_action = action if callable(action) else None
        if self._bildirim_action and action_text:
            self._bildirim_action_button.configure(text=str(action_text))
            self._bildirim_action_button.grid()
        else:
            self._bildirim_action_button.grid_remove()
        try:
            was_visible = bool(frame.winfo_ismapped())
        except Exception:
            was_visible = False
        self.ui_motion_cancel("notification-height")
        if not was_visible:
            frame.configure(height=1)
        frame.grid()
        frame.lift()
        if not was_visible:
            self.ui_motion_tween(
                "notification-height",
                1,
                42,
                lambda value: frame.configure(height=max(1, round(value))),
                duration=MOTION_NORMAL_MS,
            )

        old_after = getattr(self, "_bildirim_after_id", None)
        if old_after:
            try:
                self.root.after_cancel(old_after)
            except Exception:
                pass
        if duration is None:
            duration = 8000 if level in {"warning", "error"} else 5000
        self._bildirim_after_id = (
            self.root.after(max(1000, int(duration)), self.bildirim_gizle)
            if duration and int(duration) > 0
            else None
        )

    def _task_status_bildir(self, message, level="info"):
        """Görev motoru durumunu günlüğe ve gerekli olduğunda bildirim şeridine aktar."""
        self.set_status(message, level=level)
        if level == "error":
            self.bildirim_goster(
                message,
                level=level,
                action_text="Görevleri Aç",
                action=self.gorev_merkezi_penceresi,
                log=False,
            )

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
                        percent = getattr(first, "progress_percent", None)
                        percent_text = (
                            f"%{percent:.0f}"
                            if percent is not None
                            else f"{first.completed:g}/{first.total:g}"
                        )
                        detail = f" · {first.name} {percent_text}"
                    else:
                        detail = f" · {first.name}"
                self.task_status_var.set(f"İşlem: {active} görev{detail}")
            else:
                self.task_status_var.set("İşlem: hazır")
        if hasattr(self, "task_status_label"):
            self.task_status_label.config(fg=COLOR_WARNING if active else COLOR_TEXT_MUTED)
        progress = getattr(self, "task_activity_progress", None)
        if progress is not None:
            if active:
                try:
                    if not progress.winfo_ismapped():
                        progress.pack(side="right", before=self.task_status_label, padx=(4, 0))
                    progress.start(12)
                except tk.TclError:
                    pass
            else:
                try:
                    progress.stop()
                    progress.pack_forget()
                except tk.TclError:
                    pass

    def islem_gunlugu_durum_ayarla(self, expanded, immediate=False):
        """Alt işlem günlüğünü kompakt ve akıcı biçimde açıp daralt."""
        splitter = getattr(self, "main_splitter", None)
        body = getattr(self, "log_body", None)
        button = getattr(self, "log_toggle_button", None)
        if splitter is None or body is None:
            return
        expanded = bool(expanded)
        self.log_panel_expanded = expanded
        try:
            splitter.update_idletasks()
            total_height = max(1, splitter.winfo_height())
            start_y = float(splitter.sash_coord(0)[1])
        except (tk.TclError, IndexError):
            return
        if total_height < 100:
            try:
                self.root.after(
                    80,
                    lambda: self.islem_gunlugu_durum_ayarla(expanded, immediate=immediate),
                )
            except tk.TclError:
                pass
            return

        target_height = min(210, max(130, round(total_height * 0.22))) if expanded else 34
        target_y = max(0, total_height - target_height)
        if expanded and not body.winfo_manager():
            body.pack(fill="both", expand=True)
        if button is not None:
            button.configure(text="▼" if expanded else "▲")

        def update(value):
            splitter.sash_place(0, 0, round(value))

        def complete():
            if not expanded:
                body.pack_forget()

        if immediate or not getattr(self, "ui_motion_enabled", True):
            self.ui_motion_cancel("activity-log-height")
            update(target_y)
            complete()
            return
        self.ui_motion_tween(
            "activity-log-height",
            start_y,
            target_y,
            update,
            duration=MOTION_NORMAL_MS,
            complete=complete,
        )

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
        self.ui_motion_prepare_window(win)
        return win

    def pencere_kapat(self, win, callback=None):
        """Hazırlanmış pencereyi ortak çıkış geçişiyle kapat."""
        self.ui_motion_window_close(win, callback=callback)

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
            self.ui_motion_window_enter(tip, duration=100)

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
                state["tip"] = None
                self.ui_motion_window_close(tip, duration=70)

        widget.bind("<Enter>", schedule, add="+")
        widget.bind("<Leave>", cancel, add="+")
        widget.bind("<ButtonPress>", cancel, add="+")
        return widget

    def toolbar_menu(self, parent, title, commands, bg="#ECF0F1", fg="#111111", tooltip=None, role=None):
        role = role or self._role_from_color(bg)
        image = self._button_icon_image(title, role=role, outline=True, size=16)
        menu_images = []
        fallback_button = False
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
                fallback_button = True
                btn = tk.Menubutton(parent, text=f"{title} ▾", bg=bg, fg=fg, font=FONT_BOLD, relief="flat", padx=10, pady=3)
        else:
            fallback_button = True
            btn = tk.Menubutton(parent, text=f"{title} ▾", bg=bg, fg=fg, font=FONT_BOLD, relief="flat", padx=10, pady=3)
        self._attach_button_icon(btn, image)
        menu = tk.Menu(
            btn,
            tearoff=0,
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT,
            activebackground=COLOR_ACCENT_SOFT,
            activeforeground=COLOR_PRIMARY,
            disabledforeground=COLOR_TEXT_MUTED,
            font=FONT_UI_BODY,
            relief="solid",
            bd=1,
            activeborderwidth=0,
        )
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
        if fallback_button:
            self.ui_motion_bind_hover(btn, bg, blend_hex(bg, "#FFFFFF", 0.28))
        self.tooltip_ekle(btn, tooltip or f"{title} komutları")
        return btn
