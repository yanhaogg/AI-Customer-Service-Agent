import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import { shopRequest, useShop, money } from '../lib/shop'
import CatalogStatus from './CatalogStatus'
import SecureEvidence from './SecureEvidence'
import { refundLabels } from '../lib/refunds'

const eventLabels = {
  submitted: '提交申请',
  refunded: '退款完成',
  return_authorized: '批准退货',
  return_shipped: '寄回商品',
  rejected: '审核驳回',
  withdrawn: '撤销申请',
}

function RequestForm({ order, options, onSaved }) {
  const { token } = useAuth(),
    key = useRef(crypto.randomUUID())
  const [reason, setReason] = useState('not_needed'),
    [description, setDescription] = useState(''),
    [phone, setPhone] = useState(options.contact_phone || '')
  const [received, setReceived] = useState(
    order.status === 'completed' ? 'yes' : order.status === 'paid' ? 'no' : '',
  )
  const [evidence, setEvidence] = useState([]),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('')
  const requiredEvidence = ['quality', 'damaged'].includes(reason)
  function changed() {
    key.current = crypto.randomUUID()
  }
  async function upload(file) {
    if (!file) return
    if (file.size > 5_000_000) {
      setError('图片最多5MB')
      return
    }
    setBusy(true)
    setError('')
    try {
      const data = await new Promise((resolve, reject) => {
        const reader = new FileReader()
        reader.onload = () => resolve(reader.result.split(',')[1])
        reader.onerror = () => reject(new Error('读取图片失败'))
        reader.readAsDataURL(file)
      })
      const result = await shopRequest(token, `/api/shop/orders/${order.id}/refund-evidence`, {
        method: 'POST',
        body: JSON.stringify({ data }),
      })
      setEvidence((previous) => [...previous, result])
      changed()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }
  async function submit(event) {
    event.preventDefault()
    setError('')
    if (requiredEvidence && !evidence.length) {
      setError('质量或破损问题请至少上传1张照片')
      return
    }
    setBusy(true)
    try {
      await shopRequest(token, `/api/shop/orders/${order.id}/refunds`, {
        method: 'POST',
        body: JSON.stringify({
          request_key: key.current,
          reason,
          description,
          contact_phone: phone,
          received: received === 'yes',
          evidence_ids: evidence.map((e) => e.id),
        }),
      })
      onSaved()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <form onSubmit={submit} className="refund-form">
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <fieldset disabled={busy}>
        <h3>申请整单全额模拟退款 · {money(order.total, order.currency)}</h3>
        <div className="product-form-grid">
          <label>
            退款原因
            <select
              value={reason}
              onChange={(e) => {
                setReason(e.target.value)
                changed()
              }}
            >
              {options.reasons.map((r) => (
                <option key={r.code} value={r.code}>
                  {r.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            是否已收到货
            <select
              required
              value={received}
              disabled={order.status === 'paid' || order.status === 'completed'}
              onChange={(e) => {
                setReceived(e.target.value)
                changed()
              }}
            >
              <option value="">请选择实际情况</option>
              <option value="no">尚未收到</option>
              <option value="yes">已经收到</option>
            </select>
          </label>
          <label>
            确认联系电话
            <input
              required
              type="tel"
              minLength={6}
              maxLength={30}
              value={phone}
              onChange={(e) => {
                setPhone(e.target.value)
                changed()
              }}
            />
          </label>
          <label className="full-width">
            情况说明（至少10字）
            <textarea
              required
              minLength={10}
              maxLength={2000}
              rows={3}
              value={description}
              onChange={(e) => {
                setDescription(e.target.value)
                changed()
              }}
              placeholder="请说明退款原因、商品情况或支付/物流异常。请勿提供银行卡、密码或验证码。"
            />
          </label>
          <label className="full-width">
            凭证照片{requiredEvidence ? '（必填）' : '（选填）'}
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              disabled={evidence.length >= 3 || busy}
              onChange={(e) => {
                upload(e.target.files[0])
                e.target.value = ''
              }}
            />
            <small>最多3张，每张5MB以内。凭证仅申请人和审核人员可见。</small>
          </label>
        </div>
        <div className="refund-evidence">
          {evidence.map((item) => (
            <div key={item.id}>
              <SecureEvidence evidence={item} />
              <button
                type="button"
                className="secondary"
                onClick={() => {
                  setEvidence((items) => items.filter((e) => e.id !== item.id))
                  changed()
                }}
              >
                移除
              </button>
            </div>
          ))}
        </div>
        <p className="demo-note">
          {options.auto_possible &&
          ['not_needed', 'wrong_order', 'change_mind'].includes(reason) &&
          received === 'no'
            ? '当前符合自动退款条件，提交后将完成整单模拟退款。'
            : '本申请将进入人工审核；已收到货的退货需审核通过后再寄回。'}
        </p>
        <button>{busy ? '提交中…' : '确认提交退款申请'}</button>
      </fieldset>
    </form>
  )
}

function CaseActions({ refund, admin, onSaved }) {
  const { token } = useAuth()
  const [action, setAction] = useState(
      refund.status === 'return_in_transit' ? 'confirm_return' : 'approve',
    ),
    [note, setNote] = useState(''),
    [address, setAddress] = useState(''),
    [carrier, setCarrier] = useState(''),
    [tracking, setTracking] = useState('')
  const [busy, setBusy] = useState(false),
    [error, setError] = useState('')
  async function run(path, body) {
    setBusy(true)
    setError('')
    try {
      await shopRequest(token, path, {
        method: 'POST',
        ...(body ? { body: JSON.stringify(body) } : {}),
      })
      onSaved()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {admin && ['review_pending', 'return_in_transit'].includes(refund.status) && (
        <form
          className="refund-review"
          onSubmit={(e) => {
            e.preventDefault()
            run(`/api/admin/refunds/${refund.id}/review`, {
              action,
              note,
              return_address: address,
            })
          }}
        >
          <fieldset disabled={busy}>
            <h3>人工审核处理</h3>
            <label>
              处理方式
              <select value={action} onChange={(e) => setAction(e.target.value)}>
                {refund.status === 'review_pending' ? (
                  <>
                    <option value="approve">批准申请</option>
                    <option value="reject">驳回申请</option>
                  </>
                ) : (
                  <option value="confirm_return">确认退货验收并模拟退款</option>
                )}
              </select>
            </label>
            <label>
              处理说明（至少5字）
              <textarea
                required
                minLength={5}
                maxLength={1000}
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
            </label>
            {action === 'approve' &&
              refund.received &&
              ['shipped', 'completed'].includes(refund.original_status) && (
                <label>
                  退货地址及收件联系人
                  <input
                    required
                    minLength={10}
                    maxLength={1000}
                    value={address}
                    onChange={(e) => setAddress(e.target.value)}
                    placeholder="完整退货地址、收件人及电话"
                  />
                </label>
              )}
            <button>确认处理</button>
          </fieldset>
        </form>
      )}
      {!admin && refund.status === 'awaiting_return' && (
        <form
          className="refund-review"
          onSubmit={(e) => {
            e.preventDefault()
            run(`/api/shop/refunds/${refund.id}/return-shipping`, {
              carrier,
              tracking_number: tracking,
            })
          }}
        >
          <fieldset disabled={busy}>
            <h3>填写寄回物流</h3>
            <p>请按上方客服提供的退货地址寄回，填写真实物流后等待验收。</p>
            <label>
              退货快递公司
              <input
                required
                maxLength={100}
                value={carrier}
                onChange={(e) => setCarrier(e.target.value)}
              />
            </label>
            <label>
              退货单号
              <input
                required
                minLength={3}
                maxLength={100}
                pattern="[A-Za-z0-9-]+"
                value={tracking}
                onChange={(e) => setTracking(e.target.value)}
              />
            </label>
            <button>提交退货物流</button>
          </fieldset>
        </form>
      )}
      {!admin && ['review_pending', 'awaiting_return'].includes(refund.status) && (
        <button
          className="secondary"
          disabled={busy}
          onClick={() => run(`/api/shop/refunds/${refund.id}/withdraw`)}
        >
          撤销此申请
        </button>
      )}
    </>
  )
}

export default function AftersalesPanel({ order, admin, onChanged, onClose }) {
  const records = useShop(`/api/${admin ? 'admin' : 'shop'}/orders/${order.id}/refunds`)
  const options = useShop(admin ? null : `/api/shop/orders/${order.id}/refund-options`)
  function saved() {
    records.retry()
    options.retry()
    onChanged()
  }
  return (
    <section className="aftersales-panel">
      <div className="shop-toolbar">
        <h2>退款与售后</h2>
        <button className="secondary" onClick={onClose}>
          收起
        </button>
      </div>
      <p className="demo-note">仅整单全额模拟退款，不发生真实资金转账。</p>
      {!admin && options.data && (
        <details className="refund-policy" open>
          <summary>自动退款、人工审核与所需资料</summary>
          <p>{options.data.auto_rule}</p>
          <p>{options.data.manual_rule}</p>
          <p>{options.data.return_rule}</p>
          <p>{options.data.timing}</p>
          <p>{options.data.evidence_rule}</p>
        </details>
      )}
      {!admin && options.data?.can_apply && (
        <RequestForm order={order} options={options.data} onSaved={saved} />
      )}{' '}
      {!admin && options.error && <CatalogStatus {...options} />}{' '}
      {records.loading || records.error ? (
        <CatalogStatus {...records} />
      ) : (
        records.data?.items.map((refund) => (
          <article className="refund-case" key={refund.id}>
            <div className="shop-toolbar">
              <h3>
                申请 #{refund.id} · {refundLabels[refund.status]}
              </h3>
              <strong>{money(refund.amount, refund.currency)}</strong>
            </div>
            <p>{refund.description}</p>
            <p>
              联系电话：{refund.contact_phone} · {refund.received ? '已收到货' : '未收到货'}
            </p>
            <p>{refund.route_reason}</p>
            {refund.review_note && <p>客服处理：{refund.review_note}</p>}
            {refund.return_address && (
              <p>
                <strong>退货地址：</strong>
                {refund.return_address}
                <br />
                建议 {new Date(refund.return_due_at).toLocaleDateString('zh-CN')}{' '}
                前寄出，超期请联系人工客服。
              </p>
            )}
            {refund.return_tracking && (
              <p>
                退货物流：{refund.return_carrier} · {refund.return_tracking}
              </p>
            )}
            <div className="refund-evidence">
              {refund.evidence.map((e) => (
                <SecureEvidence key={e.id} evidence={e} />
              ))}
            </div>
            {refund.chat_session_id && (!admin || refund.human_status !== 'none') && (
              <Link
                className="button secondary"
                to={`${admin ? '/admin/support' : '/chat'}?session=${refund.chat_session_id}`}
              >
                {admin ? '接待此售后会话' : '查看订单售后会话'}
              </Link>
            )}
            <CaseActions
              key={`${refund.id}:${refund.status}`}
              refund={refund}
              admin={admin}
              onSaved={saved}
            />
            <details className="refund-events">
              <summary>处理记录</summary>
              {refund.events.map((event, index) => (
                <p key={index}>
                  {new Date(event.created_at).toLocaleString('zh-CN')} ·{' '}
                  {eventLabels[event.action] || event.action}：{event.note}
                </p>
              ))}
            </details>
          </article>
        ))
      )}
    </section>
  )
}
