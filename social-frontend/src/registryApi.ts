import axios from 'axios';
import { REGISTRY_API_URL, REGISTRY_TOKEN_KEY } from './config';

/** Fired when the registry session changes, so the Registry tab can re-open it. */
export const REGISTRY_SESSION_EVENT = 'registry-session-changed';

export function getRegistryToken(): string | null {
  return localStorage.getItem(REGISTRY_TOKEN_KEY);
}

export function setRegistryToken(token: string) {
  localStorage.setItem(REGISTRY_TOKEN_KEY, token);
  window.dispatchEvent(new Event(REGISTRY_SESSION_EVENT));
}

export function clearRegistryToken() {
  localStorage.removeItem(REGISTRY_TOKEN_KEY);
  window.dispatchEvent(new Event(REGISTRY_SESSION_EVENT));
}

const registryApi = axios.create({ baseURL: REGISTRY_API_URL });

registryApi.interceptors.request.use((config) => {
  const token = getRegistryToken();
  if (token) {
    config.headers = config.headers ?? {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

registryApi.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      // Standalone, the registry redirected the whole window to its own /login. Inside
      // VibeSocial that would throw the user out of an app they are still signed in to,
      // so an expired registry session only clears its own token -- the Registry tab
      // then signs the same VibeSocial user back in, and the rest of the app is untouched.
      clearRegistryToken();
    }
    return Promise.reject(err);
  }
);

export default registryApi;
