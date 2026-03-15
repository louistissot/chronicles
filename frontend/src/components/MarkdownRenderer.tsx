/**
 * MarkdownRenderer — renders LLM-generated markdown to styled JSX.
 * Supports: headers, bold, italic, inline code, bullet/numbered lists,
 * blockquotes, dividers, tables, line-break preservation.
 */
import { cn } from '@/lib/utils'

// ── Inline parser: handles **bold**, *italic*, `code` ──────────────────────

function InlineText({ text }: { text: string }) {
  const parts: React.ReactNode[] = []
  const re = /(\*\*(.+?)\*\*|\*(.+?)\*|`([^`]+)`)/g
  let last = 0
  let m: RegExpExecArray | null

  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index))
    if (m[2] !== undefined) {
      parts.push(<strong key={m.index} className="font-bold text-parchment/90">{m[2]}</strong>)
    } else if (m[3] !== undefined) {
      parts.push(<em key={m.index} className="italic text-parchment/80">{m[3]}</em>)
    } else if (m[4] !== undefined) {
      parts.push(
        <code key={m.index} className="px-1 py-0.5 rounded text-xs bg-white/8 text-gold/70 font-mono">
          {m[4]}
        </code>
      )
    }
    last = m.index + m[0].length
  }
  if (last < text.length) parts.push(text.slice(last))
  return <>{parts}</>
}

// ── Block-level renderer ──────────────────────────────────────────────────

interface MarkdownRendererProps {
  text: string
  className?: string
  /** When true, add id attributes to headings (for TOC linking) */
  headingIds?: boolean
}

export function MarkdownRenderer({ text, className, headingIds }: MarkdownRendererProps) {
  const lines = text.split('\n')
  const nodes: React.ReactNode[] = []
  let i = 0
  let headingCounter = 0

  while (i < lines.length) {
    const line = lines[i]

    // Skip blank lines
    if (!line.trim()) { i++; continue }

    // ── H1
    if (line.startsWith('# ')) {
      const hId = headingIds ? `md-heading-${headingCounter++}` : undefined
      nodes.push(
        <h2 key={i} id={hId} className="text-base font-heading text-gold uppercase tracking-widest mt-5 mb-2 first:mt-0">
          <InlineText text={line.slice(2)} />
        </h2>
      )
      i++; continue
    }

    // ── H2
    if (line.startsWith('## ')) {
      const hId = headingIds ? `md-heading-${headingCounter++}` : undefined
      nodes.push(
        <h3 key={i} id={hId} className="text-sm font-heading text-gold/80 uppercase tracking-widest mt-4 mb-1.5 first:mt-0">
          <InlineText text={line.slice(3)} />
        </h3>
      )
      i++; continue
    }

    // ── H3
    if (line.startsWith('### ')) {
      const hId = headingIds ? `md-heading-${headingCounter++}` : undefined
      nodes.push(
        <h4 key={i} id={hId} className="text-sm font-heading text-parchment/50 uppercase tracking-wide mt-3 mb-1 first:mt-0">
          <InlineText text={line.slice(4)} />
        </h4>
      )
      i++; continue
    }

    // ── Horizontal rule
    if (/^---+$/.test(line.trim())) {
      nodes.push(<hr key={i} className="border-white/8 my-3" />)
      i++; continue
    }

    // ── Table: detect lines matching |...|
    if (/^\|.*\|$/.test(line.trim())) {
      const tableLines: string[] = []
      while (i < lines.length && /^\|.*\|$/.test(lines[i].trim())) {
        tableLines.push(lines[i].trim())
        i++
      }
      if (tableLines.length >= 2) {
        const parseRow = (row: string) =>
          row.split('|').slice(1, -1).map(cell => cell.trim())
        const headers = parseRow(tableLines[0])
        const isSeparator = (row: string) => /^\|[\s\-:]+\|$/.test(row)
        const dataStart = isSeparator(tableLines[1]) ? 2 : 1
        const dataRows = tableLines.slice(dataStart).map(parseRow)

        nodes.push(
          <div key={`table-${i}`} className="my-3 overflow-x-auto">
            <table className="w-full text-sm font-body border-collapse">
              <thead>
                <tr className="border-b border-white/10">
                  {headers.map((h, j) => (
                    <th key={j} className="text-left px-3 py-1.5 text-xs font-heading text-gold/70 uppercase tracking-wider">
                      <InlineText text={h} />
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {dataRows.map((row, ri) => (
                  <tr key={ri} className="border-b border-white/5">
                    {row.map((cell, ci) => (
                      <td key={ci} className="px-3 py-1.5 text-sm text-parchment/65">
                        <InlineText text={cell} />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
        continue
      }
    }

    // ── Bullet list: collect consecutive bullet lines
    if (/^(\s*[-*])\s/.test(line)) {
      const items: { text: string; indent: number }[] = []
      while (i < lines.length && /^(\s*)[-*]\s/.test(lines[i])) {
        const m = lines[i].match(/^(\s*)[-*]\s(.*)$/)!
        items.push({ text: m[2], indent: m[1].length })
        i++
      }
      nodes.push(
        <ul key={`ul-${i}`} className="space-y-1 my-2">
          {items.map((item, j) => (
            <li key={j} className="flex gap-2 text-sm text-parchment/70 font-body leading-relaxed"
              style={{ paddingLeft: `${item.indent * 8}px` }}>
              <span className="text-gold/40 flex-none mt-0.5 text-xs">·</span>
              <span><InlineText text={item.text} /></span>
            </li>
          ))}
        </ul>
      )
      continue
    }

    // ── Numbered list: collect consecutive numbered lines
    if (/^\d+\.\s/.test(line)) {
      const items: string[] = []
      while (i < lines.length && /^\d+\.\s/.test(lines[i])) {
        items.push(lines[i].replace(/^\d+\.\s*/, ''))
        i++
      }
      nodes.push(
        <ol key={`ol-${i}`} className="space-y-1 my-2 list-none">
          {items.map((item, j) => (
            <li key={j} className="flex gap-2 text-sm text-parchment/70 font-body leading-relaxed">
              <span className="text-gold/50 flex-none font-mono text-xs mt-0.5 w-4 text-right">{j + 1}.</span>
              <span><InlineText text={item} /></span>
            </li>
          ))}
        </ol>
      )
      continue
    }

    // ── Blockquote
    if (line.startsWith('> ')) {
      nodes.push(
        <blockquote key={i} className="border-l-2 border-gold/25 pl-3 my-2 italic text-sm text-parchment/55 font-body leading-relaxed">
          <InlineText text={line.slice(2)} />
        </blockquote>
      )
      i++; continue
    }

    // ── Regular paragraph: accumulate until blank line or block element
    const paraLines: string[] = []
    while (
      i < lines.length &&
      lines[i].trim() &&
      !lines[i].startsWith('#') &&
      !/^---+$/.test(lines[i].trim()) &&
      !/^(\s*[-*])\s/.test(lines[i]) &&
      !/^\d+\.\s/.test(lines[i]) &&
      !lines[i].startsWith('> ') &&
      !/^\|.*\|$/.test(lines[i].trim())
    ) {
      paraLines.push(lines[i])
      i++
    }
    if (paraLines.length) {
      nodes.push(
        <p key={`p-${i}`} className="text-sm text-parchment/70 font-body leading-relaxed my-2.5">
          {paraLines.map((pl, j) => (
            <span key={j}>
              {j > 0 && <br />}
              <InlineText text={pl} />
            </span>
          ))}
        </p>
      )
    }
  }

  return <div className={cn('space-y-0', className)}>{nodes}</div>
}
