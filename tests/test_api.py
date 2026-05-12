from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ocr_endpoint(monkeypatch):
    captured = {}

    def fake_run_ocr(file_bytes: bytes, di_model_id=None, cu_analyzer_id=None):
        captured["file_bytes"] = file_bytes
        captured["di_model_id"] = di_model_id
        captured["cu_analyzer_id"] = cu_analyzer_id
        return {
            "documentIntelligence": {
                "service": "documentIntelligence",
                "modelId": di_model_id or "prebuilt-read",
                "elapsedMs": 100,
                "extractedText": "DI-TEXT",
                "extractedMarkdown": "DI-TEXT",
                "page1": {"width": 1, "height": 1, "unit": "inch", "words": []},
                "raw": {"content": "DI-TEXT"},
            },
            "contentUnderstanding": {
                "service": "contentUnderstanding",
                "analyzerId": cu_analyzer_id or "prebuilt-read",
                "elapsedMs": 200,
                "extractedText": "CU-TEXT",
                "extractedMarkdown": "CU-TEXT",
                "page1": {"width": 1, "height": 1, "unit": "inch", "words": []},
                "raw": {"contents": [{"markdown": "CU-TEXT"}]},
            },
        }

    monkeypatch.setattr("app.main.run_ocr", fake_run_ocr)

    client = TestClient(app)
    response = client.post(
        "/ocr",
        files={"file": ("sample.txt", b"demo", "text/plain")},
        data={"di_model_id": "prebuilt-layout", "cu_analyzer_id": "prebuilt-documentAnalyzer"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["documentIntelligence"]["extractedText"] == "DI-TEXT"
    assert body["documentIntelligence"]["modelId"] == "prebuilt-layout"
    assert body["contentUnderstanding"]["extractedText"] == "CU-TEXT"
    assert body["contentUnderstanding"]["analyzerId"] == "prebuilt-documentAnalyzer"
    assert captured["di_model_id"] == "prebuilt-layout"
    assert captured["cu_analyzer_id"] == "prebuilt-documentAnalyzer"


def test_ocr_empty_file():
    client = TestClient(app)
    response = client.post(
        "/ocr",
        files={"file": ("sample.txt", b"", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Uploaded file is empty"}
