import axios from 'axios';

/**
 * Axios Instance
 *
 * Pre-configured Axios client for all API calls.
 * When the Django REST Framework backend is ready, simply update
 * the baseURL and the interceptors will handle JWT injection.
 */
const axiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// ─── Request Interceptor: Attach JWT token ─────────────────────
axiosInstance.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// ─── Response Interceptor: Handle auth errors ──────────────────
axiosInstance.interceptors.response.use(
  (response) => response,
  (error) => {
    // If we get a 401, the token has expired — redirect to login
    if (error.response?.status === 401) {
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default axiosInstance;

/**
 * Utility: Simulate network delay for mock services.
 * Adds a realistic delay so loading states are visible.
 *
 * @param ms - Delay in milliseconds (default: 300-600ms random)
 */
export const simulateDelay = (ms?: number): Promise<void> => {
  const delay = ms ?? Math.floor(Math.random() * 300) + 300;
  return new Promise((resolve) => setTimeout(resolve, delay));
};
