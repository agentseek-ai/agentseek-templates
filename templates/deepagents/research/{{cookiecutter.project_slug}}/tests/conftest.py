import os

os.environ["AGENTSEEK_MODEL_PROVIDER"] = "openai"
os.environ["AGENTSEEK_MODEL"] = "course-scripted"
os.environ["OPENAI_API_KEY"] = "unused-scripted-key"
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["CONTENT_MODE"] = "text"
os.environ["CONTENT_ENABLE_SEARCH"] = "false"
os.environ["CONTENT_ENABLE_IMAGES"] = "false"
os.environ.pop("TAVILY_API_KEY", None)
os.environ.pop("GOOGLE_API_KEY", None)
