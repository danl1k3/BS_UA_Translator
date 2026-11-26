import io
import zipfile

import pytest
from app.documents import DocumentError, parse_document
from docx import Document
from docx.oxml.ns import qn


def _parse(name, raw, source="bos_Latn"):
    return parse_document(name, raw, source)


def _upper(doc):
    return doc.build([t.upper() for t in doc.texts])


def test_txt_keeps_layout():
    doc = _parse("a.txt", b"Jedan.\r\n\r\nDva.")
    assert _upper(doc).decode() == "JEDAN.\r\n\r\nDVA."


@pytest.mark.parametrize(
    "source,encoding,text", [("bos_Latn", "cp1250", "Šuma"), ("ukr_Cyrl", "cp1251", "Ліс")]
)
def test_txt_legacy_encodings(source, encoding, text):
    assert _parse("a.txt", text.encode(encoding), source).texts == [text]


def test_html_does_not_double_escape():
    doc = _parse("a.html", b"<html><p>A &amp; <b>B</b></p><p>&lt;i&gt;</p></html>")
    assert doc.texts == ["A & B", "<i>"]
    assert doc.build(doc.texts) == b"<p>A &amp; B</p>\n<p>&lt;i&gt;</p>"


def _docx_bytes(document) -> bytes:
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


def test_docx_keeps_run_formatting_pictures_and_hyperlink_text():
    source = Document()
    paragraph = source.add_paragraph()
    paragraph.add_run("Hello ").bold = True
    paragraph.add_run().add_break()  # run without own text must stay intact
    paragraph.add_run("world")
    link = paragraph._p.makeelement(qn("w:hyperlink"), {})
    linked = paragraph.add_run(" link")
    link.append(linked._r)
    paragraph._p.append(link)
    picture = paragraph.add_run("caption")
    picture._r.append(picture._r.makeelement(qn("w:drawing"), {}))

    doc = _parse("a.docx", _docx_bytes(source))
    assert doc.texts == ["Hello world link"]
    result = Document(io.BytesIO(doc.build(["ПРИВІТ СВІТЕ ЛІНК"])))
    xml = result.paragraphs[0]._p.xml
    assert "w:drawing" in xml
    assert result.paragraphs[0].runs[0].bold is True
    text = "".join(t.text for t in result.paragraphs[0]._p.iter(qn("w:t")))
    assert text.split() == ["ПРИВІТ", "СВІТЕ", "ЛІНКcaption"]
    assert "w:br" in xml


@pytest.mark.parametrize(
    "name,raw,status",
    [
        ("a.exe", b"MZ", 415),
        ("a.docx", b"not a zip", 400),
        ("a.txt", b"   ", 400),
    ],
)
def test_rejects_bad_input(name, raw, status):
    with pytest.raises(DocumentError) as error:
        _parse(name, raw)
    assert error.value.status_code == status


def test_rejects_docx_that_expands_too_much():
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", b"0" * (40 * 1024 * 1024))
    with pytest.raises(DocumentError) as error:
        _parse("bomb.docx", out.getvalue())
    assert error.value.status_code == 413
