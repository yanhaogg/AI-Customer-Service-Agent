import { Link, useParams } from 'react-router-dom'
import Navbar from '../components/Navbar'
import CatalogImage from '../components/CatalogImage'
import CatalogStatus from '../components/CatalogStatus'
import ProductCard from '../components/ProductCard'
import PurchaseActions from '../components/PurchaseActions'
import TrackProductView from '../components/TrackProductView'
import { formatPrice, productQuestion, useCatalog } from '../lib/catalog'
export default function ProductDetail() {
 const {id} = useParams()
 const catalog = useCatalog(`/products/${encodeURIComponent(id)}`)
 const product = catalog.data
 const specs = product?.specs || {}
 const fields = {manufacturer:'厂商',model:'型号',upc:'UPC 商品编码',type:'商品类型'}
 return <><Navbar/><main className="container page">{catalog.loading || catalog.error ? <CatalogStatus {...catalog}/> : <><TrackProductView key={product.id} productId={product.id}/><div className="breadcrumbs"><Link to="/home">首页</Link><span>/</span><Link to="/products">全部商品</Link><span>/</span><span>{product.category}</span></div><section className="detail-hero"><div className="detail-image"><span className="eyebrow">{product.brand || product.category}</span><CatalogImage product={product} eager/><span className="detail-image-note">商品资料图片</span></div><div className="detail-copy"><span className="flagship-label">{product.category} / {product.brand}</span><h1>{product.name}</h1><p>{product.introduction}</p><div className="detail-price">{formatPrice(product.price)}<small>历史参考价 · 非当前售价</small></div>{product.model && <p className="product-model">型号：{product.model}</p>}<PurchaseActions key={product.id} product={product}/><Link className="button detail-cta" to={productQuestion(product)}>咨询这款商品 ↗</Link><p className="detail-notice">商品资料及历史参考价仅供了解，演示订单请使用上方演示售价。</p></div></section><section className="specification panel"><span className="eyebrow">THE DETAILS MATTER</span><h2>商品信息</h2><dl>{[['品牌',product.brand],['分类',product.category],...Object.entries(specs.source_original || {}).map(([key,value])=>[fields[key] || key,value]),...Object.entries(specs.verified || {}).map(([key,value])=>[key,typeof value === 'object' ? JSON.stringify(value) : String(value)])].filter(([,value])=>value).map(([label,value],index)=><div key={index}><dt>{label}</dt><dd>{value}</dd></div>)}</dl></section><section className="panel original-description"><h2>原始商品介绍</h2><p>{product.description_original}</p>{specs.extracted?.length > 0 && <details><summary>查看原文提及的参数与证据</summary><p className="detail-notice">以下为原文提取片段，可能涉及兼容设备或配件，不等同于已核实参数。</p>{specs.extracted.map((item,index)=><div className="evidence-item" key={index}><strong>{item.value_original}</strong><p>{item.evidence_original}</p></div>)}</details>}</section><section className="store-section"><div className="section-heading"><div><span className="eyebrow">MORE TO EXPLORE</span><h2>同类商品，更多选择</h2></div><Link to={`/products?category=${product.category_code}`}>全部同类商品 →</Link></div><div className="catalog-grid">{product.related.map(item=><ProductCard key={item.id} product={item}/>)}</div></section></>}</main></>
}
