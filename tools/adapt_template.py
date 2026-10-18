"""Turn a template designed in Word into the bundled starter template.

    python tools/adapt_template.py design.docx assets/templates/packing_list_template.docx

The design is a normal TallyCraft template whose totals row is the parts table's
last row and whose footnotes / sign-off / note / shop record follow the table.
This script (SPEC §9.2):
- uses {{ p.display_name }} for the part name, drops "({{ total_weight_g }} g)"
  from the total weight, and turns the "Total count" heading into {{ count_header }};
- narrows the {%tc %} tag columns (they're removed when filled in) and gives the
  room to the Part column, so the template looks right while editing;
- moves the totals row and everything after the table into one unsplittable,
  full-width last row (the totals as a one-row table with the same columns), so the
  sign-off never starts a page alone; a bordered note paragraph becomes a one-cell
  table, since Word hides a paragraph's side borders inside a cell;
- clears the "last modified by" name (the repo is public).
"""
import copy
import sys
import zipfile

from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W}


def q(tag):
    return f"{{{W}}}{tag}"


def el(tag, **attrs):
    e = etree.Element(q(tag))
    for k, v in attrs.items():
        e.set(q(k), str(v))
    return e


def sub(parent, tag, **attrs):
    e = el(tag, **attrs)
    parent.append(e)
    return e


def text_of(node):
    return "".join(t.text or "" for t in node.iter(q("t")))


def set_para_text(p, new):
    """Put `new` in the paragraph's first text run and drop the other runs' text."""
    ts = list(p.iter(q("t")))
    ts[0].text = new
    for t in ts[1:]:
        r = t.getparent()
        r.getparent().remove(r)


def tc_pr(tc):
    pr = tc.find(q("tcPr"))
    if pr is None:
        pr = el("tcPr")
        tc.insert(0, pr)
    return pr


def margins(parent_tag, top, left, bottom, right):
    m = el(parent_tag)
    for side, v in (("top", top), ("left", left), ("bottom", bottom), ("right", right)):
        sub(m, side, w=v, type="dxa")
    return m


def borders(parent_tag, spec):
    b = el(parent_tag)
    for side in ("top", "left", "bottom", "right"):
        if side in spec and spec[side]:
            sub(b, side, val="single", sz=spec[side][0], space=0, color=spec[side][1])
        else:
            sub(b, side, val="nil")
    return b


def insert_tcpr_child(pr, child, after=("cnfStyle", "tcW", "gridSpan", "hMerge", "vMerge", "tcBorders", "shd",
                                        "noWrap", "tcMar", "textDirection", "tcFitText", "vAlign", "hideMark")):
    """Insert respecting the schema order of tcPr children."""
    order = list(after)
    name = etree.QName(child).localname
    old = pr.find(q(name))
    if old is not None:
        pr.remove(old)
    pos = order.index(name)
    idx = 0
    for i, c in enumerate(pr):
        if etree.QName(c).localname in order and order.index(etree.QName(c).localname) < pos:
            idx = i + 1
    pr.insert(idx, child)


def main(src, dst):
    with zipfile.ZipFile(src) as z:
        items = [(i, z.read(i.filename)) for i in z.infolist()]
    data = dict((i.filename, d) for i, d in items)
    root = etree.fromstring(data["word/document.xml"])
    body = root.find(q("body"))

    # -- 2. simple text changes
    for p in root.iter(q("p")):
        t = text_of(p)
        if "{{ p.name }}" in t:
            set_para_text(p, t.replace("{{ p.name }}", "{{ p.display_name }}"))
        elif "{{ total_weight_lb_oz }}" in t and "total_weight_g" in t:
            set_para_text(p, "{{ total_weight_lb_oz }}")
        elif t.strip() == "Total count":
            set_para_text(p, "{{ count_header }}")

    # -- 3. parts table
    parts = next(t for t in root.iter(q("tbl"))
                 if t.find("w:tblPr/w:tblDescription[@w:val='TallyCraft parts table']", NS) is not None)
    grid = parts.find(q("tblGrid"))
    cols = grid.findall(q("gridCol"))
    rows = parts.findall(q("tr"))
    header = rows[0].findall(q("tc"))
    start = next(i for i, tc in enumerate(header) if "{%tc for" in text_of(tc))
    end = next(i for i, tc in enumerate(header) if "{%tc endfor" in text_of(tc))
    name_i = 1

    # tidy the {%tc %} tag columns: narrow, 1 pt text, no margins (they're removed when filled in);
    # the freed width goes to the Part column so the template looks right while editing.
    TAG_W = 72
    widths = [int(c.get(q("w"))) for c in cols]
    freed = widths[start] + widths[end] - 2 * TAG_W
    widths[start] = widths[end] = TAG_W
    widths[name_i] += freed
    for c, w in zip(cols, widths):
        c.set(q("w"), str(w))
    for tr in rows:
        tcs = tr.findall(q("tc"))
        if len(tcs) != len(widths):
            continue
        for i, (tc, w) in enumerate(zip(tcs, widths)):
            tc_pr(tc).find(q("tcW")).set(q("w"), str(w))
            if i in (start, end) and "{%tc" in text_of(tc):
                insert_tcpr_child(tc_pr(tc), margins("tcMar", 0, 0, 0, 0))
                for rpr in tc.iter(q("rPr")):
                    for s in rpr.findall(q("sz")) + rpr.findall(q("szCs")):
                        rpr.remove(s)
                    sub(rpr, "sz", val=2)

    # -- 4. the last row: one unsplittable full-width cell holding the totals (a one-row table
    # with the same columns), footnotes, sign-off, note and shop record.
    totals_tr = rows[-1]
    parts.remove(totals_tr)
    total_w = sum(widths)

    end_tr = sub(parts, "tr")
    sub(sub(end_tr, "trPr"), "cantSplit")
    end_tc = sub(end_tr, "tc")
    pr = sub(end_tc, "tcPr")
    sub(pr, "tcW", w=total_w, type="dxa")
    sub(pr, "gridSpan", val=len(widths))
    pr.append(borders("tcBorders", {}))
    sub(pr, "shd", val="clear", color="auto", fill="auto")
    pr.append(margins("tcMar", 0, 0, 0, 0))

    tot = sub(end_tc, "tbl")
    tpr = copy.deepcopy(parts.find(q("tblPr")))
    tpr.find(q("tblDescription")).set(q("val"), "TallyCraft totals row")
    look = tpr.find(q("tblLook"))
    # no header-row formatting, no row banding (TallyCraft shades the moved part row itself)
    look.set(q("val"), "0680")
    look.set(q("firstRow"), "0")
    look.set(q("noHBand"), "1")
    tb = el("tblBorders")
    sub(tb, "top", val="nil")
    look.addprevious(tb)
    tot.append(tpr)
    tot.append(copy.deepcopy(grid))
    for cnf in totals_tr.iter(q("cnfStyle")):
        cnf.getparent().remove(cnf)
    tot.append(totals_tr)

    # everything after the parts table moves into the cell
    after = []
    nxt = parts.getnext()
    while nxt is not None and nxt.tag != q("sectPr"):
        after.append(nxt)
        nxt = nxt.getnext()
    for e in after:
        body.remove(e)
        if e.tag == q("p") and e.find("w:pPr/w:pBdr", NS) is not None:
            # A paragraph border loses its sides inside a table cell in Word: use a one-cell table.
            ppr = e.find(q("pPr"))
            ppr.remove(ppr.find(q("pBdr")))
            sp = ppr.find(q("spacing"))
            before = sp.get(q("before"), "0") if sp is not None else "0"
            spacer = sub(end_tc, "p")
            spr = sub(spacer, "pPr")
            sub(spr, "spacing", before=before, after=0, line=240, lineRule="auto")
            sub(sub(spr, "rPr"), "sz", val=2)
            if sp is not None:
                for a in ("before", "after"):
                    sp.set(q(a), "80")
            ind = el("ind", left=120, right=120)
            (sp if sp is not None else ppr[0]).addnext(ind)
            box = sub(end_tc, "tbl")
            bpr = sub(box, "tblPr")
            sub(bpr, "tblW", w=total_w - 30, type="dxa")
            bpr.append(borders("tblBorders", {s: (6, "A6A6A6") for s in ("top", "left", "bottom", "right")}))
            sub(bpr, "tblLayout", type="fixed")
            bpr.append(margins("tblCellMar", 0, 0, 0, 0))
            sub(sub(box, "tblGrid"), "gridCol", w=total_w - 30)
            btc = sub(sub(box, "tr"), "tc")
            sub(sub(btc, "tcPr"), "tcW", w=total_w - 30, type="dxa")
            btc.append(e)
        else:
            end_tc.append(e)
    # The table style makes the first column bold, and this cell counts as the first column;
    # the sign-off text wasn't bold outside the table, so say so explicitly.
    for r in end_tc.iter(q("r")):
        if tot in list(r.iterancestors(q("tbl"))):
            continue
        rpr = r.find(q("rPr"))
        if rpr is None:
            rpr = el("rPr")
            r.insert(0, rpr)
        if rpr.find(q("b")) is None:
            anchor = next((c for c in rpr if etree.QName(c).localname not in ("rStyle", "rFonts")), None)
            for tag in ("b", "bCs"):  # schema order: rStyle, rFonts, b, bCs, …
                e = el(tag, val=0)
                if anchor is not None:
                    anchor.addprevious(e)
                else:
                    rpr.append(e)
    if end_tc[-1].tag != q("p"):
        sub(end_tc, "p")
    # Word needs a paragraph between a table and the end of the document
    tail = el("p")
    tpr2 = sub(tail, "pPr")
    sub(tpr2, "spacing", after=0, line=240, lineRule="auto")
    sub(sub(tpr2, "rPr"), "sz", val=2)
    parts.addnext(tail)

    data["word/document.xml"] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    # public repo: no personal names in the file properties
    import re
    data["docProps/core.xml"] = re.sub(rb"<cp:lastModifiedBy>[^<]*</cp:lastModifiedBy>", b"<cp:lastModifiedBy/>",
                                       data["docProps/core.xml"])
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
        for info, _ in items:
            z.writestr(info, data[info.filename])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
