# Dosya: RaporPro/kesit_export.py
from pathlib import Path
from xml.etree import ElementTree

from matplotlib.backends.backend_pdf import PdfPages


def kesit_cikti_dogrula(path, expected_pages=1):
    """Kaydedilen kesit dosyasinin temel yapisini ve sayfa sayisini denetler."""
    output_path = Path(path)
    if not output_path.is_file() or output_path.stat().st_size <= 0:
        raise ValueError(f"Kesit cikti dosyasi olusturulamadi: {output_path}")

    suffix = output_path.suffix.lower()
    result = {
        "path": str(output_path),
        "format": suffix.lstrip("."),
        "size": output_path.stat().st_size,
        "page_count": 1,
    }
    if suffix == ".pdf":
        import fitz

        with fitz.open(output_path) as document:
            result["page_count"] = int(document.page_count)
        if result["page_count"] != int(expected_pages):
            raise ValueError(
                f"Kesit PDF sayfa sayisi {result['page_count']}; "
                f"beklenen {int(expected_pages)}."
            )
    elif suffix == ".svg":
        root = ElementTree.parse(output_path).getroot()
        if not str(root.tag).lower().endswith("svg"):
            raise ValueError("Kesit SVG dosyasinda gecerli <svg> kok elemani bulunamadi.")
    return result


def kesit_figuru_kaydet(fig, path, *, dpi=300, bbox_inches=None):
    """Tek bir kesit figurunu kaydeder ve olusan dosyayi dogrular."""
    fig.savefig(
        path,
        dpi=int(dpi),
        bbox_inches=bbox_inches,
        facecolor="white",
    )
    return kesit_cikti_dogrula(path, expected_pages=1)


def kesit_cok_sayfali_cikti_kaydet(
    path,
    fmt,
    page_plan,
    render_page,
    *,
    dpi=300,
):
    """Sayfa planindaki tum kesit pencerelerini PDF'e veya ayri dosyalara kaydeder."""
    output_path = Path(path)
    windows = list((page_plan or {}).get("windows") or [])
    if not windows:
        raise ValueError("Cok sayfali kesit icin sayfa penceresi bulunamadi.")

    normalized_format = str(fmt or output_path.suffix.lstrip(".")).strip().lower()
    page_count = len(windows)
    saved_paths = []
    if normalized_format == "pdf":
        with PdfPages(output_path) as pdf:
            for page_index, x_window in enumerate(windows, start=1):
                page_fig = render_page(page_index, x_window)
                try:
                    pdf.savefig(
                        page_fig,
                        dpi=int(dpi),
                        bbox_inches=None,
                        facecolor="white",
                    )
                finally:
                    page_fig.clear()
        validation = kesit_cikti_dogrula(output_path, expected_pages=page_count)
        saved_paths.append(str(output_path))
    else:
        validation = None
        for page_index, x_window in enumerate(windows, start=1):
            page_fig = render_page(page_index, x_window)
            page_path = output_path.with_name(
                f"{output_path.stem}_Sayfa{page_index}{output_path.suffix}"
            )
            try:
                page_validation = kesit_figuru_kaydet(
                    page_fig,
                    page_path,
                    dpi=dpi,
                    bbox_inches=None,
                )
            finally:
                page_fig.clear()
            validation = page_validation
            saved_paths.append(str(page_path))

    return {
        "format": normalized_format,
        "page_count": page_count,
        "paths": saved_paths,
        "validation": validation,
    }
