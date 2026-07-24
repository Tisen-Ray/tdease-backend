/**
 * HTTP API Client Service
 * Handles all communication with the backend API
 */

import type { APIResponse, APIError } from '../../types/api'
import { ErrorCode, TimeoutError, NetworkError, createError } from '../../types/errors'
import { getAuthHeaders, clearAuthentication } from '../auth/AuthService'
import { getRuntimeConfig } from '../runtimeConfig'

export interface RetryConfig {
  maxRetries: number
  retryDelay: number
  retryOn: number[]
}

export interface APIClientConfig {
  baseURL: string
  timeout?: number
  headers?: Record<string, string>
  retryConfig?: RetryConfig
}

export interface RequestOptions {
  signal?: AbortSignal
  headers?: Record<string, string>
  responseType?: 'json' | 'text' | 'blob' | 'stream'
  timeoutMs?: number | null
}

export interface APIClientLike {
  get<T>(url: string, params?: Record<string, unknown>, options?: RequestOptions): Promise<APIResponse<T>>
  post<T>(url: string, data?: unknown, options?: RequestOptions): Promise<APIResponse<T>>
  put<T>(url: string, data?: unknown, options?: RequestOptions): Promise<APIResponse<T>>
  delete<T>(url: string, options?: RequestOptions): Promise<APIResponse<T>>
  patch<T>(url: string, data?: unknown, options?: RequestOptions): Promise<APIResponse<T>>
}

const DEFAULT_TIMEOUT = 30000 // 30 seconds
const DEFAULT_RETRY_CONFIG: RetryConfig = {
  maxRetries: 3,
  retryDelay: 1000,
  retryOn: [408, 429, 500, 502, 503, 504],
}
const DEFAULT_BASE_URL = resolveAPIBaseURL()
const LOCAL_API_ORIGINS = ['http://127.0.0.1:8000', 'http://localhost:8000'] as const

type AbortSource = 'timeout' | 'signal' | null

function createAbortError(): Error {
  const error = new Error('Request aborted')
  error.name = 'AbortError'
  return error
}

export function resolveAPIBaseURL(rawBaseURL?: string | null): string {
  if (typeof window !== 'undefined' && window.location.protocol === 'file:') {
    return 'http://127.0.0.1:8000'
  }
  const runtimeBaseURL = getRuntimeConfig().VITE_API_BASE_URL
  const envBaseURL = typeof import.meta !== 'undefined' ? import.meta.env.VITE_API_BASE_URL : ''
  const candidate = String(rawBaseURL ?? runtimeBaseURL ?? envBaseURL ?? '').trim()
  if (!candidate || candidate.includes('1421')) {
    return ''
  }
  if (shouldPreferRelativeApiBase(candidate)) {
    return ''
  }
  return candidate
}

function isLoopbackHost(hostname: string): boolean {
  return hostname === '127.0.0.1' || hostname === 'localhost'
}

function shouldPreferRelativeApiBase(candidate: string): boolean {
  if (typeof window === 'undefined' || typeof window.location === 'undefined') {
    return false
  }

  let parsed: URL
  try {
    parsed = new URL(candidate)
  } catch {
    return false
  }

  const { protocol, port } = window.location
  if (!protocol.startsWith('http')) {
    return false
  }
  if (port === '8000') {
    return false
  }

  return isLoopbackHost(parsed.hostname) && parsed.port === '8000'
}

function resolveApiPath(url: string): string | null {
  if (!url) return null
  if (url.startsWith('/api') || url.startsWith('/health')) {
    return url
  }

  try {
    const parsed = new URL(url)
    if (!parsed.pathname.startsWith('/api') && parsed.pathname !== '/health') {
      return null
    }
    return `${parsed.pathname}${parsed.search}`
  } catch {
    return null
  }
}

export function buildLocalApiFallbackUrls(url: string): string[] {
  const apiPath = resolveApiPath(url)
  if (!apiPath) return []

  const candidates = [apiPath, ...LOCAL_API_ORIGINS.map((origin) => `${origin}${apiPath}`)]
  const uniqueCandidates = candidates.filter((candidate, index) => (
    candidate !== url && candidates.indexOf(candidate) === index
  ))
  return uniqueCandidates
}

export function isRequestAbortedError(error: unknown): boolean {
  return error instanceof Error && error.name === 'AbortError'
}

/**
 * APIClient class for handling HTTP requests
 */
export class APIClient {
  private baseURL: string
  private timeout: number
  private headers: Record<string, string>
  private retryConfig: RetryConfig

  constructor(config: APIClientConfig) {
    this.baseURL = config.baseURL
    this.timeout = config.timeout ?? DEFAULT_TIMEOUT
    this.headers = {
      'Content-Type': 'application/json',
      ...config.headers,
    }
    this.retryConfig = config.retryConfig ?? DEFAULT_RETRY_CONFIG
  }

  /**
   * Set the base URL for API requests
   */
  setBaseURL(url: string): void {
    this.baseURL = url
  }

  /**
   * Set a default header for all requests
   */
  setHeader(key: string, value: string): void {
    this.headers[key] = value
  }

  /**
   * Remove a default header
   */
  removeHeader(key: string): void {
    delete this.headers[key]
  }

  /**
   * GET request
   */
  async get<T>(
    url: string,
    params?: Record<string, unknown>,
    options?: RequestOptions
  ): Promise<APIResponse<T>> {
    const queryString = this.buildQueryString(params)
    const fullUrl = `${this.baseURL}${url}${queryString}`
    return this.request<T>('GET', fullUrl, undefined, 0, options)
  }

  /**
   * POST request
   */
  async post<T>(url: string, data?: unknown, options?: RequestOptions): Promise<APIResponse<T>> {
    const fullUrl = `${this.baseURL}${url}`
    return this.request<T>('POST', fullUrl, data, 0, options)
  }

  /**
   * PUT request
   */
  async put<T>(url: string, data?: unknown, options?: RequestOptions): Promise<APIResponse<T>> {
    const fullUrl = `${this.baseURL}${url}`
    return this.request<T>('PUT', fullUrl, data, 0, options)
  }

  /**
   * DELETE request
   */
  async delete<T>(url: string, options?: RequestOptions): Promise<APIResponse<T>> {
    const fullUrl = `${this.baseURL}${url}`
    return this.request<T>('DELETE', fullUrl, undefined, 0, options)
  }

  /**
   * PATCH request
   */
  async patch<T>(url: string, data?: unknown, options?: RequestOptions): Promise<APIResponse<T>> {
    const fullUrl = `${this.baseURL}${url}`
    return this.request<T>('PATCH', fullUrl, data, 0, options)
  }

  /**
   * Internal request method with retry logic
   */
  private async request<T>(
    method: string,
    url: string,
    data?: unknown,
    attempt: number = 0,
    options?: RequestOptions,
    fallbackUrls: string[] = buildLocalApiFallbackUrls(url),
  ): Promise<APIResponse<T>> {
    let timeoutId: ReturnType<typeof setTimeout> | null = null
    let offAbort: (() => void) | null = null
    let abortSource: AbortSource = null
    try {
      const controller = new AbortController()
      const requestTimeoutMs = options?.timeoutMs
      const timeoutMs =
        requestTimeoutMs === undefined
          ? this.timeout
          : requestTimeoutMs
      if (typeof timeoutMs === 'number' && Number.isFinite(timeoutMs) && timeoutMs > 0) {
        timeoutId = setTimeout(() => {
          abortSource = 'timeout'
          controller.abort()
        }, timeoutMs)
      }
      const externalSignal = options?.signal
      if (externalSignal) {
        if (externalSignal.aborted) {
          abortSource = 'signal'
          if (timeoutId) clearTimeout(timeoutId)
          throw createAbortError()
        }
        const onAbort = (): void => {
          abortSource = 'signal'
          controller.abort()
          if (timeoutId) clearTimeout(timeoutId)
        }
        externalSignal.addEventListener('abort', onAbort)
        offAbort = () => externalSignal.removeEventListener('abort', onAbort)
      }

      const mergedHeaders: Record<string, string> = {
        ...this.headers,
        ...(options?.headers ?? {}),
      }

      const requestInit: RequestInit = {
        method,
        headers: mergedHeaders,
        signal: controller.signal,
      }

      Object.assign(requestInit.headers as Record<string, string>, getAuthHeaders())

      if (data instanceof FormData) {
        // Let the browser set multipart boundary automatically.
        delete mergedHeaders['Content-Type']
        requestInit.body = data
      } else if (data instanceof URLSearchParams || data instanceof Blob || data instanceof ArrayBuffer || typeof data === 'string') {
        requestInit.body = data as BodyInit
      } else if (data !== undefined) {
        requestInit.body = JSON.stringify(data)
      }

      const response = await fetch(url, requestInit)
      if (timeoutId) clearTimeout(timeoutId)
      // For streaming responses, keep the abort listener wired so an external
      // signal can still cancel the ReadableStream during body consumption.
      if (options?.responseType !== 'stream') {
        offAbort?.()
      }

      // Handle response
      let responseData: unknown

      // 204 No Content has no body — skip parsing to avoid JSON parse errors
      if (response.status === 204) {
        responseData = null
      } else if (options?.responseType === 'stream') {
        responseData = response
      } else if (options?.responseType === 'blob') {
        responseData = await response.blob()
      } else if (options?.responseType === 'text') {
        responseData = await response.text()
      } else {
        const contentType = response.headers.get('content-type')
        if (contentType?.includes('application/json')) {
          responseData = await response.json()
        } else {
          responseData = await response.text()
        }
      }

      // Check if response is successful
      if (!response.ok) {
        let errorPayload = responseData
        if (options?.responseType === 'stream') {
          try {
            errorPayload = await response.text()
          } catch {
            errorPayload = `HTTP ${response.status}`
          }
        }
        return this.handleErrorResponse<T>(response.status, errorPayload, method, url, attempt, options, data)
      }

      return {
        data: responseData as T,
        status: response.status,
        headers: this.headersToObject(response.headers),
      }
    } catch (error) {
      if (timeoutId) clearTimeout(timeoutId)
      offAbort?.()
      if (error instanceof TypeError && fallbackUrls.length > 0) {
        const [nextUrl, ...remainingFallbacks] = fallbackUrls
        return this.request<T>(method, nextUrl, data, attempt, options, remainingFallbacks)
      }
      return this.handleRequestError<T>(error, method, url, abortSource)
    }
  }

  /**
   * Handle error responses
   */
  private async handleErrorResponse<T>(
    status: number,
    data: unknown,
    method: string,
    url: string,
    attempt: number,
    options?: RequestOptions,
    requestData?: unknown
  ): Promise<APIResponse<T>> {
    if (status === 401) {
      clearAuthentication()
    }

    // Check if we should retry
    if (this.shouldRetry(status, attempt)) {
      const delay = this.retryConfig.retryDelay * Math.pow(2, attempt)
      await this.sleep(delay)
      return this.request<T>(method, url, requestData, attempt + 1, options)
    }

    // Parse error response
    const errorData = this.parseErrorResponse(data)
    const error = createError(
      this.mapStatusToErrorCode(status),
      errorData.message || `HTTP ${status}`,
      undefined,
      {
        status,
        url,
        method,
        details: errorData.details,
      }
    )

    throw error
  }

  /**
   * Handle request errors (network, timeout, etc.)
   */
  private handleRequestError<T>(
    error: unknown,
    method: string,
    url: string,
    abortSource: AbortSource = null
  ): Promise<APIResponse<T>> {
    // Check if it's an abort error (user abort or timeout)
    if (error instanceof Error && error.name === 'AbortError') {
      if (abortSource === 'signal') {
        return Promise.reject(
          createAbortError()
        )
      }
      return Promise.reject(
        new TimeoutError('Request timeout', {
          url,
          method,
        })
      )
    }

    // Network error
    if (error instanceof TypeError) {
      return Promise.reject(
        new NetworkError(`Network error: ${error.message}`, {
          url,
          method,
          originalError: error.message,
        })
      )
    }

    // Unknown error
    return Promise.reject(
      createError(
        ErrorCode.UNKNOWN_ERROR,
        `Unknown error during request: ${error instanceof Error ? error.message : String(error)}`,
        undefined,
        { url, method, error }
      )
    )
  }

  /**
   * Check if request should be retried
   */
  private shouldRetry(status: number, attempt: number): boolean {
    return attempt < this.retryConfig.maxRetries && this.retryConfig.retryOn.includes(status)
  }

  /**
   * Map HTTP status to error code
   */
  private mapStatusToErrorCode(status: number): ErrorCode {
    switch (status) {
      case 400:
        return ErrorCode.VALIDATION_ERROR
      case 401:
        return ErrorCode.UNAUTHORIZED
      case 403:
        return ErrorCode.FORBIDDEN
      case 404:
        return ErrorCode.NOT_FOUND
      case 408:
        return ErrorCode.TIMEOUT_ERROR
      case 409:
        return ErrorCode.CONFLICT
      case 429:
        return ErrorCode.RATE_LIMITED
      case 500:
      case 502:
      case 503:
      case 504:
        return ErrorCode.API_ERROR
      default:
        return ErrorCode.API_ERROR
    }
  }

  /**
   * Parse error response
   */
  private parseErrorResponse(data: unknown): APIError {
    if (typeof data === 'object' && data !== null) {
      const obj = data as Record<string, unknown>
      const detail = obj.detail

      let message = typeof obj.message === 'string' ? obj.message : ''
      if (!message) {
        if (typeof detail === 'string') {
          message = detail
        } else if (Array.isArray(detail)) {
          message = detail
            .map((item) => {
              if (typeof item === 'string') return item
              if (item && typeof item === 'object') {
                const msg = (item as Record<string, unknown>).msg
                return typeof msg === 'string' ? msg : JSON.stringify(item)
              }
              return String(item)
            })
            .join('; ')
        } else if (detail && typeof detail === 'object') {
          const msg = (detail as Record<string, unknown>).msg
          if (typeof msg === 'string') {
            message = msg
          }
        }
      }

      return {
        message: message || 'Unknown error',
        status: (obj.status as number) || 0,
        code: (obj.code as string) || 'UNKNOWN',
        details: obj.details ?? detail ?? obj,
      }
    }

    return {
      message: String(data) || 'Unknown error',
      status: 0,
      code: 'UNKNOWN',
    }
  }

  /**
   * Build query string from parameters
   */
  private buildQueryString(params?: Record<string, unknown>): string {
    if (!params || Object.keys(params).length === 0) {
      return ''
    }

    const queryParams = new URLSearchParams()
    for (const [key, value] of Object.entries(params)) {
      if (value !== null && value !== undefined) {
        queryParams.append(key, String(value))
      }
    }

    return `?${queryParams.toString()}`
  }

  /**
   * Convert Headers object to plain object
   */
  private headersToObject(headers: Headers): Record<string, string> {
    const obj: Record<string, string> = {}
    headers.forEach((value, key) => {
      obj[key] = value
    })
    return obj
  }

  /**
   * Sleep utility for delays
   */
  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms))
  }
}

/**
 * Create a singleton instance of APIClient
 */
let apiClientInstance: APIClient | null = null

export function createAPIClient(config: APIClientConfig): APIClient {
  apiClientInstance = new APIClient(config)
  return apiClientInstance
}

export function getOrCreateAPIClient(config: Partial<APIClientConfig> = {}): APIClient {
  if (apiClientInstance) {
    apiClientInstance.setBaseURL(resolveAPIBaseURL(config.baseURL ?? DEFAULT_BASE_URL))
    return apiClientInstance
  }
  return createAPIClient({
    baseURL: resolveAPIBaseURL(config.baseURL ?? DEFAULT_BASE_URL),
    timeout: config.timeout ?? DEFAULT_TIMEOUT,
    headers: config.headers,
    retryConfig: config.retryConfig,
  })
}

export function getAPIClient(): APIClient {
  if (!apiClientInstance) {
    throw new Error('APIClient not initialized. Call createAPIClient first.')
  }
  return apiClientInstance
}
