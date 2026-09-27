import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from ticketward import healthcheck


class _Handler(BaseHTTPRequestHandler):
    status = 200

    def do_GET(self) -> None:
        self.send_response(self.status)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return


@pytest.fixture
def server() -> Iterator[ThreadingHTTPServer]:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def _url(server: ThreadingHTTPServer) -> str:
    return f"http://127.0.0.1:{server.server_address[1]}/api/v1/health/live"


def test_probe_passes_on_http_200(server: ThreadingHTTPServer) -> None:
    _Handler.status = 200
    assert healthcheck.probe(_url(server)) is True


def test_probe_fails_on_error_status(server: ThreadingHTTPServer) -> None:
    _Handler.status = 503
    try:
        assert healthcheck.probe(_url(server)) is False
    finally:
        _Handler.status = 200


def test_probe_fails_when_nothing_listens() -> None:
    assert healthcheck.probe("http://127.0.0.1:9/api/v1/health/live", timeout_s=1.0) is False


@pytest.mark.parametrize(
    "url", ["https://127.0.0.1:8000/", "http://example.com/", "file:///etc/passwd"]
)
def test_probe_only_targets_loopback_http(url: str) -> None:
    with pytest.raises(ValueError, match="only probes"):
        healthcheck.probe(url)


@pytest.mark.parametrize(("healthy", "code"), [(True, 0), (False, 1)])
def test_main_maps_probe_result_to_exit_code(
    monkeypatch: pytest.MonkeyPatch, healthy: bool, code: int
) -> None:
    monkeypatch.setattr(healthcheck, "probe", lambda *args, **kwargs: healthy)
    assert healthcheck.main() == code
