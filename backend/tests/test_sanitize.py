import json

from app.sanitize import clean_filename, clean_text
from fakes import FakeBackend, make_client, submit, wait_for_job


def test_removes_control_and_invisible_characters():
    dirty = "Do\x00bar\x1b ‮dan​﻿­.\ud800"
    assert clean_text(dirty) == "Dobar dan."


def test_keeps_lines_tabs_markup_and_emoji_joiners():
    text = "<b>Zdravo</b>\n\tkako si? \U0001f468‍\U0001f469"
    assert clean_text(text) == text


def test_normalizes_line_endings_and_unicode():
    assert clean_text("a\r\nb\rc d e") == "a\nb\nc\nd\ne"
    assert clean_text("č") == "č"
    assert clean_text("a\x0cb") == "a b"


def test_filename_loses_paths_and_control_characters():
    assert clean_filename("../../etc\\pass\r\nwd‮.txt") == "pass wd.txt"
    assert clean_filename("\x00.txt") == "document.txt"
    assert len(clean_filename("a" * 500 + ".docx")) <= 105


def test_text_endpoint_sends_clean_text_to_backend():
    backend = FakeBackend()
    with make_client(backend) as client:
        client.post("/translate/stream", json={"text": "Do\x00bar‮ dan."})
    assert backend.calls == ["Dobar dan."]


def test_text_of_only_invisible_characters_is_empty():
    with make_client() as client:
        body = json.dumps({"text": "​\x00 ﻿"})
        response = client.post(
            "/translate/stream", content=body, headers={"Content-Type": "application/json"}
        )
    assert response.status_code == 400


def test_file_text_and_name_are_cleaned():
    backend = FakeBackend()
    with make_client(backend) as client:
        job = submit(client, "..\\evil‮.txt", "Do​bar dan.".encode()).json()
        status = wait_for_job(client, job["job_id"])
    assert backend.calls == ["Dobar dan."]
    assert status["filename"] == "evil_translated.txt"
