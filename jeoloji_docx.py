# Dosya: RaporPro/jeoloji_docx.py
"""Word gövdesindeki 2. JEOLOJİ bölümünü ilişkileriyle taşıyan OOXML yardımcıları."""

from __future__ import annotations

import copy
import os
from pathlib import Path
import posixpath
import re

from docx import Document
from docx.opc.packuri import PackURI
from docx.opc.part import Part
from docx.oxml.ns import qn

from jeoloji_kutuphanesi import BolumSinirlari, bolum_sinirlarini_bul, word_belgesi_ac


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
HEADER_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/header"
FOOTER_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer"
STYLE_REFERENCE_TAGS = {"pStyle", "rStyle", "tblStyle"}
STYLE_INHERITANCE_TAGS = {"basedOn", "next", "link"}


class JeolojiDocxHatasi(RuntimeError):
    """Bölüm aktarımının güvenli biçimde yapılamadığı durum."""


def _local_name(tag):
    return str(tag or "").rsplit("}", 1)[-1]


def _relationship_attr(attribute):
    if not str(attribute).startswith("{" + REL_NS + "}"):
        return False
    return _local_name(attribute) in {"id", "embed", "link"}


def _strip_section_properties(element):
    copied = copy.deepcopy(element)
    for descendant in list(copied.iter()):
        if _local_name(descendant.tag) != "sectPr":
            continue
        parent = descendant.getparent()
        if parent is not None:
            parent.remove(descendant)
    return copied


def _element_signature(element):
    """XML tanımını styleId'den bağımsız, karşılaştırılabilir biçimde üret."""
    return (
        _local_name(element.tag),
        tuple(sorted((str(key), str(value)) for key, value in element.attrib.items())),
        element.text or "",
        tuple(_element_signature(child) for child in element),
    )


def _style_signature(element, style_map=None):
    copied = copy.deepcopy(element)
    copied.attrib.pop(qn("w:styleId"), None)
    if style_map:
        for descendant in copied.iter():
            if _local_name(descendant.tag) not in STYLE_INHERITANCE_TAGS:
                continue
            value = descendant.get(qn("w:val"))
            if value in style_map:
                descendant.set(qn("w:val"), style_map[value])
    return _element_signature(copied)


def _unique_style_id(source_id, known_ids):
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", str(source_id)) or "Style"
    base = f"RaporProSrc_{safe_id}"
    candidate = base
    suffix = 2
    while candidate in known_ids:
        candidate = f"{base}_{suffix}"
        suffix += 1
    return candidate


def _remap_style_references(elements, style_map):
    for element in elements:
        for descendant in element.iter():
            if _local_name(descendant.tag) not in STYLE_REFERENCE_TAGS:
                continue
            value = descendant.get(qn("w:val"))
            if value in style_map:
                descendant.set(qn("w:val"), style_map[value])


def _copy_style_definitions(target_doc, source_doc):
    """Kaynak stillerini ekle ve çakışan styleId'leri bölüm için yeniden adlandır."""
    try:
        target_styles = target_doc.styles.element
        source_styles = source_doc.styles.element
    except Exception:
        return {}
    target_by_id = {
        child.get(qn("w:styleId")): child
        for child in target_styles
        if _local_name(child.tag) == "style" and child.get(qn("w:styleId"))
    }
    source_by_id = {
        child.get(qn("w:styleId")): child
        for child in source_styles
        if _local_name(child.tag) == "style" and child.get(qn("w:styleId"))
    }
    known_ids = set(target_by_id) | set(source_by_id)
    style_map = {}

    for style_id, source_style in source_by_id.items():
        target_style = target_by_id.get(style_id)
        if target_style is None or _style_signature(target_style) == _style_signature(source_style):
            style_map[style_id] = style_id
        else:
            remapped_id = _unique_style_id(style_id, known_ids)
            style_map[style_id] = remapped_id
            known_ids.add(remapped_id)

    changed = True
    while changed:
        changed = False
        for style_id, source_style in source_by_id.items():
            target_style = target_by_id.get(style_id)
            if target_style is None or style_map[style_id] != style_id:
                continue
            if _style_signature(target_style) == _style_signature(source_style, style_map):
                continue
            remapped_id = _unique_style_id(style_id, known_ids)
            style_map[style_id] = remapped_id
            known_ids.add(remapped_id)
            changed = True

    for style_id, source_style in source_by_id.items():
        target_id = style_map[style_id]
        if target_id == style_id and style_id in target_by_id:
            continue
        copied_style = copy.deepcopy(source_style)
        copied_style.set(qn("w:styleId"), target_id)
        for descendant in copied_style.iter():
            if _local_name(descendant.tag) not in STYLE_INHERITANCE_TAGS:
                continue
            value = descendant.get(qn("w:val"))
            if value in style_map:
                descendant.set(qn("w:val"), style_map[value])
        target_styles.append(copied_style)
    return style_map


def _num_id_attributes(elements):
    result = set()
    for element in elements:
        for descendant in element.iter():
            if _local_name(descendant.tag) != "numId":
                continue
            value = descendant.get(qn("w:val"))
            if value:
                result.add(value)
    return result


def _numbering_parts(doc):
    try:
        return doc.part.numbering_part.element
    except Exception:
        return None


def _next_xml_id(elements, tag_name, attr_name):
    values = []
    for element in elements:
        if _local_name(element.tag) != tag_name:
            continue
        raw = element.get(qn("w:" + attr_name))
        try:
            values.append(int(raw))
        except (TypeError, ValueError):
            continue
    return max(values, default=0) + 1


def _merge_numbering(target_doc, source_doc, copied_elements):
    source_numbering = _numbering_parts(source_doc)
    target_numbering = _numbering_parts(target_doc)
    if source_numbering is None or target_numbering is None:
        return {}
    source_num_ids = _num_id_attributes(copied_elements)
    if not source_num_ids:
        return {}
    source_nums = {
        element.get(qn("w:numId")): element
        for element in source_numbering
        if _local_name(element.tag) == "num" and element.get(qn("w:numId"))
    }
    source_abstracts = {
        element.get(qn("w:abstractNumId")): element
        for element in source_numbering
        if _local_name(element.tag) == "abstractNum" and element.get(qn("w:abstractNumId"))
    }
    next_num = _next_xml_id(target_numbering, "num", "numId")
    next_abstract = _next_xml_id(target_numbering, "abstractNum", "abstractNumId")
    mapping = {}
    for source_num_id in sorted(source_num_ids, key=lambda value: int(value) if str(value).isdigit() else 0):
        source_num = source_nums.get(source_num_id)
        if source_num is None:
            continue
        abstract_ref = source_num.find(qn("w:abstractNumId"))
        source_abstract_id = abstract_ref.get(qn("w:val")) if abstract_ref is not None else None
        source_abstract = source_abstracts.get(source_abstract_id)
        new_abstract_id = str(next_abstract)
        next_abstract += 1
        if source_abstract is not None:
            new_abstract = copy.deepcopy(source_abstract)
            new_abstract.set(qn("w:abstractNumId"), new_abstract_id)
            target_numbering.append(new_abstract)
        new_num_id = str(next_num)
        next_num += 1
        new_num = copy.deepcopy(source_num)
        new_num.set(qn("w:numId"), new_num_id)
        new_abstract_ref = new_num.find(qn("w:abstractNumId"))
        if new_abstract_ref is not None:
            new_abstract_ref.set(qn("w:val"), new_abstract_id)
        target_numbering.append(new_num)
        mapping[source_num_id] = new_num_id

    for element in copied_elements:
        for descendant in element.iter():
            if _local_name(descendant.tag) != "numId":
                continue
            value = descendant.get(qn("w:val"))
            if value in mapping:
                descendant.set(qn("w:val"), mapping[value])
    return mapping


def _part_template(part):
    name = str(part.partname)
    directory, filename = posixpath.split(name)
    stem, extension = posixpath.splitext(filename)
    stem = re.sub(r"\d+$", "", stem) or "part"
    return f"{directory}/{stem}%d{extension or '.bin'}"


def _same_blob_part(package, source_part):
    try:
        source_blob = source_part.blob
        source_content_type = source_part.content_type
    except Exception:
        return None
    if not source_blob:
        return None
    for part in package.iter_parts():
        try:
            if part.content_type == source_content_type and part.blob == source_blob:
                return part
        except Exception:
            continue
    return None


def _clone_part_graph(source_part, target_package, memo, reserved_names=None):
    reserved_names = reserved_names if reserved_names is not None else set()
    source_key = id(source_part)
    if source_key in memo:
        return memo[source_key]
    existing = _same_blob_part(target_package, source_part)
    if existing is not None and str(source_part.partname).startswith("/word/media/"):
        memo[source_key] = existing
        return existing
    try:
        template = _part_template(source_part)
        target_partname = target_package.next_partname(template)
        while str(target_partname) in reserved_names:
            match = re.search(r"(\d+)([^0-9]*)$", str(target_partname))
            if match:
                current = int(match.group(1)) + 1
                target_partname = PackURI(str(target_partname)[: match.start(1)] + str(current) + match.group(2))
            else:
                target_partname = target_package.next_partname(template)
                break
        reserved_names.add(str(target_partname))
        target_part = Part(target_partname, source_part.content_type, source_part.blob, target_package)
    except Exception as exc:
        raise JeolojiDocxHatasi(f"Kaynak Word parçası hedef pakete eklenemedi: {exc}") from exc
    memo[source_key] = target_part
    try:
        relationships = list(source_part.rels.values())
    except Exception:
        relationships = []
    for relationship in relationships:
        if relationship.is_external:
            target_part.load_rel(
                relationship.reltype,
                relationship.target_ref,
                relationship.rId,
                is_external=True,
            )
            continue
        child_part = _clone_part_graph(relationship.target_part, target_package, memo, reserved_names)
        target_part.load_rel(relationship.reltype, child_part, relationship.rId)
    return target_part


def _copy_document_relationships(source_doc, target_doc, copied_elements):
    relationship_ids = set()
    for element in copied_elements:
        for descendant in element.iter():
            for attribute, value in descendant.attrib.items():
                if _relationship_attr(attribute):
                    relationship_ids.add(value)
    mapping = {}
    memo = {}
    reserved_names = set()
    for source_id in sorted(relationship_ids):
        if source_id not in source_doc.part.rels:
            continue
        relationship = source_doc.part.rels[source_id]
        if relationship.reltype in {HEADER_REL, FOOTER_REL}:
            continue
        if relationship.is_external:
            target_id = target_doc.part.relate_to(
                relationship.target_ref,
                relationship.reltype,
                is_external=True,
            )
        else:
            target_part = _clone_part_graph(relationship.target_part, target_doc.part.package, memo, reserved_names)
            target_id = target_doc.part.relate_to(target_part, relationship.reltype)
        mapping[source_id] = target_id

    for element in copied_elements:
        for descendant in element.iter():
            for attribute, value in list(descendant.attrib.items()):
                if _relationship_attr(attribute) and value in mapping:
                    descendant.set(attribute, mapping[value])
    return mapping


def _package_xml_roots(document):
    seen = set()
    try:
        parts = document.part.package.iter_parts()
    except Exception:
        parts = ()
    for part in parts:
        try:
            root = part.element
        except Exception:
            continue
        if root is None or id(root) in seen:
            continue
        seen.add(id(root))
        yield root


def _used_numeric_ids(document, tag_name, attribute):
    values = set()
    for root in _package_xml_roots(document):
        for descendant in root.iter():
            if _local_name(descendant.tag) != tag_name:
                continue
            raw = descendant.get(attribute)
            try:
                values.add(int(raw))
            except (TypeError, ValueError):
                continue
    return values


def _next_free_id(used_ids):
    candidate = max(used_ids, default=0) + 1
    while candidate in used_ids:
        candidate += 1
    return candidate


def _remap_embedded_ids(target_doc, copied_elements):
    """Çizim ve bookmark kimliklerini hedef paketindeki kimliklerle çakıştırma."""
    used_docpr_ids = _used_numeric_ids(target_doc, "docPr", "id")
    next_docpr_id = _next_free_id(used_docpr_ids)
    for element in copied_elements:
        for descendant in element.iter():
            if _local_name(descendant.tag) != "docPr":
                continue
            descendant.set("id", str(next_docpr_id))
            used_docpr_ids.add(next_docpr_id)
            next_docpr_id = _next_free_id(used_docpr_ids)

    bookmark_id_attr = qn("w:id")
    used_bookmark_ids = _used_numeric_ids(target_doc, "bookmarkStart", bookmark_id_attr)
    used_bookmark_ids.update(_used_numeric_ids(target_doc, "bookmarkEnd", bookmark_id_attr))
    next_bookmark_id = _next_free_id(used_bookmark_ids)
    bookmark_map = {}
    for element in copied_elements:
        for descendant in element.iter():
            if _local_name(descendant.tag) not in {"bookmarkStart", "bookmarkEnd"}:
                continue
            source_id = descendant.get(bookmark_id_attr)
            if source_id is None:
                continue
            if source_id not in bookmark_map:
                bookmark_map[source_id] = next_bookmark_id
                used_bookmark_ids.add(next_bookmark_id)
                next_bookmark_id = _next_free_id(used_bookmark_ids)
            descendant.set(bookmark_id_attr, str(bookmark_map[source_id]))


def _section_elements(doc, boundaries):
    children = list(doc.element.body.iterchildren())
    if not boundaries.found:
        return []
    return [
        child
        for index, child in enumerate(children)
        if boundaries.start_index <= index < boundaries.end_index and _local_name(child.tag) != "sectPr"
    ]


def _sinirlari_donustur(boundaries):
    if not isinstance(boundaries, dict):
        return boundaries
    return BolumSinirlari(
        start_index=int(boundaries.get("start_index", -1)),
        end_index=int(boundaries.get("end_index", -1)),
        heading_level=int(boundaries.get("heading_level", 1)),
        start_heading=str(boundaries.get("start_heading", "")),
        end_heading=str(boundaries.get("end_heading", "")),
        end_found=bool(boundaries.get("end_found", False)),
        warnings=tuple(boundaries.get("warnings", ()) or ()),
    )


def _bolum_elemanlarini_hazirla(target_doc, source_doc, source_boundaries):
    source_elements = [
        _strip_section_properties(element)
        for element in _section_elements(source_doc, source_boundaries)
    ]
    if not source_elements:
        raise JeolojiDocxHatasi("Kaynak 2. JEOLOJİ bölümü boş veya okunamıyor.")
    style_map = _copy_style_definitions(target_doc, source_doc)
    _remap_style_references(source_elements, style_map)
    _merge_numbering(target_doc, source_doc, source_elements)
    _copy_document_relationships(source_doc, target_doc, source_elements)
    _remap_embedded_ids(target_doc, source_elements)
    return source_elements


def jeoloji_bolumu_belgesi_olustur(source_doc, source_boundaries=None):
    """Kaynak rapordan yalnız 2. JEOLOJİ aralığını içeren bağımsız Document üret."""
    source_boundaries = _sinirlari_donustur(
        source_boundaries or bolum_sinirlarini_bul(source_doc)
    )
    if not source_boundaries.found:
        raise JeolojiDocxHatasi("Kaynak Word dosyasında 2. JEOLOJİ başlığı bulunamadı.")

    section_doc = Document()
    section_elements = _bolum_elemanlarini_hazirla(
        section_doc,
        source_doc,
        source_boundaries,
    )
    body = section_doc.element.body
    neutral_sect_pr = next(
        (child for child in body.iterchildren() if _local_name(child.tag) == "sectPr"),
        None,
    )
    for child in list(body.iterchildren()):
        if child is not neutral_sect_pr:
            body.remove(child)
    if neutral_sect_pr is not None:
        for descendant in list(neutral_sect_pr.iter()):
            if _local_name(descendant.tag) not in {"headerReference", "footerReference"}:
                continue
            parent = descendant.getparent()
            if parent is not None:
                parent.remove(descendant)

    insert_index = 0
    for element in section_elements:
        body.insert(insert_index, element)
        insert_index += 1
    return section_doc


def jeoloji_bolumunu_dosyaya_cikar(source_path, target_path, source_boundaries=None):
    """Tam rapordaki 2. JEOLOJİ bölümünü atomik biçimde section-only DOCX'e yaz."""
    source_doc = word_belgesi_ac(source_path)
    boundaries = _sinirlari_donustur(
        source_boundaries or bolum_sinirlarini_bul(source_doc)
    )
    section_doc = jeoloji_bolumu_belgesi_olustur(source_doc, boundaries)
    target_path = Path(target_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    staged = target_path.parent / f".{target_path.name}.{os.getpid()}.tmp.docx"
    try:
        section_doc.save(str(staged))
        os.replace(staged, target_path)
    finally:
        try:
            staged.unlink()
        except OSError:
            pass
    return {
        "cache_path": str(target_path),
        "inserted_elements": len(_section_elements(section_doc, bolum_sinirlarini_bul(section_doc))),
        "source_start_heading": boundaries.start_heading,
        "source_end_heading": boundaries.end_heading,
    }


def jeoloji_bolumunu_degistir(target_doc, source_doc, source_boundaries=None):
    """Target document'teki ilk 2. JEOLOJİ aralığını source gövde aralığıyla değiştir."""
    source_boundaries = _sinirlari_donustur(
        source_boundaries or bolum_sinirlarini_bul(source_doc)
    )
    target_boundaries = bolum_sinirlarini_bul(target_doc)
    if not source_boundaries.found:
        raise JeolojiDocxHatasi("Kaynak Word dosyasında 2. JEOLOJİ başlığı bulunamadı.")
    if not target_boundaries.found:
        raise JeolojiDocxHatasi("Hedef rapor şablonunda 2. JEOLOJİ başlığı bulunamadı.")

    source_elements = _bolum_elemanlarini_hazirla(
        target_doc,
        source_doc,
        source_boundaries,
    )

    body = target_doc.element.body
    target_children = list(body.iterchildren())
    removed = target_children[target_boundaries.start_index:target_boundaries.end_index]
    insert_index = target_boundaries.start_index
    for child in removed:
        body.remove(child)
    for element in source_elements:
        body.insert(insert_index, element)
        insert_index += 1

    return {
        "removed_elements": len(removed),
        "inserted_elements": len(source_elements),
        "source_start_heading": source_boundaries.start_heading,
        "source_end_heading": source_boundaries.end_heading,
        "target_start_heading": target_boundaries.start_heading,
    }


def jeoloji_bolumunu_uygula(target_doc, source_path, source_boundaries=None):
    """Cache DOCX'ten bölümü hedef Document nesnesine uygula."""
    source_doc = word_belgesi_ac(source_path)
    return jeoloji_bolumunu_degistir(target_doc, source_doc, source_boundaries=source_boundaries)


replace_jeoloji_section = jeoloji_bolumunu_degistir
replace_jeoloji_section_from_path = jeoloji_bolumunu_uygula


__all__ = [
    "JeolojiDocxHatasi",
    "jeoloji_bolumu_belgesi_olustur",
    "jeoloji_bolumunu_degistir",
    "jeoloji_bolumunu_dosyaya_cikar",
    "jeoloji_bolumunu_uygula",
    "replace_jeoloji_section",
    "replace_jeoloji_section_from_path",
]
