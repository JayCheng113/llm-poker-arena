import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { Markdown } from './renderMarkdown'

describe('Markdown', () => {
  it('renders **bold** as <strong>', () => {
    const { container } = render(<Markdown text="Fold **AKo** here." />)
    const strong = container.querySelector('strong')
    expect(strong).not.toBeNull()
    expect(strong?.textContent).toBe('AKo')
  })

  it('renders inline `code` as <code>', () => {
    const { container } = render(<Markdown text="Call `pot_odds()` first." />)
    const code = container.querySelector('code')
    expect(code?.textContent).toBe('pot_odds()')
  })

  it('renders bullet list as <ul><li>', () => {
    const text = `- Hand strength low
- Position bad
- Stack short`
    const { container } = render(<Markdown text={text} />)
    expect(container.querySelector('ul')).not.toBeNull()
    expect(container.querySelectorAll('li')).toHaveLength(3)
  })

  it('renders headings as actual heading tags (we only restyle, not demote)', () => {
    const text = `## Decision

Fold.`
    const { container } = render(<Markdown text={text} />)
    expect(container.querySelector('h2')?.textContent).toBe('Decision')
  })

  it('strips <script> tag itself; surrounding text content is preserved', () => {
    // We sanitize by removing <script>/<iframe>/etc tags and on*= handlers,
    // not by escaping inner text. The point is that no executable code
    // can run, NOT that "alert(1)" never appears as a string. (LLMs that
    // happen to write the word "alert" in poker reasoning would otherwise
    // trigger this if we matched the bare string.)
    const { container } = render(
      <Markdown text="Normal <script>alert(1)</script> after." />,
    )
    expect(container.innerHTML).not.toContain('<script>')
    expect(container.innerHTML).not.toContain('</script>')
    // The text remnant survives — that's fine, no execution context.
    expect(container.textContent).toContain('Normal')
    expect(container.textContent).toContain('after')
  })

  it('strips inline event handlers (on*=)', () => {
    const { container } = render(
      <Markdown text='Click me <a href="#" onclick="alert(1)">here</a>' />,
    )
    expect(container.innerHTML).not.toContain('onclick')
  })

  it('treats single newlines as soft breaks (matches LLM expectation)', () => {
    const text = `line one
line two`
    const { container } = render(<Markdown text={text} />)
    expect(container.querySelector('br')).not.toBeNull()
  })

  it('passes className through to wrapper', () => {
    const { container } = render(<Markdown text="hi" className="my-cls" />)
    expect(container.firstElementChild?.classList.contains('my-cls')).toBe(true)
  })
})
