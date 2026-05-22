import os
from dataclasses import dataclass
from typing import List


def _split_csv(value: str) -> List[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    llm_provider: str
    llm_temperature: float
    xai_api_key: str
    grok_model: str
    grok_api_base: str
    openai_api_key: str
    openai_model: str
    groq_api_key: str
    groq_model: str
    allowed_origins: List[str]

    @property
    def active_model(self) -> str:
        if self.llm_provider == "openai":
            return self.openai_model
        if self.llm_provider == "groq":
            return self.groq_model
        return self.grok_model


def get_settings() -> Settings:
    provider = os.getenv("LLM_PROVIDER", "grok").strip().lower()
    if provider not in {"grok", "openai", "groq"}:
        raise ValueError("LLM_PROVIDER must be one of: grok, openai, groq")

    return Settings(
        llm_provider=provider,
        llm_temperature=float(os.getenv("LLM_TEMPERATURE", "0.2")),
        xai_api_key=os.getenv("XAI_API_KEY", ""),
        grok_model=os.getenv("GROK_MODEL", "grok-4.3"),
        grok_api_base=os.getenv("GROK_API_BASE", "https://api.x.ai/v1"),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        groq_api_key=os.getenv("GROQ_API_KEY", ""),
        groq_model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        allowed_origins=_split_csv(
            os.getenv("ALLOWED_ORIGINS", "http://localhost:4321,http://127.0.0.1:4321")
        ),
    )


def build_chat_model(settings: Settings):
    if settings.llm_provider == "openai":
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=settings.openai_model,
            temperature=settings.llm_temperature,
            api_key=settings.openai_api_key,
        )

    if settings.llm_provider == "groq":
        if not settings.groq_api_key:
            raise ValueError("GROQ_API_KEY is required when LLM_PROVIDER=groq")
        from langchain_groq import ChatGroq

        return ChatGroq(
            model=settings.groq_model,
            temperature=settings.llm_temperature,
            api_key=settings.groq_api_key,
        )

    if not settings.xai_api_key:
        raise ValueError("XAI_API_KEY is required when LLM_PROVIDER=grok")
    from langchain_xai import ChatXAI

    return ChatXAI(
        model=settings.grok_model,
        temperature=settings.llm_temperature,
        max_tokens=1500,
        api_key=settings.xai_api_key,
    )
