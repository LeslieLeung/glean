import axios from 'axios'

const api = axios.create({
  baseURL: '/api/admin',
})

// Add request interceptor to include auth token
api.interceptors.request.use(
  (config) => {
    // Get token from localStorage
    const storedAuth = localStorage.getItem('glean-admin-auth')
    if (storedAuth) {
      try {
        const { state } = JSON.parse(storedAuth)
        if (state?.token) {
          config.headers.Authorization = `Bearer ${state.token}`
        }
      } catch (error) {
        console.error('Failed to parse stored auth:', error)
      }
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Add response interceptor to handle 401 errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      console.log('API Interceptor - 401 Unauthorized, clearing auth and redirecting');
      localStorage.removeItem('glean-admin-auth')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export default api

