import { marked } from 'marked'
import type { JSX } from 'react'

// LLM-generated reasoning text often arrives in light markdown — Claude
// uses **bold** + ## headers + - bullets aggressively, Kimi/DeepSeek
// occasionally. Without rendering those marks come through as literal
// asterisks/hashes which looks like a bug.
//
// We use `marked` (smallest serious markdown lib, ~9KB gzip) on the
// content path and inject the result via dangerouslySetInnerHTML.
// Safety stance: the input is *LLM-generated text*, not user input —
// these models don't try to inject scripts. We still belt-and-suspender
// strip `<script>`, `<iframe>`, and `on*=` event handlers to neutralize
// the rare case a model echoes attacker text back to us.

marked.setOptions({
  // single newline → <br>, matches the LLM's expectation that a Shift+Enter
  // counts as a soft break (it almost never means "new paragraph").
  breaks: true,
  // tables, strikethrough, autolinks — useful when models emit tables.
  gfm: true,
})

const FORBIDDEN_TAG_RE = /<\/?(?:script|iframe|object|embed|style|link|meta|form|input)[^>]*>/gi
const ON_HANDLER_RE = / on\w+="[^"]*"/gi
const ON_HANDLER_RE_2 = / on\w+='[^']*'/gi

function sanitize(html: string): string {
  return html
    .replace(FORBIDDEN_TAG_RE, '')
    .replace(ON_HANDLER_RE, '')
    .replace(ON_HANDLER_RE_2, '')
}

export interface MarkdownProps {
  text: string
  className?: string
  'data-testid'?: string
}

export function Markdown({ text, className, ...rest }: MarkdownProps): JSX.Element {
  // marked.parse is async-capable as of v9+ but we use the sync path so
  // the React tree stays renderable in one pass without Suspense.
  const html = sanitize(marked.parse(text, { async: false }) as string)
  return (
    <div
      className={className}
      // Markdown produces nested block elements (<p>, <ul>, <code>); the
      // wrapper class controls spacing/typography.
      dangerouslySetInnerHTML={{ __html: html }}
      {...rest}
    />
  )
}
