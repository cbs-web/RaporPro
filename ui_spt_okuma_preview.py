# Dosya: RaporPro/ui_spt_okuma_preview.py
import os
from collections import OrderedDict


class SPTPreviewController:
    _thumbnail_cache = OrderedDict()
    _thumbnail_cache_limit = 24

    def __init__(self, win, canvas, image_ref=None):
        self.win = win
        self.canvas = canvas
        self.image_ref = image_ref if image_ref is not None else {}
        self.state = {
            "path": "",
            "message": "Satır seçildiğinde kaynak burada görünür.",
            "photo": None,
            "after_id": None,
            "zoom": 1.0,
            "angle": 0,
        }

    def draw_message(self, text):
        self.state["path"] = ""
        self.state["message"] = text
        self.state["photo"] = None
        self.image_ref["ref"] = None
        self.canvas.delete("all")
        w = max(240, self.canvas.winfo_width())
        h = max(180, self.canvas.winfo_height())
        self.canvas.create_text(
            w / 2,
            h / 2,
            text=text,
            fill="#555555",
            width=max(220, w - 40),
            justify="center",
            font=("Segoe UI", 10),
        )

    def draw_image(self, path, fallback_text="Kaynak dosya bilgisi yok."):
        self.state["path"] = path or ""
        self.state["message"] = fallback_text
        self.state["photo"] = None
        self.image_ref["ref"] = None
        if not path or not os.path.exists(path):
            self.draw_message(fallback_text)
            return
        if os.path.splitext(path)[1].lower() not in (".jpg", ".jpeg", ".png", ".bmp", ".webp"):
            self.draw_message(f"Kaynak dosya:\n{path}")
            return
        try:
            from PIL import Image, ImageOps, ImageTk
            self.canvas.update_idletasks()
            canvas_w = max(360, self.canvas.winfo_width())
            canvas_h = max(260, self.canvas.winfo_height())
            stat = os.stat(path)
            cache_key = (
                os.path.realpath(path),
                int(stat.st_mtime_ns),
                canvas_w - 18,
                canvas_h - 18,
                int(self.state.get("angle", 0)),
                round(float(self.state.get("zoom", 1.0)), 2),
            )
            cache_enabled = float(self.state.get("zoom", 1.0)) <= 1.01
            image = self._thumbnail_cache.get(cache_key) if cache_enabled else None
            if image is None:
                with Image.open(path) as source:
                    try:
                        image = ImageOps.exif_transpose(source)
                    except Exception:
                        image = source.copy()
                    image = image.convert("RGB")
                    angle = int(self.state.get("angle", 0)) % 360
                    if angle:
                        image = image.rotate(-angle, expand=True)
                    resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.BICUBIC)
                    fit_w = max(1, canvas_w - 18)
                    fit_h = max(1, canvas_h - 18)
                    scale = min(fit_w / image.width, fit_h / image.height)
                    scale *= max(0.25, min(4.0, float(self.state.get("zoom", 1.0))))
                    image = image.resize(
                        (
                            max(1, int(round(image.width * scale))),
                            max(1, int(round(image.height * scale))),
                        ),
                        resample,
                    )
                    image = image.copy()
                if cache_enabled:
                    self._thumbnail_cache[cache_key] = image
                    self._thumbnail_cache.move_to_end(cache_key)
                    while len(self._thumbnail_cache) > self._thumbnail_cache_limit:
                        self._thumbnail_cache.popitem(last=False)
            else:
                self._thumbnail_cache.move_to_end(cache_key)
            tk_image = ImageTk.PhotoImage(image)
            self.state["photo"] = tk_image
            self.image_ref["ref"] = tk_image
            self.canvas.delete("all")
            self.canvas.create_image(canvas_w / 2, canvas_h / 2, image=tk_image, anchor="center")
        except Exception as exc:
            self.draw_message(f"Önizleme açılamadı:\n{exc}")

    def schedule_redraw(self, event=None):
        if not self.state.get("path"):
            return
        if self.state.get("after_id"):
            try:
                self.win.after_cancel(self.state["after_id"])
            except Exception:
                pass
        self.state["after_id"] = self.win.after(
            120,
            self._redraw_scheduled,
        )

    def _redraw_scheduled(self):
        self.state["after_id"] = None
        self.draw_image(self.state["path"], self.state["message"])

    def show(self, kayit):
        path = kayit.kaynak_yolu
        if path != self.state.get("path"):
            self.state["zoom"] = 1.0
            self.state["angle"] = 0
        self.draw_image(path, kayit.kaynak or "Kaynak dosya bilgisi yok.")

    def zoom_in(self):
        if not self.state.get("path"):
            return
        self.state["zoom"] = min(4.0, float(self.state.get("zoom", 1.0)) * 1.25)
        self.draw_image(self.state["path"], self.state["message"])

    def zoom_out(self):
        if not self.state.get("path"):
            return
        self.state["zoom"] = max(0.25, float(self.state.get("zoom", 1.0)) / 1.25)
        self.draw_image(self.state["path"], self.state["message"])

    def rotate(self):
        if not self.state.get("path"):
            return
        self.state["angle"] = (int(self.state.get("angle", 0)) + 90) % 360
        self.draw_image(self.state["path"], self.state["message"])

    def fit(self):
        if not self.state.get("path"):
            return
        self.state["zoom"] = 1.0
        self.draw_image(self.state["path"], self.state["message"])

    def open_original(self):
        path = self.state.get("path")
        if not path or not os.path.exists(path):
            return
        try:
            os.startfile(path)
        except Exception:
            pass
