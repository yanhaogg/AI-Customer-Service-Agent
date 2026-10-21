import { useEffect, useState } from 'react'
import { useAuth } from '../auth/useAuth'
import { apiUrl } from '../lib/catalog'

export default function SecureEvidence({ evidence }) {
  const { token } = useAuth(),
    [image, setImage] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    let objectUrl = ''
    fetch(apiUrl(evidence.url), {
      headers: { Authorization: `Bearer ${token}` },
      signal: controller.signal,
    })
      .then((response) => {
        if (!response.ok) throw new Error('无法读取凭证')
        return response.blob()
      })
      .then((blob) => {
        if (!controller.signal.aborted) {
          objectUrl = URL.createObjectURL(blob)
          setImage(objectUrl)
        }
      })
      .catch(() => {})
    return () => {
      controller.abort()
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [token, evidence.url])
  return image ? (
    <a href={image} target="_blank" rel="noreferrer">
      <img src={image} alt={`退款凭证 ${evidence.id}`} />
    </a>
  ) : (
    <span>凭证加载中…</span>
  )
}
