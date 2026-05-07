from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ocr_endpoint(monkeypatch):
    def fake_run_ocr(file_bytes: bytes):
        assert file_bytes == b"demo"
        return {
            "documentIntelligence": {"content": "text"},
            "contentUnderstanding": {"summary": "ok"},
        }

    monkeypatch.setattr("app.main.run_ocr", fake_run_ocr)

    client = TestClient(app)
    response = client.post(
        "/ocr",
        files={"file": ("sample.txt", b"demo", "text/plain")},
    )

    assert response.status_code == 200
    assert response.json()["documentIntelligence"]["content"] == "text"


def test_ocr_empty_file():
    client = TestClient(app)
    response = client.post(
        "/ocr",
        files={"file": ("sample.txt", b"", "text/plain")},
    )

    assert response.status_code == 400
