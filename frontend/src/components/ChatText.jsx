import { Link } from 'react-router-dom'

// Render emphasis and verified-shape local links, without HTML or external URLs.
export default function ChatText({ text }) {
  const pieces = []
  const pattern = /\[([^\]\n]+)\]\((\/(?:products|orders)\/\d+|\/history)\)|\*\*([^*\n]+)\*\*/g
  let offset = 0
  for (const match of text.matchAll(pattern)) {
    if (match.index > offset) pieces.push(text.slice(offset, match.index))
    pieces.push(
      match[2] ? (
        <Link key={match.index} to={match[2]}>
          {match[1]}
        </Link>
      ) : (
        <strong key={match.index}>{match[3]}</strong>
      ),
    )
    offset = match.index + match[0].length
  }
  pieces.push(text.slice(offset))
  return <p>{pieces}</p>
}
