import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { ProviderBadge } from './ProviderBadge'
import { shortAgentLabel } from './agentLabel'

describe('shortAgentLabel', () => {
  it('formats anthropic claude variants', () => {
    expect(shortAgentLabel('anthropic:claude-haiku-4-5')).toBe('Haiku 4.5')
    expect(shortAgentLabel('anthropic:claude-sonnet-4-6')).toBe('Sonnet 4.6')
  })

  it('formats openai gpt variants', () => {
    expect(shortAgentLabel('openai:gpt-5.4-mini')).toContain('GPT')
    expect(shortAgentLabel('openai:gpt-4o')).toContain('GPT')
  })

  it('formats deepseek as plain "DeepSeek" for chat alias', () => {
    expect(shortAgentLabel('deepseek:deepseek-chat')).toBe('DeepSeek')
    expect(shortAgentLabel('deepseek:deepseek-reasoner')).toBe('DeepSeek')
  })

  it('formats deepseek v4 with version suffix', () => {
    expect(shortAgentLabel('deepseek:deepseek-v4-flash')).toBe('DeepSeek v4 flash')
  })

  it('formats qwen with version', () => {
    expect(shortAgentLabel('qwen:qwen3.6-plus')).toBe('Qwen 3.6 plus')
  })

  it('formats kimi / grok / gemini', () => {
    expect(shortAgentLabel('kimi:kimi-k2.6')).toBe('Kimi K2.6')
    expect(shortAgentLabel('grok:grok-4.1-fast')).toBe('Grok 4.1 fast')
    expect(shortAgentLabel('gemini:gemini-3.1-pro')).toBe('Gemini 3.1 pro')
    // legacy versions still format correctly
    expect(shortAgentLabel('gemini:gemini-2.0-flash')).toBe('Gemini 2.0 flash')
  })

  it('returns "Rule-based" for rule_based agents', () => {
    expect(shortAgentLabel('rule_based:tag_v1')).toBe('Rule-based')
  })
})

describe('ProviderBadge', () => {
  it('renders an SVG for known provider', () => {
    const { container } = render(<ProviderBadge agentId="anthropic:claude-haiku-4-5" />)
    expect(container.querySelector('svg')).not.toBeNull()
  })

  it('renders the lucide Bot icon for rule_based', () => {
    const { container } = render(<ProviderBadge agentId="rule_based:tag_v1" />)
    expect(container.querySelector('svg')).not.toBeNull()
  })

  it('falls back to a help icon for unknown providers', () => {
    const { container } = render(<ProviderBadge agentId="totally:unknown:format" />)
    expect(container.querySelector('svg')).not.toBeNull()
  })
})
