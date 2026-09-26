"""Per-run System One selection; credentials and endpoints remain server-side."""

import os
from urllib.parse import urlsplit

from langchain_core.runnables import RunnableLambda
from langchain_core.runnables.config import ensure_config
from langchain_typesafe import TypeSafeClassifier

MODELS = {
    "semif": ("siliconflow", "semif", "SemIf"),
    "kev-4b": ("siliconflow", "kev-4b", "Kev-4B"),
    "jev": ("typesafe", "jev-latest", "Jev"),
}


def selection(config=None):
    value = ensure_config(config).get("configurable", {}).get("decision_model", "semif")
    if not isinstance(value, str) or value not in MODELS:
        raise ValueError("Unknown decision model. Choose semif, kev-4b, or jev.")
    return value


def siliconflow_key():
    key = os.getenv("SILICONFLOW_API_KEY", "").strip()
    # Reuse the chat key only when its configured host is SiliconFlow China.
    # Switching chat providers must never send that provider's key to SiliconFlow.
    chat_base = os.getenv("OPENAI_API_BASE", "{{ cookiecutter.chat_api_base }}")
    if not key and urlsplit(chat_base).hostname == "api.siliconflow.cn":
        key = os.getenv("OPENAI_API_KEY", "").strip()
    return key


class DecisionClassifier(RunnableLambda):
    """Dispatch to immutable clients, never mutate environment or a shared model.

    Only configured providers get clients. Selecting an unavailable provider fails
    explicitly; there is no fallback that could disguise a different model's answer.
    """

    def __init__(self, questions):
        self.classifiers = {}
        credentials = {"siliconflow": siliconflow_key(), "typesafe": os.getenv("TYPESAFE_API_KEY", "").strip()}
        bases = {
            "siliconflow": os.getenv("SILICONFLOW_BASE_URL") or "https://api.siliconflow.cn",
            "typesafe": os.getenv("TYPESAFE_BASE_URL") or "https://api.typesafe.ai",
        }
        for name, (provider, model, _) in MODELS.items():
            if credentials[provider]:
                self.classifiers[name] = TypeSafeClassifier(
                    questions=questions, api_key=credentials[provider], base_url=bases[provider],
                    model=(os.getenv("TYPESAFE_MODEL") or model) if name == "jev" else model,
                    timeout=60,
                )
        super().__init__(self._classify, afunc=self._aclassify)

    def _client(self, config):
        name = selection(config)
        if name not in self.classifiers:
            setting = "TYPESAFE_API_KEY" if name == "jev" else "SILICONFLOW_API_KEY (or OPENAI_API_KEY with a SiliconFlow chat endpoint)"
            raise ValueError(f"{MODELS[name][2]}: fill {setting} in the server .env, then restart.")
        return self.classifiers[name]

    def _classify(self, state, config):
        return self._client(config).invoke(state, config)

    async def _aclassify(self, state, config):
        return await self._client(config).ainvoke(state, config)

    @staticmethod
    def report(response, config=None):
        name = selection(config)
        provider, _, label = MODELS[name]
        return {"selection": name, "provider": provider, "label": label, "model": response.model}
