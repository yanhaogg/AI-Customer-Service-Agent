import { useEffect, useState } from 'react'
import { AuthContext } from './context'
import { apiUrl } from '../lib/catalog'
export default function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem('token') || '')
  const [attempt, setAttempt] = useState(0)
  const [identity, setIdentity] = useState({
    key: '',
    token: '',
    user: null,
    error: '',
  })
  const key = `${token}:${attempt}`
  useEffect(() => {
    if (!token) return
    const controller = new AbortController()
    fetch(apiUrl('/auth/me'), {
      headers: { Authorization: `Bearer ${token}` },
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok)
          throw new Error(
            response.status === 401 ? '登录已过期，请重新登录' : '暂时无法验证账号，请重试',
          )
        return response.json()
      })
      .then((user) => {
        if (!controller.signal.aborted) setIdentity({ key, token, user, error: '' })
      })
      .catch((error) => {
        if (!controller.signal.aborted)
          setIdentity({ key, token, user: null, error: error.message })
      })
    return () => controller.abort()
  }, [token, key])
  useEffect(() => {
    const sync = () => setToken(localStorage.getItem('token') || '')
    const refresh = () => setAttempt((value) => value + 1)
    window.addEventListener('storage', sync)
    window.addEventListener('focus', refresh)
    return () => {
      window.removeEventListener('storage', sync)
      window.removeEventListener('focus', refresh)
    }
  }, [])
  function login(accessToken) {
    localStorage.setItem('token', accessToken)
    setToken(accessToken)
    setAttempt((value) => value + 1)
  }
  function logout() {
    localStorage.removeItem('token')
    localStorage.removeItem('username')
    setToken('')
  }
  // Revalidate the same session in the background so returning from an image picker
  // does not unmount an editor and discard its unsaved fields. New tokens still wait.
  const sameSession = !!token && identity.token === token
  const user = sameSession ? identity.user : null
  const value = {
    token,
    user,
    loading: !!token && !sameSession,
    error: sameSession ? identity.error : '',
    isAdmin: user?.role === 'super_admin',
    login,
    logout,
    refresh: () => setAttempt((value) => value + 1),
  }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
