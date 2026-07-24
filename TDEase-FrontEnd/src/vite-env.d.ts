/// <reference types="vite/client" />

declare module "*.vue" {
  import type { DefineComponent } from "vue";
  // eslint-disable-next-line @typescript-eslint/no-empty-object-type
  const component: DefineComponent<{}, {}, any>;
  export default component;
}

declare module "plotly.js-dist-min" {
  const Plotly: {
    react: (
      el: HTMLElement,
      data: unknown[],
      layout?: Record<string, unknown>,
      config?: Record<string, unknown>
    ) => Promise<unknown>;
    purge: (el: HTMLElement) => void;
  };
  export default Plotly;
}
