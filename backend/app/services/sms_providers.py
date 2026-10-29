"""SMS provider abstraction.

AfricasTalkingProvider calls the documented Messaging REST API:
  POST {base}/version1/messaging  (form-encoded: username, to, message, [from])
  headers: apiKey, Accept: application/json
A recipient status code of 100/101/102 means the provider *accepted* the message. Delivery is
only confirmed later by a delivery-report callback.
"""

import logging
import secrets
from dataclasses import dataclass

import httpx

from app.config import Settings

log = logging.getLogger("stockout.sms")

AT_ACCEPTED_CODES = {100, 101, 102}
# Codes worth retrying (gateway/internal issues). Others (invalid number, blacklist, DND,
# insufficient balance, invalid sender id) are permanent until configuration changes.
AT_RETRYABLE_CODES = {500, 501, 502}


@dataclass
class SendResult:
    accepted: bool
    retryable: bool
    provider: str
    message_id: str | None = None
    provider_status: str | None = None
    error: str | None = None
    simulated: bool = False


class SmsProvider:
    name = "base"

    def send(self, to: str, message: str) -> SendResult:  # pragma: no cover - interface
        raise NotImplementedError


class SimulatedProvider(SmsProvider):
    """Demo provider: nothing leaves the server. Results are labelled 'simulated'."""

    name = "simulated"

    def __init__(self, reason: str = "demo mode") -> None:
        self.reason = reason

    def send(self, to: str, message: str) -> SendResult:
        log.info("SIMULATED SMS (%s) to %s***: %s", self.reason, to[:7], message[:40])
        return SendResult(True, False, self.name, message_id=f"SIM-{secrets.token_hex(6)}",
                          provider_status=f"Simulated ({self.reason})", simulated=True)


class UnconfiguredProvider(SmsProvider):
    name = "unconfigured"

    def send(self, to: str, message: str) -> SendResult:
        return SendResult(False, False, self.name, error="SMS provider is not configured (set AT_USERNAME/AT_API_KEY)")


class AfricasTalkingProvider(SmsProvider):
    name = "africastalking"

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self.username = settings.at_username
        self.api_key = settings.at_api_key
        self.sender_id = settings.at_sender_id
        self.base = (
            "https://api.sandbox.africastalking.com"
            if settings.at_environment == "sandbox"
            else "https://api.africastalking.com"
        )
        self.client = client or httpx.Client(timeout=settings.sms_http_timeout_seconds)

    def send(self, to: str, message: str) -> SendResult:
        data = {"username": self.username, "to": to, "message": message}
        if self.sender_id:
            data["from"] = self.sender_id
        try:
            resp = self.client.post(
                f"{self.base}/version1/messaging",
                data=data,
                headers={"apiKey": self.api_key, "Accept": "application/json"},
            )
        except httpx.TimeoutException:
            return SendResult(False, True, self.name, error="Provider request timed out")
        except httpx.HTTPError as exc:
            return SendResult(False, True, self.name, error=f"Network error: {type(exc).__name__}")

        if resp.status_code >= 500:
            return SendResult(False, True, self.name, error=f"Provider HTTP {resp.status_code}")
        if resp.status_code in (401, 403):
            return SendResult(False, False, self.name, error="Provider rejected credentials")
        if resp.status_code >= 400:
            return SendResult(False, False, self.name, error=f"Provider HTTP {resp.status_code}: {resp.text[:120]}")
        try:
            recipients = resp.json()["SMSMessageData"]["Recipients"]
        except (ValueError, KeyError, TypeError):
            return SendResult(False, True, self.name, error="Unexpected provider response")
        if not recipients:
            try:
                msg = resp.json()["SMSMessageData"].get("Message", "No recipients accepted")
            except Exception:  # noqa: BLE001
                msg = "No recipients accepted"
            return SendResult(False, False, self.name, error=str(msg)[:200])
        r = recipients[0]
        code = int(r.get("statusCode", 0))
        status = str(r.get("status", ""))
        if code in AT_ACCEPTED_CODES:
            return SendResult(True, False, self.name, message_id=r.get("messageId"), provider_status=status)
        return SendResult(False, code in AT_RETRYABLE_CODES, self.name, message_id=r.get("messageId") or None,
                          provider_status=status, error=f"Provider status {code} {status}")


_override: SmsProvider | None = None


def set_provider_override(provider: SmsProvider | None) -> None:
    """Used by tests to inject a fake provider."""
    global _override
    _override = provider


def provider_for(settings: Settings, recipient: str) -> SmsProvider:
    if _override is not None:
        return _override
    if settings.sms_force_simulation:
        return SimulatedProvider("simulation forced")
    if not settings.at_configured:
        return SimulatedProvider("no credentials") if settings.demo_mode else UnconfiguredProvider()
    if settings.demo_mode and recipient not in settings.demo_sms_allowlist_set:
        return SimulatedProvider("recipient not in DEMO_SMS_ALLOWLIST")
    return AfricasTalkingProvider(settings)


def integration_mode(settings: Settings) -> str:
    if settings.sms_force_simulation or not settings.at_configured:
        return "simulated" if (settings.demo_mode or settings.sms_force_simulation) else "unconfigured"
    return f"live-{settings.at_environment}"
