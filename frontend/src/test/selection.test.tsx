import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { useState } from 'react'
import { DslRenderer } from '../dsl/DslRenderer'
import type { DslDocument, DslNode } from '../dsl/types'
import App from '../App'

// Test harness that mimics App's selection behavior but accepts custom data
function SelectionHarness({ doc }: { doc: DslDocument }) {
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)

  function findNodeById(node: DslNode, id: string): DslNode | null {
    if (node.id === id) return node
    if ('children' in node && node.children) {
      for (const child of node.children) {
        const found = findNodeById(child, id)
        if (found) return found
      }
    }
    return null
  }

  const selectedNode = selectedNodeId ? findNodeById(doc.root, selectedNodeId) : null

  return (
    <div>
      <DslRenderer node={doc.root} selectedNodeId={selectedNodeId} onSelect={setSelectedNodeId} />
      <aside data-testid="info-panel">
        {selectedNode ? (
          <>
            <span data-testid="panel-id">{selectedNode.id}</span>
            <span data-testid="panel-type">{selectedNode.type}</span>
            <span data-testid="panel-props">{JSON.stringify(selectedNode.props ?? {}, null, 2)}</span>
          </>
        ) : (
          <span data-testid="panel-empty">No selection</span>
        )}
      </aside>
    </div>
  )
}

const nestedDoc: DslDocument = {
  version: '0.1',
  root: {
    id: 'page',
    type: 'Page',
    props: { title: 'Test' },
    children: [
      {
        id: 'section-1',
        type: 'Section',
        props: { ariaLabel: 'Section One' },
        children: [
          { id: 'deep-text', type: 'Text', props: { text: 'Deep' } },
          { id: 'deep-button', type: 'Button', props: { text: 'Click' } },
        ],
      },
      {
        id: 'input-node',
        type: 'Input',
        props: { name: 'field', label: 'Field', inputType: 'text', placeholder: 'Enter' },
      },
    ],
  },
}

// 省略 props 和 children 的合法容器节点（对齐 Schema：容器 props/children 均可省略）
const barePageDoc: DslDocument = {
  version: '0.1',
  root: { id: 'bare-page', type: 'Page' },
}

const bareContainersDoc: DslDocument = {
  version: '0.1',
  root: {
    id: 'bare-root',
    type: 'Page',
    children: [
      { id: 'bare-section', type: 'Section' },
      { id: 'bare-card', type: 'Card' },
      { id: 'bare-form', type: 'Form' },
    ],
  },
}

describe('Selection behavior', () => {
  describe('Initial state', () => {
    it('initial selectedNodeId is null (no data-selected anywhere)', () => {
      const { container } = render(<SelectionHarness doc={nestedDoc} />)
      const selected = container.querySelectorAll('[data-selected]')
      expect(selected).toHaveLength(0)
    })
  })

  describe('Click selection', () => {
    it('clicking a leaf node selects it (data-selected appears)', () => {
      const { container } = render(<SelectionHarness doc={nestedDoc} />)
      const textNode = container.querySelector('[data-node-id="deep-text"]')!
      fireEvent.click(textNode)
      expect(textNode.getAttribute('data-selected')).toBe('true')
    })

    it('clicking a container node selects it', () => {
      const { container } = render(<SelectionHarness doc={nestedDoc} />)
      const sectionNode = container.querySelector('[data-node-id="section-1"]')!
      fireEvent.click(sectionNode)
      expect(sectionNode.getAttribute('data-selected')).toBe('true')
    })

    it('clicking a deep node does NOT select ancestor (stopPropagation works)', () => {
      const { container } = render(<SelectionHarness doc={nestedDoc} />)
      const deepText = container.querySelector('[data-node-id="deep-text"]')!
      fireEvent.click(deepText)

      // Deep text should be selected
      expect(deepText.getAttribute('data-selected')).toBe('true')
      // Section (ancestor) should NOT be selected
      const section = container.querySelector('[data-node-id="section-1"]')!
      expect(section.hasAttribute('data-selected')).toBe(false)
      // Page (ancestor) should NOT be selected
      const page = container.querySelector('[data-node-id="page"]')!
      expect(page.hasAttribute('data-selected')).toBe(false)
    })

    it('switching selection: old node loses data-selected, new node gains it', () => {
      const { container } = render(<SelectionHarness doc={nestedDoc} />)
      const textNode = container.querySelector('[data-node-id="deep-text"]')!
      const buttonNode = container.querySelector('[data-node-id="deep-button"]')!

      fireEvent.click(textNode)
      expect(textNode.getAttribute('data-selected')).toBe('true')

      fireEvent.click(buttonNode)
      expect(buttonNode.getAttribute('data-selected')).toBe('true')
      expect(textNode.hasAttribute('data-selected')).toBe(false)
    })

    it('only one node has data-selected at any time', () => {
      const { container } = render(<SelectionHarness doc={nestedDoc} />)
      const deepText = container.querySelector('[data-node-id="deep-text"]')!
      fireEvent.click(deepText)

      const selectedNodes = container.querySelectorAll('[data-selected]')
      expect(selectedNodes).toHaveLength(1)
    })

    it('button click only selects, does not trigger business action', () => {
      const { container } = render(<SelectionHarness doc={nestedDoc} />)
      const button = container.querySelector('[data-node-id="deep-button"]')!
      // Clicking should not cause navigation or any side effect beyond selection
      fireEvent.click(button)
      expect(button.getAttribute('data-selected')).toBe('true')
      // The button is still in the DOM (no navigation happened)
      expect(container.querySelector('[data-node-id="deep-button"]')).not.toBeNull()
    })

    it('input node can be selected', () => {
      const { container } = render(<SelectionHarness doc={nestedDoc} />)
      const inputLabel = container.querySelector('[data-node-id="input-node"]')!
      fireEvent.click(inputLabel)
      expect(inputLabel.getAttribute('data-selected')).toBe('true')
    })
  })

  describe('Keyboard selection', () => {
    it('Enter key triggers selection on focused node', () => {
      const { container } = render(<SelectionHarness doc={nestedDoc} />)
      const textNode = container.querySelector('[data-node-id="deep-text"]')!
      fireEvent.keyDown(textNode, { key: 'Enter' })
      expect(textNode.getAttribute('data-selected')).toBe('true')
    })

    it('Space key triggers selection on focused node', () => {
      const { container } = render(<SelectionHarness doc={nestedDoc} />)
      const buttonNode = container.querySelector('[data-node-id="deep-button"]')!
      fireEvent.keyDown(buttonNode, { key: ' ' })
      expect(buttonNode.getAttribute('data-selected')).toBe('true')
    })
  })

  describe('Info panel', () => {
    it('info panel shows correct node id when selected', () => {
      const { container } = render(<SelectionHarness doc={nestedDoc} />)
      const textNode = container.querySelector('[data-node-id="deep-text"]')!
      fireEvent.click(textNode)

      const panelId = container.querySelector('[data-testid="panel-id"]')!
      expect(panelId.textContent).toBe('deep-text')
    })

    it('info panel shows correct node type when selected', () => {
      const { container } = render(<SelectionHarness doc={nestedDoc} />)
      const textNode = container.querySelector('[data-node-id="deep-text"]')!
      fireEvent.click(textNode)

      const panelType = container.querySelector('[data-testid="panel-type"]')!
      expect(panelType.textContent).toBe('Text')
    })

    it('info panel shows props content when selected', () => {
      const { container } = render(<SelectionHarness doc={nestedDoc} />)
      const textNode = container.querySelector('[data-node-id="deep-text"]')!
      fireEvent.click(textNode)

      const panelProps = container.querySelector('[data-testid="panel-props"]')!
      const parsedProps = JSON.parse(panelProps.textContent!) as Record<string, unknown>
      expect(parsedProps).toEqual({ text: 'Deep' })
    })
  })

  describe('Data immutability', () => {
    it('selection does NOT modify the DSL data (deep equality check)', () => {
      const docCopy = JSON.parse(JSON.stringify(nestedDoc)) as DslDocument
      const { container } = render(<SelectionHarness doc={nestedDoc} />)

      const textNode = container.querySelector('[data-node-id="deep-text"]')!
      fireEvent.click(textNode)

      // Original data must not be mutated
      expect(nestedDoc).toEqual(docCopy)
    })

    it('selectedNodeId does NOT appear in serialized DSL', () => {
      const serialized = JSON.stringify(nestedDoc)
      expect(serialized).not.toContain('selectedNodeId')
      expect(serialized).not.toContain('data-selected')
    })
  })

  describe('App integration', () => {
    it('App renders the gold case and info panel', () => {
      const { container } = render(<App />)
      // Should render the page
      expect(container.querySelector('[data-node-id="page"]')).not.toBeNull()
      // Should render the info panel with hint text
      expect(screen.getByText('点击页面中的任意元素以选中')).not.toBeNull()
    })

    it('App selection shows info in panel', () => {
      const { container } = render(<App />)
      const heroTitle = container.querySelector('[data-node-id="hero.title"]')!
      fireEvent.click(heroTitle)

      // Panel should show ID and Type
      expect(screen.getByText('hero.title')).not.toBeNull()
      expect(screen.getByText('Heading')).not.toBeNull()
    })
  })

  describe('Containers with omitted props and children (Schema 对齐)', () => {
    it('Page with omitted props and children is selectable, panel shows {}', () => {
      const { container } = render(<SelectionHarness doc={barePageDoc} />)
      const page = container.querySelector('[data-node-id="bare-page"]')!
      fireEvent.click(page)
      expect(page.getAttribute('data-selected')).toBe('true')

      const panelId = container.querySelector('[data-testid="panel-id"]')!
      expect(panelId.textContent).toBe('bare-page')
      const panelProps = container.querySelector('[data-testid="panel-props"]')!
      expect(panelProps.textContent).toBe('{}')
    })

    it('Section with omitted props and children is selectable, panel shows {}', () => {
      const { container } = render(<SelectionHarness doc={bareContainersDoc} />)
      const section = container.querySelector('[data-node-id="bare-section"]')!
      fireEvent.click(section)
      expect(section.getAttribute('data-selected')).toBe('true')

      const panelId = container.querySelector('[data-testid="panel-id"]')!
      expect(panelId.textContent).toBe('bare-section')
      const panelProps = container.querySelector('[data-testid="panel-props"]')!
      expect(panelProps.textContent).toBe('{}')
    })

    it('Card with omitted props and children is selectable, panel shows {}', () => {
      const { container } = render(<SelectionHarness doc={bareContainersDoc} />)
      const card = container.querySelector('[data-node-id="bare-card"]')!
      fireEvent.click(card)
      expect(card.getAttribute('data-selected')).toBe('true')

      const panelId = container.querySelector('[data-testid="panel-id"]')!
      expect(panelId.textContent).toBe('bare-card')
      const panelProps = container.querySelector('[data-testid="panel-props"]')!
      expect(panelProps.textContent).toBe('{}')
    })

    it('Form with omitted props and children is selectable, panel shows {}', () => {
      const { container } = render(<SelectionHarness doc={bareContainersDoc} />)
      const form = container.querySelector('[data-node-id="bare-form"]')!
      fireEvent.click(form)
      expect(form.getAttribute('data-selected')).toBe('true')

      const panelId = container.querySelector('[data-testid="panel-id"]')!
      expect(panelId.textContent).toBe('bare-form')
      const panelProps = container.querySelector('[data-testid="panel-props"]')!
      expect(panelProps.textContent).toBe('{}')
    })
  })
})
