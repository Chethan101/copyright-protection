export const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8001';
export const API_URL = `${API_BASE_URL}/api`;

// The copyright registry is a separate service with its own database, reached from the
// Registry tab. The two backends sign tokens with different keys, so VibeSocial's backend
// brokers a registry session for the signed-in user (same username, no second login);
// that registry token is kept under its own storage key.
export const REGISTRY_BASE_URL = import.meta.env.VITE_REGISTRY_URL || 'http://127.0.0.1:8000';
export const REGISTRY_API_URL = `${REGISTRY_BASE_URL}/api`;
export const REGISTRY_TOKEN_KEY = 'registry_token';
