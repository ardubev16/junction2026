"""The server's configuration and secrets, from environment variables (names case-insensitive; `uv run
--env-file .env`, or docker-compose.yml's env_file), validated once at import: a bad value stops the
server, naming the variable. Empty variables count as unset. Modal (MODAL_*) and OpenTelemetry
(OTEL_*) read their own variables.
"""

from ipaddress import IPv4Network, IPv6Network, ip_network
from typing import Annotated, Any, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Network = IPv4Network | IPv6Network


class Settings(BaseSettings):
    # hide_input_in_errors: a validation error would otherwise print every variable read, secrets included.
    model_config = SettingsConfigDict(env_ignore_empty=True, extra="ignore", hide_input_in_errors=True)

    # MariaDB, as docker-compose.yml runs it
    db_host: str = "127.0.0.1"
    db_port: int = 3308
    db_user: str = "wikicross"
    db_password: SecretStr = SecretStr("wikicross")
    db_name: str = "wikicross"

    # Rate limit (app.py): on with RATE_LIMIT=1; ALLOWED_IPS (IPs or CIDR ranges, space-separated) are exempt
    rate_limit: bool = False
    allowed_ips: Annotated[list[Network], NoDecode] = Field(
        default_factory=lambda: [ip_network("127.0.0.1"), ip_network("::1")]
    )

    # LLM (llm.py), required: its API, endpoint, model and key. LLM_EXTRA (JSON) goes into each request:
    # the body for "openai", generationConfig for "gemini" (e.g. {"thinkingConfig": {"thinkingLevel": "low"}}).
    llm_api_type: Literal["gemini", "openai"]
    llm_url: str
    llm_model: str
    llm_api_key: SecretStr
    llm_extra: dict[str, Any] = {}

    # Decision model (decide.py), required: OpenRouter's Decisions API endpoint, model and key
    decision_url: str = "https://openrouter.ai/api/alpha/decisions"
    decision_model: str = "perplexity/pplx-decider-v1.3:free"
    decision_api_key: SecretStr

    # Azure AI Translator (translator.py): the region only for a regional or multi-service resource
    azure_translator_key: SecretStr | None = None
    azure_translator_region: str | None = None
    azure_translator_url: str = "https://api.cognitive.microsofttranslator.com"

    @field_validator("allowed_ips", mode="before")
    @classmethod
    def split_networks(cls, value: object) -> object:
        # Host bits allowed ("10.1.2.3/8"), as ipaddress.ip_network(strict=False).
        return [ip_network(n, strict=False) for n in value.split()] if isinstance(value, str) else value


settings = Settings()
