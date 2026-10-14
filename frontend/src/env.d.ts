/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL da API FastAPI (read-only). Default: http://localhost:8000 */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
