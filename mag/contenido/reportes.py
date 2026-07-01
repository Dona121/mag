# -*- coding: utf-8 -*-
"""
Generación de informes de evaluación por dependencia (Excel y PDF).

Estos constructores reciben datos **planos** (los arma `construir_matriz` en
`views.py`) y no tocan el ORM ni las vistas: así se evita el import circular
(views importa este módulo de forma perezosa). Cada dependencia va en una hoja
(Excel) o página (PDF) distinta, con el logo de la Gobernación arriba a la
derecha y el encabezado institucional (Categoría · Dependencia · Periodo ·
Versión), replicando la jerarquía Pilar → Indicador → Subindicador → Criterios
de la pantalla de evaluación, con desglose por mes, puntaje y ponderación.

Motores: **openpyxl** (Excel) y **fpdf2** (PDF, Python puro). El logo se embebe
con manejo *best-effort*: si Pillow no está disponible (p. ej. bloqueado por una
política del SO), el informe se genera igual, solo sin la imagen.

Paleta y tipografía: tokens del Manual de Identidad (ver GUIA_DISEÑO.md).
"""
from decimal import Decimal
from io import BytesIO

from django.contrib.staticfiles import finders

from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# --- Paleta institucional (GUIA_DISEÑO.md) ---------------------------------
VERDE_SUP = "0e4d2a"
VERDE_PRIM = "109d39"
VERDE_CLARO = "e3f4ea"
AZUL = "0b72ab"
GRIS_CLARO = "dfe0e1"
GRIS_OSC = "5a595d"
BLANCO = "ffffff"

# equivalentes RGB para fpdf2
RGB_VERDE_SUP = (14, 77, 42)
RGB_VERDE_PRIM = (16, 157, 57)
RGB_PILAR = (205, 235, 214)
RGB_IND = (233, 244, 234)
RGB_AZUL = (11, 114, 171)
RGB_GRIS = (90, 89, 93)
RGB_GRIS_CLARO = (223, 224, 225)

LOGO_REL = "logos/2025_logo-gob-Sucre_2.png"
NUMFMT = "0.00###"  # mínimo 2 decimales, hasta 5 (igual que el filtro `decimales`)

COLS_FIJAS = ["Pilar", "Indicador", "Subindicador", "Tipo", "Criterios"]
COLS_TOTALES = ["Puntaje", "Ponderación"]


def _logo_path():
    return finders.find(LOGO_REL)


def _fmt(value):
    """Número a texto con mínimo 2 y hasta 5 decimales, coma decimal (es-col)."""
    if value is None:
        return ""
    d = value if isinstance(value, Decimal) else Decimal(str(value))
    exp = d.normalize().as_tuple().exponent
    usados = -exp if isinstance(exp, int) and exp < 0 else 0
    places = max(2, min(5, usados))
    return ("{:.%df}" % places).format(d).replace(".", ",")


def _pct(value):
    """Peso a texto con exactamente 2 decimales, coma decimal (es-col), con %."""
    if value is None:
        return ""
    d = value if isinstance(value, Decimal) else Decimal(str(value))
    return "{:.2f}".format(d).replace(".", ",") + "%"


def _num(value):
    """Decimal/None a float para celdas numéricas de Excel (None -> None)."""
    return float(value) if value is not None else None


def _criterios_txt(criterios):
    return "\n".join("{}: {}".format(n, r) for n, r in criterios) if criterios else ""


# ===========================================================================
# EXCEL
# ===========================================================================
_XL_INVALIDOS = set('[]:*?/\\')


def _sheet_title(nombre, usados):
    """Título de hoja válido: sin caracteres prohibidos, ≤31 chars y único."""
    base = "".join(c for c in (nombre or "Hoja") if c not in _XL_INVALIDOS).strip() or "Hoja"
    base = base[:31]
    titulo, i = base, 2
    while titulo.lower() in usados:
        sufijo = " ({})".format(i)
        titulo = base[:31 - len(sufijo)] + sufijo
        i += 1
    usados.add(titulo.lower())
    return titulo


def generar_excel(items):
    """items: lista de dicts de `construir_matriz`. Devuelve un BytesIO (.xlsx)."""
    wb = Workbook()
    wb.remove(wb.active)
    logo = _logo_path()
    usados = set()
    for it in items:
        ws = wb.create_sheet(_sheet_title(it["dependencia"], usados))
        _excel_hoja(ws, it, logo)
    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)
    return bio


def _head_cell(ws, r, c, texto, fill, alignment, borde):
    cell = ws.cell(r, c, texto)
    cell.font = Font(bold=True, color=BLANCO, size=10)
    cell.fill = fill
    cell.alignment = alignment
    cell.border = borde
    return cell


def _excel_hoja(ws, it, logo):
    meses = it["meses"]
    n_meses = len(meses)
    # Columnas (calca la evaluación): 1 Pilar | 2 Indicador | 3 Subindicador | 4 Tipo |
    # 5 Criterios | 6..(5+n) meses (bajo "Puntaje 0-100") | (6+n) Ponderación.
    mes0, mesN = 6, 5 + n_meses
    col_pond = 6 + n_meses
    col_obs = col_pond + 1
    n_cols = col_obs

    thin = Side(style="thin", color=GRIS_CLARO)
    borde = Border(left=thin, right=thin, top=thin, bottom=thin)
    fill_head = PatternFill("solid", fgColor=VERDE_SUP)
    fill_pilar = PatternFill("solid", fgColor=VERDE_CLARO)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left = Alignment(horizontal="left", vertical="center", wrap_text=True)

    # --- Encabezado institucional (filas 1-5) + logo arriba a la derecha ---
    ws["A1"] = "INFORME · MODELO DE ALTA GERENCIA"
    ws["A1"].font = Font(size=14, bold=True, color=VERDE_SUP)
    info = [
        ("Categoría", it["categoria"]),
        ("Dependencia", it["dependencia"]),
        ("Periodo", "{}{}".format(it["periodo"], " · {}".format(it["vigencia"]) if it["vigencia"] else "")),
        ("Versión", str(it["version"])),
    ]
    for i, (k, v) in enumerate(info, start=2):
        ws.cell(i, 1, "{}:".format(k)).font = Font(bold=True, color=GRIS_OSC, size=10)
        ws.cell(i, 2, v).font = Font(color=GRIS_OSC, size=10)
    if logo:
        try:
            img = XLImage(logo)
            ratio = (img.width / img.height) if img.height else 3
            img.height = 58
            img.width = int(58 * ratio)
            ws.add_image(img, "{}1".format(get_column_letter(max(1, n_cols - 1))))
        except Exception:
            pass  # sin Pillow: informe igual, sin logo

    # --- Cabecera de la tabla en 2 filas (7-8) ---
    hr, hr2 = 7, 8
    fijos = ["Pilar", "Indicador", "Subindicador", "Tipo", "Criterios"]
    for c, texto in enumerate(fijos, start=1):
        ws.merge_cells(start_row=hr, start_column=c, end_row=hr2, end_column=c)
        _head_cell(ws, hr, c, texto, fill_head, center, borde)
    if n_meses > 1:
        ws.merge_cells(start_row=hr, start_column=mes0, end_row=hr, end_column=mesN)
    _head_cell(ws, hr, mes0, "Puntaje (0-100)", fill_head, center, borde)
    for mi, (_mnum, lbl) in enumerate(meses):
        _head_cell(ws, hr2, mes0 + mi, lbl, fill_head, center, borde)
    ws.merge_cells(start_row=hr, start_column=col_pond, end_row=hr2, end_column=col_pond)
    _head_cell(ws, hr, col_pond, "Ponderación", fill_head, center, borde)
    ws.merge_cells(start_row=hr, start_column=col_obs, end_row=hr2, end_column=col_obs)
    _head_cell(ws, hr, col_obs, "Observaciones", fill_head, center, borde)
    for c in range(1, n_cols + 1):  # fill/borde en celdas cubiertas de la cabecera
        for rr in (hr, hr2):
            cell = ws.cell(rr, c)
            cell.fill = fill_head
            cell.border = borde

    # --- Filas de datos con celdas combinadas por Pilar/Indicador ---
    r = hr2 + 1
    for pilar in it["pilares"]:
        pilar_ini = r
        indicadores = pilar["indicadores"] or [None]
        for ind in indicadores:
            ind_ini = r
            subs = (ind["subindicadores"] if ind else []) or [None]
            for sub in subs:
                if sub:
                    nombre_sub = sub["nombre"]
                    if sub["peso"] is not None:
                        nombre_sub = "{}\n(peso {})".format(sub["nombre"], _pct(sub["peso"]))
                    ws.cell(r, 3, nombre_sub).alignment = left
                    ws.cell(r, 4, (sub["tipo"] or "").capitalize()).alignment = center
                    ws.cell(r, 5, _criterios_txt(sub["criterios"])).alignment = left
                    if sub["tipo"] == "mensual":
                        for mi, (mnum, _lbl) in enumerate(meses):
                            cc = ws.cell(r, mes0 + mi, _num(sub["meses"].get(mnum)))
                            cc.number_format = NUMFMT; cc.alignment = center
                    else:  # directo: combina las celdas de los meses y muestra el puntaje
                        if n_meses > 1:
                            ws.merge_cells(start_row=r, start_column=mes0, end_row=r, end_column=mesN)
                        cc = ws.cell(r, mes0, _num(sub["puntaje"]))
                        cc.number_format = NUMFMT; cc.alignment = center
                    co = ws.cell(r, col_pond, _num(sub["ponderacion"]))
                    co.number_format = NUMFMT; co.alignment = center
                    ws.cell(r, col_obs, sub.get("observaciones", "")).alignment = left
                else:
                    ws.cell(r, 3, "—").alignment = left
                for c in range(1, n_cols + 1):
                    ws.cell(r, c).border = borde
                r += 1
            if ind:
                _merge_v(ws, 2, ind_ini, r - 1,
                         "{}\n(peso {})".format(ind["nombre"], _pct(ind["peso"])), center, borde)
        _merge_v(ws, 1, pilar_ini, r - 1,
                 "{}\n(peso {})".format(pilar["nombre"], _pct(pilar["peso"])), center, borde,
                 fill=fill_pilar)

    # --- Anchos de columna ---
    for col, w in (("A", 20), ("B", 22), ("C", 30), ("D", 10), ("E", 34)):
        ws.column_dimensions[col].width = w
    for mi in range(n_meses):
        ws.column_dimensions[get_column_letter(mes0 + mi)].width = 11
    ws.column_dimensions[get_column_letter(col_pond)].width = 13
    ws.column_dimensions[get_column_letter(col_obs)].width = 34
    ws.freeze_panes = ws.cell(hr2 + 1, 1)
    ws.sheet_view.showGridLines = False


def _merge_v(ws, col, r0, r1, texto, alignment, borde, fill=None):
    if r1 < r0:
        return
    if r1 > r0:
        ws.merge_cells(start_row=r0, start_column=col, end_row=r1, end_column=col)
    cell = ws.cell(r0, col, texto)
    cell.alignment = alignment
    cell.font = Font(bold=True, size=10, color=(VERDE_SUP if fill is not None else GRIS_OSC))
    for rr in range(r0, r1 + 1):
        c = ws.cell(rr, col)
        c.border = borde
        if fill is not None:
            c.fill = fill


# ===========================================================================
# PDF  (fpdf2 — Python puro; logo best-effort)
# ===========================================================================
def _lat1(s):
    """Sanea texto al set latin-1 de las fuentes core de fpdf2 (evita errores por
    caracteres no soportados; devuelve '?' para los que falten)."""
    return str(s).encode("latin-1", "replace").decode("latin-1")


def generar_pdf(items):
    """items: lista de dicts de `construir_matriz`. Devuelve bytes (PDF)."""
    from fpdf import FPDF

    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(True, margin=12)
    pdf.set_margins(12, 10, 12)
    logo = _logo_path()
    for it in items:
        pdf.add_page()
        _pdf_encabezado(pdf, it, logo)
        _pdf_tabla(pdf, it)
    return bytes(pdf.output())


def _pdf_encabezado(pdf, it, logo):
    top = pdf.get_y()
    if logo:
        try:
            pdf.image(logo, x=pdf.w - pdf.r_margin - 42, y=top, h=14)
        except Exception:
            pass  # sin Pillow: informe igual, sin logo
    pdf.set_xy(pdf.l_margin, top)
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(*RGB_VERDE_SUP)
    pdf.cell(0, 7, _lat1("INFORME · MODELO DE ALTA GERENCIA"), new_x="LMARGIN", new_y="NEXT")

    per = "{}{}".format(it["periodo"], " · {}".format(it["vigencia"]) if it["vigencia"] else "")
    lineas = [
        ("Categoría", it["categoria"]), ("Dependencia", it["dependencia"]),
        ("Periodo", per), ("Versión", str(it["version"])),
    ]
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*RGB_GRIS)
    for k, v in lineas:
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(pdf.get_string_width(k + ": ") + 1, 5, _lat1(k + ":"))
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(0, 5, " " + _lat1(v), new_x="LMARGIN", new_y="NEXT")

    y = pdf.get_y() + 1
    pdf.set_draw_color(*RGB_VERDE_PRIM)
    pdf.set_line_width(0.5)
    pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
    pdf.ln(4)


def _pdf_tabla(pdf, it):
    from fpdf.fonts import FontFace

    meses = it["meses"]
    n_meses = len(meses)
    fijos = ["Pilar", "Indicador", "Subindicador", "Tipo", "Criterios"]

    usable = pdf.w - pdf.l_margin - pdf.r_margin
    base = [24, 28, 34, 13, 44] + [14] * n_meses + [16, 38]
    factor = usable / sum(base)
    widths = [w * factor for w in base]

    est_head = FontFace(emphasis="BOLD", color=(255, 255, 255), fill_color=RGB_VERDE_SUP)
    est_pilar = FontFace(emphasis="BOLD", color=RGB_VERDE_SUP, fill_color=RGB_PILAR)
    est_ind = FontFace(emphasis="BOLD", color=RGB_AZUL, fill_color=RGB_IND)

    pdf.set_font("Helvetica", "", 7)
    pdf.set_text_color(*RGB_GRIS)
    pdf.set_draw_color(*RGB_GRIS_CLARO)
    pdf.set_line_width(0.2)

    with pdf.table(col_widths=widths, line_height=4.4, first_row_as_headings=False,
                   text_align="LEFT", v_align="MIDDLE", borders_layout="ALL") as table:
        # Cabecera en 2 filas: los meses van bajo "Puntaje (0-100)".
        h1 = table.row()
        for t in fijos:
            h1.cell(_lat1(t), rowspan=2, style=est_head, align="CENTER")
        h1.cell("Puntaje (0-100)", colspan=n_meses, style=est_head, align="CENTER")
        h1.cell("Ponderación", rowspan=2, style=est_head, align="CENTER")
        h1.cell("Observaciones", rowspan=2, style=est_head, align="CENTER")
        h2 = table.row()
        for _mnum, lbl in meses:
            h2.cell(_lat1(lbl), style=est_head, align="CENTER")

        # Filas con Pilar/Indicador combinados (rowspan), como en la evaluación.
        for pilar in it["pilares"]:
            inds = pilar["indicadores"] or [None]
            pilar_rows = sum(max(len(i["subindicadores"]) if i else 0, 1) for i in inds)
            pilar_txt = _lat1("{}\n(peso {})".format(pilar["nombre"], _pct(pilar["peso"])))
            pilar_first = True
            for ind in inds:
                subs = (ind["subindicadores"] if ind else []) or [None]
                ind_txt = _lat1("{}\n(peso {})".format(ind["nombre"], _pct(ind["peso"]))) if ind else "—"
                ind_first = True
                for sub in subs:
                    row = table.row()
                    if pilar_first:
                        row.cell(pilar_txt, rowspan=pilar_rows, style=est_pilar)
                        pilar_first = False
                    if ind_first:
                        row.cell(ind_txt, rowspan=len(subs), style=est_ind)
                        ind_first = False
                    if sub:
                        row.cell(_lat1("{}\n(peso {})".format(sub["nombre"], _pct(sub["peso"]))))
                        row.cell(_lat1((sub["tipo"] or "").capitalize()), align="CENTER")
                        row.cell(_lat1(_criterios_txt(sub["criterios"])))
                        if sub["tipo"] == "mensual":
                            for mnum, _lbl in meses:
                                row.cell(_fmt(sub["meses"].get(mnum)), align="CENTER")
                        else:  # directo: combina las celdas de los meses y muestra el puntaje
                            row.cell(_fmt(sub["puntaje"]), colspan=n_meses, align="CENTER")
                        row.cell(_fmt(sub["ponderacion"]), align="CENTER")
                        row.cell(_lat1(sub.get("observaciones", "")))
                    else:
                        row.cell("—")
                        row.cell("", align="CENTER")
                        row.cell("")
                        row.cell("", colspan=n_meses)
                        row.cell("")
                        row.cell("")
