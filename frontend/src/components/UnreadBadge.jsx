export default function UnreadBadge({count=0}){
 return count>0 ? <span className="unread-badge" aria-label={`${count} 条未读消息`}>{count>99 ? '99+':count}</span>:null
}
