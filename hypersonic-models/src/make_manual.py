"""Generate the assembly manual PDF from the built STL files and previews."""

import math
import os

import trimesh
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

import build_models as bm

OUT = bm.OUT
PREV = os.path.join(OUT, "previews")
PDF = os.path.join(OUT, "Hypersonic_Models_Assembly_Manual.pdf")

ss = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=ss["Heading1"], fontSize=20, spaceAfter=8,
                    textColor=colors.HexColor("#1d2a44"))
H2 = ParagraphStyle("H2", parent=ss["Heading2"], fontSize=14, spaceBefore=10,
                    spaceAfter=4, textColor=colors.HexColor("#1d2a44"))
H3 = ParagraphStyle("H3", parent=ss["Heading3"], fontSize=11, spaceBefore=6,
                    spaceAfter=2)
B = ParagraphStyle("B", parent=ss["BodyText"], fontSize=9.5, leading=13)
SM = ParagraphStyle("SM", parent=B, fontSize=8, leading=10)
CAP = ParagraphStyle("CAP", parent=SM, alignment=TA_CENTER,
                     textColor=colors.HexColor("#555555"))
NOTE = ParagraphStyle("NOTE", parent=B, backColor=colors.HexColor("#eef3fb"),
                      borderColor=colors.HexColor("#9fb4d9"), borderWidth=0.6,
                      borderPadding=6, spaceBefore=6, spaceAfter=8)

PIN_LEN = 2 * bm.PIN_DEPTH - 0.5


def img(name, width, max_h=3.4 * inch):
    path = os.path.join(PREV, name)
    from PIL import Image as PI
    w, h = PI.open(path).size
    if width * h / w > max_h:
        width = max_h * w / h
    return Image(path, width=width, height=width * h / w)


def p(text, style=B):
    return Paragraph(text, style)


def bullets(items, style=B):
    return [Paragraph("&bull;&nbsp; " + t, style) for t in items]


def steps(items):
    return [Paragraph(f"<b>{i}.</b>&nbsp; {t}", B) for i, t in enumerate(items, 1)]


def tbl(rows, widths, header=True, font=8.5):
    t = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ("FONT", (0, 0), (-1, -1), "Helvetica", font),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b8bfcc")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#f4f6fa")]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1d2a44")),
                  ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                  ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", font)]
    t.setStyle(TableStyle(style))
    return t


def dims(name):
    m = trimesh.load(os.path.join(bm.STL_DIR, name + ".stl"))
    e = m.extents
    return f"{e[0]:.0f} x {e[1]:.0f} x {e[2]:.0f}"


def parts_table(rows):
    """rows: (file, qty, orientation, supports)."""
    data = [["File (stl/ and step/)", "Qty", "Size mm (as printed)",
             "Print orientation", "Supports"]]
    for f, q, o, s in rows:
        data.append([f + ".stl", str(q), dims(f), Paragraph(o, SM), s])
    return tbl(data, [1.75 * inch, 0.35 * inch, 1.2 * inch, 2.4 * inch,
                      0.7 * inch])


def thumbs(names, per_row=4):
    cells, row = [], []
    w = 6.9 * inch / per_row
    for n in names:
        row.append([img(f"print_{n}.png", w - 6, 1.1 * inch), p(n, CAP)])
        if len(row) == per_row:
            cells.append(row)
            row = []
    if row:
        cells.append(row + [""] * (per_row - len(row)))
    t = Table(cells, colWidths=[w] * per_row)
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM")]))
    return t


def stand_rows(slug):
    return [(f"{slug}_stand_base", 1, "Flat, label up", "No"),
            (f"{slug}_stand_post", 1, "Standing upright, peg up; 5 mm brim",
             "No")]


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.HexColor("#777777"))
    canvas.drawString(0.75 * inch, 0.5 * inch,
                      "Hypersonic Vehicle Display Models - Assembly Manual")
    canvas.drawRightString(7.75 * inch, 0.5 * inch, f"Page {doc.page}")
    canvas.restoreState()


def build():
    beta = bm.shock_angle(6.0, math.radians(7.0))
    th = math.radians(7.0)
    mn2 = (6.0 * math.sin(beta)) ** 2
    p21 = 1 + 2 * 1.4 / 2.4 * (mn2 - 1)

    s = []
    # ---------------------------------------------------------------- cover
    s += [Spacer(1, 0.3 * inch),
          p("Hypersonic Vehicle Display Models", H1),
          p("Print-and-assemble kit for PLA+ &nbsp;|&nbsp; X-43A &middot; "
            "X-51A &middot; HTV-2 &middot; X-15 &middot; Caret waverider", H3),
          Spacer(1, 8)]
    cov = Table([[img("x43a_assembled.png", 3.3 * inch),
                  img("x51a_assembled.png", 3.3 * inch)],
                 [p("X-43A Hyper-X, 1:24", CAP), p("X-51A Waverider, 1:24", CAP)],
                 [img("x15_assembled.png", 3.3 * inch),
                  img("htv2_assembled.png", 3.3 * inch)],
                 [p("X-15, 1:72", CAP), p("HTV-2, 1:24", CAP)]],
                colWidths=[3.45 * inch] * 2)
    s += [cov, Spacer(1, 6),
          p("<b>About these models.</b> The outer shapes are <b>approximations</b> "
            "built from published overall dimensions and public photographs. "
            "Detailed outer mold lines for these vehicles are not public, so the "
            "models are meant for display and teaching, not for wind-tunnel or "
            "CFD-grade geometry. The one exception is the caret waverider, which "
            "is the exact inviscid shape from oblique-shock theory for its design "
            "point.", NOTE),
          PageBreak()]

    # ---------------------------------------------------------- contents
    s += [p("What's in the kit", H2),
          tbl([["Model", "Scale", "Length", "Parts", "Real vehicle"],
               ["X-43A Hyper-X", "1:24", "153 mm", "2 body + 4 surfaces",
                "3.66 m, H2 scramjet, Mach 9.6 (2004)"],
               ["X-51A Waverider (cruiser)", "1:24", "178 mm",
                "2 body + 4 fins", "4.27 m cruiser, JP-7 scramjet, Mach 5.1 (2013)"],
               ["HTV-2 Falcon", "1:24", "163 mm", "1 body",
                "~3.7 m boost-glide vehicle (2010, 2011)"],
               ["North American X-15", "1:72", "215 mm",
                "2 body + 6 surfaces", "15.45 m, rocket plane, Mach 6.70 (1967)"],
               ["Caret waverider", "-", "160 mm", "1 body",
                "Nonweiler caret, M = 6, theta = 7 deg"]],
              [1.7 * inch, 0.5 * inch, 0.6 * inch, 1.35 * inch, 2.75 * inch]),
          Spacer(1, 4),
          p("Every model also has a display stand (base with engraved label + post). "
            "Each part comes as an <b>STL</b> (for your slicer) and a <b>STEP</b> "
            "(opens as an editable solid in Fusion or SolidWorks). The Python "
            "source in <font face='Courier'>src/</font> regenerates everything "
            "and holds all dimensions as parameters.", B),
          p("Printer bed", H3),
          p("All parts except the X-15 body halves fit within 180 x 180 mm. The "
            "X-15 halves are 215 mm long: they fit a 220 mm (or larger) bed, or "
            "lie diagonally on a 180 mm bed (for example a Bambu A1 mini).", B),

          p("Materials and tools", H2)]
    s += bullets([
        "PLA+ filament, roughly 250-350 g for the whole set (about 40-90 g per model "
        "including its stand).",
        f"<b>Alignment pins:</b> a short length of 1.75 mm filament. Cut pins to "
        f"<b>{PIN_LEN:.1f} mm</b>. The holes are {bm.PIN_D} mm wide and "
        f"{bm.PIN_DEPTH} mm deep in each half.",
        "Glue: medium CA (super glue) with accelerator, or 5-minute epoxy for a "
        "longer working time on the body seams.",
        "Hobby knife, flush cutters, needle files, sandpaper (220, 400, 800 grit), "
        "small square or set square, rubber bands or small clamps.",
        "Optional: filler putty or filler primer, spray primer, acrylic or enamel "
        "paints, decals.",
    ])

    s += [p("Print settings (PLA+)", H2),
          tbl([["Setting", "Body parts", "Fins / surfaces", "Stand"],
               ["Nozzle", "0.4 mm", "0.4 mm", "0.4 mm"],
               ["Layer height", "0.12-0.16 mm (finer = smoother curves)",
                "0.12 mm", "0.2 mm"],
               ["Walls / perimeters", "3-4", "4 (effectively solid)", "3"],
               ["Top / bottom layers", "5 / 4", "solid", "4 / 4"],
               ["Infill", "15-20 % gyroid", "100 %", "15 %"],
               ["Nozzle / bed temp", "205-220 C / 55-60 C (follow your spool)",
                "same", "same"],
               ["Supports", "None (split face down)", "None", "None"],
               ["Adhesion", "Brim on X-43A lower half, HTV-2, caret",
                "None or 3 mm brim", "Brim on post"]],
              [1.3 * inch, 2.35 * inch, 1.6 * inch, 1.55 * inch]),
          Spacer(1, 4),
          p("<b>Why split bodies?</b> Each fuselage is cut in half at a flat "
            "horizontal plane. Each half prints on that flat face with no "
            "supports, and the curved outer skin builds up as gentle overhangs. "
            "Fins print flat on the bed, which makes them stronger and keeps the "
            "edges crisp.", NOTE),
          PageBreak()]

    # ------------------------------------------------------ general method
    s += [p("General assembly technique (all models)", H2)]
    s += steps([
        "<b>Clean up.</b> Remove brims. Shave the 'elephant foot' lip off every "
        "split face with a hobby knife held flat, so the two halves close with "
        "no gap. Check that the pin holes are clear (twist a 2 mm drill bit by "
        "hand if needed).",
        f"<b>Make the pins.</b> Cut {PIN_LEN:.1f} mm lengths of 1.75 mm filament, "
        "one per pin hole pair. Glue them into the <b>lower</b> half only.",
        "<b>Dry fit everything</b> before gluing. Close the halves on the pins, "
        "then push every fin tab into its slot. Slots have 0.2 mm clearance per "
        "side. If a tab is tight, sand its faces, not the slot. Each fin root "
        "is trimmed to the curved body, so it seats flush only the right way "
        "round, with the swept leading edge facing the nose.",
        "<b>Glue the body.</b> Run a thin bead of CA or epoxy around the split "
        "face, keeping 2 mm away from the outer edge so glue doesn't squeeze "
        "out. Close on the pins and hold with rubber bands for a few minutes.",
        "<b>Fit the surfaces.</b> Put a drop of glue on each tab, insert it, and "
        "set its angle with a square while the glue grabs. Mirror-image pairs "
        "(left and right wings, for example) are the same part flipped over.",
        "<b>Finish.</b> Fill the seam with putty or filler primer, then sand "
        "220 &rarr; 400 &rarr; 800. Prime, check under strong side light, fill "
        "again if needed, then paint.",
        "<b>Stand.</b> Glue the post into the base. Leave the 6 mm peg unglued "
        "in the model's socket so the model lifts off for handling.",
    ])
    s += [p("Fit tuning: if your printer runs tight, scale <b>only the fin "
            "parts</b> to 98-99 % in the slicer, or set <font face='Courier'>CLEAR"
            "</font> in <font face='Courier'>build_models.py</font> to 0.25-0.3 mm "
            "and regenerate. Don't scale a whole model in the slicer if you want "
            "the pins and peg to keep fitting.", NOTE),
          PageBreak()]

    # ------------------------------------------------------------- X-43A
    s += [p("1. NASA X-43A Hyper-X &nbsp;(1:24)", H2),
          p("NASA built the X-43A to show that an airframe-integrated, "
            "hydrogen-fuelled scramjet could work in flight. It was carried by a "
            "B-52B and boosted by a modified Pegasus rocket. On 27 March 2004 it "
            "flew at about Mach 6.8, and on 16 November 2004 at about Mach 9.6, a "
            "record for an air-breathing vehicle.", B),
          p("<b>What to look for:</b> the whole underside is the engine. The "
            "forebody ramps compress the air before the inlet, the cowl and "
            "sidewalls form a real flow-through duct (you can see daylight "
            "through it), and the upswept aft underside is the single-expansion "
            "ramp nozzle (SERN).", B),
          img("x43a_exploded.png", 4.6 * inch),
          p("Exploded view. Grey: body halves; orange: printed-flat surfaces.",
            CAP),
          parts_table([
              ("x43a_body_upper", 1, "Split face down", "No"),
              ("x43a_body_lower", 1, "Split face down (cowl on top; the duct "
               "roof is a 23 mm bridge). 5 mm brim", "No"),
              ("x43a_wing_x2", 2, "Flat", "No"),
              ("x43a_vtail_x2", 2, "Flat", "No"),
          ] + stand_rows("x43a")),
          Spacer(1, 4),
          thumbs(["x43a_body_upper", "x43a_body_lower", "x43a_wing_x2",
                  "x43a_vtail_x2"]),
          p("Assembly", H3)]
    s += steps([
        f"Glue three pins ({PIN_LEN:.1f} mm) into the lower half. Dry-fit the "
        "upper half.",
        "Glue the halves (see General technique). The duct lies entirely in "
        "the lower half, so keep glue off the cowl.",
        "<b>All-moving wings:</b> the side slots sit exactly on the seam. Push a "
        "wing tab into each side with the long straight root against the body, "
        "the swept edge forward, and the wing level (0 deg dihedral).",
        "<b>Vertical tails:</b> push the tabs into the two slots on the upper "
        "aft deck and square them at 90 deg to the deck.",
        "Socket: under the forebody ramp, about 69 mm behind the nose.",
    ])
    s += [p("<b>Paint:</b> refer to NASA Armstrong flight photographs for the "
            "scheme. A flat-black overall finish with the underside engine "
            "module left slightly lighter makes the flowpath stand out on a "
            "display model.", SM), PageBreak()]

    # ------------------------------------------------------------- X-51A
    s += [p("2. X-51A Waverider &nbsp;(1:24, cruiser)", H2),
          p("A USAF / DARPA / NASA program with Boeing and Pratt &amp; Whitney "
            "Rocketdyne. The SJY61 scramjet burned JP-7, which also cooled the "
            "engine. After a B-52H drop and a booster burn, the fourth and final "
            "flight on 1 May 2013 reached Mach 5.1, with about 210 s of scramjet "
            "operation.", B),
          p("<b>What to look for:</b> the flat, sharp forebody is a waverider "
            "surface that pre-compresses air into the underside inlet, so the "
            "vehicle rides its own shock. The model has an open inlet and an "
            "open nozzle on the ventral nacelle. Only the cruiser is modeled "
            "here, not the interstage or booster.", B),
          img("x51a_exploded.png", 4.6 * inch),
          p("Exploded view.", CAP),
          parts_table([
              ("x51a_body_upper", 1, "Split face down", "No"),
              ("x51a_body_lower", 1, "Split face down (nacelle on top)", "No"),
              ("x51a_fin_upper_x2", 2, "Flat", "No"),
              ("x51a_fin_lower_x2", 2, "Flat (root notched to clear nacelle)",
               "No"),
          ] + stand_rows("x51a")),
          Spacer(1, 4),
          thumbs(["x51a_body_upper", "x51a_body_lower", "x51a_fin_upper_x2",
                  "x51a_fin_lower_x2"]),
          p("Assembly", H3)]
    s += steps([
        f"Glue three pins into the lower half: two side by side mid-body and "
        "one aft. There are no pins in the thin nose; glue it carefully and "
        "clamp the tip.",
        "Glue the halves.",
        "<b>Fins (X layout, 45 deg):</b> the upper pair goes into the slots in "
        "the upper half, the lower pair into the slots beside the nacelle. Keep "
        "upper and lower fins apart; their roots are shaped differently. The "
        "slot sets the 45 deg angle.",
        "Socket: under the nacelle, about 115 mm behind the nose.",
    ])
    s += [p("<b>Paint:</b> follow USAF / AFRL flight-vehicle photographs.", SM),
          PageBreak()]

    # ------------------------------------------------------------- HTV-2
    s += [p("3. DARPA HTV-2 Falcon &nbsp;(1:24)", H2),
          p("A hypersonic boost-glide test vehicle built by Lockheed Martin for "
            "DARPA's Falcon program. It flew twice on Minotaur IV Lite rockets "
            "from Vandenberg, on 22 April 2010 and 11 August 2011, and was meant "
            "to glide at about Mach 20 with a carbon-carbon aeroshell. Both "
            "flights ended early.", B),
          p("<b>Note:</b> the detailed HTV-2 shape is not public. This model is "
            "a generic sharp-nosed, flat-bottomed lifting cone with two body "
            "flaps, sized from the published length. Treat it as representative "
            "of the class.", NOTE),
          img("htv2_assembled.png", 4.2 * inch),
          parts_table([("htv2_body", 1, "On its flat bottom; 5 mm brim. "
                        "Flaps print as part of the first layers", "No")] +
                      stand_rows("htv2")),
          Spacer(1, 4),
          thumbs(["htv2_body", "htv2_stand_base", "htv2_stand_post"]),
          p("Assembly", H3)]
    s += steps([
        "Remove the brim carefully around the thin (1.5 mm) body flaps.",
        "Sand the upper surface lightly, 400 then 800 grit, along the length.",
        "Socket: centred in the flat bottom, about 92 mm behind the nose.",
    ])
    s += [p("<b>Paint:</b> dark grey / charcoal (carbon-carbon).", SM),
          PageBreak()]

    # ------------------------------------------------------------- X-15
    s += [p("4. North American X-15 &nbsp;(1:72)", H2),
          p("The X-15 was a rocket-powered research aircraft that flew 199 "
            "missions between 1959 and 1968 from a B-52 mothership. Pete Knight "
            "set the speed record of Mach 6.70 on 3 October 1967 in the "
            "lengthened X-15A-2. This model shows the standard-length "
            "aircraft.", B),
          p("<b>What to look for:</b> the thick wedge-section vertical tails, "
            "which gave stability at high Mach; the side fairings; and the "
            "all-moving horizontal tails with 15 deg anhedral. The lower ventral "
            "fin was jettisoned before landing, so it's optional on the model.",
            B),
          img("x15_exploded.png", 4.8 * inch),
          p("Exploded view.", CAP),
          parts_table([
              ("x15_body_upper", 1, "Split face down", "No"),
              ("x15_body_lower", 1, "Split face down", "No"),
              ("x15_wing_x2", 2, "Flat", "No"),
              ("x15_htail_x2", 2, "Flat", "No"),
              ("x15_upper_vtail", 1, "Flat", "No"),
              ("x15_ventral_fin", 1, "Flat (optional)", "No"),
          ] + stand_rows("x15")),
          Spacer(1, 4),
          thumbs(["x15_body_upper", "x15_body_lower", "x15_wing_x2",
                  "x15_htail_x2", "x15_upper_vtail", "x15_ventral_fin"]),
          p("Assembly", H3)]
    s += steps([
        "Glue three pins into the lower half, dry-fit, then glue the halves.",
        "<b>Wings:</b> the side slots are on the seam. Insert both wings level, "
        "with the swept edge forward.",
        "<b>Horizontal tails:</b> the slots are angled, so the tails take up "
        "15 deg anhedral (tips down) on their own. Check that both sides "
        "match when viewed from behind.",
        "<b>Upper vertical tail:</b> insert into the dorsal slot and square it "
        "to the wings.",
        "<b>Ventral fin (optional):</b> insert into the slot under the tail. "
        "Leave it off for the post-jettison landing look.",
        "Socket: under the fuselage at mid-wing, about 119 mm behind the nose.",
        "Optional: sand a 10 deg wedge onto the vertical tail faces for more "
        "accuracy.",
    ])
    s += [p("<b>Paint:</b> gloss or semi-gloss black overall. This was the "
            "heat-resistant black finish on the Inconel X skin.", SM),
          PageBreak()]

    # ------------------------------------------------------------- caret
    s += [p("5. Caret waverider &nbsp;(exact design, M = 6)", H2),
          p("Nonweiler's caret waverider is built from a known flow: the 2-D "
            "oblique shock from a wedge. The leading edges lie in a single "
            "planar shock. The upper surfaces are parallel to the freestream, "
            "so they stay at freestream pressure. The two lower surfaces are "
            "made of wedge-flow streamlines. At the design point the shock sits "
            "exactly on the leading edges, so there's no spillage from the "
            "high-pressure underside to the top.", B),
          tbl([["Parameter", "Value"],
               ["Design Mach number", "6.0  (gamma = 1.4)"],
               ["Wedge deflection theta", "7.0 deg"],
               ["Shock angle beta (weak solution)", f"{math.degrees(beta):.2f} deg"],
               ["Lower-surface pressure ratio p2/p1",
                f"{p21:.2f}  = 1 + 2gamma/(gamma+1) (M^2 sin^2 beta - 1)"],
               ["Inviscid L/D (pressure only, no base drag)",
                f"cot theta = {1 / math.tan(th):.2f}"],
               ["Length / span / base height", f"160 / 128 / {160 * math.tan(beta):.1f} mm"]],
              [3.0 * inch, 3.8 * inch]),
          Spacer(1, 6),
          Table([[img("caret_assembled.png", 3.2 * inch),
                  img("print_caret_waverider.png", 2.2 * inch)]],
                colWidths=[3.5 * inch, 3.3 * inch]),
          p("Left: as displayed. Right: print orientation (standing on its base, "
            "nose up).", CAP),
          parts_table([("caret_waverider", 1, "Standing on its flat base, nose "
                        "up; 5 mm brim; min layer time 8 s for a clean tip",
                        "No")] + stand_rows("caret")),
          p("Assembly", H3)]
    s += steps([
        "Print with the brim. The leading edges are knife edges and come out "
        "as thin as your nozzle allows. Leave them; don't sand them round.",
        "The socket is in the lower ridge at 60 % of the length. Push it onto "
        "the stand peg so the flat upper surfaces face up.",
        "To make other design points (Mach number, theta, span), edit the "
        "<font face='Courier'>build_caret(L, M, theta_deg, span_ratio)</font> "
        "call and regenerate. The stand label updates to match.",
    ])
    s += [PageBreak()]

    # ------------------------------------------------------- editing / trouble
    s += [p("Editing the models in CAD", H2)]
    s += bullets([
        "<b>Fusion (free personal license) / SolidWorks:</b> open any file "
        "from <font face='Courier'>step/</font>. It comes in as a solid body you "
        "can edit directly: Press/Pull, add holes, cut panel lines, re-fillet. "
        "STEP files don't carry the feature history.",
        "<b>Full parametric control:</b> <font face='Courier'>src/build_models.py"
        "</font> defines every vehicle from a list of cross-section stations "
        "(x, half width, top and bottom half heights, shape exponents) in "
        "full-scale metres, plus fin planforms. Change a number and run "
        "<font face='Courier'>pip install cadquery trimesh reportlab</font>, then "
        "<font face='Courier'>python make_all.py</font> to regenerate the STL, "
        "STEP and preview files, and <font face='Courier'>python "
        "make_manual.py</font> to rebuild this manual.",
        "<b>Changing scale:</b> pass <font face='Courier'>scale=</font> to a build "
        "function (for example <font face='Courier'>build_x43a(scale=16)</font>). "
        "Pins, slot clearances and the stand peg stay at printable sizes.",
    ])
    s += [p("Troubleshooting", H2),
          tbl([["Problem", "Fix"],
               ["Halves rock or show a gap", "Elephant foot on the split face: "
                "shave or sand it flat on sandpaper taped to glass."],
               ["Fin tab won't go in", "Sand the tab faces, or regenerate with "
                "a larger CLEAR value."],
               ["Thin nose or edges curl", "Lower nozzle temp 5 C, raise the "
                "minimum layer time, use the part-cooling fan at 100 %."],
               ["Duct roof (X-43A) sags", "Bridging: slow bridge speed, fan "
                "100 %. A little sag is hidden inside the duct."],
               ["Body lifts at the ends", "Use a brim, clean the bed with IPA, "
                "raise the bed temp 5 C."],
               ["Peg loose in socket", "One wrap of tape on the peg, or a drop "
                "of glue if you want it permanent."]],
              [2.0 * inch, 4.8 * inch]),
          Spacer(1, 8),
          p("Sources for the public figures quoted: NASA Armstrong fact sheets "
            "(X-43A, X-15), AFRL / Boeing X-51A releases, DARPA HTV-2 releases. "
            "Shapes are approximate; check against reference photographs if "
            "accuracy matters for your use.", SM)]

    doc = SimpleDocTemplate(PDF, pagesize=letter, leftMargin=0.8 * inch,
                            rightMargin=0.8 * inch, topMargin=0.7 * inch,
                            bottomMargin=0.75 * inch,
                            title="Hypersonic Vehicle Display Models - Assembly Manual")
    doc.build(s, onFirstPage=footer, onLaterPages=footer)
    print("wrote", PDF)


if __name__ == "__main__":
    build()
