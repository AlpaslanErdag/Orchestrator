from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from typing import Any, Dict, List, Optional


class MailTool:
    """
    SMTP-based mail sender tool.

    Uses environment variables for configuration:
    - AGENTFLOW_SMTP_HOST
    - AGENTFLOW_SMTP_PORT
    - AGENTFLOW_SMTP_USER
    - AGENTFLOW_SMTP_PASS
    - AGENTFLOW_SMTP_FROM  (default From address)
    """

    @staticmethod
    def _get_smtp_config() -> Dict[str, Any]:
        host = os.getenv("AGENTFLOW_SMTP_HOST")
        port = int(os.getenv("AGENTFLOW_SMTP_PORT", "587"))
        user = os.getenv("AGENTFLOW_SMTP_USER")
        password = os.getenv("AGENTFLOW_SMTP_PASS")
        from_addr = os.getenv("AGENTFLOW_SMTP_FROM", user or "")

        if not host or not user or not password:
            raise RuntimeError("SMTP configuration is incomplete. Please set AGENTFLOW_SMTP_* env vars.")

        return {
            "host": host,
            "port": port,
            "user": user,
            "password": password,
            "from_addr": from_addr,
        }

    @classmethod
    def send_email(
        cls,
        to: List[str],
        subject: str,
        body: str,
        from_addr: Optional[str] = None,
    ) -> None:
        """
        Send a simple text email.
        """
        cfg = cls._get_smtp_config()

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = from_addr or cfg["from_addr"]
        msg["To"] = ", ".join(to)
        msg.set_content(body)

        with smtplib.SMTP(cfg["host"], cfg["port"]) as server:
            server.starttls()
            server.login(cfg["user"], cfg["password"])
            server.send_message(msg)

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """
        Optional function-calling schema for email sending.
        """
        return {
            "name": "send_email",
            "description": "Send an email with the given subject and body to one or more recipients.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {
                        "type": "array",
                        "items": {"type": "string", "format": "email"},
                        "description": "List of recipient email addresses.",
                    },
                    "subject": {
                        "type": "string",
                        "description": "Subject line of the email.",
                    },
                    "body": {
                        "type": "string",
                        "description": "Plain-text email body.",
                    },
                },
                "required": ["to", "subject", "body"],
            },
        }


