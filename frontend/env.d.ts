/// <reference types="vite/client" />
/// <reference types="unplugin-vue-router/client" />

export interface ImportMetaEnv {
  readonly VITE_API_URL: string
  readonly VITE_HLJS_LIGHT_STYLE_URL: string
  readonly VITE_HLJS_DARK_STYLE_URL: string
}
