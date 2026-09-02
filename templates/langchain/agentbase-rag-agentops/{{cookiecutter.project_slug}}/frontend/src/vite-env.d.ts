/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_LANGGRAPH_API_URL?: string;
  readonly VITE_AGENTBASE_USER_ID?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
