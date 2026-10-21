import { Link } from 'react-router-dom'
import CatalogImage from './CatalogImage'
import PurchaseActions from './PurchaseActions'
import { displayName, formatPrice } from '../lib/catalog'
export default function ProductCard({ product }) {
 return <article className="catalog-card"><Link className="catalog-card-main" to={`/products/${product.id}`}><div className="catalog-image"><span className="catalog-tag">{product.brand || product.category}</span><CatalogImage product={product}/></div><div className="catalog-info"><span className="eyebrow">{product.category}</span><h3 title={product.name}>{displayName(product)}</h3><p>{product.model ? `型号 ${product.model}` : product.brand || '日常电子好物'}</p><div><strong>{formatPrice(product.offer?.is_active ? product.offer : product.price)}</strong><span>查看详情 ↗</span></div><small className="historical-label">{product.offer?.is_active ? '演示售价 · 模拟购买' : product.price ? '历史参考价' : '来源暂无价格'}</small></div></Link><PurchaseActions product={product} compact/></article>
}
