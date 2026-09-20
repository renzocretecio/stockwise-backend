import httpx
import pytest

from app.config.settings import settings
from app.services.email import EmailDeliveryError, EmailService
from app.services import email


def test_brevo_email_uses_the_transactional_api(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return httpx.Response(
            201,
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(settings, "BREVO_API_KEY", "brevo-key")
    monkeypatch.setattr(
        settings,
        "BREVO_SENDER_EMAIL",
        "mail@example.com",
    )
    monkeypatch.setattr(settings, "BREVO_SENDER_NAME", "KitaStock")
    monkeypatch.setattr(email.httpx, "post", fake_post)

    EmailService.send(
        ["owner@example.com"],
        "Weekly Owner Summary",
        "Plain text summary",
        "<p>HTML summary</p>",
    )

    assert captured["url"] == settings.BREVO_API_URL
    assert captured["headers"]["api-key"] == "brevo-key"
    assert captured["json"]["sender"] == {
        "email": "mail@example.com",
        "name": "KitaStock",
    }
    assert captured["json"]["to"] == [{"email": "owner@example.com"}]
    assert captured["json"]["htmlContent"] == "<p>HTML summary</p>"


def test_brevo_email_reports_provider_rejection(monkeypatch):
    def fake_post(url, **kwargs):
        request = httpx.Request("POST", url)
        response = httpx.Response(401, request=request)
        raise httpx.HTTPStatusError(
            "Unauthorized",
            request=request,
            response=response,
        )

    monkeypatch.setattr(settings, "BREVO_API_KEY", "invalid-key")
    monkeypatch.setattr(
        settings,
        "BREVO_SENDER_EMAIL",
        "mail@example.com",
    )
    monkeypatch.setattr(email.httpx, "post", fake_post)

    with pytest.raises(EmailDeliveryError, match="status 401"):
        EmailService.send(
            ["owner@example.com"],
            "Subject",
            "Text",
        )
