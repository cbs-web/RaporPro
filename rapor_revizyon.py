# Dosya: RaporPro/rapor_revizyon.py
import os
import re
import tempfile
from copy import deepcopy
from types import SimpleNamespace

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn


REVIZYON_BOOKMARK_PREFIX = "RPRO_"


def revizyon_bookmark_name(tag):
    raw = re.sub(r"[^A-Za-z0-9]+", "_", str(tag or "")).strip("_")
    if not raw:
        raw = "ETIKET"
    return (REVIZYON_BOOKMARK_PREFIX + raw)[:40]


def _bookmark_idleri(doc):
    ids = []
    for el in doc.element.iter():
        if el.tag == qn("w:bookmarkStart"):
            try:
                ids.append(int(el.get(qn("w:id"))))
            except Exception:
                continue
    return ids


def _sonraki_bookmark_id(doc):
    ids = _bookmark_idleri(doc)
    return (max(ids) + 1) if ids else 1


def _bookmark_start(bookmark_id, name):
    el = OxmlElement("w:bookmarkStart")
    el.set(qn("w:id"), str(bookmark_id))
    el.set(qn("w:name"), name)
    return el


def _bookmark_end(bookmark_id):
    el = OxmlElement("w:bookmarkEnd")
    el.set(qn("w:id"), str(bookmark_id))
    return el


def revizyon_isaretleri_ekle(doc, paragraph_index, tags=None):
    """Etiket paragraflarını görünmeyen Word bookmark aralıklarıyla sarar."""
    if not paragraph_index:
        return 0
    tag_list = list(tags or paragraph_index.keys())
    next_id = _sonraki_bookmark_id(doc)
    existing_names = set()
    added = 0

    for tag in tag_list:
        paragraph = paragraph_index.get(tag)
        if paragraph is None or tag not in (paragraph.text or ""):
            continue
        name = revizyon_bookmark_name(tag)
        if name in existing_names or _bookmark_var_mi(doc, name):
            continue
        bookmark_id = next_id
        next_id += 1
        paragraph._p.addprevious(_bookmark_start(bookmark_id, name))
        paragraph._p.addnext(_bookmark_end(bookmark_id))
        existing_names.add(name)
        added += 1
    return added


def _bookmark_var_mi(doc, name):
    for el in doc.element.iter():
        if el.tag == qn("w:bookmarkStart") and el.get(qn("w:name")) == name:
            return True
    return False


def _bookmark_range(doc, tag):
    name = revizyon_bookmark_name(tag)
    start = None
    for el in doc.element.iter():
        if el.tag == qn("w:bookmarkStart") and el.get(qn("w:name")) == name:
            start = el
            break
    if start is None:
        return None, None, None

    bookmark_id = start.get(qn("w:id"))
    parent = start.getparent()
    if parent is None:
        return None, None, None

    children = list(parent)
    try:
        start_idx = children.index(start)
    except ValueError:
        return None, None, None

    for end in children[start_idx + 1:]:
        if end.tag == qn("w:bookmarkEnd") and end.get(qn("w:id")) == bookmark_id:
            return parent, start, end
    return None, None, None


def revizyon_etiketi_var_mi(doc, tag):
    parent, start, end = _bookmark_range(doc, tag)
    return parent is not None and start is not None and end is not None


def _range_elements(doc, tag):
    parent, start, end = _bookmark_range(doc, tag)
    if parent is None:
        return None
    children = list(parent)
    start_idx = children.index(start)
    end_idx = children.index(end)
    return list(children[start_idx + 1:end_idx])


def docx_bolumlerini_degistir(target_doc, source_doc, tags):
    updated = []
    missing = []
    for tag in tags or []:
        source_elements = _range_elements(source_doc, tag)
        target_info = _bookmark_range(target_doc, tag)
        target_parent, target_start, target_end = target_info
        if source_elements is None or target_parent is None:
            missing.append(tag)
            continue

        children = list(target_parent)
        start_idx = children.index(target_start)
        end_idx = children.index(target_end)
        for element in children[start_idx + 1:end_idx]:
            target_parent.remove(element)

        insert_idx = list(target_parent).index(target_start) + 1
        for element in source_elements:
            target_parent.insert(insert_idx, deepcopy(element))
            insert_idx += 1
        updated.append(tag)
    return updated, missing


def revizyonlu_rapor_olustur(app_instance, hazir_rapor_path, tags, output_path):
    from raporlama import duzeltme_etiket_sablonu_olustur, duzeltme_etiketleri_temizle, raporla

    selected = duzeltme_etiketleri_temizle(tags)
    if not selected:
        return {"success": False, "message": "En az bir etiket seçilmelidir.", "updated": [], "missing": []}
    if not hazir_rapor_path or not os.path.exists(hazir_rapor_path):
        return {"success": False, "message": "Revize edilecek Word raporu bulunamadı.", "updated": [], "missing": selected}
    if not output_path:
        return {"success": False, "message": "Kaydedilecek revizyonlu rapor yolu seçilmedi.", "updated": [], "missing": selected}

    with tempfile.TemporaryDirectory(prefix="raporpro_revizyon_") as tmp:
        tmp_template = os.path.join(tmp, "revizyon_etiket_sablonu.docx")
        tmp_sections = os.path.join(tmp, "revizyon_guncel_bolumler.docx")
        duzeltme_etiket_sablonu_olustur(selected, tmp_template)

        attrs = dict(getattr(app_instance, "__dict__", {}))
        attrs["word_path"] = tmp_template
        attrs.setdefault("set_status", lambda *_args, **_kwargs: None)
        context = SimpleNamespace(**attrs)
        success, msg = raporla(context, final_path=tmp_sections, autosave=False)
        if not success:
            return {"success": False, "message": msg, "updated": [], "missing": selected}

        target_doc = Document(hazir_rapor_path)
        source_doc = Document(tmp_sections)
        updated, missing = docx_bolumlerini_degistir(target_doc, source_doc, selected)
        if not updated:
            message = (
                "Bu Word raporunda revizyon işaretleri bulunamadı. "
                "Bu özellik, bu sürümden sonra oluşturulan raporlarda hazır rapor üzerinden çalışır. "
                "Eski raporlar için Düzeltme Etiketleri çıktısını kullanın veya raporu yeniden oluşturun."
            )
            return {"success": False, "message": message, "updated": [], "missing": missing or selected}

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        target_doc.save(output_path)
        warning = f" Eksik/güncellenemeyen etiket: {', '.join(missing)}." if missing else ""
        message = f"Revizyonlu rapor oluşturuldu. Güncellenen etiket: {len(updated)}.{warning}"
        return {"success": True, "message": message, "updated": updated, "missing": missing, "output_path": output_path}
