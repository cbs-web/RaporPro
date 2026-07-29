# Dosya: RaporPro/motor_kesit.py
import math
from datetime import datetime
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
import matplotlib.patches as mpatches
import textwrap

from kesit_motor_ayarlari import KESIT_ENGINE_DEFAULT, kesit_motoru_normalize

from sabitler import (
    A4_LANDSCAPE_SIZE,
    LEJANTLAR,
    SECTION_AXES_RECT,
    SECTION_FIGURE_DPI,
)
from yardimcilar import safe_float, haversine_distance, litoloji_cozumle
from cizim import GeoEngineDraw
from kesit_baski import (
    kesit_baski_yerlesimi,
    kesit_cok_sayfa_plani,
    kesit_dusey_abarti,
    kesit_sayfa_boyutu,
)
from performans import log_exception

from motor_interaktif import GeoInteractiveTool
from kesit_korelasyon import (
    build_semantic_lens_tracks,
    build_section_correlations,
    normalize_section_layers,
    turkce_buyuk_harf,
)
from kesit_topografya import (
    topografya_profili_hazirla,
    topografya_profili_ornekle,
    topografya_yuzey_egrisi,
    yuzeye_uyumlu_tabaka_poligonu,
)


class GeoEngineKesitMixin:
    @staticmethod
    def kesit_ciz_interaktif(sondajlar, log_callback=None, options=None):
        if not sondajlar: return Figure(), []
        options = options or {}
        sondajlar = list(sondajlar)
        
        # --- AYARLAR ---
        def option_bool(name, default=True):
            value = options.get(name, default)
            return str(value).lower() not in ("0", "false", "no", "off", "hayir", "hayır")

        TARAMA_SIKLIGI_KESIT = safe_float(options.get("section_pattern_density", 10.0)) or 10.0
        TARAMA_SIKLIGI_LEJANT = safe_float(options.get("legend_pattern_density", 6.0)) or 6.0
        MARGIN = safe_float(options.get("plot_margin", 10.0)) or 10.0
        dx_default = safe_float(options.get("dx_default", 25.0)) or 25.0
        mode = options.get("mode", "schematic")
        use_line_projection = mode == "line_projection"
        use_true_distance = mode == "true_distance"
        use_distance_axis = use_true_distance or use_line_projection
        print_scale_enabled = option_bool("print_scale_enabled", False)
        print_page_size = str(options.get("print_page_size", "A4 Yatay") or "A4 Yatay")
        horizontal_scale = safe_float(options.get("horizontal_scale", 500.0)) or 500.0
        vertical_scale = safe_float(options.get("vertical_scale", 100.0)) or 100.0
        print_auto_fit = option_bool("print_auto_fit", True)
        print_title_block = option_bool("print_title_block", True)
        print_multi_page = option_bool("print_multi_page", True)
        print_page_overlap = safe_float(options.get("print_page_overlap", 5.0)) or 5.0
        vertical_exaggeration = safe_float(options.get("vertical_exaggeration", 1.0)) or 1.0
        if print_scale_enabled:
            vertical_exaggeration = kesit_dusey_abarti(horizontal_scale, vertical_scale)
        if vertical_exaggeration <= 0:
            vertical_exaggeration = 1.0
        corr_tolerance = safe_float(options.get("corr_tolerance", 0.0))
        max_offset = safe_float(options.get("max_offset", 10.0))
        show_consistency_labels = option_bool("show_consistency_labels", True)
        show_station_offset_labels = option_bool("show_station_offset_labels", True)
        show_well_elevation_labels = option_bool("show_well_elevation_labels", True)
        show_layer_depth_labels = option_bool("show_layer_depth_labels", True)
        show_distance_labels = option_bool("show_distance_labels", True)
        show_legend = option_bool("show_legend", True)
        show_yass = option_bool("show_yass", True)
        show_yass_labels = option_bool("show_yass_labels", True)
        show_topography_profile = option_bool("show_topography_profile", False)
        conform_layers_to_topography = option_bool("conform_layers_to_topography", True)
        topography_source = str(options.get("topography_source", "sondaj") or "sondaj").strip().lower()
        avoid_label_collisions = option_bool("avoid_label_collisions", True)
        hide_same_unit_seams = option_bool("hide_same_unit_seams", True)
        auto_lens = option_bool("auto_lens", True)
        two_well_lens = option_bool("two_well_lens", True)
        section_engine = kesit_motoru_normalize(
            options.get("section_engine", KESIT_ENGINE_DEFAULT)
        )
        use_correlation_v2 = section_engine == "v2"
        show_detailed_lithology_labels = option_bool(
            "show_detailed_lithology_labels",
            False,
        )
        title_mode = str(options.get("title_mode", "full")).lower()
        well_width = safe_float(options.get("well_width", 2.0)) or 2.0
        legend_scale = safe_float(options.get("legend_scale", 1.0)) or 1.0
        facies_overlap_min = safe_float(options.get("facies_overlap_min", 0.1)) or 0.1
        zigzag_width_ratio = safe_float(options.get("zigzag_width_ratio", 0.03)) or 0.03
        lens_max_thickness = safe_float(options.get("lens_max_thickness", 2.0)) or 2.0
        lens_closure_ratio = safe_float(options.get("lens_closure_ratio", 0.58)) or 0.58
        lens_closure_ratio = max(0.20, min(0.90, lens_closure_ratio))
        manual_edits = options.get("manual_edits") or options.get("manual_polygons") or {}
        if not isinstance(manual_edits, dict):
            manual_edits = {}
        label_min_height = safe_float(options.get("consistency_label_min_height", 0.9)) or 0.9
        consistency_font_max = safe_float(options.get("consistency_label_font_max", 8.4)) or 8.4
        consistency_font_min = safe_float(options.get("consistency_label_font_min", 5.0)) or 5.0
        if consistency_font_max < consistency_font_min:
            consistency_font_max = consistency_font_min
        spt_label_search_margin = safe_float(options.get("spt_label_search_margin", 1.5)) or 1.5
        # ---------------

        def pattern_density_for_code(code, base_density, legend=False):
            code = str(code or "").lower()
            if not legend:
                override_key = {
                    "kl": "clay_pattern_density",
                    "s": "silt_pattern_density",
                    "k": "sand_pattern_density",
                    "c": "gravel_pattern_density",
                }.get(code)
                override = safe_float(options.get(override_key)) if override_key else 0
                if override > 0:
                    return override
            multiplier = 1.0
            if code == "k":
                multiplier = 1.45
            elif code == "c":
                multiplier = 1.60
            if legend:
                multiplier = max(1.0, multiplier * 0.92)
            return base_density * multiplier

        def set_artist_zorder(artists, zorder):
            for artist in artists or []:
                try:
                    artist.set_zorder(zorder)
                except Exception:
                    pass

        def get_zigzag_verts(x, y_top, y_bot, width):
            pts = []
            y_high, y_low = (y_top, y_bot) if y_top > y_bot else (y_bot, y_top)
            dist = abs(y_high - y_low)
            if dist < 0.1: return [(x, y_high), (x, y_low)]
            num_teeth = max(2, int(dist / 0.75)) 
            ys = np.linspace(y_high, y_low, num_teeth * 2 + 1)
            for i, y in enumerate(ys):
                if i == 0 or i == len(ys) - 1: pts.append((x, y))
                elif i % 2 == 1: pts.append((x + width, y))
                else: pts.append((x - width, y))
            return pts

        def has_coords(s):
            y, x = safe_float(s.get("y")), safe_float(s.get("x"))
            return y != 0 and x != 0

        def parse_yass_depth(s):
            for key in ("yass_d2", "yass_d1"):
                raw = str(s.get(key, "") or "").strip()
                if not raw or raw.lower() in ("-", "yok", "none", "nan", "null"):
                    continue
                depth = safe_float(raw)
                if depth < 0:
                    continue
                return depth, key
            return None, None

        def parse_spt_n30(row):
            if not row:
                return None

            depth = safe_float(row[0])
            vals = [str(v).strip() for v in row[1:5]]
            vals_lower = [v.lower() for v in vals]
            refused = any(v == "r" or v == "-" or "refu" in v or "ref" in v or "50/" in v for v in vals_lower)
            if refused:
                return {"depth": depth, "n30": None, "refused": True}

            n30_text = vals[3] if len(vals) > 3 else ""
            n30 = safe_float(n30_text)
            if n30 > 0 or n30_text.replace(",", ".") in ("0", "0.0"):
                return {"depth": depth, "n30": n30, "refused": False}

            if len(row) > 3:
                calculated = safe_float(row[2]) + safe_float(row[3])
                if calculated > 0:
                    return {"depth": depth, "n30": calculated, "refused": False}
            return {"depth": depth, "n30": None, "refused": False}

        def classify_consistency(code, n30=None, refused=False):
            if code in ("kl", "s"):
                if refused:
                    return "Sert"
                if n30 is None:
                    return ""
                if n30 < 2: return "Çok yumuşak"
                if n30 < 4: return "Yumuşak"
                if n30 < 8: return "Orta katı"
                if n30 < 15: return "Katı"
                if n30 < 30: return "Çok katı"
                return "Sert"

            if code in ("k", "c"):
                if refused:
                    return "Çok sıkı"
                if n30 is None:
                    return ""
                if n30 < 4: return "Çok gevşek"
                if n30 < 10: return "Gevşek"
                if n30 < 30: return "Orta sıkı"
                if n30 < 50: return "Sıkı"
                return "Çok sıkı"

            return ""

        def consistency_label_for_layer(sondaj, layer):
            code = layer.get("code")
            if code not in ("kl", "s", "k", "c"):
                return ""

            top = safe_float(layer.get("top"))
            bot = safe_float(layer.get("bot"))
            mid = (top + bot) / 2
            thickness = abs(bot - top)
            n_values = []
            has_refusal = False
            parsed_rows = []

            for spt_row in sondaj.get("spt", []):
                parsed = parse_spt_n30(spt_row)
                if not parsed:
                    continue
                parsed_rows.append(parsed)
                depth = parsed["depth"]
                if depth < top - 0.01 or depth > bot + 0.01:
                    continue
                if parsed["refused"]:
                    has_refusal = True
                elif parsed["n30"] is not None:
                    n_values.append(parsed["n30"])

            if has_refusal:
                return classify_consistency(code, refused=True)
            if n_values:
                return classify_consistency(code, n30=float(np.median(n_values)))

            parsed_rows = sorted(parsed_rows, key=lambda item: item["depth"])
            if parsed_rows:
                last_spt = parsed_rows[-1]
                if last_spt["refused"] and top >= last_spt["depth"] - 0.01:
                    return classify_consistency(code, refused=True)

            # Tabakanin icinde SPT yoksa, ayni sondajdaki en yakin SPT'yi kullan.
            # Bu, ozellikle ince tabakalarda veya SPT derinligi sinira denk geldiginde bos etiket kalmasini azaltir.
            nearest = None
            nearest_dist = None
            max_dist = max(spt_label_search_margin, thickness / 2)
            for parsed in parsed_rows:
                dist = abs(parsed["depth"] - mid)
                if dist <= max_dist and (nearest_dist is None or dist < nearest_dist):
                    nearest = parsed
                    nearest_dist = dist
            if nearest:
                if nearest["refused"]:
                    return classify_consistency(code, refused=True)
                if nearest["n30"] is not None:
                    return classify_consistency(code, n30=float(nearest["n30"]))
            return ""

        def consistency_labels_for_layer(sondaj, layer):
            code = layer.get("code")
            if code not in ("kl", "s", "k", "c"):
                return []

            top = safe_float(layer.get("top"))
            bot = safe_float(layer.get("bot"))
            mid = (top + bot) / 2
            parsed_labels = []

            for spt_row in sondaj.get("spt", []):
                parsed = parse_spt_n30(spt_row)
                if not parsed:
                    continue
                depth = parsed["depth"]
                if depth < top - 0.01 or depth > bot + 0.01:
                    continue
                if parsed["refused"]:
                    label = classify_consistency(code, refused=True)
                elif parsed["n30"] is not None:
                    label = classify_consistency(code, n30=float(parsed["n30"]))
                else:
                    label = ""
                if label:
                    parsed_labels.append({"label": label, "depth": depth, "source": "spt"})

            parsed_labels.sort(key=lambda item: item["depth"])
            if parsed_labels:
                grouped = []
                current = {"label": parsed_labels[0]["label"], "depths": [parsed_labels[0]["depth"]]}
                for item in parsed_labels[1:]:
                    if item["label"] == current["label"]:
                        current["depths"].append(item["depth"])
                    else:
                        grouped.append(current)
                        current = {"label": item["label"], "depths": [item["depth"]]}
                grouped.append(current)
                records = []
                for group in grouped:
                    depths = group["depths"]
                    records.append({
                        "label": group["label"],
                        "depth": float(np.median(depths)) if depths else mid,
                        "source": "spt",
                    })
                return records

            fallback = consistency_label_for_layer(sondaj, layer)
            if fallback:
                return [{"label": fallback, "depth": mid, "source": "fallback"}]
            return []

        def consistency_label_positions(records, layer, y_top, y_bot, top_elevation):
            if not records:
                return []
            high_y = max(y_top, y_bot)
            low_y = min(y_top, y_bot)
            layer_height = abs(high_y - low_y)
            if layer_height <= 0:
                return []
            top_pad = min(0.42, max(0.16, layer_height * 0.16))
            bottom_pad = min(0.28, max(0.10, layer_height * 0.12))
            if layer_height < 0.70:
                top_pad = layer_height * 0.22
                bottom_pad = layer_height * 0.16
            usable_high = high_y - top_pad
            usable_low = low_y + bottom_pad
            if usable_high < usable_low:
                usable_high = high_y
                usable_low = low_y

            positioned = []
            for record in sorted(records, key=lambda item: item.get("depth", 0)):
                if record.get("source") == "fallback":
                    y = usable_high
                else:
                    y = top_elevation - safe_float(record.get("depth"))
                y = max(usable_low, min(usable_high, y))
                positioned.append({"label": record["label"], "y": y, "source": record.get("source", "spt")})

            if len(positioned) <= 1:
                return positioned

            available = max(0.0, usable_high - usable_low)
            min_gap = min(0.55, max(0.28, layer_height / max(len(positioned), 1) * 0.55))
            if available < min_gap * (len(positioned) - 1):
                ys = np.linspace(usable_high, usable_low, len(positioned))
                for item, y in zip(positioned, ys):
                    item["y"] = float(y)
                return positioned

            last_y = None
            for item in positioned:
                if last_y is not None and last_y - item["y"] < min_gap:
                    item["y"] = last_y - min_gap
                last_y = item["y"]
            if positioned[-1]["y"] < usable_low:
                shift = usable_low - positioned[-1]["y"]
                for item in positioned:
                    item["y"] = min(usable_high, item["y"] + shift)
            return positioned

        def wrap_consistency_label(label):
            label = str(label).upper()
            parts = label.split()
            if len(parts) <= 1:
                return label
            return "\n".join(parts)

        def preferred_consistency_font(label, layer_height, label_count):
            wrapped = wrap_consistency_label(label)
            line_count = max(1, len(wrapped.splitlines()))
            fs = consistency_font_max
            if label_count > 1:
                fs -= min(1.4, (label_count - 1) * 0.45)
            if line_count > 1:
                fs -= 0.25
            if layer_height < label_min_height:
                fs = min(fs, 6.6)
            if layer_height < 0.55:
                fs = min(fs, 5.6)
            return max(consistency_font_min, min(consistency_font_max, fs))

        def get_coords(s):
            y, x = safe_float(s.get("y")), safe_float(s.get("x"))
            if y == 0 or x == 0:
                return None
            return y, x

        def build_line_projector(start_y, start_x, end_y, end_x):
            lat0_rad = math.radians(start_y)
            meters_per_lat = 111320.0
            meters_per_lon = 111320.0 * math.cos(lat0_rad)

            def to_local(y, x):
                return (x - start_x) * meters_per_lon, (y - start_y) * meters_per_lat

            end_lx, end_ly = to_local(end_y, end_x)
            line_len = math.hypot(end_lx, end_ly)
            if line_len <= 0.01:
                raise ValueError("kesit hatti baslangic ve bitis koordinatlari ayni")
            ux, uy = end_lx / line_len, end_ly / line_len

            def project(y, x):
                px, py = to_local(y, x)
                station = px * ux + py * uy
                offset = px * (-uy) + py * ux
                return station, offset

            return line_len, project

        project_to_line = None
        try:
            if use_line_projection:
                start_y = safe_float(options.get("line_start_y"))
                start_x = safe_float(options.get("line_start_x"))
                end_y = safe_float(options.get("line_end_y"))
                end_x = safe_float(options.get("line_end_x"))

                if start_y == 0 or start_x == 0 or end_y == 0 or end_x == 0:
                    first_coords = get_coords(sondajlar[0])
                    last_coords = get_coords(sondajlar[-1])
                    if not first_coords or not last_coords:
                        raise ValueError("kesit hatti icin koordinat bulunamadi")
                    start_y, start_x = first_coords
                    end_y, end_x = last_coords

                _, project_to_line = build_line_projector(start_y, start_x, end_y, end_x)
                projected = []

                for i, s in enumerate(sondajlar):
                    s["_kot"] = safe_float(s.get("k", 100.0))
                    coords = get_coords(s)
                    if coords:
                        station, offset = project_to_line(coords[0], coords[1])
                        if max_offset > 0 and abs(offset) > max_offset and log_callback:
                            log_callback(f"{s.get('no','SK')} kesit hattindan {abs(offset):.1f} m uzakta.", "warning")
                    else:
                        station, offset = i * dx_default, 0.0
                        if log_callback:
                            log_callback(f"{s.get('no','SK')} koordinati eksik; kesit hattinda varsayilan station kullanildi.", "warning")
                    s["_station"] = station
                    s["_offset"] = offset
                    s["_plot_x"] = station if print_scale_enabled else station / vertical_exaggeration
                    projected.append(s)

                sondajlar = sorted(projected, key=lambda item: (item.get("_station", 0.0), item.get("no", "")))
                for i, s in enumerate(sondajlar):
                    if i < len(sondajlar) - 1:
                        s["_true_dist"] = abs(sondajlar[i+1].get("_station", 0.0) - s.get("_station", 0.0))
                    else:
                        s["_true_dist"] = 0.0
            else:
                cumulative_dist = 0.0
                for i, s in enumerate(sondajlar):
                    s["_kot"] = safe_float(s.get("k", 100.0))
                    if i == 0:
                        s["_plot_x"] = 0.0
                    else:
                        if use_true_distance:
                            s["_plot_x"] = cumulative_dist if print_scale_enabled else cumulative_dist / vertical_exaggeration
                        else:
                            s["_plot_x"] = i * dx_default

                    if i < len(sondajlar) - 1:
                        s_next = sondajlar[i+1]
                        y1, x1 = safe_float(s.get("y")), safe_float(s.get("x"))
                        y2, x2 = safe_float(s_next.get("y")), safe_float(s_next.get("x"))
                        if has_coords(s) and has_coords(s_next):
                            true_dist = haversine_distance(y1, x1, y2, x2)
                        else:
                            true_dist = dx_default
                            if use_true_distance and log_callback:
                                log_callback(f"{s.get('no','SK')} - {s_next.get('no','SK')} arasinda koordinat eksik; varsayilan mesafe kullanildi.", "warning")
                        s["_true_dist"] = true_dist
                        cumulative_dist += true_dist
        except Exception as exc:
            if log_callback:
                log_callback(f"Kesit mesafe hesabi yapilamadi, sematik aralik kullanildi: {exc}", "warning")
            for i, s in enumerate(sondajlar): 
                s["_kot"] = safe_float(s.get("k", 100.0))
                s["_plot_x"] = i * dx_default
                s["_true_dist"] = dx_default
        
        _, print_figure_size = kesit_sayfa_boyutu(print_page_size)
        fig = Figure(
            figsize=print_figure_size if print_scale_enabled else A4_LANDSCAPE_SIZE,
            dpi=SECTION_FIGURE_DPI,
        )
        ax = fig.add_axes(SECTION_AXES_RECT) 
        if use_line_projection:
            start_no = options.get("line_start_no", "Baslangic")
            end_no = options.get("line_end_no", "Bitis")
            mode_label = f"Kesit hatti: {start_no} - {end_no}"
        elif use_true_distance:
            mode_label = "Gercek mesafe"
        else:
            mode_label = "Sematik"
        ax._geo_title_simple = "Jeolojik Kesit"
        ax._geo_title_full = f"Jeolojik Kesit ({mode_label}, D.A. x{vertical_exaggeration:g})"
        if title_mode == "none":
            ax.set_title("")
        elif title_mode == "simple":
            ax.set_title(ax._geo_title_simple, fontsize=12, fontweight='bold')
        else:
            ax.set_title(ax._geo_title_full, fontsize=12, fontweight='bold')
        
        if use_distance_axis:
            ax.tick_params(axis='x', which='both', bottom=True, top=False, labelbottom=True)
            distance_label_factor = 1.0 if print_scale_enabled else vertical_exaggeration
            ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, pos: f"{x * distance_label_factor:g}"))
            axis_label = "Kesit hatti station (m)" if use_line_projection else "Kesit boyunca gercek mesafe (m)"
            ax.set_xlabel(axis_label, fontsize=9)
        else:
            ax.tick_params(axis='x', which='both', bottom=False, top=False, labelbottom=False)
        ax.yaxis.set_ticks_position('both'); ax.tick_params(axis='y', which='both', labelleft=True, labelright=True)
        ax.set_ylabel("Kot (m)", fontsize=10)
        w_well = well_width
        
        xs, ys = [s["_plot_x"] for s in sondajlar], [s["_kot"] for s in sondajlar]

        topography_x = list(xs)
        topography_y = list(ys)
        topography_info = {
            "points": [
                {"station": x, "elevation": y}
                for x, y in zip(xs, ys)
            ],
            "source": "sondaj",
            "warning": "",
        }
        station_scale = (
            1.0
            if print_scale_enabled or not use_distance_axis
            else 1.0 / vertical_exaggeration
        )
        if show_topography_profile:
            topography_info = topografya_profili_hazirla(
                source=topography_source,
                manual_points=options.get("topography_points") or [],
                coordinate_points=options.get("topography_coordinate_points") or [],
                borehole_points=[
                    {"station": x, "elevation": y}
                    for x, y in zip(xs, ys)
                ],
                project_to_line=project_to_line,
                station_scale=station_scale,
            )
            topography_x, topography_y = topografya_profili_ornekle(
                topography_info.get("points") or []
            )
            if topography_info.get("warning") and log_callback:
                log_callback(topography_info["warning"], "warning")
        
        full_min_x_plot = xs[0] - MARGIN
        full_max_x_plot = xs[-1] + MARGIN
        min_x_plot = full_min_x_plot
        max_x_plot = full_max_x_plot
        try:
            requested_x_min = float(options.get("print_x_min"))
            requested_x_max = float(options.get("print_x_max"))
        except (TypeError, ValueError):
            requested_x_min = None
            requested_x_max = None
        has_print_window = (
            print_scale_enabled
            and requested_x_min is not None
            and requested_x_max is not None
            and requested_x_max > requested_x_min
        )
        if has_print_window:
            min_x_plot = requested_x_min
            max_x_plot = requested_x_max
        
        if show_topography_profile and len(topography_x) >= 2:
            surface_line, = ax.plot(
                topography_x,
                topography_y,
                color="#202020",
                linestyle="-",
                lw=1.8,
                alpha=0.95,
                zorder=30,
            )
        else:
            surface_line = None
            try:
                from scipy.interpolate import make_interp_spline
                if len(xs) >= 3:
                    xs_arr, ys_arr = np.array(xs), np.array(ys); sort_idx = np.argsort(xs_arr)
                    ux, idx = np.unique(xs_arr[sort_idx], return_index=True); uy = ys_arr[sort_idx][idx]
                    if len(ux) >= 3:
                        spline_degree = min(3, len(ux) - 1)
                        X_ = np.linspace(ux.min(), ux.max(), 100); Y_ = make_interp_spline(ux, uy, k=spline_degree)(X_)
                        surface_line, = ax.plot(X_, Y_, 'k--', lw=1.5, alpha=0.8, zorder=30)
                    else:
                        surface_line, = ax.plot(xs, ys, 'k--', lw=1.5, alpha=0.8, zorder=30)
                else:
                    surface_line, = ax.plot(xs, ys, 'k--', lw=1.5, alpha=0.8, zorder=30)
            except Exception as exc:
                log_exception("motor.section_surface_spline", exc_value=exc)
                surface_line, = ax.plot(xs, ys, 'k--', lw=1.5, alpha=0.8, zorder=30)
        if surface_line is not None:
            surface_line._geo_live_group = "topography"
        
        yass_points = []
        if show_yass:
            for s in sondajlar:
                yass_depth, yass_key = parse_yass_depth(s)
                if yass_depth is None:
                    continue
                der = safe_float(s.get("der", 15))
                if der > 0 and yass_depth > der + 0.01:
                    if log_callback:
                        log_callback(f"{s.get('no','SK')} YASS derinligi kuyu derinliginden buyuk; kesitte gosterilmedi.", "warning")
                    continue
                yass_points.append({
                    "sondaj": s,
                    "no": s.get("no", "SK"),
                    "x": s["_plot_x"],
                    "depth": yass_depth,
                    "source": yass_key,
                    "elevation": s["_kot"] - yass_depth,
                })

        all_y = [s["_kot"] for s in sondajlar] + [s["_kot"] - safe_float(s.get("der",15)) for s in sondajlar]
        all_y.extend(point["elevation"] for point in yass_points)
        all_y.extend(topography_y)
        
        min_y_visual = min(all_y) - 1.5 
        used_codes = set()
        detail_names_by_code = {}
        
        interactive_polys = []
        snap_lines = []
        depth_label_anchors = []

        def tag_live_artist(artist, group):
            try:
                artist._geo_live_group = group
            except Exception:
                pass
            return artist

        def label_collides(x, y, x_tol, y_tol):
            if not avoid_label_collisions:
                return False
            for anchor in depth_label_anchors:
                dx = abs(safe_float(anchor.get("x")) - x)
                dy = abs(safe_float(anchor.get("y")) - y)
                if dx <= x_tol and dy <= y_tol:
                    return True
            return False

        def place_label_avoiding_anchors(x, preferred_y, x_tol=None, y_tol=0.42, offsets=None):
            if not avoid_label_collisions:
                return preferred_y
            x_tol = x_tol if x_tol is not None else max(3.6, w_well * 2.1)
            offsets = offsets or [0, 0.36, -0.36, 0.72, -0.72, 1.08, -1.08, 1.48, -1.48]
            for offset in offsets:
                candidate = preferred_y + offset
                if not label_collides(x, candidate, x_tol, y_tol):
                    return candidate
            return preferred_y + offsets[-1]

        def register_geo_poly(
            poly,
            code,
            kind="section",
            edit_id=None,
            correlation_key=None,
            detail_name=None,
            surface_connected=False,
        ):
            poly._geo_unit_code = code or "tanimsiz"
            poly._geo_poly_kind = kind
            poly._geo_edit_id = edit_id
            poly._geo_correlation_key = correlation_key or code or "tanimsiz"
            poly._geo_detail_name = detail_name or ""
            poly._geo_surface_connected = bool(surface_connected)
            try:
                poly._geo_default_xy = [[float(x), float(y)] for x, y in poly.get_xy()]
            except Exception:
                poly._geo_default_xy = []
            if edit_id and kind != "well":
                edited = manual_edits.get(edit_id)
                hidden = False
                if isinstance(edited, dict):
                    hidden = bool(edited.get("hidden"))
                    edited = edited.get("vertices") or edited.get("xy")
                poly._geo_hidden = hidden
                if isinstance(edited, list) and len(edited) >= 3:
                    try:
                        poly.set_xy([(safe_float(x), safe_float(y)) for x, y in edited])
                    except Exception:
                        pass
            else:
                poly._geo_hidden = False
            return poly

        def sync_poly_visibility(poly):
            visible = not bool(getattr(poly, "_geo_hidden", False))
            try:
                poly.set_visible(visible)
            except Exception:
                pass
            for artist in getattr(poly, "_geo_pattern_artists", []) or []:
                try:
                    artist.set_visible(visible)
                except Exception:
                    pass

        label_renderer_cache = {"renderer": None}

        def get_label_renderer():
            renderer = label_renderer_cache.get("renderer")
            if renderer is not None:
                return renderer
            try:
                if not hasattr(fig.canvas, "get_renderer"):
                    from matplotlib.backends.backend_agg import FigureCanvasAgg
                    FigureCanvasAgg(fig)
                fig.canvas.draw()
                renderer = fig.canvas.get_renderer()
                label_renderer_cache["renderer"] = renderer
                return renderer
            except Exception:
                return None

        def add_fitted_consistency_label(x, y, label, xl, xr, slot_low, slot_high, layer_height, label_count, clip_poly=None):
            wrapped = wrap_consistency_label(label)
            preferred_fs = preferred_consistency_font(label, layer_height, label_count)
            txt = ax.text(
                x, y,
                wrapped,
                ha='center', va='center',
                fontsize=preferred_fs,
                fontweight='bold',
                color='#111111',
                zorder=26,
                bbox=dict(facecolor='white', edgecolor='none', alpha=0.82, pad=0.38)
            )
            tag_live_artist(txt, "consistency")
            if clip_poly is not None:
                try:
                    txt.set_clip_path(clip_poly)
                    txt.set_clip_on(True)
                except Exception:
                    pass

            renderer = get_label_renderer()
            if renderer is None:
                return txt

            x_pad = max((xr - xl) * 0.06, 0.03)
            y_pad = max(abs(slot_high - slot_low) * 0.06, 0.02)
            x0, x1 = xl + x_pad, xr - x_pad
            y0, y1 = slot_low + y_pad, slot_high - y_pad
            if x1 <= x0:
                x0, x1 = xl, xr
            if y1 <= y0:
                y0, y1 = slot_low, slot_high
            p0 = ax.transData.transform((x0, y0))
            p1 = ax.transData.transform((x1, y1))
            allowed_w = abs(p1[0] - p0[0])
            allowed_h = abs(p1[1] - p0[1])
            if allowed_w <= 0 or allowed_h <= 0:
                return txt
            allowed_x0, allowed_x1 = sorted((p0[0], p1[0]))
            allowed_y0, allowed_y1 = sorted((p0[1], p1[1]))

            def nudge_label_inside():
                try:
                    bbox = txt.get_window_extent(renderer=renderer)
                except Exception:
                    return
                dx = 0.0
                dy = 0.0
                if bbox.x0 < allowed_x0:
                    dx += allowed_x0 - bbox.x0
                if bbox.x1 > allowed_x1:
                    dx -= bbox.x1 - allowed_x1
                if bbox.y0 < allowed_y0:
                    dy += allowed_y0 - bbox.y0
                if bbox.y1 > allowed_y1:
                    dy -= bbox.y1 - allowed_y1
                if abs(dx) < 0.1 and abs(dy) < 0.1:
                    return
                anchor = ax.transData.transform(txt.get_position())
                new_x, new_y = ax.transData.inverted().transform((anchor[0] + dx, anchor[1] + dy))
                txt.set_position((float(new_x), float(new_y)))

            fs = preferred_fs
            while fs >= consistency_font_min:
                txt.set_fontsize(fs)
                try:
                    bbox = txt.get_window_extent(renderer=renderer)
                except Exception:
                    break
                if bbox.width <= allowed_w * 0.98 and bbox.height <= allowed_h * 0.98:
                    nudge_label_inside()
                    return txt
                fs -= 0.35
            txt.set_fontsize(consistency_font_min)
            nudge_label_inside()
            return txt
        
        for idx, s in enumerate(sondajlar):
            x_cen, top, der = s["_plot_x"], s["_kot"], safe_float(s.get("der", 15))
            bottom = top - der
            ax.plot([x_cen, x_cen], [top, top-der], 'k-', lw=1.0, zorder=20)
            plain_label = f"{s.get('no','SK')}"
            label = plain_label
            label_size = 9
            if use_line_projection and show_station_offset_labels:
                station = s.get("_station", 0.0)
                offset = s.get("_offset", 0.0)
                label = f"{label}\nSta {station:.1f}\nOff {offset:+.1f}"
                label_size = 7
            well_label = ax.text(x_cen, top + 0.85, label, ha='center', va='bottom', fontsize=label_size, fontweight='bold')
            well_label._geo_save_text = plain_label
            well_label._geo_save_fontsize = 9
            well_label._geo_full_text = label
            well_label._geo_full_fontsize = label_size
            tag_live_artist(well_label, "station")
            if show_well_elevation_labels:
                top_label_y = place_label_avoiding_anchors(
                    x_cen, top + 0.18,
                    x_tol=max(3.2, w_well * 1.9),
                    y_tol=0.42,
                    offsets=[0, 0.40, -0.40, 0.78, -0.78, 1.14, -1.14],
                )
                top_elev_text = ax.text(
                    x_cen, top_label_y,
                    f"{top:.2f}",
                    ha='center', va='bottom',
                    fontsize=7, fontweight='bold', color='#1B2631', zorder=31,
                    bbox=dict(facecolor='white', edgecolor='none', alpha=0.78, pad=0.4)
                )
                tag_live_artist(top_elev_text, "well_elevation")
                depth_label_anchors.append({"x": x_cen, "y": top_label_y, "kind": "kot"})
                bottom_label_y = place_label_avoiding_anchors(
                    x_cen, bottom - 0.35,
                    x_tol=max(3.2, w_well * 1.9),
                    y_tol=0.42,
                    offsets=[0, -0.40, 0.40, -0.78, 0.78, -1.14, 1.14],
                )
                bottom_elev_text = ax.text(
                    x_cen, bottom_label_y,
                    f"{bottom:.2f}",
                    ha='center', va='top',
                    fontsize=7, fontweight='bold', color='#1B2631', zorder=31,
                    bbox=dict(facecolor='white', edgecolor='none', alpha=0.78, pad=0.4)
                )
                tag_live_artist(bottom_elev_text, "well_elevation")
                depth_label_anchors.append({"x": x_cen, "y": bottom_label_y, "kind": "kot"})
            
            snap_lines.extend([x_cen - w_well/2, x_cen + w_well/2])
            
            if idx < len(sondajlar) - 1:
                plot_next = sondajlar[idx+1]["_plot_x"]
                true_dist = s.get("_true_dist", dx_default)
                if show_distance_labels and abs(plot_next - x_cen) > 0.01:
                    distance_arrow = ax.annotate("", xy=(x_cen, min_y_visual), xytext=(plot_next, min_y_visual), arrowprops=dict(arrowstyle="<->", lw=0.8))
                    tag_live_artist(distance_arrow, "distance")
                    dist_x = (x_cen + plot_next) / 2
                    dist_y = place_label_avoiding_anchors(dist_x, min_y_visual + 0.5, x_tol=5.0, y_tol=0.45)
                    distance_text = ax.text(dist_x, dist_y, f"{true_dist:.1f} m", ha='center', va='bottom', fontsize=9, backgroundcolor='white')
                    tag_live_artist(distance_text, "distance")
                    depth_label_anchors.append({"x": dist_x, "y": dist_y, "kind": "distance"})

            raw_lit, merged = s.get("litoloji", []), []
            if use_correlation_v2:
                merged = normalize_section_layers(s)
                s["merged_layers_v2"] = merged
                used_codes.update(layer.get("code") for layer in merged if layer.get("code"))
                for layer in merged:
                    code = layer.get("code")
                    detail_name = str(layer.get("detail_name") or "").strip()
                    if code and detail_name:
                        detail_names_by_code.setdefault(code, set()).add(detail_name)
            elif raw_lit:
                cur_t, cur_b, cur_r = safe_float(raw_lit[0][0]), safe_float(raw_lit[0][1]), raw_lit[0][2]
                cur_c = litoloji_cozumle(cur_r)
                if cur_c: used_codes.add(cur_c)
                for i in range(1, len(raw_lit)):
                    nt, nb, nr = safe_float(raw_lit[i][0]), safe_float(raw_lit[i][1]), raw_lit[i][2]
                    nc = litoloji_cozumle(nr)
                    if nc: used_codes.add(nc)
                    if nc == cur_c and abs(cur_b - nt) < 0.1: cur_b = nb
                    else: merged.append({'top': cur_t, 'bot': cur_b, 'code': cur_c}); cur_t, cur_b, cur_c = nt, nb, nc
                merged.append({'top': cur_t, 'bot': cur_b, 'code': cur_c})
            s['merged_layers'] = merged

            for layer_idx, layer in enumerate(merged):
                kod = layer['code']; stil = next((item for item in LEJANTLAR if item["kod"] == kod), LEJANTLAR[-1])
                y_t, y_b, xl, xr = top - layer['top'], top - layer['bot'], x_cen - w_well/2, x_cen + w_well/2
                verts = [(xl, y_t), (xr, y_t), (xr, y_b), (xl, y_b)]
                poly = mpatches.Polygon(verts, closed=True, facecolor=stil["zemin"], edgecolor='black', zorder=21)
                register_geo_poly(
                    poly,
                    kod,
                    kind="well",
                    edit_id=f"well:{plain_label}:{layer_idx}:{kod}",
                    correlation_key=layer.get("correlation_key"),
                    detail_name=layer.get("detail_name"),
                )
                ax.add_patch(poly)
                interactive_polys.append(poly) 
                if stil:
                    GeoEngineDraw.draw_pattern(
                        ax, poly, stil["desen"], stil["sembol"],
                        density_scale=pattern_density_for_code(kod, TARAMA_SIKLIGI_KESIT)
                    )
                if show_layer_depth_labels:
                    depth_label_x = xl - 0.5 if idx == 0 else xr + 0.5
                    depth_label_y = place_label_avoiding_anchors(
                        depth_label_x, y_b,
                        x_tol=max(3.4, w_well * 1.8),
                        y_tol=0.34,
                        offsets=[0, 0.30, -0.30, 0.58, -0.58, 0.88, -0.88, 1.18, -1.18],
                    )
                    depth_text = ax.text(depth_label_x, depth_label_y, f"{layer['bot']:.2f}", ha='right' if idx == 0 else 'left', va='center', fontsize=7, fontweight='bold', zorder=25)
                    tag_live_artist(depth_text, "layer_depth")
                    depth_label_anchors.append({"x": depth_label_x, "y": depth_label_y, "kind": "layer_depth"})
                if show_consistency_labels:
                    layer_height = abs(y_t - y_b)
                    records = consistency_labels_for_layer(s, layer)
                    positions = consistency_label_positions(records, layer, y_t, y_b, top)
                    if positions and layer_height >= min(label_min_height, 0.25):
                        high_y, low_y = max(y_t, y_b), min(y_t, y_b)
                        for pos_idx, item in enumerate(positions):
                            label = item.get("label", "")
                            if not label:
                                continue
                            slot_high = high_y if pos_idx == 0 else (positions[pos_idx - 1]["y"] + item["y"]) / 2
                            slot_low = low_y if pos_idx == len(positions) - 1 else (item["y"] + positions[pos_idx + 1]["y"]) / 2
                            add_fitted_consistency_label(
                                x_cen, item["y"], label,
                                xl, xr, slot_low, slot_high,
                                layer_height, len(positions), clip_poly=poly
                            )

        def layer_elevation_info(sondaj, layer):
            y_top = sondaj["_kot"] - safe_float(layer.get("top"))
            y_bot = sondaj["_kot"] - safe_float(layer.get("bot"))
            high = max(y_top, y_bot)
            low = min(y_top, y_bot)
            return {
                "top": high,
                "bot": low,
                "mid": (high + low) / 2,
                "thickness": abs(high - low),
            }

        def layer_overlap(info1, info2):
            return min(info1["top"], info2["top"]) - max(info1["bot"], info2["bot"])

        def match_limit_for_distance(dx_true):
            if corr_tolerance and corr_tolerance > 0:
                return corr_tolerance
            return max(3.0, min(8.0, abs(dx_true) * 0.12))

        def layer_match_cost(s1, s2, l1, l2, idx1, idx2, dx_true):
            if l1.get("code") != l2.get("code"):
                return None
            info1 = layer_elevation_info(s1, l1)
            info2 = layer_elevation_info(s2, l2)
            overlap = layer_overlap(info1, info2)
            mid_dist = abs(info1["mid"] - info2["mid"])
            top_dist = abs(info1["top"] - info2["top"])
            bot_dist = abs(info1["bot"] - info2["bot"])
            boundary_dist = (top_dist + bot_dist) / 2
            thickness_diff = abs(info1["thickness"] - info2["thickness"])
            match_limit = match_limit_for_distance(dx_true)
            small_overlap = max(0.15, min(info1["thickness"], info2["thickness"]) * 0.10)
            if mid_dist > match_limit and overlap <= small_overlap:
                return None
            if boundary_dist > match_limit * 1.8 and overlap <= 0:
                return None

            cost = mid_dist + boundary_dist * 0.35 + thickness_diff * 0.20
            if overlap > 0:
                cost -= min(overlap, info1["thickness"], info2["thickness"]) * 0.45
            else:
                cost += abs(overlap) * 0.70
            cost += abs(idx1 - idx2) * 0.08
            return cost

        def match_layers_between_wells(s1, s2, layers1, layers2, dx_true):
            candidates = []
            for idx1, l1 in enumerate(layers1):
                for idx2, l2 in enumerate(layers2):
                    cost = layer_match_cost(s1, s2, l1, l2, idx1, idx2, dx_true)
                    if cost is not None:
                        candidates.append((cost, idx1, idx2))
            candidates.sort(key=lambda item: (item[0], item[1], item[2]))

            selected = []
            used1, used2 = set(), set()
            for _, idx1, idx2 in candidates:
                if idx1 in used1 or idx2 in used2:
                    continue
                crosses = any((idx1 - m1) * (idx2 - m2) < 0 for m1, m2 in selected)
                if crosses:
                    continue
                selected.append((idx1, idx2))
                used1.add(idx1)
                used2.add(idx2)

            selected.sort(key=lambda item: item[0])
            matches_s1 = {idx1: idx2 for idx1, idx2 in selected}
            matches_s2 = {idx2: idx1 for idx1, idx2 in selected}
            return matches_s1, matches_s2

        def facies_links_between_wells(s1, s2, layers1, layers2, matches_s1, matches_s2):
            facies_s1, facies_s2 = {}, {}
            for idx1, l1 in enumerate(layers1):
                if idx1 in matches_s1:
                    continue
                y1t, y1b = s1["_kot"] - l1['top'], s1["_kot"] - l1['bot']
                best_overlap, best_idx2 = 0, -1
                for idx2, l2 in enumerate(layers2):
                    if idx2 in matches_s2 or idx2 in facies_s2:
                        continue
                    y2t, y2b = s2["_kot"] - l2['top'], s2["_kot"] - l2['bot']
                    overlap = min(y1t, y2t) - max(y1b, y2b)
                    if overlap > facies_overlap_min and overlap > best_overlap:
                        best_overlap, best_idx2 = overlap, idx2
                if best_idx2 != -1:
                    facies_s1[idx1] = best_idx2
                    facies_s2[best_idx2] = idx1
            return facies_s1, facies_s2

        pair_links = []
        if use_correlation_v2:
            pair_links = build_section_correlations(sondajlar, options)
        else:
            for i in range(len(sondajlar) - 1):
                s1, s2 = sondajlar[i], sondajlar[i+1]
                layers1, layers2 = s1.get('merged_layers', []), s2.get('merged_layers', [])
                dx_true = s1.get("_true_dist", dx_default)
                matches_s1, matches_s2 = match_layers_between_wells(s1, s2, layers1, layers2, dx_true)
                facies_s1, facies_s2 = facies_links_between_wells(s1, s2, layers1, layers2, matches_s1, matches_s2)
                pair_links.append({
                    "matches_s1": matches_s1,
                    "matches_s2": matches_s2,
                    "facies_s1": facies_s1,
                    "facies_s2": facies_s2,
                })

        semantic_lens_tracks = []
        semantic_lens_layer_keys = set()
        if use_correlation_v2 and auto_lens:
            semantic_lens_tracks = build_semantic_lens_tracks(
                sondajlar,
                pair_links,
                max_thickness=lens_max_thickness,
                include_edge_lenses=two_well_lens,
            )
            semantic_lens_layer_keys = {
                tuple(node_key)
                for track in semantic_lens_tracks
                for node_key in track.get("node_keys", [])
            }

        def is_lens_candidate(layer):
            code = str(layer.get("code") or "")
            thickness = abs(safe_float(layer.get("bot")) - safe_float(layer.get("top")))
            if code in ("", "tanimsiz", "bt"):
                return False
            if thickness <= 0.05:
                return False
            return lens_max_thickness <= 0 or thickness <= lens_max_thickness

        def adjacent_layer_linked(well_idx, layer_idx, neighbor_idx):
            if neighbor_idx < 0 or neighbor_idx >= len(sondajlar):
                return False
            pair_idx = min(well_idx, neighbor_idx)
            if pair_idx < 0 or pair_idx >= len(pair_links):
                return False
            link = pair_links[pair_idx]
            if well_idx == pair_idx:
                return (
                    layer_idx in link.get("matches_s1", {})
                    or layer_idx in link.get("facies_s1", {})
                )
            return (
                layer_idx in link.get("matches_s2", {})
                or layer_idx in link.get("facies_s2", {})
            )

        def neighbor_has_same_code_overlap(center_s, neighbor_s, layer):
            code = layer.get("code")
            correlation_key = layer.get("correlation_key")
            center_info = layer_elevation_info(center_s, layer)
            min_overlap = max(0.12, center_info["thickness"] * 0.18)
            for neighbor_layer in neighbor_s.get('merged_layers', []):
                if neighbor_layer.get("code") != code:
                    continue
                if (
                    use_correlation_v2
                    and neighbor_layer.get("correlation_key") != correlation_key
                ):
                    continue
                overlap = layer_overlap(center_info, layer_elevation_info(neighbor_s, neighbor_layer))
                if overlap >= min_overlap:
                    return True
                mid_dist = abs(center_info["mid"] - layer_elevation_info(neighbor_s, neighbor_layer)["mid"])
                if mid_dist <= max(0.35, center_info["thickness"] * 0.55):
                    return True
            return False

        lens_layer_keys = set()
        if auto_lens and not use_correlation_v2 and len(sondajlar) >= 3:
            for well_idx in range(1, len(sondajlar) - 1):
                center_s = sondajlar[well_idx]
                left_s = sondajlar[well_idx - 1]
                right_s = sondajlar[well_idx + 1]
                for layer_idx, layer in enumerate(sondajlar[well_idx].get('merged_layers', [])):
                    if not is_lens_candidate(layer):
                        continue
                    has_left_same_unit = (
                        neighbor_has_same_code_overlap(center_s, left_s, layer)
                        or adjacent_layer_linked(well_idx, layer_idx, well_idx - 1)
                    )
                    has_right_same_unit = (
                        neighbor_has_same_code_overlap(center_s, right_s, layer)
                        or adjacent_layer_linked(well_idx, layer_idx, well_idx + 1)
                    )
                    if not has_left_same_unit and not has_right_same_unit:
                        lens_layer_keys.add((well_idx, layer_idx))

        def draw_lens_layer(well_idx, layer_idx):
            s = sondajlar[well_idx]
            left_s = sondajlar[well_idx - 1]
            right_s = sondajlar[well_idx + 1]
            layer = s.get('merged_layers', [])[layer_idx]
            code = layer.get('code')
            stil = next((item for item in LEJANTLAR if item["kod"] == code), LEJANTLAR[-1])
            x_left = s["_plot_x"] - w_well / 2
            x_right = s["_plot_x"] + w_well / 2
            left_limit = left_s["_plot_x"] + w_well / 2
            right_limit = right_s["_plot_x"] - w_well / 2
            left_tip = x_left - max(0.05, x_left - left_limit) * lens_closure_ratio
            right_tip = x_right + max(0.05, right_limit - x_right) * lens_closure_ratio
            y_top = s["_kot"] - layer['top']
            y_bot = s["_kot"] - layer['bot']
            y_mid = (y_top + y_bot) / 2
            verts = [
                (left_tip, y_mid),
                (x_left, y_top),
                (x_right, y_top),
                (right_tip, y_mid),
                (x_right, y_bot),
                (x_left, y_bot),
            ]
            poly = mpatches.Polygon(verts, closed=True, facecolor=stil["zemin"], edgecolor='gray', alpha=1.0, zorder=10.20)
            edit_id = (
                f"lens:{left_s.get('no','SK')}:{s.get('no','SK')}:"
                f"{right_s.get('no','SK')}:{layer_idx}:{code}"
            )
            register_geo_poly(
                poly,
                code,
                edit_id=edit_id,
                correlation_key=layer.get("correlation_key"),
                detail_name=layer.get("detail_name"),
            )
            ax.add_patch(poly)
            interactive_polys.append(poly)
            pattern_artists = GeoEngineDraw.draw_pattern(
                ax, poly, stil["desen"], stil["sembol"],
                density_scale=pattern_density_for_code(code, TARAMA_SIKLIGI_KESIT)
            )
            poly._geo_pattern_zorder = 10.35
            set_artist_zorder(pattern_artists, 10.35)

        def draw_semantic_lens_track(track):
            nodes = list(track.get("nodes") or [])
            if not nodes:
                return
            code = track.get("code")
            stil = next((item for item in LEJANTLAR if item["kod"] == code), LEJANTLAR[-1])
            verts = []
            tip_indices = []

            first_node = nodes[0]
            first_s = sondajlar[first_node["well_index"]]
            first_layer = first_node["layer"]
            first_x_left = first_s["_plot_x"] - w_well / 2
            first_y_top = first_s["_kot"] - safe_float(first_layer.get("top"))
            first_y_bot = first_s["_kot"] - safe_float(first_layer.get("bot"))
            if track.get("left_closed"):
                left_neighbor = sondajlar[first_node["well_index"] - 1]
                left_limit = left_neighbor["_plot_x"] + w_well / 2
                left_tip = first_x_left - max(0.05, first_x_left - left_limit) * lens_closure_ratio
                tip_indices.append(len(verts))
                verts.append((left_tip, (first_y_top + first_y_bot) / 2))

            for node in nodes:
                s = sondajlar[node["well_index"]]
                layer = node["layer"]
                x_left = s["_plot_x"] - w_well / 2
                x_right = s["_plot_x"] + w_well / 2
                y_top = s["_kot"] - safe_float(layer.get("top"))
                verts.extend([(x_left, y_top), (x_right, y_top)])

            last_node = nodes[-1]
            last_s = sondajlar[last_node["well_index"]]
            last_layer = last_node["layer"]
            last_x_right = last_s["_plot_x"] + w_well / 2
            last_y_top = last_s["_kot"] - safe_float(last_layer.get("top"))
            last_y_bot = last_s["_kot"] - safe_float(last_layer.get("bot"))
            if track.get("right_closed"):
                right_neighbor = sondajlar[last_node["well_index"] + 1]
                right_limit = right_neighbor["_plot_x"] - w_well / 2
                right_tip = last_x_right + max(0.05, right_limit - last_x_right) * lens_closure_ratio
                tip_indices.append(len(verts))
                verts.append((right_tip, (last_y_top + last_y_bot) / 2))

            for node in reversed(nodes):
                s = sondajlar[node["well_index"]]
                layer = node["layer"]
                x_left = s["_plot_x"] - w_well / 2
                x_right = s["_plot_x"] + w_well / 2
                y_bot = s["_kot"] - safe_float(layer.get("bot"))
                verts.extend([(x_right, y_bot), (x_left, y_bot)])

            if len(verts) < 3:
                return
            poly = mpatches.Polygon(
                verts,
                closed=True,
                facecolor=stil["zemin"],
                edgecolor="gray",
                alpha=1.0,
                zorder=10.20,
            )
            register_geo_poly(
                poly,
                code,
                edit_id=track.get("track_id"),
                correlation_key=track.get("correlation_key"),
                detail_name=track.get("detail_name"),
            )
            poly._geo_lens_tip_indices = tip_indices
            poly._geo_lens_node_keys = list(track.get("node_keys") or [])
            ax.add_patch(poly)
            interactive_polys.append(poly)
            pattern_artists = GeoEngineDraw.draw_pattern(
                ax,
                poly,
                stil["desen"],
                stil["sembol"],
                density_scale=pattern_density_for_code(code, TARAMA_SIKLIGI_KESIT),
            )
            poly._geo_pattern_zorder = 10.35
            set_artist_zorder(pattern_artists, 10.35)

        half_lens_layer_keys = {}
        if auto_lens and not use_correlation_v2 and two_well_lens and len(sondajlar) >= 2:
            edge_specs = [
                (0, "right", 1),
                (len(sondajlar) - 1, "left", len(sondajlar) - 2),
            ]
            for well_idx, direction, neighbor_idx in edge_specs:
                if neighbor_idx < 0 or neighbor_idx >= len(sondajlar):
                    continue
                source_s = sondajlar[well_idx]
                neighbor_s = sondajlar[neighbor_idx]
                for idx, layer in enumerate(source_s.get('merged_layers', [])):
                    if not is_lens_candidate(layer):
                        continue
                    if adjacent_layer_linked(well_idx, idx, neighbor_idx):
                        continue
                    if not neighbor_has_same_code_overlap(source_s, neighbor_s, layer):
                        half_lens_layer_keys[(well_idx, idx)] = direction

        def draw_half_lens_layer(well_idx, layer_idx, direction):
            s = sondajlar[well_idx]
            neighbor_idx = well_idx + 1 if direction == "right" else well_idx - 1
            if neighbor_idx < 0 or neighbor_idx >= len(sondajlar):
                return
            neighbor = sondajlar[neighbor_idx]
            layer = s.get('merged_layers', [])[layer_idx]
            code = layer.get('code')
            stil = next((item for item in LEJANTLAR if item["kod"] == code), LEJANTLAR[-1])
            x_left = s["_plot_x"] - w_well / 2
            x_right = s["_plot_x"] + w_well / 2
            y_top = s["_kot"] - layer['top']
            y_bot = s["_kot"] - layer['bot']
            y_mid = (y_top + y_bot) / 2
            if direction == "right":
                neighbor_edge = neighbor["_plot_x"] - w_well / 2
                tip = x_right + max(0.05, neighbor_edge - x_right) * lens_closure_ratio
                verts = [(x_left, y_top), (x_right, y_top), (tip, y_mid), (x_right, y_bot), (x_left, y_bot)]
            else:
                neighbor_edge = neighbor["_plot_x"] + w_well / 2
                tip = x_left - max(0.05, x_left - neighbor_edge) * lens_closure_ratio
                verts = [(tip, y_mid), (x_left, y_top), (x_right, y_top), (x_right, y_bot), (x_left, y_bot)]
            poly = mpatches.Polygon(verts, closed=True, facecolor=stil["zemin"], edgecolor='gray', alpha=1.0, zorder=10.20)
            edit_id = f"half-lens:{s.get('no','SK')}:{neighbor.get('no','SK')}:{direction}:{layer_idx}:{code}"
            register_geo_poly(
                poly,
                code,
                edit_id=edit_id,
                correlation_key=layer.get("correlation_key"),
                detail_name=layer.get("detail_name"),
            )
            ax.add_patch(poly)
            interactive_polys.append(poly)
            pattern_artists = GeoEngineDraw.draw_pattern(
                ax, poly, stil["desen"], stil["sembol"],
                density_scale=pattern_density_for_code(code, TARAMA_SIKLIGI_KESIT)
            )
            poly._geo_pattern_zorder = 10.35
            set_artist_zorder(pattern_artists, 10.35)

        lens_host_skip_keys = set()
        lens_host_segments = []

        def lens_host_span(well_idx, layer_idx):
            layers = sondajlar[well_idx].get('merged_layers', [])
            if layer_idx <= 0 or layer_idx >= len(layers) - 1:
                return None
            upper = layers[layer_idx - 1]
            lens = layers[layer_idx]
            lower = layers[layer_idx + 1]
            host_code = upper.get("code")
            if not host_code or host_code == "tanimsiz":
                return None
            if lower.get("code") != host_code or lens.get("code") == host_code:
                return None
            if (
                use_correlation_v2
                and lower.get("correlation_key") != upper.get("correlation_key")
            ):
                return None
            return {
                "code": host_code,
                "correlation_key": upper.get("correlation_key"),
                "detail_name": upper.get("detail_name"),
                "upper_idx": layer_idx - 1,
                "lower_idx": layer_idx + 1,
                "top_depth": safe_float(upper.get("top")),
                "bot_depth": safe_float(lower.get("bot")),
            }

        def find_neighbor_host_layer(center_s, neighbor_s, span):
            target_top = center_s["_kot"] - span["top_depth"]
            target_bot = center_s["_kot"] - span["bot_depth"]
            target_info = {
                "top": max(target_top, target_bot),
                "bot": min(target_top, target_bot),
                "mid": (target_top + target_bot) / 2,
                "thickness": abs(target_top - target_bot),
            }
            best_layer = None
            best_score = None
            for layer in neighbor_s.get('merged_layers', []):
                if layer.get("code") != span["code"]:
                    continue
                if (
                    use_correlation_v2
                    and layer.get("correlation_key") != span.get("correlation_key")
                ):
                    continue
                info = layer_elevation_info(neighbor_s, layer)
                overlap = layer_overlap(target_info, info)
                mid_dist = abs(target_info["mid"] - info["mid"])
                if overlap <= max(0.15, min(target_info["thickness"], info["thickness"]) * 0.15) and mid_dist > max(0.5, target_info["thickness"] * 0.55):
                    continue
                score = (-max(0.0, overlap), mid_dist)
                if best_score is None or score < best_score:
                    best_score = score
                    best_layer = layer
            return best_layer

        def add_lens_host_segment(center_idx, layer_idx, direction):
            span = lens_host_span(center_idx, layer_idx)
            if not span:
                return
            neighbor_idx = center_idx - 1 if direction == "left" else center_idx + 1
            if neighbor_idx < 0 or neighbor_idx >= len(sondajlar):
                return
            center_s = sondajlar[center_idx]
            neighbor_s = sondajlar[neighbor_idx]
            neighbor_layer = find_neighbor_host_layer(center_s, neighbor_s, span)
            if not neighbor_layer:
                return
            lens_host_skip_keys.add((center_idx, span["upper_idx"]))
            lens_host_skip_keys.add((center_idx, span["lower_idx"]))
            lens_host_segments.append((center_idx, neighbor_idx, layer_idx, direction, span, neighbor_layer))

        for well_idx, layer_idx in sorted(lens_layer_keys):
            add_lens_host_segment(well_idx, layer_idx, "left")
            add_lens_host_segment(well_idx, layer_idx, "right")
        for (well_idx, layer_idx), direction in sorted(half_lens_layer_keys.items()):
            add_lens_host_segment(well_idx, layer_idx, direction)
        for track in semantic_lens_tracks:
            nodes = list(track.get("nodes") or [])
            if not nodes:
                continue
            if track.get("left_closed"):
                first_node = nodes[0]
                add_lens_host_segment(
                    first_node["well_index"],
                    first_node["layer_index"],
                    "left",
                )
            if track.get("right_closed"):
                last_node = nodes[-1]
                add_lens_host_segment(
                    last_node["well_index"],
                    last_node["layer_index"],
                    "right",
                )

        def draw_lens_host_segment(center_idx, neighbor_idx, layer_idx, direction, span, neighbor_layer):
            center_s = sondajlar[center_idx]
            neighbor_s = sondajlar[neighbor_idx]
            code = span["code"]
            stil = next((item for item in LEJANTLAR if item["kod"] == code), LEJANTLAR[-1])
            center_top_y = center_s["_kot"] - span["top_depth"]
            center_bot_y = center_s["_kot"] - span["bot_depth"]
            neighbor_top_y = neighbor_s["_kot"] - safe_float(neighbor_layer.get("top"))
            neighbor_bot_y = neighbor_s["_kot"] - safe_float(neighbor_layer.get("bot"))
            if direction == "right":
                center_edge = center_s["_plot_x"] + w_well / 2
                neighbor_edge = neighbor_s["_plot_x"] - w_well / 2
                verts = [
                    (center_edge, center_top_y),
                    (neighbor_edge, neighbor_top_y),
                    (neighbor_edge, neighbor_bot_y),
                    (center_edge, center_bot_y),
                ]
            else:
                center_edge = center_s["_plot_x"] - w_well / 2
                neighbor_edge = neighbor_s["_plot_x"] + w_well / 2
                verts = [
                    (neighbor_edge, neighbor_top_y),
                    (center_edge, center_top_y),
                    (center_edge, center_bot_y),
                    (neighbor_edge, neighbor_bot_y),
                ]
            poly = mpatches.Polygon(verts, closed=True, facecolor=stil["zemin"], edgecolor='gray', alpha=0.50, zorder=8.55)
            edit_id = f"lens-host:{center_s.get('no','SK')}:{neighbor_s.get('no','SK')}:{direction}:{layer_idx}:{code}"
            register_geo_poly(
                poly,
                code,
                edit_id=edit_id,
                correlation_key=span.get("correlation_key"),
                detail_name=span.get("detail_name"),
            )
            ax.add_patch(poly)
            interactive_polys.append(poly)
            pattern_artists = GeoEngineDraw.draw_pattern(
                ax, poly, stil["desen"], stil["sembol"],
                density_scale=pattern_density_for_code(code, TARAMA_SIKLIGI_KESIT)
            )
            poly._geo_pattern_zorder = 8.70
            set_artist_zorder(pattern_artists, 8.70)

        for segment in lens_host_segments:
            draw_lens_host_segment(*segment)
        for track in semantic_lens_tracks:
            draw_semantic_lens_track(track)
        for well_idx, layer_idx in sorted(lens_layer_keys):
            draw_lens_layer(well_idx, layer_idx)
        for (well_idx, layer_idx), direction in sorted(half_lens_layer_keys.items()):
            draw_half_lens_layer(well_idx, layer_idx, direction)
        
        for i in range(len(sondajlar) - 1):
            s1, s2 = sondajlar[i], sondajlar[i+1]
            layers1, layers2 = s1.get('merged_layers', []), s2.get('merged_layers', [])
            
            dx_plot = s2["_plot_x"] - s1["_plot_x"] 
            dx_true = s1.get("_true_dist", dx_default) 
            
            mid_x, x1, x2 = s1["_plot_x"] + dx_plot/2, s1["_plot_x"] + w_well/2, s2["_plot_x"] - w_well/2
            
            link = pair_links[i]
            matches_s1, matches_s2 = link["matches_s1"], link["matches_s2"]
            facies_s1, facies_s2 = link["facies_s1"], link["facies_s2"]

            for idx1, idx2 in matches_s1.items():
                if (
                    (i, idx1) in semantic_lens_layer_keys
                    or (i + 1, idx2) in semantic_lens_layer_keys
                ):
                    continue
                if (i, idx1) in lens_host_skip_keys or (i + 1, idx2) in lens_host_skip_keys:
                    continue
                l1, l2 = layers1[idx1], layers2[idx2]
                stil = next((item for item in LEJANTLAR if item["kod"] == l1['code']), LEJANTLAR[-1])
                verts = [(x1, s1["_kot"] - l1['top']), (x2, s2["_kot"] - l2['top']), (x2, s2["_kot"] - l2['bot']), (x1, s1["_kot"] - l1['bot'])]
                poly = mpatches.Polygon(verts, closed=True, facecolor=stil["zemin"], edgecolor='gray', alpha=0.6, zorder=10)
                edit_id = f"match:{s1.get('no','SK')}:{s2.get('no','SK')}:{idx1}:{idx2}:{l1['code']}"
                register_geo_poly(
                    poly,
                    l1['code'],
                    edit_id=edit_id,
                    correlation_key=l1.get("correlation_key"),
                    detail_name=l1.get("detail_name"),
                )
                ax.add_patch(poly)
                interactive_polys.append(poly)
                if stil:
                    GeoEngineDraw.draw_pattern(
                        ax, poly, stil["desen"], stil["sembol"],
                        density_scale=pattern_density_for_code(l1['code'], TARAMA_SIKLIGI_KESIT)
                    )

            zzw = max(0.5, dx_plot * zigzag_width_ratio) 
            for idx1, idx2 in facies_s1.items():
                if (
                    (i, idx1) in semantic_lens_layer_keys
                    or (i + 1, idx2) in semantic_lens_layer_keys
                ):
                    continue
                if (i, idx1) in lens_layer_keys or (i + 1, idx2) in lens_layer_keys:
                    continue
                if (i, idx1) in lens_host_skip_keys or (i + 1, idx2) in lens_host_skip_keys:
                    continue
                l1, l2 = layers1[idx1], layers2[idx2]
                stil1 = next((item for item in LEJANTLAR if item["kod"] == l1['code']), LEJANTLAR[-1])
                stil2 = next((item for item in LEJANTLAR if item["kod"] == l2['code']), LEJANTLAR[-1])
                
                y1t, y1b = s1["_kot"] - l1['top'], s1["_kot"] - l1['bot']
                y2t, y2b = s2["_kot"] - l2['top'], s2["_kot"] - l2['bot']
                myt, myb = (y1t + y2t) / 2, (y1b + y2b) / 2
                
                zz_pts = get_zigzag_verts(mid_x, myt, myb, zzw)
                
                verts1 = [(x1, y1t)] + zz_pts + [(x1, y1b)]
                poly1 = mpatches.Polygon(verts1, closed=True, facecolor=stil1["zemin"], edgecolor='gray', alpha=0.45, zorder=9)
                edit_id1 = f"facies-left:{s1.get('no','SK')}:{s2.get('no','SK')}:{idx1}:{idx2}:{l1['code']}"
                register_geo_poly(
                    poly1,
                    l1['code'],
                    edit_id=edit_id1,
                    correlation_key=l1.get("correlation_key"),
                    detail_name=l1.get("detail_name"),
                )
                ax.add_patch(poly1); interactive_polys.append(poly1); GeoEngineDraw.draw_pattern(
                    ax, poly1, stil1["desen"], stil1["sembol"],
                    density_scale=pattern_density_for_code(l1['code'], TARAMA_SIKLIGI_KESIT)
                )
                
                verts2 = [(x2, y2t)] + zz_pts + [(x2, y2b)]
                poly2 = mpatches.Polygon(verts2, closed=True, facecolor=stil2["zemin"], edgecolor='gray', alpha=0.45, zorder=9)
                edit_id2 = f"facies-right:{s1.get('no','SK')}:{s2.get('no','SK')}:{idx1}:{idx2}:{l2['code']}"
                register_geo_poly(
                    poly2,
                    l2['code'],
                    edit_id=edit_id2,
                    correlation_key=l2.get("correlation_key"),
                    detail_name=l2.get("detail_name"),
                )
                ax.add_patch(poly2); interactive_polys.append(poly2); GeoEngineDraw.draw_pattern(
                    ax, poly2, stil2["desen"], stil2["sembol"],
                    density_scale=pattern_density_for_code(l2['code'], TARAMA_SIKLIGI_KESIT)
                )

            for idx1, l1 in enumerate(layers1):
                if (i, idx1) in semantic_lens_layer_keys:
                    continue
                if (i, idx1) in lens_layer_keys or (i, idx1) in half_lens_layer_keys or (i, idx1) in lens_host_skip_keys:
                    continue
                if idx1 not in matches_s1 and idx1 not in facies_s1:
                    stil = next((item for item in LEJANTLAR if item["kod"] == l1['code']), LEJANTLAR[-1])
                    y1t, y1b = s1["_kot"] - l1['top'], s1["_kot"] - l1['bot']
                    verts = [(x1, y1t), (x2, (y1t+y1b)/2), (x1, y1b)]
                    poly = mpatches.Polygon(verts, closed=True, facecolor=stil["zemin"], edgecolor='gray', alpha=0.45, zorder=8)
                    edit_id = f"pinch-left:{s1.get('no','SK')}:{s2.get('no','SK')}:{idx1}:{l1['code']}"
                    register_geo_poly(
                        poly,
                        l1['code'],
                        edit_id=edit_id,
                        correlation_key=l1.get("correlation_key"),
                        detail_name=l1.get("detail_name"),
                    )
                    ax.add_patch(poly); interactive_polys.append(poly); GeoEngineDraw.draw_pattern(
                        ax, poly, stil["desen"], stil["sembol"],
                        density_scale=pattern_density_for_code(l1['code'], TARAMA_SIKLIGI_KESIT)
                    )
                    
            for idx2, l2 in enumerate(layers2):
                if (i + 1, idx2) in semantic_lens_layer_keys:
                    continue
                if (i + 1, idx2) in lens_layer_keys or (i + 1, idx2) in half_lens_layer_keys or (i + 1, idx2) in lens_host_skip_keys:
                    continue
                if idx2 not in matches_s2 and idx2 not in facies_s2:
                    stil = next((item for item in LEJANTLAR if item["kod"] == l2['code']), LEJANTLAR[-1])
                    y2t, y2b = s2["_kot"] - l2['top'], s2["_kot"] - l2['bot']
                    verts = [(x2, y2t), (x1, (y2t+y2b)/2), (x2, y2b)]
                    poly = mpatches.Polygon(verts, closed=True, facecolor=stil["zemin"], edgecolor='gray', alpha=0.45, zorder=8)
                    edit_id = f"pinch-right:{s1.get('no','SK')}:{s2.get('no','SK')}:{idx2}:{l2['code']}"
                    register_geo_poly(
                        poly,
                        l2['code'],
                        edit_id=edit_id,
                        correlation_key=l2.get("correlation_key"),
                        detail_name=l2.get("detail_name"),
                    )
                    ax.add_patch(poly); interactive_polys.append(poly); GeoEngineDraw.draw_pattern(
                        ax, poly, stil["desen"], stil["sembol"],
                        density_scale=pattern_density_for_code(l2['code'], TARAMA_SIKLIGI_KESIT)
                    )

        surface_cap_polys = []
        surface_clamped_count = 0

        def surface_layer(sondaj):
            valid_layers = [
                layer for layer in (sondaj.get("merged_layers") or [])
                if safe_float(layer.get("bot")) > safe_float(layer.get("top"))
            ]
            if not valid_layers:
                return None
            layer = min(valid_layers, key=lambda item: (safe_float(item.get("top")), safe_float(item.get("bot"))))
            return layer if safe_float(layer.get("top")) <= 0.10 else None

        def add_surface_cap(vertices, layer, edit_id, surface_curve, pair_index):
            if len(vertices) < 3:
                return None
            code = layer.get("code") or "tanimsiz"
            stil = next((item for item in LEJANTLAR if item["kod"] == code), LEJANTLAR[-1])
            poly = mpatches.Polygon(
                vertices,
                closed=True,
                facecolor=stil["zemin"],
                edgecolor="gray",
                linewidth=0.8,
                alpha=1.0,
                zorder=11.0,
            )
            register_geo_poly(
                poly,
                code,
                edit_id=edit_id,
                correlation_key=layer.get("correlation_key"),
                detail_name=layer.get("detail_name"),
                surface_connected=True,
            )
            poly._geo_surface_curve = [
                (float(x), float(y))
                for x, y in (surface_curve or [])
            ]
            poly._geo_surface_pair_index = int(pair_index)
            ax.add_patch(poly)
            interactive_polys.append(poly)
            surface_cap_polys.append(poly)
            pattern_artists = GeoEngineDraw.draw_pattern(
                ax,
                poly,
                stil["desen"],
                stil["sembol"],
                density_scale=pattern_density_for_code(code, TARAMA_SIKLIGI_KESIT),
            )
            poly._geo_pattern_zorder = 11.15
            set_artist_zorder(pattern_artists, 11.15)
            return poly

        if (
            show_topography_profile
            and conform_layers_to_topography
            and len(topography_info.get("points") or []) >= 2
        ):
            for pair_index in range(len(sondajlar) - 1):
                s1, s2 = sondajlar[pair_index], sondajlar[pair_index + 1]
                layer1, layer2 = surface_layer(s1), surface_layer(s2)
                if layer1 is None or layer2 is None:
                    continue
                x1 = s1["_plot_x"] + w_well / 2
                x2 = s2["_plot_x"] - w_well / 2
                if x2 <= x1 + 0.05:
                    continue
                sample_count = max(16, min(120, int(abs(x2 - x1) * 2.5)))
                surface_curve = topografya_yuzey_egrisi(
                    topography_info["points"],
                    x1,
                    x2,
                    left_elevation=s1["_kot"],
                    right_elevation=s2["_kot"],
                    sample_count=sample_count,
                )
                if len(surface_curve) < 2:
                    continue
                bottom1 = s1["_kot"] - safe_float(layer1.get("bot"))
                bottom2 = s2["_kot"] - safe_float(layer2.get("bot"))

                if layer1.get("code") == layer2.get("code"):
                    cap = yuzeye_uyumlu_tabaka_poligonu(
                        surface_curve,
                        bottom1,
                        bottom2,
                    )
                    surface_clamped_count += cap["clamped_count"]
                    add_surface_cap(
                        cap["vertices"],
                        layer1,
                        (
                            f"surface:{s1.get('no','SK')}:{s2.get('no','SK')}:"
                            f"{layer1.get('code')}"
                        ),
                        cap["top_curve"],
                        pair_index,
                    )
                    continue

                mid_x = (x1 + x2) / 2.0
                split_index = min(
                    range(len(surface_curve)),
                    key=lambda idx: abs(surface_curve[idx][0] - mid_x),
                )
                mid_surface = surface_curve[split_index][1]
                left_curve = list(surface_curve[:split_index + 1])
                right_curve = list(surface_curve[split_index:])
                if not left_curve or left_curve[-1][0] < mid_x - 1e-6:
                    left_curve.append((mid_x, mid_surface))
                else:
                    left_curve[-1] = (mid_x, mid_surface)
                if not right_curve or right_curve[0][0] > mid_x + 1e-6:
                    right_curve.insert(0, (mid_x, mid_surface))
                else:
                    right_curve[0] = (mid_x, mid_surface)
                bottom_mid = (bottom1 + bottom2) / 2.0
                left_cap = yuzeye_uyumlu_tabaka_poligonu(left_curve, bottom1, bottom_mid)
                right_cap = yuzeye_uyumlu_tabaka_poligonu(right_curve, bottom_mid, bottom2)
                surface_clamped_count += left_cap["clamped_count"] + right_cap["clamped_count"]
                zigzag_width = max(0.25, abs(x2 - x1) * zigzag_width_ratio)
                interface_top = min(
                    left_cap["top_curve"][-1][1],
                    right_cap["top_curve"][0][1],
                )
                interface = get_zigzag_verts(
                    mid_x,
                    interface_top,
                    bottom_mid,
                    zigzag_width,
                )
                left_vertices = left_cap["top_curve"] + interface[1:] + [(x1, bottom1)]
                right_vertices = right_cap["top_curve"] + [(x2, bottom2)] + list(reversed(interface[:-1]))
                add_surface_cap(
                    left_vertices,
                    layer1,
                    (
                        f"surface-left:{s1.get('no','SK')}:{s2.get('no','SK')}:"
                        f"{layer1.get('code')}"
                    ),
                    left_cap["top_curve"],
                    pair_index,
                )
                add_surface_cap(
                    right_vertices,
                    layer2,
                    (
                        f"surface-right:{s1.get('no','SK')}:{s2.get('no','SK')}:"
                        f"{layer2.get('code')}"
                    ),
                    right_cap["top_curve"],
                    pair_index,
                )

        for polygon in interactive_polys:
            if getattr(polygon, "_geo_poly_kind", "section") == "well":
                continue
            try:
                pattern_zorder = min(18.0, float(polygon.get_zorder()) + 0.15)
            except Exception:
                pattern_zorder = 18.0
            polygon._geo_pattern_zorder = pattern_zorder
            set_artist_zorder(
                getattr(polygon, "_geo_pattern_artists", []) or [],
                pattern_zorder,
            )

        topography_mask = None
        if (
            show_topography_profile
            and conform_layers_to_topography
            and len(topography_x) >= 2
        ):
            mask_top = max(topography_y) + 100.0
            mask_vertices = list(zip(topography_x, topography_y))
            mask_vertices.extend([
                (topography_x[-1], mask_top),
                (topography_x[0], mask_top),
            ])
            topography_mask = mpatches.Polygon(
                mask_vertices,
                closed=True,
                facecolor="white",
                edgecolor="none",
                linewidth=0,
                zorder=19.5,
            )
            topography_mask._geo_export_group = "topography_mask"
            ax.add_patch(topography_mask)

        for poly in interactive_polys:
            sync_poly_visibility(poly)

        if hide_same_unit_seams:
            GeoEngineDraw.hide_same_unit_seams(ax, interactive_polys)

        if use_correlation_v2 and show_detailed_lithology_labels:
            detail_candidates = []
            for poly in interactive_polys:
                if getattr(poly, "_geo_poly_kind", "section") == "well":
                    continue
                if getattr(poly, "_geo_hidden", False):
                    continue
                if hasattr(poly, "get_visible") and not poly.get_visible():
                    continue
                detail_name = str(getattr(poly, "_geo_detail_name", "") or "").strip()
                correlation_key = str(getattr(poly, "_geo_correlation_key", "") or "").strip()
                if not detail_name or not correlation_key or correlation_key == "tanimsiz":
                    continue
                try:
                    xy = np.asarray(poly.get_xy(), dtype=float)
                    x_min, x_max = float(np.min(xy[:, 0])), float(np.max(xy[:, 0]))
                    y_min, y_max = float(np.min(xy[:, 1])), float(np.max(xy[:, 1]))
                except Exception:
                    continue
                width = abs(x_max - x_min)
                height = abs(y_max - y_min)
                if width < max(2.6, w_well * 1.35) or height < 0.45:
                    continue
                detail_candidates.append({
                    "poly": poly,
                    "key": correlation_key,
                    "name": detail_name,
                    "x": (x_min + x_max) / 2,
                    "y": (y_min + y_max) / 2,
                    "x_min": x_min,
                    "x_max": x_max,
                    "y_min": y_min,
                    "y_max": y_max,
                    "width": width,
                    "height": height,
                    "area": width * height,
                })

            def detail_regions_connected(first, second):
                if first["key"] != second["key"]:
                    return False
                x_gap = max(first["x_min"], second["x_min"]) - min(first["x_max"], second["x_max"])
                y_overlap = min(first["y_max"], second["y_max"]) - max(first["y_min"], second["y_min"])
                return x_gap <= max(0.20, w_well * 1.25) and y_overlap > 0.05

            detail_clusters = []
            unseen = set(range(len(detail_candidates)))
            while unseen:
                seed = unseen.pop()
                cluster_indices = {seed}
                stack = [seed]
                while stack:
                    current = stack.pop()
                    connected = [
                        other for other in list(unseen)
                        if detail_regions_connected(
                            detail_candidates[current],
                            detail_candidates[other],
                        )
                    ]
                    for other in connected:
                        unseen.remove(other)
                        cluster_indices.add(other)
                        stack.append(other)
                detail_clusters.append([detail_candidates[index] for index in cluster_indices])

            selected_detail_labels = []
            for cluster in detail_clusters:
                cluster_x_min = min(item["x_min"] for item in cluster)
                cluster_x_max = max(item["x_max"] for item in cluster)
                cluster_center_x = (cluster_x_min + cluster_x_max) / 2
                selected_detail_labels.append(min(
                    cluster,
                    key=lambda item: (abs(item["x"] - cluster_center_x), -item["area"]),
                ))

            selected_detail_labels.sort(key=lambda item: (item["key"], -item["y"], item["x"]))
            for item in selected_detail_labels:
                label_y = place_label_avoiding_anchors(
                    item["x"],
                    item["y"],
                    x_tol=max(4.0, item["width"] * 0.28),
                    y_tol=0.55,
                    offsets=[0, 0.45, -0.45, 0.90, -0.90],
                )
                font_size = max(5.8, min(8.2, 5.9 + min(item["width"], 12.0) * 0.11))
                detail_text = ax.text(
                    item["x"],
                    label_y,
                    turkce_buyuk_harf(item["name"]),
                    ha="center",
                    va="center",
                    fontsize=font_size,
                    fontweight="bold",
                    color="#202020",
                    zorder=27,
                    bbox=dict(facecolor="white", edgecolor="#888888", alpha=0.80, pad=0.45, linewidth=0.35),
                )
                tag_live_artist(detail_text, "detailed_lithology")
                detail_text._geo_correlation_key = item["key"]
                depth_label_anchors.append({"x": item["x"], "y": label_y, "kind": "detailed_lithology"})

        if show_yass and yass_points:
            yass_sorted = sorted(yass_points, key=lambda item: item["x"])
            water_color = "#0077B6"

            def yass_label_position(x_base, y_base):
                return place_label_avoiding_anchors(
                    x_base, y_base + 0.12,
                    x_tol=max(4.2, w_well * 2.0),
                    y_tol=0.46,
                    offsets=[0, 0.60, -0.84, 1.00, -1.24, 1.43, -1.67, 1.88, -2.12],
                )

            if len(yass_sorted) >= 2:
                yass_line, = ax.plot(
                    [item["x"] for item in yass_sorted],
                    [item["elevation"] for item in yass_sorted],
                    color=water_color,
                    lw=1.7,
                    linestyle=(0, (6, 4)),
                    alpha=0.95,
                    zorder=23.5,
                )
                tag_live_artist(yass_line, "yass")
            for item in yass_sorted:
                x_cen = item["x"]
                y = item["elevation"]
                yass_well_line, = ax.plot(
                    [x_cen - w_well / 2, x_cen + w_well / 2],
                    [y, y],
                    color=water_color,
                    lw=2.2,
                    solid_capstyle="round",
                    zorder=24,
                )
                tag_live_artist(yass_well_line, "yass")
                yass_marker = ax.scatter([x_cen], [y], marker="v", s=34, color=water_color, edgecolor="white", linewidth=0.45, zorder=24.5)
                tag_live_artist(yass_marker, "yass")
                if show_yass_labels:
                    label_x = x_cen + w_well / 2 + 0.35
                    label_y = yass_label_position(label_x, y)
                    yass_text = ax.text(
                        label_x,
                        label_y,
                        f"YASS {item['depth']:.2f} m",
                        ha="left",
                        va="bottom",
                        fontsize=7,
                        color=water_color,
                        fontweight="bold",
                        zorder=46,
                        bbox=dict(facecolor="white", edgecolor="none", alpha=0.78, pad=0.35),
                    )
                    tag_live_artist(yass_text, "yass_label")
                    depth_label_anchors.append({"x": label_x, "y": label_y, "kind": "yass"})

        box_bottom = min_y_visual - 1.5 
        plot_top = max(all_y) + 2.0
        
        for spine in ax.spines.values():
            spine.set_visible(False)
            
        ax.plot([min_x_plot, max_x_plot], [plot_top, plot_top], 'k-', lw=1.0, zorder=50) 
        ax.plot([min_x_plot, max_x_plot], [box_bottom, box_bottom], 'k-', lw=1.0, zorder=50) 
        ax.plot([min_x_plot, min_x_plot], [box_bottom, plot_top], 'k-', lw=1.0, zorder=50) 
        ax.plot([max_x_plot, max_x_plot], [box_bottom, plot_top], 'k-', lw=1.0, zorder=50) 
        
        ticks = np.arange(math.floor(box_bottom), math.ceil(plot_top)+1, 5)
        ax.set_yticks(ticks)

        def legend_label_width(items):
            max_len = max((len(str(item.get("ad", ""))) for item in items), default=8)
            return max(8.2, min(14.0, 4.2 + max_len * 0.38))

        def legend_text_for_label(label):
            label = str(label or "")
            if len(label) <= 12:
                return label
            wrapped = textwrap.wrap(label, width=12, break_long_words=False, break_on_hyphens=False)
            return "\n".join(wrapped[:2]) if wrapped else label

        def legend_layout_for_items(items, plot_span, requested_cols, requested_scale):
            n_items = len(items)
            plot_span = max(1.0, abs(plot_span))
            target_width = plot_span * 0.92
            base_scale = max(0.55, min(1.25, requested_scale))
            min_scale = 0.55
            base_item_width = legend_label_width(items)

            if requested_cols > 0:
                cols = max(1, min(n_items, requested_cols))
                while cols > 1 and cols * base_item_width * min_scale > target_width:
                    cols -= 1
                scale = min(base_scale, target_width / max(cols * base_item_width, 0.01))
                return cols, max(min_scale, scale), base_item_width

            max_cols = min(n_items, 8)
            candidates = []
            for cols in range(1, max_cols + 1):
                scale = min(base_scale, target_width / max(cols * base_item_width, 0.01))
                scale = max(min_scale, scale)
                width = cols * base_item_width * scale
                rows = math.ceil(n_items / cols)
                overflow = max(0.0, width - target_width)
                scale_penalty = max(0.0, base_scale - scale)
                score = rows * 10.0 + overflow * 4.0 + scale_penalty * 2.5 - cols * 0.12
                candidates.append((score, rows, -scale, cols, scale))

            _, _, _, cols, scale = min(candidates, key=lambda item: item[0])
            return cols, scale, base_item_width

        items = []
        for legend_item in LEJANTLAR:
            code = legend_item.get("kod")
            if code not in used_codes:
                continue
            detail_names = sorted(detail_names_by_code.get(code, []))
            if use_correlation_v2 and detail_names:
                for detail_name in detail_names:
                    detailed_item = dict(legend_item)
                    detailed_item["ad"] = detail_name
                    items.append(detailed_item)
            else:
                items.append(legend_item)
        legend_rows = 0
        legend_ax = None
        if items and show_legend and print_scale_enabled:
            n_items = len(items)
            requested_cols = int(safe_float(options.get("legend_columns", 0)) or 0)
            default_cols = 8 if str(print_page_size).upper().startswith("A3") else 6
            n_cols = max(1, min(n_items, requested_cols or default_cols))
            legend_rows = math.ceil(n_items / n_cols)
            legend_ax = fig.add_axes([0.08, 0.02, 0.84, 0.10])
            legend_ax.set_xlim(0, n_cols)
            legend_ax.set_ylim(0, legend_rows + 0.52)
            legend_ax.axis("off")

            legend_title = legend_ax.text(
                n_cols / 2,
                legend_rows + 0.30,
                "LEJANT",
                ha="center",
                va="center",
                fontsize=9,
                fontweight="bold",
                zorder=41,
            )
            legend_title._geo_export_group = "legend"

            for i, legend_item in enumerate(items):
                row = i // n_cols
                col = i % n_cols
                y_top = legend_rows - row - 0.12
                y_bottom = y_top - 0.48
                x_left = col + 0.04
                x_right = col + 0.32
                polygon = mpatches.Polygon(
                    [
                        (x_left, y_top),
                        (x_right, y_top),
                        (x_right, y_bottom),
                        (x_left, y_bottom),
                    ],
                    closed=True,
                    facecolor=legend_item["zemin"],
                    edgecolor="black",
                    linewidth=0.8,
                    zorder=21,
                )
                polygon._geo_export_group = "legend"
                legend_ax.add_patch(polygon)
                for artist in GeoEngineDraw.draw_pattern(
                    legend_ax,
                    polygon,
                    legend_item["desen"],
                    legend_item["sembol"],
                    density_scale=max(
                        0.45,
                        pattern_density_for_code(
                            legend_item.get("kod"),
                            TARAMA_SIKLIGI_LEJANT,
                            legend=True,
                        ) / 4.0,
                    ),
                ):
                    artist._geo_export_group = "legend"
                legend_text = legend_ax.text(
                    x_right + 0.04,
                    (y_top + y_bottom) / 2,
                    legend_text_for_label(legend_item["ad"]),
                    va="center",
                    ha="left",
                    fontsize=7.2,
                    linespacing=0.92,
                    zorder=46,
                )
                legend_text._geo_export_group = "legend"

            ax.set_xlim(min_x_plot, max_x_plot)
            ax.set_ylim(box_bottom - 1.0, plot_top + 1.0)
        elif items and show_legend:
            n_items = len(items)
            plot_span = max_x_plot - min_x_plot
            requested_cols = int(safe_float(options.get("legend_columns", 0)) or 0)
            n_cols, legend_scale_auto, base_item_width = legend_layout_for_items(items, plot_span, requested_cols, legend_scale)
            n_rows = math.ceil(n_items / n_cols)
            
            box_w = 1.7 * legend_scale_auto
            box_h = 1.05 * legend_scale_auto
            item_width = base_item_width * legend_scale_auto
            y_spc = 2.25 * legend_scale_auto
            
            leg_w = n_cols * item_width
            x_center = (max_x_plot + min_x_plot) / 2
            start_x = x_center - (leg_w / 2)
            
            start_y = box_bottom - (1.45 * legend_scale_auto)
            
            legend_title = ax.text(x_center, start_y + (0.75 * legend_scale_auto), "LEJANT", ha='center', fontsize=max(7, 11 * legend_scale_auto), fontweight='bold', zorder=41)
            legend_title._geo_export_group = "legend"
            
            for i, l in enumerate(items):
                r = i // n_cols
                c = i % n_cols
                
                y_t = start_y - r * y_spc
                y_b = y_t - box_h
                xl = start_x + c * item_width
                xr = xl + box_w
                
                verts = [(xl, y_t), (xr, y_t), (xr, y_b), (xl, y_b)]
                poly = mpatches.Polygon(verts, closed=True, facecolor=l['zemin'], edgecolor='black', zorder=21) 
                poly._geo_export_group = "legend"
                ax.add_patch(poly)
                
                if l:
                    for artist in GeoEngineDraw.draw_pattern(
                        ax, poly, l["desen"], l["sembol"],
                        density_scale=pattern_density_for_code(l.get("kod"), TARAMA_SIKLIGI_LEJANT, legend=True)
                    ):
                        artist._geo_export_group = "legend"
                legend_text = ax.text(
                    xr + (0.25 * legend_scale_auto), (y_t + y_b)/2,
                    legend_text_for_label(l['ad']),
                    va='center', ha='left',
                    fontsize=max(5.8, 8.5 * legend_scale_auto),
                    linespacing=0.92,
                    zorder=46
                )
                legend_text._geo_export_group = "legend"
            
            ax.set_xlim(min_x_plot, max_x_plot)
            ax.set_ylim(start_y - (n_rows * y_spc) - 1.0, plot_top + 1.0)
        else:
            ax.set_xlim(min_x_plot, max_x_plot)
            ax.set_ylim(box_bottom - 1.0, plot_top + 1.0)

        print_layout = None
        title_block_ax = None
        page_plan = None
        if print_scale_enabled:
            if print_multi_page:
                page_plan = kesit_cok_sayfa_plani(
                    full_min_x_plot,
                    full_max_x_plot,
                    page_name=print_page_size,
                    horizontal_scale=horizontal_scale,
                    overlap_m=print_page_overlap,
                )
            x_limits = ax.get_xlim()
            y_limits = ax.get_ylim()
            print_layout = kesit_baski_yerlesimi(
                abs(x_limits[1] - x_limits[0]),
                abs(y_limits[1] - y_limits[0]),
                page_name=print_page_size,
                horizontal_scale=horizontal_scale,
                vertical_scale=vertical_scale,
                legend_rows=legend_rows,
                show_title_block=print_title_block,
                auto_fit=print_auto_fit,
            )
            fig.set_size_inches(*print_layout["figure_size"], forward=True)
            ax.set_position(print_layout["axes_rect"])
            if legend_ax is not None and print_layout.get("legend_rect"):
                legend_ax.set_position(print_layout["legend_rect"])

            effective_horizontal = print_layout["horizontal_scale"]
            effective_vertical = print_layout["vertical_scale"]
            vertical_exaggeration = print_layout["vertical_exaggeration"]
            ax._geo_title_full = (
                f"Jeolojik Kesit ({mode_label}, "
                f"Y 1/{effective_horizontal:g}, D 1/{effective_vertical:g}, "
                f"D.A. x{vertical_exaggeration:g})"
            )
            if title_mode == "none":
                ax.set_title("")
            elif title_mode == "simple":
                ax.set_title(ax._geo_title_simple, fontsize=12, fontweight="bold")
            else:
                ax.set_title(ax._geo_title_full, fontsize=12, fontweight="bold")

            if print_layout["adjusted"] and log_callback:
                log_callback(
                    (
                        f"{print_layout['page_name']} sayfasına sığması için baskı ölçeği "
                        f"Y 1/{effective_horizontal:g}, D 1/{effective_vertical:g} olarak ayarlandı."
                    ),
                    "warning",
                )

            title_block_rect = print_layout.get("title_block_rect")
            if title_block_rect:
                title_block_ax = fig.add_axes(title_block_rect)
                title_block_ax.set_xlim(0, 1)
                title_block_ax.set_ylim(0, 1)
                title_block_ax.axis("off")
                border = mpatches.Rectangle(
                    (0.005, 0.02),
                    0.99,
                    0.96,
                    fill=False,
                    edgecolor="#202020",
                    linewidth=0.9,
                )
                border._geo_export_group = "print_title_block"
                title_block_ax.add_patch(border)
                for y in (0.72, 0.49, 0.26):
                    line, = title_block_ax.plot(
                        [0.005, 0.995],
                        [y, y],
                        color="#202020",
                        linewidth=0.55,
                    )
                    line._geo_export_group = "print_title_block"
                divider, = title_block_ax.plot(
                    [0.58, 0.58],
                    [0.02, 0.72],
                    color="#202020",
                    linewidth=0.55,
                )
                divider._geo_export_group = "print_title_block"

                project_name = str(options.get("project_name") or "Adsız proje").strip()
                project_location = str(options.get("project_location") or "Konum belirtilmedi").strip()
                project_cadastral = str(options.get("project_cadastral") or "Pafta / Ada / Parsel belirtilmedi").strip()
                selected_names = options.get("selected_sondajlar") or []
                if isinstance(selected_names, str):
                    selected_names = [selected_names]
                section_name = str(options.get("section_name") or "").strip()
                if not section_name:
                    section_name = " - ".join(str(item) for item in selected_names if str(item).strip())
                section_name = section_name or "Kesit"
                page_index = int(safe_float(options.get("print_page_index", 0)) or 0)
                page_count = int(safe_float(options.get("print_page_count", 0)) or 0)
                if page_index > 0 and page_count > 1:
                    section_name = f"{section_name} ({page_index}/{page_count})"
                print_date = str(options.get("print_date") or datetime.now().strftime("%d.%m.%Y"))

                def block_text(x, y, label, value, width, fontsize=6.4):
                    value_text = textwrap.shorten(
                        " ".join(str(value or "-").split()),
                        width=width,
                        placeholder="...",
                    )
                    artist = title_block_ax.text(
                        x,
                        y,
                        f"{label}: {value_text}",
                        ha="left",
                        va="center",
                        fontsize=fontsize,
                        color="#202020",
                    )
                    artist._geo_export_group = "print_title_block"

                title_artist = title_block_ax.text(
                    0.5,
                    0.85,
                    "JEOLOJİK KESİT PAFTASI",
                    ha="center",
                    va="center",
                    fontsize=8.3,
                    fontweight="bold",
                    color="#202020",
                )
                title_artist._geo_export_group = "print_title_block"
                block_text(0.025, 0.605, "Proje", project_name, 38)
                block_text(0.025, 0.375, "Konum", project_location, 38)
                block_text(0.025, 0.145, "Pafta/Ada/Parsel", project_cadastral, 34, fontsize=6.0)
                block_text(0.605, 0.605, "Kesit", section_name, 24)
                block_text(
                    0.605,
                    0.375,
                    "Ölçek",
                    f"Y 1/{effective_horizontal:g} | D 1/{effective_vertical:g}",
                    30,
                )
                block_text(0.605, 0.145, "Tarih", print_date, 20)

            if page_plan and page_plan["page_count"] > 1 and not has_print_window:
                for page_index, (page_start, page_end) in enumerate(page_plan["windows"], start=1):
                    if page_index < page_plan["page_count"]:
                        boundary = page_end
                        page_line = ax.axvline(
                            boundary,
                            color="#2471A3",
                            linewidth=0.9,
                            linestyle=(0, (5, 4)),
                            alpha=0.85,
                            zorder=54,
                        )
                        page_line._geo_export_group = "page_break"
                    page_mid = (page_start + page_end) / 2.0
                    page_label = ax.text(
                        page_mid,
                        plot_top + 0.55,
                        f"Sayfa {page_index}",
                        ha="center",
                        va="center",
                        fontsize=6.5,
                        color="#2471A3",
                        bbox=dict(facecolor="white", edgecolor="#2471A3", linewidth=0.4, pad=1.2),
                        zorder=55,
                    )
                    page_label._geo_export_group = "page_break"

            if has_print_window:
                def clip_polygon_x(vertices, x_min, x_max):
                    points = [
                        (float(x), float(y))
                        for x, y in vertices
                        if math.isfinite(float(x)) and math.isfinite(float(y))
                    ]
                    if len(points) < 3:
                        return []
                    if points[0] == points[-1]:
                        points = points[:-1]

                    def clip_side(source, boundary, keep_greater):
                        if not source:
                            return []
                        result = []
                        previous = source[-1]
                        previous_inside = previous[0] >= boundary if keep_greater else previous[0] <= boundary
                        for current in source:
                            current_inside = current[0] >= boundary if keep_greater else current[0] <= boundary
                            if current_inside != previous_inside:
                                dx = current[0] - previous[0]
                                if abs(dx) > 1e-12:
                                    ratio = (boundary - previous[0]) / dx
                                    crossing_y = previous[1] + ratio * (current[1] - previous[1])
                                    result.append((boundary, crossing_y))
                            if current_inside:
                                result.append(current)
                            previous = current
                            previous_inside = current_inside
                        return result

                    points = clip_side(points, x_min, True)
                    points = clip_side(points, x_max, False)
                    if len(points) >= 3:
                        points.append(points[0])
                    return points

                for polygon in ax.patches:
                    if not isinstance(polygon, mpatches.Polygon):
                        continue
                    try:
                        clipped_vertices = clip_polygon_x(
                            polygon.get_xy(),
                            min_x_plot,
                            max_x_plot,
                        )
                        polygon.set_xy(clipped_vertices)
                        polygon.set_visible(bool(clipped_vertices))
                        for pattern_artist in getattr(polygon, "_geo_pattern_artists", []) or []:
                            pattern_artist.set_visible(bool(clipped_vertices))
                    except Exception:
                        pass
                for artist in [
                    *ax.lines,
                    *ax.collections,
                    *ax.patches,
                    *ax.texts,
                ]:
                    try:
                        artist.set_clip_box(ax.bbox)
                        if artist in ax.texts:
                            artist.set_clip_on(True)
                            artist.set_clip_path(ax.patch)
                    except Exception:
                        pass

        if topography_mask is not None:
            annotation_zorder = float(topography_mask.get_zorder()) + 1.0
            for text_artist in ax.texts:
                try:
                    if float(text_artist.get_zorder()) <= float(topography_mask.get_zorder()):
                        text_artist.set_zorder(annotation_zorder)
                except Exception:
                    pass

        fig._geo_hide_same_unit_seams = hide_same_unit_seams
        fig._geo_section_engine = "v2" if use_correlation_v2 else "v1"
        fig._geo_correlation_links = pair_links if use_correlation_v2 else []
        fig._geo_semantic_lenses = semantic_lens_tracks if use_correlation_v2 else []
        fig._geo_print_layout = print_layout
        fig._geo_page_plan = page_plan
        fig._geo_full_x_limits = (full_min_x_plot, full_max_x_plot)
        fig._geo_print_title_block_axes = title_block_ax
        fig._geo_topography_profile = {
            "enabled": show_topography_profile,
            "source": topography_info.get("source", "sondaj"),
            "points": list(topography_info.get("points") or []),
            "borehole_points": [
                {"station": x, "elevation": y}
                for x, y in zip(xs, ys)
            ],
            "station_scale": station_scale,
            "warning": topography_info.get("warning", ""),
        }
        fig._geo_surface_caps = surface_cap_polys
        fig._geo_topography_clamped_count = surface_clamped_count
        fig._geo_topography_mask = topography_mask
        fig._geo_surface_expected_pair_count = max(0, len(sondajlar) - 1)
        fig._geo_surface_covered_pair_count = len({
            getattr(poly, "_geo_surface_pair_index", None)
            for poly in surface_cap_polys
        } - {None})
        fig._geo_tool = GeoInteractiveTool(fig, ax, snap_lines, interactive_polys)

        return fig, (ax, interactive_polys, None)

