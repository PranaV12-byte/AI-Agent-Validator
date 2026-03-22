import axios from "axios"

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1"

type SessionProvider = () => { accessToken: string | null }

let getSession: SessionProvider = () => ({ accessToken: null })
let onUnauthorized: (() => void) | null = null

export function registerSessionProvider(provider: SessionProvider) {
  getSession = provider
}

export function registerUnauthorizedHandler(handler: (() => void) | null) {
  onUnauthorized = handler
}

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15000,
})

apiClient.interceptors.request.use((config) => {
  const { accessToken } = getSession()

  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`
  }

  return config
})

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      onUnauthorized?.()
    }

    return Promise.reject(error)
  },
)
