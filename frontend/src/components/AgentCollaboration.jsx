const agents={product_agent:'商品咨询',order_agent:'订单查询',aftersales_agent:'售后服务'}
const states={completed:'已完成',incomplete:'部分完成',unavailable:'暂时不可用',limited:'达到查询上限',rejected:'未执行',invalid_arguments:'参数未通过验证',limit:'达到调度上限'}

export default function AgentCollaboration({metadata}){
 if(!metadata?.agents?.length)return null
 return <details className="chat-tool-summary"><summary>本次服务分工</summary><ul>{metadata.agents.map((entry,index)=><li key={index}>{agents[entry.agent] || '专业服务'} · {states[entry.status] || '未完成'}</li>)}</ul>{metadata.limited && <small>部分查询达到本轮上限，可以补充信息后继续咨询。</small>}</details>
}
