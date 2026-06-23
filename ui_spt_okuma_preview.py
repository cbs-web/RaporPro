# Dosya: RaporPro/ui_spt_okuma_preview.py
import os


class SPTPreviewController:
    def __init__(self, win, canvas, image_ref=None):
        self.win = win
        self.canvas = canvas
        self.image_ref = image_ref if image_ref is not None else {}
        self.state = {
            "path": "",
            "message": "Satır seçildiğinde kaynak burada görünür.",
            "photo": None,
            "after_id": None,
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
            image = Image.open(path)
            try:
                image = ImageOps.exif_transpose(image)
            except Exception:
                pass
            image = image.convert("RGB")
            self.canvas.update_idletasks()
            canvas_w = max(360, self.canvas.winfo_width())
            canvas_h = max(260, self.canvas.winfo_height())
            resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.BICUBIC)
            image.thumbnail((canvas_w - 18, canvas_h - 18), resample)
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
            lambda: self.draw_image(self.state["path"], self.state["message"]),
        )

    def show(self, kayit):
        path = kayit.kaynak_yolu
        self.draw_image(path, kayit.kaynak or "Kaynak dosya bilgisi yok.")
