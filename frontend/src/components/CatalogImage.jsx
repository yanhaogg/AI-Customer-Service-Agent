import { useState } from 'react'
import { apiUrl } from '../lib/catalog'
export default function CatalogImage({ product, eager = false }) {
  const [failedUrl, setFailedUrl] = useState('')
  const src = product.image ? apiUrl(product.image.url) : ''
  return src && failedUrl !== src ? (
    <img
      className="real-product-image"
      src={src}
      alt={product.image.alt || product.name}
      loading={eager ? 'eager' : 'lazy'}
      onError={() => setFailedUrl(src)}
    />
  ) : (
    <div className="image-unavailable" role="img" aria-label={`${product.name}，图片暂不可用`}>
      <span>▧</span>
      <small>图片暂不可用</small>
    </div>
  )
}
