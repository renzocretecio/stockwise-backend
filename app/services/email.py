from typing import Sequence

import httpx

from app.config.settings import settings


class EmailDeliveryError(RuntimeError):
    """Raised when the transactional email provider rejects delivery."""


class EmailService:
    @staticmethod
    def is_configured() -> bool:
        return bool(settings.BREVO_API_KEY and settings.BREVO_SENDER_EMAIL)

    @staticmethod
    def send(
        recipients: Sequence[str],
        subject: str,
        text: str,
        html: str | None = None,
    ) -> None:
        if not EmailService.is_configured():
            raise EmailDeliveryError(
                "BREVO_API_KEY and BREVO_SENDER_EMAIL are required"
            )

        payload = {
            "sender": {
                "email": settings.BREVO_SENDER_EMAIL,
                "name": settings.BREVO_SENDER_NAME,
            },
            "to": [{"email": recipient} for recipient in recipients],
            "subject": subject,
            "textContent": text,
        }
        if html:
            payload["htmlContent"] = html

        try:
            response = httpx.post(
                settings.BREVO_API_URL,
                headers={
                    "accept": "application/json",
                    "api-key": settings.BREVO_API_KEY,
                    "content-type": "application/json",
                },
                json=payload,
                timeout=settings.BREVO_API_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise EmailDeliveryError(
                "Brevo rejected the email request with status "
                f"{error.response.status_code}"
            ) from error
        except httpx.HTTPError as error:
            raise EmailDeliveryError("Brevo email request failed") from error
