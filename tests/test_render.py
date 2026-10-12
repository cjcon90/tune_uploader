import io
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest
import zxingcpp
from PIL import Image
from pypdf import PdfReader

from app.errors import NotMusicXML, TitleTooLong
from app.render import (
    _hide_part_names,
    _remove_courtesy_accidentals,
    _remove_tempo_marking,
    key_alterations,
    parse,
    render,
    set_composer,
    set_title,
)
from tests.conftest import needs_render

QR_URL = "https://audio.paulinemahon.com/k7mq3xpw"

COURTESY_XML = """
<score-partwise>
  <part id="P1">
    <measure number="1">
      <attributes><key><fifths>2</fifths></key></attributes>
      <note>
        <pitch><step>C</step><octave>5</octave></pitch>
        <accidental>natural</accidental>
      </note>
      <note>
        <pitch><step>C</step><alter>1</alter><octave>5</octave></pitch>
        <accidental cautionary="yes">sharp</accidental>
      </note>
      <note>
        <pitch><step>F</step><alter>1</alter><octave>4</octave></pitch>
        <accidental parentheses="yes">sharp</accidental>
      </note>
      <note>
        <pitch><step>G</step><alter>1</alter><octave>4</octave></pitch>
        <accidental cautionary="yes">sharp</accidental>
      </note>
    </measure>
  </part>
</score-partwise>
"""


def test_parse_accepts_staffpad_export(fixture_xml):
    assert parse(fixture_xml).getroot().tag == "score-partwise"


@pytest.mark.parametrize(
    "data",
    [
        b"%PDF-1.7 not xml",
        b"<score-timewise/>",
        b"",
    ],
)
def test_parse_rejects_non_musicxml(data):
    with pytest.raises(NotMusicXML):
        parse(data)


def test_parse_rejects_compressed_mxl(fixture_xml):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as mxl:
        mxl.writestr("score.xml", fixture_xml)
    with pytest.raises(NotMusicXML):
        parse(buffer.getvalue())


def test_hides_the_instrument_name(fixture_xml):
    root = parse(fixture_xml).getroot()
    _hide_part_names(root)
    part_names = root.findall(".//part-name")
    assert part_names
    assert all(p.get("print-object") == "no" for p in part_names)


def test_removes_tempo_marking_but_keeps_playback_tempo(fixture_xml):
    root = parse(fixture_xml).getroot()
    _remove_tempo_marking(root)
    assert root.find(".//metronome") is None
    sounds = [s for s in root.iter("sound") if s.get("tempo") is not None]
    assert [s.get("tempo") for s in sounds] == ["140"]


def test_d_major_sharpens_f_and_c():
    assert key_alterations(2) == {"F": 1, "C": 1}


def test_b_flat_major_flattens_b_and_e():
    assert key_alterations(-2) == {"B": -1, "E": -1}


def test_removes_only_courtesy_accidentals_that_match_the_key():
    root = ET.fromstring(COURTESY_XML)
    _remove_courtesy_accidentals(root)
    accidentals = [n.find("accidental") is not None for n in root.iter("note")]
    # G# is outside D major, so its courtesy mark is a real accidental
    assert accidentals == [True, False, False, True]


def test_set_title_overwrites_work_title(fixture_xml):
    root = parse(fixture_xml).getroot()
    set_title(root, "The Kesh")
    assert root.find("work/work-title").text == "The Kesh"


def test_set_title_creates_work_and_updates_movement_title():
    root = ET.fromstring("<score-partwise><movement-title>Old</movement-title></score-partwise>")
    set_title(root, "The Kesh")
    assert root[0].tag == "work"
    assert root.find("work/work-title").text == "The Kesh"
    assert root.find("movement-title").text == "The Kesh"


def test_set_composer_fixes_capitalisation(fixture_xml):
    root = parse(fixture_xml).getroot()
    set_composer(root)
    assert [c.text for c in root.iter("creator")] == ["Pauline Mahon"]


def test_set_composer_creates_identification_after_titles():
    root = ET.fromstring(
        "<score-partwise><work><work-title>T</work-title></work><part-list/></score-partwise>"
    )
    set_composer(root)
    assert [child.tag for child in root] == ["work", "identification", "part-list"]
    assert root.find("identification/creator[@type='composer']").text == "Pauline Mahon"


def _decode_qr(pdf_path: Path) -> list[str]:
    png_root = pdf_path.with_suffix("")
    subprocess.run(["pdftoppm", "-r", "100", "-png", "-singlefile", pdf_path, png_root], check=True)
    return [b.text for b in zxingcpp.read_barcodes(Image.open(f"{png_root}.png"))]


def _page_text(pdf_path: Path) -> str:
    # MuseScore's PDFs separate words with tabs and newlines.
    return " ".join(PdfReader(pdf_path).pages[0].extract_text().split())


@needs_render
def test_render_makes_plain_and_qr_pdfs(fixture_xml, tmp_path):
    plain, qr = render(fixture_xml, "A Pint for Ciaran", QR_URL, tmp_path)
    assert _decode_qr(plain) == []
    assert _decode_qr(qr) == [QR_URL]
    text = _page_text(qr)
    assert "A Pint for Ciaran" in text
    assert "Pauline Mahon" in text


@needs_render
def test_render_refuses_a_title_that_reaches_the_qr(fixture_xml, tmp_path):
    with pytest.raises(TitleTooLong):
        render(fixture_xml, "A Pint for Ciaran and the Humours of Ballyloughlin", QR_URL, tmp_path)


def test_courtesy_cleanup_survives_odd_exports():
    root = ET.fromstring(
        """<score-partwise><part id="P1"><measure number="1">
        <attributes><key><fifths>1.0</fifths></key></attributes>
        <note><unpitched><display-step>F</display-step></unpitched>
          <accidental cautionary="yes">sharp</accidental></note>
        <note><pitch><step>F</step><alter>0.5</alter><octave>4</octave></pitch>
          <accidental cautionary="yes">quarter-sharp</accidental></note>
        <note><pitch><step>F</step><alter>1</alter><octave>4</octave></pitch>
          <accidental cautionary="yes">sharp</accidental></note>
        </measure></part></score-partwise>"""
    )
    _remove_courtesy_accidentals(root)
    accidentals = [n.find("accidental") is not None for n in root.iter("note")]
    assert accidentals == [True, True, False]
