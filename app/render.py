import subprocess
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import qrcode
from PIL import Image
from pypdf import PageObject, PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject

from app.errors import NotMusicXML, TitleTooLong

SHARP_ORDER = "FCGDAEB"
COMPOSER = "Pauline Mahon"
# MuseScore 4.7 ignores QT_QPA_PLATFORM=offscreen and needs an X display.
MSCORE = ["xvfb-run", "-a", "mscore"]
# pt from the top-left; left of the title, above the tune type, in line with the staff
QR_LEFT, QR_TOP, QR_SIZE = 42.5, 47.0, 44.0
QR_MARGIN = 4.0

# MuseScore applies only these keys; MusicXML can't carry style, hence .mscz.
SCORE_STYLE = """<?xml version="1.0" encoding="UTF-8"?>
<museScore version="4.70">
  <Style>
    <enableIndentationOnFirstSystem>0</enableIndentationOnFirstSystem>
    <maxSystemSpread>12</maxSystemSpread>
  </Style>
</museScore>
"""


def parse(data: bytes) -> ET.ElementTree:
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise NotMusicXML from e
    if root.tag != "score-partwise":
        raise NotMusicXML(root.tag)
    return ET.ElementTree(root)


def key_alterations(fifths: int) -> dict[str, int]:
    if fifths >= 0:
        return dict.fromkeys(SHARP_ORDER[:fifths], 1)
    return dict.fromkeys(SHARP_ORDER[::-1][:-fifths], -1)


def clean_up(root: ET.Element) -> None:
    _hide_part_names(root)
    _remove_tempo_marking(root)
    _remove_courtesy_accidentals(root)
    _break_lines(root)


def _break_lines(root: ET.Element) -> None:
    # Tune-book layout: four bars a line, where a 2nd-time ending shares its bar slot with the
    # 1st-time ending before it, so each 8-bar part fills two lines.
    for part in root.iter("part"):
        slot = 0
        for measure in part.iter("measure"):
            for old in measure.findall("print"):
                measure.remove(old)
            if _is_later_ending(measure):
                continue
            if slot and slot % 4 == 0:
                measure.insert(0, ET.Element("print", {"new-system": "yes"}))
            slot += 1


def _is_later_ending(measure: ET.Element) -> bool:
    ending = measure.find("barline/ending[@type='start']")
    return ending is not None and not ending.get("number", "").startswith("1")


def _bars_to_keep_with_next(root: ET.Element) -> list[int]:
    measures = list(root.find("part").iter("measure"))
    return [i - 1 for i, measure in enumerate(measures) if i and _is_later_ending(measure)]


def _keep_with_next(mscz_path: Path, indexes: list[int]) -> None:
    # MusicXML can't say "keep these bars on one line", so it goes into MuseScore's own file;
    # without it a busy line pushes the 2nd-time ending onto a line of its own.
    with zipfile.ZipFile(mscz_path) as mscz:
        files = {name: mscz.read(name) for name in mscz.namelist()}
    mscx_name = next(name for name in files if name.endswith(".mscx"))
    mscx = ET.fromstring(files[mscx_name])
    measures = mscx.find("Score/Staff").findall("Measure")
    for i in indexes:
        layout_break = ET.Element("LayoutBreak")
        ET.SubElement(layout_break, "subtype").text = "noBreak"
        measures[i].insert(1, layout_break)
    files[mscx_name] = ET.tostring(mscx, encoding="UTF-8", xml_declaration=True)
    with zipfile.ZipFile(mscz_path, "w", zipfile.ZIP_DEFLATED) as mscz:
        for name, data in files.items():
            mscz.writestr(name, data)


def _hide_part_names(root: ET.Element) -> None:
    for part_name in root.iter("part-name"):
        part_name.set("print-object", "no")


def _remove_tempo_marking(root: ET.Element) -> None:
    # MuseScore ignores print-object="no" on metronomes; keep the playback <sound>.
    for measure in root.iter("measure"):
        for direction in measure.findall("direction"):
            if direction.find("direction-type/metronome") is None:
                continue
            sound = direction.find("sound")
            index = list(measure).index(direction)
            measure.remove(direction)
            if sound is not None:
                measure.insert(index, sound)


def _remove_courtesy_accidentals(root: ET.Element) -> None:
    for part in root.iter("part"):
        key: dict[str, int] = {}
        for measure in part.iter("measure"):
            fifths = measure.find("attributes/key/fifths")
            if fifths is not None:
                key = key_alterations(int(float(fifths.text)))
            for note in measure.findall("note"):
                accidental = note.find("accidental")
                if accidental is None or "yes" not in (
                    accidental.get("cautionary"),
                    accidental.get("parentheses"),
                ):
                    continue
                pitch = note.find("pitch")
                if pitch is None:  # unpitched percussion
                    continue
                alter_elem = pitch.find("alter")
                alter = float(alter_elem.text) if alter_elem is not None else 0
                if alter == key.get(pitch.find("step").text, 0):
                    note.remove(accidental)


def set_title(root: ET.Element, title: str) -> None:
    work = root.find("work")
    if work is None:
        work = ET.Element("work")
        root.insert(0, work)
    work_title = work.find("work-title")
    if work_title is None:
        work_title = ET.SubElement(work, "work-title")
    work_title.text = title
    movement_title = root.find("movement-title")
    if movement_title is not None:
        movement_title.text = title


def set_composer(root: ET.Element) -> None:
    identification = root.find("identification")
    if identification is None:
        identification = ET.Element("identification")
        index = sum(c.tag in ("work", "movement-number", "movement-title") for c in root)
        root.insert(index, identification)
    for creator in identification.findall("creator[@type='composer']"):
        identification.remove(creator)
    composer = ET.Element("creator", type="composer")
    composer.text = COMPOSER
    identification.insert(0, composer)


def render(xml: bytes, title: str, qr_url: str, work_dir: Path) -> tuple[Path, Path]:
    tree = parse(xml)
    root = tree.getroot()
    set_title(root, title)
    set_composer(root)
    clean_up(root)

    cleaned_path = work_dir / "cleaned.xml"
    style_path = work_dir / "style.mss"
    mscz_path = work_dir / "score.mscz"
    pdf_path = work_dir / "sheet.pdf"
    tree.write(cleaned_path, encoding="UTF-8", xml_declaration=True)
    style_path.write_text(SCORE_STYLE, encoding="UTF-8")
    _run_mscore("-S", style_path, "-o", mscz_path, cleaned_path)
    _keep_with_next(mscz_path, _bars_to_keep_with_next(root))
    _run_mscore("-o", pdf_path, mscz_path)
    if not qr_box_is_clear(pdf_path):
        raise TitleTooLong(title)
    return pdf_path, stamp_qr(pdf_path, qr_url, work_dir / "sheet-qr.pdf")


def _run_mscore(*args: object) -> None:
    subprocess.run([*MSCORE, *map(str, args)], check=True, capture_output=True, timeout=180)


def qr_box_is_clear(pdf_path: Path) -> bool:
    # At 72 dpi one pixel is one point, so the QR coordinates map straight onto pixels.
    png_root = pdf_path.with_name(f"{pdf_path.stem}-page1")
    subprocess.run(
        [
            "pdftoppm",
            "-r",
            "72",
            "-f",
            "1",
            "-l",
            "1",
            "-singlefile",
            "-gray",
            "-png",
            str(pdf_path),
            str(png_root),
        ],
        check=True,
        capture_output=True,
    )
    box = (
        int(QR_LEFT - QR_MARGIN),
        int(QR_TOP - QR_MARGIN),
        int(QR_LEFT + QR_SIZE + QR_MARGIN) + 1,
        int(QR_TOP + QR_SIZE + QR_MARGIN) + 1,
    )
    with Image.open(f"{png_root}.png") as page:
        return page.convert("L").crop(box).getextrema()[0] >= 250


def stamp_qr(pdf_path: Path, url: str, out_path: Path) -> Path:
    qr = qrcode.QRCode(border=0, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(url)
    matrix = qr.get_matrix()
    module = QR_SIZE / len(matrix)

    writer = PdfWriter(clone_from=PdfReader(pdf_path))
    page = writer.pages[0]
    width, height = float(page.mediabox.width), float(page.mediabox.height)
    rects = [
        f"{QR_LEFT + col * module:.3f} {height - QR_TOP - (row + 1) * module:.3f} "
        f"{module:.3f} {module:.3f} re"
        for row, cells in enumerate(matrix)
        for col, dark in enumerate(cells)
        if dark
    ]
    stream = DecodedStreamObject()
    stream.set_data(("q 0 g\n" + "\n".join(rects) + "\nf Q").encode())
    overlay = PageObject.create_blank_page(width=width, height=height)
    overlay.replace_contents(stream)
    page.merge_page(overlay)
    writer.write(out_path)
    return out_path
