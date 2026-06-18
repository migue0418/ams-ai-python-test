import httpx
import main
import respx
from fastapi.testclient import TestClient
from services import pipeline

EXTRACT_URL = "http://localhost:3001/v1/ai/extract"
NOTIFY_URL = "http://localhost:3001/v1/notify"


@respx.mock
def test_create_process_get_flow():
    respx.post(EXTRACT_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": '{"to": "user@example.com", "message": "hi", "type": "email"}',
                        },
                    },
                ],
            },
        ),
    )
    respx.post(NOTIFY_URL).mock(
        return_value=httpx.Response(
            200,
            json={"status": "delivered", "provider_id": "p-1"},
        ),
    )
    with TestClient(main.app) as client:
        create_res = client.post(
            "/v1/requests",
            json={"user_input": "manda un email a user@example.com: hi"},
        )
        assert create_res.status_code == 201
        request_id = create_res.json()["id"]

        process_res = client.post(f"/v1/requests/{request_id}/process")
        assert process_res.status_code == 202
        assert process_res.json() == {"id": request_id, "status": "processing"}

        # a second call is idempotent: no re-enqueue, just the current status
        process_again = client.post(f"/v1/requests/{request_id}/process")
        assert process_again.status_code == 200

        get_res = client.get(f"/v1/requests/{request_id}")
        assert get_res.status_code == 200
        assert get_res.json()["status"] in ("processing", "sent")


def test_process_missing_id_returns_404():
    with TestClient(main.app) as client:
        res = client.post("/v1/requests/does-not-exist/process")
        assert res.status_code == 404


def test_get_missing_id_returns_404():
    with TestClient(main.app) as client:
        res = client.get("/v1/requests/does-not-exist")
        assert res.status_code == 404


def test_process_returns_503_when_queue_is_full(monkeypatch):
    monkeypatch.setattr(pipeline, "enqueue", lambda request_id: False)
    with TestClient(main.app) as client:
        create_res = client.post("/v1/requests", json={"user_input": "hola"})
        request_id = create_res.json()["id"]

        process_res = client.post(f"/v1/requests/{request_id}/process")
        assert process_res.status_code == 503

        # rejected, so it must stay queued rather than stuck mid-processing
        get_res = client.get(f"/v1/requests/{request_id}")
        assert get_res.json()["status"] == "queued"
