import Navbar from '../components/Navbar'
import CatalogImage from '../components/CatalogImage'
import CatalogStatus from '../components/CatalogStatus'
import ProductCard from '../components/ProductCard'
import { displayName, formatPrice, useCatalog } from '../lib/catalog'
import { Link } from 'react-router-dom'

export default function Home() {
  const catalog = useCatalog('/home')
  const data = catalog.data
  const hero = data?.hero

  return (
    <>
      <Navbar />

      <main className="container storefront">
        {/* ===== 加载 / 错误 / 空目录 状态 ===== */}
        {catalog.loading || catalog.error ? (
          <CatalogStatus {...catalog} />
        ) : !hero ? (
          <div className="empty-catalog">
            <h1>好物即将到来</h1>
            <p>商品目录暂时为空，请先导入商品资料。</p>
          </div>
        ) : (
          <>
            {/* ===== 分类导航条 ===== */}
            <div className="store-category-nav">
              <span>为日常，选好物。</span>
              {data.categories.map((category) => (
                <Link key={category.code} to={`/products?category=${category.code}`}>
                  {category.name}
                </Link>
              ))}
            </div>

            {/* ===== 精选大图（hero） ===== */}
            <section className="flagship db-flagship">
              <div className="flagship-copy">
                <span className="eyebrow">SERVAI SELECT · 日常好物精选</span>
                <span className="flagship-label">本期精选 / {hero.brand || hero.category}</span>
                <h1>
                  {hero.category_code === '05_audio' ? (
                    <>
                      让好声音，
                      <br />
                      融入日常。
                    </>
                  ) : (
                    <>
                      科技好物，
                      <br />
                      陪伴日常。
                    </>
                  )}
                </h1>
                <p className="hero-product-title">{displayName(hero)}</p>
                <span className="flagship-description">
                  发现适合你的电子好物，
                  <br />
                  从了解产品，到选择更从容。
                </span>
                <div className="flagship-price">
                  {formatPrice(hero.price)}
                  <small>历史参考价</small>
                </div>
                <Link className="button" to={`/products/${hero.id}`}>
                  探索这款商品 ↗
                </Link>
                <Link className="flagship-all" to="/products">
                  浏览全部 {data.total} 件商品 →
                </Link>
              </div>

              <div className="flagship-art">
                <span className="flagship-word" aria-hidden="true">
                  {hero.brand || 'SELECT'}
                </span>
                <CatalogImage product={hero} eager />
                <div className="flagship-caption">
                  <span>EVERYDAY TECHNOLOGY</span>
                  <span>
                    {hero.category} · {hero.brand}
                  </span>
                </div>
              </div>

              <div className="flagship-features">
                <span>
                  <small>01</small>
                  {hero.category}
                </span>
                <span>
                  <small>02</small>
                  {hero.brand || '品牌好物'}
                </span>
                <span>
                  <small>03</small>了解商品 · 轻松咨询
                </span>
              </div>
            </section>

            {/* ===== 聚光商品（spotlights） ===== */}
            <section className="collection-teasers">
              {data.spotlights.map((product) => (
                <Link key={product.id} to={`/products/${product.id}`}>
                  <div>
                    <span className="eyebrow">{product.category}</span>
                    <h2>{product.brand || product.category}</h2>
                    <p className="teaser-product-title">{displayName(product)}</p>
                    <span className="teaser-link">探索商品 ↗</span>
                  </div>
                  <CatalogImage product={product} />
                </Link>
              ))}
            </section>

            {/* ===== 推荐商品网格（featured） ===== */}
            <section className="store-section">
              <div className="section-heading">
                <div>
                  <span className="eyebrow">EVERYDAY ESSENTIALS</span>
                  <h2>日常好物，刚刚好</h2>
                </div>
                <Link className="text-link" to="/products">
                  查看全部商品 →
                </Link>
              </div>
              <div className="catalog-grid">
                {data.featured.map((product) => (
                  <ProductCard key={product.id} product={product} />
                ))}
              </div>
            </section>

            {/* ===== 分类发现（categories） ===== */}
            <section className="category-discovery">
              <div className="section-heading">
                <div>
                  <span className="eyebrow">FIND YOUR EVERYDAY</span>
                  <h2>按生活所需，发现好物</h2>
                </div>
              </div>
              <div>
                {data.categories.map((category) => (
                  <Link to={`/products?category=${category.code}`} key={category.code}>
                    <strong>{category.name}</strong>
                    <span>{category.count} 件商品 ↗</span>
                  </Link>
                ))}
              </div>
            </section>

            {/* ===== 客服入口 ===== */}
            <section className="store-support">
              <div>
                <span className="eyebrow">GOOD PRODUCTS. THOUGHTFUL SERVICE.</span>
                <h2>选购有疑问？我们来帮你。</h2>
                <p>了解产品、查询订单或咨询售后，ServAI 都在这里。</p>
              </div>
              <Link className="button secondary" to="/chat">
                咨询智能客服 ↗
              </Link>
              <Link to="/orders">查看我的订单 →</Link>
            </section>
          </>
        )}
      </main>

      <footer className="container footer">
        <span className="footer-brand">
          ServAI <small>为日常，选好物。</small>
        </span>
        <span>演示商城 · 支持模拟下单与支付</span>
      </footer>
    </>
  )
}
