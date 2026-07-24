/**
 * i18n message schema type definitions for TDEase Frontend.
 *
 * These interfaces define the shape of locale messages for type-safe
 * usage of $t() / t() throughout the application.
 *
 * When adding new keys, add the corresponding entry in both zh-CN.ts and en.ts,
 * then add the property to the relevant interface below.
 */

 
export interface LocaleMessages {
  [namespace: string]: {
    [key: string]: string | Record<string, string>
  }
}

// Type helper for vue-i18n useI18n
declare module 'vue-i18n' {
// eslint-disable-next-line @typescript-eslint/no-empty-object-type
  export interface DefineLocaleMessage extends LocaleMessages {}
}
