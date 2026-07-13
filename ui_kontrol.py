import os
import tkinter as tk
from tkinter import Toplevel, ttk

from jeofizik_sheet_motoru import jeofizik_sheet_ozeti, jeofizik_sheet_var_mi
from kalite_kontrol import build_preflight_report
from kesit_kalite import build_section_quality_report
from performans import log_exception, perf_tracked
from proje_motoru import proje_saglik_ozeti
from sabitler import COLOR_BG, COLOR_DANGER, COLOR_PRIMARY, COLOR_SUCCESS, COLOR_WARNING, FONT_BOLD
from yardimcilar import safe_float


class KontrolPaneliMixin:
    @perf_tracked("preflight.summary")
    def ozet_on_kontrol(self):
        self.guncelle_veri_objesi()
        self.last_preflight_report = build_preflight_report(self)
        self.ozet_yenile(collect=False)
        errors = len(self.last_preflight_report.get("errors", []))
        warnings = len(self.last_preflight_report.get("warnings", []))
        if errors:
            self.set_status(f"Özet ön kontrol {errors} hata buldu.", level="error")
        elif warnings:
            self.set_status(f"Özet ön kontrol {warnings} uyarı buldu.", level="warning")
        else:
            self.set_status("Özet ön kontrol temiz.", level="success")

    @perf_tracked("summary.refresh")
    def ozet_yenile(self, collect=True):
        if not hasattr(self, "ozet_metric_labels"):
            return
        if collect and hasattr(self, "e_kunye"):
            try:
                self.guncelle_veri_objesi()
            except Exception:
                pass

        kunye = self.veri.get("kunye", {})
        sondajlar = self.veri.get("sondaj", [])
        jeofizik = self.veri.get("jeofizik", {})
        ss_list = jeofizik.get("ss_list", [])
        mt_list = jeofizik.get("mt_list", [])
        jeo_sheet_summary = jeofizik_sheet_ozeti(self.veri)
        jeo_sheet_ok = bool(jeo_sheet_summary.get("ready"))

        total_depth = sum(safe_float(s.get("der")) for s in sondajlar)
        lit_count = sum(1 for s in sondajlar if s.get("litoloji"))
        spt_count = sum(len(s.get("spt", [])) for s in sondajlar)
        pmt_count = sum(len(s.get("pmt", [])) for s in sondajlar)
        kaya_count = sum(len(s.get("kaya", [])) for s in sondajlar)
        layer_count = sum(len(s.get("layers", [])) for s in ss_list)

        proje_adi = str(kunye.get("sahibi") or "").strip()
        self._ozet_set("proje", proje_adi or "Adsız proje", ok=bool(proje_adi))
        konum_parts = [kunye.get("il"), kunye.get("ilce"), kunye.get("mah")]
        konum_text = " / ".join([str(p).strip() for p in konum_parts if str(p or "").strip()])
        konum_ok = bool(str(kunye.get("il") or "").strip() and str(kunye.get("ilce") or "").strip())
        self._ozet_set("konum", konum_text or "Konum girilmemiş", ok=konum_ok)
        self._ozet_set("sondaj", f"{len(sondajlar)} adet, toplam {total_depth:.2f} m", ok=len(sondajlar) > 0 and total_depth > 0)
        self._ozet_set("litoloji", f"{lit_count}/{len(sondajlar)} sondajda litoloji var", ok=lit_count == len(sondajlar) and len(sondajlar) > 0)
        self._ozet_set("deney", f"SPT: {spt_count} | PMT: {pmt_count} | Kaya: {kaya_count}", ok=(spt_count + pmt_count + kaya_count) > 0)
        if jeo_sheet_ok:
            self._ozet_set("jeofizik", f"Sheet: {jeo_sheet_summary['serim']} serim | Tabaka: {jeo_sheet_summary['layers']}", ok=True)
        else:
            self._ozet_set("jeofizik", f"SS: {len(ss_list)} | MT: {len(mt_list)} | Tabaka: {layer_count}", ok=(len(ss_list) + len(mt_list)) > 0)

        file_map = {
            "word_path": self.word_path,
            "lab_excel_path": self.lab_excel_path,
            "jeo_excel_path": self.jeo_excel_path,
            "kml_path": self.kml_path,
            "img_yer": self.img_yer,
            "img_tkgm": self.img_tkgm,
            "img_pga": self.img_pga,
            "img_mjh": getattr(self, "img_mjh", None),
            "word_img_sondaj": self.word_img_sondaj,
            "word_img_jeofizik": self.word_img_jeofizik,
        }
        image_ready = sum(1 for path in [self.img_yer, self.img_tkgm, self.img_pga, getattr(self, "img_mjh", None) or self.img_yer or self.img_tkgm, self.word_img_sondaj, self.word_img_jeofizik] if path and os.path.exists(path))
        self._ozet_set("harita", f"{image_ready}/6 görsel hazır", ok=image_ready > 0)

        label_keys = {
            "word_path": "word", "lab_excel_path": "lab", "jeo_excel_path": "jeo", "kml_path": "kml",
            "img_yer": "yer", "img_tkgm": "tkgm", "img_pga": "pga", "img_mjh": "mjh",
            "word_img_sondaj": "sondaj_img", "word_img_jeofizik": "jeo_img",
        }
        lab_sheet_ready = self._lab_sheet_ready()
        for raw_key, path in file_map.items():
            if raw_key == "lab_excel_path" and lab_sheet_ready:
                rows = self.veri.get("lab_sheet", {}).get("rows", [])
                status = f"LAB Sheet hazır: {len(rows)} satır"
                self._ozet_file_set(label_keys[raw_key], status, True)
                continue
            if raw_key == "jeo_excel_path" and jeo_sheet_ok:
                status = f"Jeofizik Sheet hazır: {jeo_sheet_summary['serim']} serim"
                self._ozet_file_set(label_keys[raw_key], status, True)
                continue
            status, ok = self._dosya_durumu(path)
            self._ozet_file_set(label_keys[raw_key], status, ok)

        health = proje_saglik_ozeti(self.veri, file_map)
        self._saglik_paneli_guncelle(health)
        self._workflow_paneli_guncelle(health)
        self._final_dashboard_guncelle(health)
        self._ozet_preflight_guncelle()

    def _ozet_set(self, key, text, ok=True):
        label = self.ozet_metric_labels.get(key)
        color = COLOR_SUCCESS if ok else COLOR_WARNING
        bg = "#F3FBF6" if ok else "#FFF4E5"
        card = getattr(self, "ozet_metric_cards", {}).get(key)
        title = getattr(self, "ozet_metric_title_labels", {}).get(key)
        if card:
            card.config(bg=bg, highlightbackground=color, highlightcolor=color, highlightthickness=1)
        if title:
            title.config(bg=bg, fg=COLOR_PRIMARY)
        if label:
            label.config(text=text, fg=color, bg=bg)

    def _ozet_file_set(self, key, text, ok=True):
        label = self.ozet_file_labels.get(key)
        display_text = self._ozet_file_text_compact(text)
        if ok:
            color = COLOR_SUCCESS
            bg = "#F3FBF6"
        elif str(text).startswith("Bulunamadı"):
            color = COLOR_DANGER
            bg = "#FDEDEC"
        else:
            color = COLOR_WARNING
            bg = "#FFF4E5"
        card = getattr(self, "ozet_file_cards", {}).get(key)
        title = getattr(self, "ozet_file_title_labels", {}).get(key)
        if card:
            card.config(bg=bg, highlightbackground=color, highlightcolor=color, highlightthickness=1)
        if title:
            title.config(bg=bg, fg=COLOR_PRIMARY)
        if label:
            label.config(text=display_text, fg=color, bg=bg)

    def _ozet_file_text_compact(self, text, max_name_len=36):
        text = str(text or "")
        for prefix in ("Hazır: ", "Bulunamadı: ", "HazÄ±r: ", "BulunamadÄ±: "):
            if text.startswith(prefix):
                name = text[len(prefix):]
                if len(name) > max_name_len:
                    name = name[: max_name_len - 3] + "..."
                return prefix + name
        return text

    def _lab_sheet_ready(self):
        rows = self.veri.get("lab_sheet", {}).get("rows", []) if isinstance(getattr(self, "veri", None), dict) else []
        return any(any(str(cell).strip() for cell in row) for row in rows or [])

    def _jeofizik_sheet_ready(self):
        return jeofizik_sheet_var_mi(getattr(self, "veri", {})) and jeofizik_sheet_ozeti(getattr(self, "veri", {})).get("ready", False)

    def _dosya_durumu(self, path):
        if path and os.path.exists(path):
            return f"Hazır: {os.path.basename(path)}", True
        if path:
            return f"Bulunamadı: {os.path.basename(path)}", False
        return "Seçilmedi", False

    def _saglik_paneli_guncelle(self, health):
        if not hasattr(self, "health_status_label"):
            return
        score = health.get("score", 0)
        state = health.get("state", "-")
        color = COLOR_SUCCESS if score >= 85 else (COLOR_WARNING if score >= 60 else COLOR_DANGER)
        self.health_status_label.config(text=f"{state} - %{score}", fg=color)
        self.health_tag_actions = {}
        self.health_detail_text.config(state="normal")
        self.health_detail_text.delete("1.0", tk.END)
        self.health_detail_text.tag_configure("ok", foreground=COLOR_SUCCESS)
        self.health_detail_text.tag_configure("missing", foreground=COLOR_DANGER)
        self.health_detail_text.tag_configure("clickable", foreground="#1F618D", underline=True)
        for item in health.get("items", []):
            idx = len(self.health_tag_actions)
            row_tag = f"health_item_{idx}"
            mark = "OK" if item.get("ok") else "EKSİK"
            status_tag = "ok" if item.get("ok") else "missing"
            start = self.health_detail_text.index(tk.END)
            self.health_detail_text.insert(tk.END, f"{mark:<6} ", (status_tag, row_tag))
            self.health_detail_text.insert(tk.END, f"{item.get('label')}: ", ("clickable", row_tag))
            self.health_detail_text.insert(tk.END, f"{item.get('detail')}", (row_tag,))
            suggestion = item.get("suggestion")
            if suggestion and not item.get("ok"):
                self.health_detail_text.insert(tk.END, f" -> {suggestion}", ("clickable", row_tag))
            self.health_detail_text.insert(tk.END, "\n", (row_tag,))
            end = self.health_detail_text.index(tk.END)
            self.health_detail_text.tag_add(row_tag, start, end)
            self.health_tag_actions[row_tag] = item
        self.health_detail_text.config(state="disabled")

    def _health_detail_click(self, event):
        if not hasattr(self, "health_detail_text"):
            return
        tags = self.health_detail_text.tag_names(f"@{event.x},{event.y}")
        for tag in tags:
            if tag in getattr(self, "health_tag_actions", {}):
                self._health_item_git(self.health_tag_actions[tag])
                return "break"

    def _health_detail_motion(self, event):
        tags = self.health_detail_text.tag_names(f"@{event.x},{event.y}")
        cursor = "hand2" if any(tag in getattr(self, "health_tag_actions", {}) for tag in tags) else ""
        self.health_detail_text.config(cursor=cursor)

    def _health_item_git(self, item):
        target = item.get("target", "ozet")
        tab_map = {
            "ozet": "tab_ozet",
            "kunye": "tab_kunye",
            "bina": "tab_bina",
            "arazi": "tab_arazi",
            "sondaj": "tab_sondaj",
            "jeofizik": "tab_jeofizik",
            "rapor": "tab_rapor",
            "haritalar": "tab_haritalar",
        }
        tab_attr = tab_map.get(target)
        if tab_attr and hasattr(self, tab_attr):
            self.nb.select(getattr(self, tab_attr))
            self.set_status(f"{item.get('label')} için ilgili sekmeye gidildi.", level="info")
        elif target == "preflight":
            self.ozet_on_kontrol()
        else:
            self.set_status(item.get("suggestion") or item.get("detail") or "Sağlık kalemi seçildi.", level="info")

    def _preflight_target_for_message(self, message):
        text = str(message or "").lower()
        if any(key in text for key in ("proje adi", "il ", "ilce", "mahalle", "kunye", "kü nye", "künye")):
            return "kunye"
        if any(key in text for key in ("sondaj", "litoloji", "spt", "pmt", "kaya", "koordinat", "kuyu", "kesit")):
            return "sondaj"
        if any(key in text for key in ("jeofizik", "sismik", "mikrotremor", "masw", " vp", " vs", " mt", " ss")):
            return "jeofizik"
        if any(key in text for key in ("kml", "harita", "gorsel", "görsel", "resim", "yerbuldurur", "tkgm", "pga")):
            return "haritalar"
        if any(key in text for key in ("word", "sablon", "şablon", "lab excel", "excel")):
            return "rapor"
        return "ozet"

    def _insert_clickable_report(self, text_widget, report):
        text_widget.config(state="normal")
        text_widget.delete("1.0", tk.END)
        text_widget.tag_configure("section", foreground=COLOR_PRIMARY, font=("Consolas", 10, "bold"))
        text_widget.tag_configure("error", foreground=COLOR_DANGER)
        text_widget.tag_configure("warning", foreground=COLOR_WARNING)
        text_widget.tag_configure("info", foreground="#1F618D")
        text_widget.tag_configure("clickable", underline=True)
        action_map = {}
        counter = 0
        text_widget.insert(tk.END, "RAPOR ÖN KONTROL\n", "section")
        text_widget.insert(tk.END, "=" * 18 + "\n\n")
        for title, key, tag in (("HATALAR", "errors", "error"), ("UYARILAR", "warnings", "warning"), ("BILGI", "info", "info")):
            text_widget.insert(tk.END, f"{title}\n", "section")
            items = report.get(key, [])
            if not items:
                text_widget.insert(tk.END, "- Yok\n\n")
                continue
            for item in items:
                row_tag = f"preflight_item_{counter}"
                counter += 1
                start = text_widget.index(tk.END)
                text_widget.insert(tk.END, f"- {item}\n", (tag, "clickable", row_tag))
                end = text_widget.index(tk.END)
                text_widget.tag_add(row_tag, start, end)
                action_map[row_tag] = {"message": item, "target": self._preflight_target_for_message(item)}
            text_widget.insert(tk.END, "\n")
        text_widget._preflight_action_map = action_map
        text_widget.bind("<Button-1>", self._preflight_text_click)
        text_widget.bind("<Double-Button-1>", self._preflight_text_click)
        text_widget.bind("<Motion>", self._preflight_text_motion)
        text_widget.config(state="disabled")

    def _preflight_text_click(self, event):
        widget = event.widget
        action_map = getattr(widget, "_preflight_action_map", {})
        for tag in widget.tag_names(f"@{event.x},{event.y}"):
            if tag in action_map:
                self._preflight_item_git(action_map[tag])
                return "break"

    def _preflight_text_motion(self, event):
        widget = event.widget
        action_map = getattr(widget, "_preflight_action_map", {})
        cursor = "hand2" if any(tag in action_map for tag in widget.tag_names(f"@{event.x},{event.y}")) else ""
        widget.config(cursor=cursor)

    def _preflight_item_git(self, action):
        target = action.get("target", "ozet")
        self._workflow_git(target)
        self.set_status(action.get("message", "On kontrol kalemi secildi."), level="info")

    def _ozet_preflight_guncelle(self):
        if not hasattr(self, "ozet_preflight_text"):
            return
        if self.last_preflight_report:
            errors = len(self.last_preflight_report.get("errors", []) or [])
            warnings = len(self.last_preflight_report.get("warnings", []) or [])
            infos = len(self.last_preflight_report.get("info", []) or [])
            if errors:
                summary = f"{errors} hata, {warnings} uyarı"
                color = COLOR_DANGER
                role = "danger"
            elif warnings:
                summary = f"0 hata, {warnings} uyarı"
                color = COLOR_WARNING
                role = "warning"
            else:
                summary = f"Temiz | {infos} bilgi"
                color = COLOR_SUCCESS
                role = "success"
            if hasattr(self, "ozet_preflight_summary_label"):
                self.ozet_preflight_summary_label.config(text=summary, fg=color)
            if hasattr(self, "ozet_preflight_action_button"):
                self.configure_modern_button(self.ozet_preflight_action_button, text="Yenile", role=role, outline=True)
            self._insert_clickable_report(self.ozet_preflight_text, self.last_preflight_report)
        else:
            if hasattr(self, "ozet_preflight_summary_label"):
                self.ozet_preflight_summary_label.config(text="Ön kontrol bekliyor", fg="#555555")
            if hasattr(self, "ozet_preflight_action_button"):
                self.configure_modern_button(self.ozet_preflight_action_button, text="Çalıştır", role="warning", outline=True)
            self.ozet_preflight_text.config(state="normal")
            self.ozet_preflight_text.delete("1.0", tk.END)
            self.ozet_preflight_text.insert("1.0", "Ön kontrol henüz çalıştırılmadı.")
            self.ozet_preflight_text.config(state="disabled")

    def final_kontrol_satir_ekle(self, items, category, label, ok, detail, target="ozet", suggestion="", warning=False):
        level = "ok" if ok else ("warning" if warning else "error")
        items.append({
            "category": category,
            "label": label,
            "level": level,
            "detail": detail,
            "target": target,
            "suggestion": suggestion,
        })

    @perf_tracked("final_control.build")
    def final_kontrol_raporu_olustur(self):
        if hasattr(self, "e_kunye"):
            try:
                self.guncelle_veri_objesi(silent=True)
            except Exception as exc:
                log_exception("final_control.collect", exc_value=exc)

        file_map = self._dosya_map()
        health = proje_saglik_ozeti(self.veri, file_map)
        preflight = build_preflight_report(self)
        self.last_preflight_report = preflight

        items = []
        kunye = self.veri.get("kunye", {})
        sondajlar = self.veri.get("sondaj", []) or []
        jeofizik = self.veri.get("jeofizik", {}) or {}

        project_ok = bool(kunye.get("sahibi") and kunye.get("il") and kunye.get("ilce"))
        self.final_kontrol_satir_ekle(
            items, "1. Proje ve şablon", "Proje bilgisi", project_ok,
            "Proje adı, il ve ilçe tamam" if project_ok else "Proje adı, il veya ilçe eksik",
            "kunye", "Künye sekmesinde proje ve konum alanlarını tamamlayın.", warning=True,
        )

        word_ok = bool(self.word_path and os.path.exists(self.word_path))
        self.final_kontrol_satir_ekle(
            items, "1. Proje ve şablon", "Word şablonu", word_ok,
            os.path.basename(self.word_path) if word_ok else "Word şablonu seçilmedi veya bulunamadı",
            "rapor", "Rapor sekmesinden Word şablonu seçin.",
        )

        lab_sheet_ok = self._lab_sheet_ready()
        lab_ok = bool(self.lab_excel_path and os.path.exists(self.lab_excel_path))
        self.final_kontrol_satir_ekle(
            items, "1. Proje ve şablon", "Laboratuvar dosyası", lab_ok or lab_sheet_ok,
            "LAB Sheet hazır" if lab_sheet_ok else (os.path.basename(self.lab_excel_path) if lab_ok else "Lab Excel bağlı değil"),
            "rapor", "Laboratuvar verisi kullanılacaksa Rapor sekmesinden LAB Sheet doldurun veya Lab Excel seçin.", warning=True,
        )

        jeo_excel_ok = bool(self.jeo_excel_path and os.path.exists(self.jeo_excel_path))
        jeo_sheet_ok = self._jeofizik_sheet_ready()
        jeo_manual_ok = bool(jeofizik.get("ss_list") or jeofizik.get("mt_list"))
        self.final_kontrol_satir_ekle(
            items, "1. Proje ve şablon", "Jeofizik verisi", jeo_excel_ok or jeo_sheet_ok or jeo_manual_ok,
            "Jeofizik Sheet hazır" if jeo_sheet_ok else ("Jeofizik verisi hazır" if (jeo_excel_ok or jeo_manual_ok) else "Jeofizik Excel, Sheet veya manuel jeofizik verisi yok"),
            "jeofizik", "Jeofizik sekmesinden Sheet doldurun, Excel bağlayın veya manuel veri girin.", warning=True,
        )

        self.final_kontrol_satir_ekle(
            items, "2. Sondaj verisi", "Sondaj kaydı", len(sondajlar) > 0,
            f"{len(sondajlar)} sondaj var" if sondajlar else "Hiç sondaj yok",
            "sondaj", "Sondaj sekmesinden sondaj ekleyin veya workbook kullanın.",
        )

        invalid_depth = [s.get("no") or f"SK-{idx + 1}" for idx, s in enumerate(sondajlar) if safe_float(s.get("der")) <= 0]
        self.final_kontrol_satir_ekle(
            items, "2. Sondaj verisi", "Sondaj derinlikleri", not invalid_depth,
            "Tüm sondaj derinlikleri geçerli" if not invalid_depth else "Geçersiz derinlik: " + ", ".join(invalid_depth[:8]),
            "sondaj", "Sondaj derinliği alanlarını kontrol edin.",
        )

        missing_coords = [s.get("no") or f"SK-{idx + 1}" for idx, s in enumerate(sondajlar) if not (s.get("y") and s.get("x"))]
        self.final_kontrol_satir_ekle(
            items, "2. Sondaj verisi", "Koordinatlar", not missing_coords and bool(sondajlar),
            "Tüm sondaj koordinatları girilmiş" if not missing_coords and sondajlar else "Koordinatı eksik: " + (", ".join(missing_coords[:8]) if missing_coords else "sondaj yok"),
            "sondaj", "Sondaj koordinatlarını doldurun veya harita aracını kullanın.", warning=True,
        )

        missing_elev = [s.get("no") or f"SK-{idx + 1}" for idx, s in enumerate(sondajlar) if str(s.get("k") or "").strip() in ("", "-", "None", "null")]
        self.final_kontrol_satir_ekle(
            items, "2. Sondaj verisi", "Başlangıç kotları", not missing_elev and bool(sondajlar),
            "Tüm sondaj kotları girilmiş" if not missing_elev and sondajlar else "Kotu eksik: " + (", ".join(missing_elev[:8]) if missing_elev else "sondaj yok"),
            "sondaj", "Sondaj kotlarını doldurun.", warning=True,
        )

        missing_lit = [s.get("no") or f"SK-{idx + 1}" for idx, s in enumerate(sondajlar) if not s.get("litoloji")]
        self.final_kontrol_satir_ekle(
            items, "2. Sondaj verisi", "Litoloji", not missing_lit and bool(sondajlar),
            "Tüm sondajlarda litoloji var" if not missing_lit and sondajlar else "Litoloji eksik: " + (", ".join(missing_lit[:8]) if missing_lit else "sondaj yok"),
            "workbook", "Workbook Litoloji sayfasından eksik satırları tamamlayın.",
        )

        missing_spt = [s.get("no") or f"SK-{idx + 1}" for idx, s in enumerate(sondajlar) if not s.get("spt")]
        self.final_kontrol_satir_ekle(
            items, "2. Sondaj verisi", "SPT", not missing_spt and bool(sondajlar),
            "Tüm sondajlarda SPT var" if not missing_spt and sondajlar else "SPT eksik: " + (", ".join(missing_spt[:8]) if missing_spt else "sondaj yok"),
            "workbook", "Workbook SPT sayfasından SPT satırlarını üretin veya girin.", warning=True,
        )

        kesit_options = self.veri.get("kesit_ayarlari", {}) or {}
        selected_names = kesit_options.get("selected_sondajlar") or []
        selected = [s for s in sondajlar if s.get("no") in selected_names] if selected_names else sondajlar
        kesit_selected_ok = len(selected) >= 2
        self.final_kontrol_satir_ekle(
            items, "3. Kesit ve görseller", "Kesit seçimi", kesit_selected_ok,
            f"{len(selected)} sondaj kesit için hazır" if kesit_selected_ok else "Kesit için en az iki sondaj seçilmeli",
            "kesit", "Kesit seçim ekranından çizilecek sondajları seçin.", warning=True,
        )
        if kesit_selected_ok:
            section_report = build_section_quality_report(selected, kesit_options)
            section_errors = len(section_report.get("errors", []))
            section_warnings = len(section_report.get("warnings", []))
            self.final_kontrol_satir_ekle(
                items, "3. Kesit ve görseller", "Kesit kalite", section_errors == 0,
                f"{section_errors} hata, {section_warnings} uyarı" if (section_errors or section_warnings) else "Kesit kalite kontrol temiz",
                "kesit", "Kesit kalite penceresinden detayları kontrol edin.", warning=section_errors == 0 and section_warnings > 0,
            )

        visual_sources = [
            ("Yerbuldurur", self.img_yer),
            ("TKGM", self.img_tkgm),
            ("PGA", self.img_pga),
            ("MJH", getattr(self, "img_mjh", None) or self.img_yer or self.img_tkgm),
            ("Sondaj haritası", self.word_img_sondaj),
            ("Jeofizik haritası", self.word_img_jeofizik),
        ]
        missing_visuals = [label for label, path in visual_sources if not (path and os.path.exists(path))]
        self.final_kontrol_satir_ekle(
            items, "3. Kesit ve görseller", "Rapor görselleri", not missing_visuals,
            "Tüm rapor görselleri hazır" if not missing_visuals else "Eksik görsel: " + ", ".join(missing_visuals[:8]),
            "haritalar", "Haritalar/Rapor sekmesinden eksik görselleri bağlayın.", warning=True,
        )

        output_folder = self.veri.get("ayarlar", {}).get("cikti_merkezi_klasor") or self.veri.get("ayarlar", {}).get("varsayilan_cikti_klasor")
        output_ok = bool(output_folder and os.path.isdir(output_folder))
        self.final_kontrol_satir_ekle(
            items, "4. Rapor ve çıktı", "Çıktı klasörü", output_ok,
            output_folder if output_ok else "Çıktı Merkezi klasörü seçilmemiş",
            "cikti", "Çıktı Merkezi'nden ana çıktı klasörünü seçin.", warning=True,
        )

        preflight_errors = len(preflight.get("errors", []))
        preflight_warnings = len(preflight.get("warnings", []))
        self.final_kontrol_satir_ekle(
            items, "4. Rapor ve çıktı", "Rapor ön kontrol", preflight_errors == 0,
            f"{preflight_errors} hata, {preflight_warnings} uyarı" if (preflight_errors or preflight_warnings) else "Ön kontrol temiz",
            "preflight", "Rapor Ön Kontrol ekranında detayları inceleyin.", warning=preflight_errors == 0 and preflight_warnings > 0,
        )

        errors = sum(1 for item in items if item["level"] == "error")
        warnings = sum(1 for item in items if item["level"] == "warning")
        score = max(0, min(100, int(health.get("score", 0)) - errors * 8 - warnings))
        if errors:
            state = "EKSİKLER VAR"
        elif warnings:
            state = "UYARILI HAZIR"
        else:
            state = "RAPORA HAZIR"
        return {
            "state": state,
            "score": score,
            "errors": errors,
            "warnings": warnings,
            "items": items,
            "health": health,
            "preflight": preflight,
        }

    def final_kontrol_penceresi(self):
        win = Toplevel(self.root)
        self.pencere_hazirla(win, "Final Proje Kontrolü", "940x660", (780, 520), modal=True)

        header = ttk.Frame(win, padding=(12, 10, 12, 6))
        header.pack(fill="x")
        status_var = tk.StringVar(value="Kontrol hazırlanıyor...")
        status_label = tk.Label(header, textvariable=status_var, bg=COLOR_BG, fg="#333333", font=("Segoe UI", 13, "bold"), anchor="w")
        status_label.pack(side="left", fill="x", expand=True)

        body = ttk.Frame(win, padding=(12, 0, 12, 8))
        body.pack(fill="both", expand=True)
        txt = tk.Text(body, wrap="word", font=("Consolas", 10), bg="#FAFAFA")
        scroll = ttk.Scrollbar(body, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=scroll.set)
        txt.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        btns = ttk.Frame(win, padding=(12, 0, 12, 12))
        btns.pack(fill="x")

        def refresh():
            report = self.final_kontrol_raporu_olustur()
            color = COLOR_SUCCESS if report["errors"] == 0 and report["warnings"] == 0 else (COLOR_WARNING if report["errors"] == 0 else COLOR_DANGER)
            status_label.config(fg=color)
            status_var.set(f"{report['state']} - %{report['score']} | {report['errors']} hata, {report['warnings']} uyarı")
            self.final_kontrol_text_doldur(txt, report)
            self.ozet_yenile(collect=False)

        tk.Button(btns, text="Yenile", command=refresh, bg="#ECF0F1", font=FONT_BOLD).pack(side="left", padx=(0, 5))
        tk.Button(btns, text="Ön Kontrol", command=self.rapor_on_kontrol, bg=COLOR_WARNING, fg="white", font=FONT_BOLD).pack(side="left", padx=5)
        tk.Button(btns, text="Çıktı Merkezi", command=self.cikti_merkezi_penceresi, bg="#117A65", fg="white", font=FONT_BOLD).pack(side="left", padx=5)
        tk.Button(btns, text="Raporu Oluştur", command=self.raporla, bg=COLOR_SUCCESS, fg="white", font=FONT_BOLD).pack(side="left", padx=5)
        tk.Button(btns, text="Kapat", command=win.destroy, bg="#ECF0F1", font=FONT_BOLD).pack(side="right")
        refresh()

    def final_kontrol_text_doldur(self, text_widget, report):
        text_widget.config(state="normal")
        text_widget.delete("1.0", tk.END)
        text_widget.tag_configure("header", foreground=COLOR_PRIMARY, font=("Consolas", 11, "bold"))
        text_widget.tag_configure("ok", foreground=COLOR_SUCCESS)
        text_widget.tag_configure("warning", foreground=COLOR_WARNING)
        text_widget.tag_configure("error", foreground=COLOR_DANGER)
        text_widget.tag_configure("clickable", underline=True)
        action_map = {}
        counter = 0

        text_widget.insert(tk.END, "FINAL PROJE KONTROLÜ\n", "header")
        text_widget.insert(tk.END, "=" * 24 + "\n")
        text_widget.insert(tk.END, f"Durum: {report['state']} | Puan: %{report['score']} | Hata: {report['errors']} | Uyarı: {report['warnings']}\n\n")

        current_category = None
        marks = {"ok": "OK", "warning": "UYARI", "error": "HATA", "info": "BİLGİ"}
        for item in report.get("items", []):
            category = item.get("category", "Kontrol")
            if category != current_category:
                current_category = category
                text_widget.insert(tk.END, f"\n{category}\n", "header")
            row_tag = f"final_control_item_{counter}"
            counter += 1
            level = item.get("level", "info")
            mark = marks.get(level, "BİLGİ")
            start = text_widget.index(tk.END)
            text_widget.insert(tk.END, f"{mark:<6} ", (level, row_tag))
            text_widget.insert(tk.END, f"{item.get('label')}: ", ("clickable", row_tag))
            text_widget.insert(tk.END, f"{item.get('detail')}", (row_tag,))
            if item.get("suggestion") and level != "ok":
                text_widget.insert(tk.END, f" -> {item.get('suggestion')}", ("clickable", row_tag))
            text_widget.insert(tk.END, "\n", (row_tag,))
            end = text_widget.index(tk.END)
            text_widget.tag_add(row_tag, start, end)
            action_map[row_tag] = item

        text_widget._final_control_action_map = action_map
        text_widget.bind("<Button-1>", self.final_kontrol_text_click)
        text_widget.bind("<Double-Button-1>", self.final_kontrol_text_click)
        text_widget.bind("<Motion>", self.final_kontrol_text_motion)
        text_widget.config(state="disabled")

    def final_kontrol_text_click(self, event):
        widget = event.widget
        action_map = getattr(widget, "_final_control_action_map", {})
        for tag in widget.tag_names(f"@{event.x},{event.y}"):
            if tag in action_map:
                self.final_kontrol_item_git(action_map[tag])
                return "break"

    def final_kontrol_text_motion(self, event):
        widget = event.widget
        action_map = getattr(widget, "_final_control_action_map", {})
        cursor = "hand2" if any(tag in action_map for tag in widget.tag_names(f"@{event.x},{event.y}")) else ""
        widget.config(cursor=cursor)

    def final_kontrol_item_git(self, item):
        target = item.get("target", "ozet")
        if target == "workbook":
            self.veri_giris_workbook_tksheet_ac()
        elif target == "preflight":
            self.rapor_on_kontrol()
        elif target == "kesit":
            self.kesit_secim_penceresi()
        elif target == "cikti":
            self.cikti_merkezi_penceresi()
        else:
            self._workflow_git(target)
        self.set_status(item.get("suggestion") or item.get("detail") or "Final kontrol kalemi seçildi.", level="info")
