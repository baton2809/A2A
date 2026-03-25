"""Сканер безопасности: обнаружение prompt-инъекций и утечек секретов.

Оба вида проверок находятся в одном модуле для согласованности логики guardrail.
"""
import re

# ---------------------------------------------------------------------------
# Паттерны prompt-инъекций
# ---------------------------------------------------------------------------
_INJECTION_RULES = [
    r"ignore\s+(all\s+)?(previous|prior)\s+instructions",
    r"disregard\s+(all\s+)?(previous|prior)",
    r"forget\s+(everything|all\s+previous|all\s+prior)",
    r"override\s+(your\s+)?instructions",
    r"you\s+are\s+now\s+(?:a|an)\s+\w+",
    r"act\s+as\s+(?:a|an)\s+\w+",                         # шире: act as a/an X
    r"without\s+restrictions",                             # ловим "unrestricted" паттерны
    r"unrestricted\s+(?:ai|mode|assistant)",
    r"pretend\s+(?:you(?:'re|\s+are)\s+)",
    r"reveal\s+(?:your\s+)?system\s+prompt",
    r"show\s+me\s+your\s+(?:system\s+)?(?:prompt|instructions)",
    r"what\s+(?:are|is)\s+your\s+(?:system\s+)?instructions",
    r"repeat\s+(?:the\s+)?(?:above|system)\s+(?:prompt|instructions)",
    r"\bjailbreak\b",
    r"\bDAN\s+mode\b",
    r"\[system\]",
    r"<\|im_start\|>\s*system",
]

_injection_re = [re.compile(p, re.IGNORECASE) for p in _INJECTION_RULES]


def detect_injection(text: str) -> str | None:
    """Возвращает совпавший паттерн инъекции или None если текст чистый."""
    for pattern in _injection_re:
        m = pattern.search(text)
        if m:
            return m.group()
    return None


# ---------------------------------------------------------------------------
# Паттерны утечки секретов
# ---------------------------------------------------------------------------
_SECRET_RULES: list[tuple[str, str]] = [
    (r"(?:sk|pk)-[a-zA-Z0-9]{32,}", "OpenAI/Stripe API key"),
    (r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}", "GitHub token"),
    (r"AKIA[0-9A-Z]{16}", "AWS access key ID"),
    (r"-----BEGIN\s(?:RSA\s|EC\s|DSA\s)?PRIVATE\sKEY-----", "Private key"),
    (r"(?:password|passwd|pwd)\s*[=:]\s*['\"][^'\"]{8,}['\"]", "Hardcoded password"),
    (r"eyJ[A-Za-z0-9\-_]+\.eyJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+", "JWT token"),
    (r"xox[bporas]-[0-9a-zA-Z\-]{10,}", "Slack token"),
    (r"AIza[0-9A-Za-z\-_]{35}", "Google API key"),
]

_secret_re = [(re.compile(p, re.IGNORECASE), label) for p, label in _SECRET_RULES]


def detect_secrets(text: str) -> list[str]:
    """Возвращает список типов найденных секретов в тексте."""
    found = []
    for pattern, label in _secret_re:
        if pattern.search(text):
            found.append(label)
    return found
