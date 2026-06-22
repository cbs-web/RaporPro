# Dosya: RaporPro/motor_hesap.py
try:
    from yardimcilar import safe_float
except ImportError:
    def safe_float(value):
        try:
            return float(str(value).replace(",", "."))
        except Exception:
            return 0.0


class GeoEngineHesapMixin:
    @staticmethod
    def hesapla_parametreler(vp, vs, h, rho=None):
        vp, vs, h = map(safe_float, [vp, vs, h])
        if vp == 0 or vs == 0:
            return {"nu": 0, "rho": 0, "G": 0, "E": 0, "K": 0, "ratio": 0}
        rho = safe_float(rho)
        if rho == 0:
            rho = 0.31 * (vp ** 0.25)
        nu = (vp ** 2 - 2 * vs ** 2) / (2 * (vp ** 2 - vs ** 2)) if vp > vs else 0.49
        g = (rho * vs ** 2) / 100
        e = 2 * g * (1 + nu)
        k = e / (3 * (1 - 2 * nu)) if (1 - 2 * nu) != 0 else 0
        return {
            "nu": round(nu, 2),
            "rho": round(rho, 2),
            "G": round(g, 2),
            "E": round(e, 2),
            "K": round(k, 2),
            "ratio": round(vp / vs if vs != 0 else 0, 2),
        }

    @staticmethod
    def vs30_hesapla(katmanlar):
        h_top, t_top = 0, 0
        for i, k in enumerate(katmanlar):
            h, vs = safe_float(k.get('h')), safe_float(k.get('vs'))
            if vs <= 0:
                continue
            kalan = 30.0 - h_top
            if kalan <= 0:
                break
            use_h = kalan if i == len(katmanlar) - 1 else (h if h <= kalan else kalan)
            h_top += use_h
            t_top += use_h / vs
        return round(30.0 / t_top, 2) if t_top > 0 else 0

    @staticmethod
    def hesapla_t0_50m(katmanlar):
        toplam_h, toplam_t, last_valid_vs = 0, 0, 0
        for k in katmanlar:
            h = safe_float(k.get("h"))
            vs = safe_float(k.get("vs"))
            if h > 0:
                toplam_h += h
                if vs > 0:
                    toplam_t += (4 * h / vs)
                    last_valid_vs = vs
            elif vs > 0:
                last_valid_vs = vs
        if toplam_h < 50.0 and last_valid_vs > 0:
            kalan_h = 50.0 - toplam_h
            toplam_t += (4 * kalan_h / last_valid_vs)
        return round(toplam_t, 4) if toplam_t > 0 else 0
