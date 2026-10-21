export default function CatalogStatus({ loading, error, retry }) {
  return (
    <div className="catalog-status" role={error ? 'alert' : 'status'}>
      {loading ? (
        <>
          <span className="loading-ring" />
          <h2>正在加载商品…</h2>
          <p>为你寻找日常好物</p>
        </>
      ) : (
        <>
          <h2>商品暂时无法加载</h2>
          <p>{error}</p>
          <button onClick={retry} className="secondary">
            重新加载
          </button>
        </>
      )}
    </div>
  )
}
