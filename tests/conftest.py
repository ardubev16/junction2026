import os

# The settings config.py requires, so the app imports without a .env; no test reaches the LLM or the
# decision model.
for name, value in {
    "LLM_API_TYPE": "openai",
    "LLM_URL": "http://llm.invalid/v1",
    "LLM_MODEL": "test",
    "LLM_API_KEY": "test",
    "DECISION_API_KEY": "test",
}.items():
    os.environ.setdefault(name, value)
