import { render } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { DslRenderer } from '../dsl/DslRenderer'
import { ErrorBoundary } from '../dsl/ErrorBoundary'
import type { DslDocument, DslNode, PageNode, SectionNode, HeadingNode, TextNode, ButtonNode, ImageNode, CardNode, FormNode, InputNode } from '../dsl/types'
import goldCaseRaw from '../../../examples/dsl/coffee-shop-landing.json'

const goldCase = goldCaseRaw as unknown as DslDocument

const noop = () => { /* no-op */ }

describe('DslRenderer', () => {
  describe('Page component', () => {
    it('renders as <main> with data-node-id and data-node-type', () => {
      const pageNode: PageNode = {
        id: 'test-page',
        type: 'Page',
        props: { title: 'Test Page' },
        children: [],
      }
      const { container } = render(
        <DslRenderer node={pageNode} selectedNodeId={null} onSelect={noop} />
      )
      const main = container.querySelector('main')
      expect(main).not.toBeNull()
      expect(main!.getAttribute('data-node-id')).toBe('test-page')
      expect(main!.getAttribute('data-node-type')).toBe('Page')
    })
  })

  describe('Section component', () => {
    it('renders as <section> with aria-label from ariaLabel', () => {
      const sectionNode: SectionNode = {
        id: 'test-section',
        type: 'Section',
        props: { ariaLabel: 'My Section' },
        children: [],
      }
      const { container } = render(
        <DslRenderer node={sectionNode} selectedNodeId={null} onSelect={noop} />
      )
      const section = container.querySelector('section')
      expect(section).not.toBeNull()
      expect(section!.getAttribute('aria-label')).toBe('My Section')
      expect(section!.getAttribute('data-node-id')).toBe('test-section')
      expect(section!.getAttribute('data-node-type')).toBe('Section')
    })
  })

  describe('Heading component', () => {
    it('renders level=1 as h1', () => {
      const headingNode: HeadingNode = {
        id: 'h1-test',
        type: 'Heading',
        props: { text: 'Title', level: 1 },
      }
      const { container } = render(
        <DslRenderer node={headingNode} selectedNodeId={null} onSelect={noop} />
      )
      const h1 = container.querySelector('h1')
      expect(h1).not.toBeNull()
      expect(h1!.textContent).toBe('Title')
    })

    it('renders level=3 as h3', () => {
      const headingNode: HeadingNode = {
        id: 'h3-test',
        type: 'Heading',
        props: { text: 'Subtitle', level: 3 },
      }
      const { container } = render(
        <DslRenderer node={headingNode} selectedNodeId={null} onSelect={noop} />
      )
      const h3 = container.querySelector('h3')
      expect(h3).not.toBeNull()
      expect(h3!.textContent).toBe('Subtitle')
    })

    it('renders level=6 as h6', () => {
      const headingNode: HeadingNode = {
        id: 'h6-test',
        type: 'Heading',
        props: { text: 'Small', level: 6 },
      }
      const { container } = render(
        <DslRenderer node={headingNode} selectedNodeId={null} onSelect={noop} />
      )
      const h6 = container.querySelector('h6')
      expect(h6).not.toBeNull()
      expect(h6!.textContent).toBe('Small')
    })
  })

  describe('Text component', () => {
    it('renders as <p> with text content', () => {
      const textNode: TextNode = {
        id: 'text-1',
        type: 'Text',
        props: { text: 'Hello World' },
      }
      const { container } = render(
        <DslRenderer node={textNode} selectedNodeId={null} onSelect={noop} />
      )
      const p = container.querySelector('p')
      expect(p).not.toBeNull()
      expect(p!.textContent).toBe('Hello World')
      expect(p!.getAttribute('data-node-type')).toBe('Text')
    })
  })

  describe('Button component', () => {
    it('renders as <button> with text content', () => {
      const buttonNode: ButtonNode = {
        id: 'btn-1',
        type: 'Button',
        props: { text: 'Click me' },
      }
      const { container } = render(
        <DslRenderer node={buttonNode} selectedNodeId={null} onSelect={noop} />
      )
      const button = container.querySelector('button')
      expect(button).not.toBeNull()
      expect(button!.textContent).toBe('Click me')
    })

    it('disabled button renders with aria-disabled', () => {
      const buttonNode: ButtonNode = {
        id: 'btn-disabled',
        type: 'Button',
        props: { text: 'Disabled', disabled: true },
      }
      const { container } = render(
        <DslRenderer node={buttonNode} selectedNodeId={null} onSelect={noop} />
      )
      const button = container.querySelector('button')
      expect(button).not.toBeNull()
      expect(button!.getAttribute('aria-disabled')).toBe('true')
      expect(button!.disabled).toBe(false)
    })

    it('disabled button is still selectable via click', () => {
      const onSelect = vi.fn()
      const buttonNode: ButtonNode = {
        id: 'btn-disabled-click',
        type: 'Button',
        props: { text: 'Disabled Click', disabled: true },
      }
      const { container } = render(
        <DslRenderer node={buttonNode} selectedNodeId={null} onSelect={onSelect} />
      )
      const button = container.querySelector('button')!
      button.click()
      expect(onSelect).toHaveBeenCalledWith('btn-disabled-click')
    })

    it('disabled button is still selectable via keyboard', () => {
      const onSelect = vi.fn()
      const buttonNode: ButtonNode = {
        id: 'btn-disabled-kb',
        type: 'Button',
        props: { text: 'Disabled KB', disabled: true },
      }
      const { container } = render(
        <DslRenderer node={buttonNode} selectedNodeId={null} onSelect={onSelect} />
      )
      const button = container.querySelector('button')!
      const event = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })
      button.dispatchEvent(event)
      expect(onSelect).toHaveBeenCalledWith('btn-disabled-kb')
    })

    it('button has type="button" to prevent implicit form submit', () => {
      const buttonNode: ButtonNode = {
        id: 'btn-type',
        type: 'Button',
        props: { text: 'Type Test' },
      }
      const { container } = render(
        <DslRenderer node={buttonNode} selectedNodeId={null} onSelect={noop} />
      )
      const button = container.querySelector('button')
      expect(button).not.toBeNull()
      expect(button!.getAttribute('type')).toBe('button')
    })

    it('variant applies as CSS class', () => {
      const buttonNode: ButtonNode = {
        id: 'btn-primary',
        type: 'Button',
        props: { text: 'Primary', variant: 'primary' },
      }
      const { container } = render(
        <DslRenderer node={buttonNode} selectedNodeId={null} onSelect={noop} />
      )
      const button = container.querySelector('button')
      expect(button).not.toBeNull()
      expect(button!.classList.contains('btn-primary')).toBe(true)
    })
  })

  describe('Image component', () => {
    it('renders as <img> with src and alt', () => {
      const imageNode: ImageNode = {
        id: 'img-1',
        type: 'Image',
        props: { src: '/photo.jpg', alt: 'A photo' },
      }
      const { container } = render(
        <DslRenderer node={imageNode} selectedNodeId={null} onSelect={noop} />
      )
      const img = container.querySelector('img')
      expect(img).not.toBeNull()
      expect(img!.getAttribute('src')).toBe('/photo.jpg')
      expect(img!.getAttribute('alt')).toBe('A photo')
      expect(img!.getAttribute('data-node-type')).toBe('Image')
    })
  })

  describe('Card component', () => {
    it('renders as <article>', () => {
      const cardNode: CardNode = {
        id: 'card-1',
        type: 'Card',
        props: { title: 'My Card' },
        children: [],
      }
      const { container } = render(
        <DslRenderer node={cardNode} selectedNodeId={null} onSelect={noop} />
      )
      const article = container.querySelector('article')
      expect(article).not.toBeNull()
      expect(article!.getAttribute('data-node-id')).toBe('card-1')
      expect(article!.getAttribute('data-node-type')).toBe('Card')
    })
  })

  describe('Form component', () => {
    it('renders as <form> with name', () => {
      const formNode: FormNode = {
        id: 'form-1',
        type: 'Form',
        props: { name: 'test-form' },
        children: [],
      }
      const { container } = render(
        <DslRenderer node={formNode} selectedNodeId={null} onSelect={noop} />
      )
      const form = container.querySelector('form')
      expect(form).not.toBeNull()
      expect(form!.getAttribute('name')).toBe('test-form')
    })

    it('does NOT submit on submit event (preventDefault)', () => {
      const formNode: FormNode = {
        id: 'form-prevent',
        type: 'Form',
        props: { name: 'prevent-form' },
        children: [],
      }
      const { container } = render(
        <DslRenderer node={formNode} selectedNodeId={null} onSelect={noop} />
      )
      const form = container.querySelector('form')!
      const submitEvent = new Event('submit', { bubbles: true, cancelable: true })
      const prevented = !form.dispatchEvent(submitEvent)
      expect(prevented).toBe(true)
    })

    it('button inside form does not trigger submit on click', () => {
      const onSubmit = vi.fn()
      const formNode: FormNode = {
        id: 'form-btn',
        type: 'Form',
        props: { name: 'btn-form' },
        children: [
          { id: 'form-btn-child', type: 'Button', props: { text: 'Click Inside' } },
        ],
      }
      const { container } = render(
        <DslRenderer node={formNode} selectedNodeId={null} onSelect={noop} />
      )
      const form = container.querySelector('form')!
      form.addEventListener('submit', onSubmit)
      const button = container.querySelector('button')!
      button.click()
      expect(onSubmit).not.toHaveBeenCalled()
    })
  })

  describe('Input component', () => {
    it('renders with label + input elements, correct type/name/placeholder/required', () => {
      const inputNode: InputNode = {
        id: 'input-1',
        type: 'Input',
        props: {
          name: 'email',
          label: 'Email Address',
          inputType: 'email',
          placeholder: 'user@example.com',
          required: true,
        },
      }
      const { container } = render(
        <DslRenderer node={inputNode} selectedNodeId={null} onSelect={noop} />
      )
      const label = container.querySelector('label')
      expect(label).not.toBeNull()
      expect(label!.textContent).toContain('Email Address')
      expect(label!.getAttribute('data-node-id')).toBe('input-1')

      const input = container.querySelector('input')
      expect(input).not.toBeNull()
      expect(input!.getAttribute('name')).toBe('email')
      expect(input!.getAttribute('type')).toBe('email')
      expect(input!.getAttribute('placeholder')).toBe('user@example.com')
      expect(input!.required).toBe(true)
    })
  })

  describe('Container children rendering', () => {
    it('container nodes render children in correct order', () => {
      const pageNode: PageNode = {
        id: 'page-order',
        type: 'Page',
        props: { title: 'Order Test' },
        children: [
          { id: 'child-1', type: 'Text', props: { text: 'First' } },
          { id: 'child-2', type: 'Text', props: { text: 'Second' } },
          { id: 'child-3', type: 'Text', props: { text: 'Third' } },
        ],
      }
      const { container } = render(
        <DslRenderer node={pageNode} selectedNodeId={null} onSelect={noop} />
      )
      const paragraphs = container.querySelectorAll('p')
      expect(paragraphs).toHaveLength(3)
      expect(paragraphs[0]!.textContent).toBe('First')
      expect(paragraphs[1]!.textContent).toBe('Second')
      expect(paragraphs[2]!.textContent).toBe('Third')
    })
  })

  describe('Common node attributes', () => {
    it('all nodes have data-node-id attribute', () => {
      const doc: DslDocument = {
        version: '0.1',
        root: {
          id: 'root-page',
          type: 'Page',
          props: { title: 'Attr Test' },
          children: [
            { id: 'heading-attr', type: 'Heading', props: { text: 'Hi', level: 2 } },
            { id: 'text-attr', type: 'Text', props: { text: 'Body' } },
          ],
        },
      }
      const { container } = render(
        <DslRenderer node={doc.root} selectedNodeId={null} onSelect={noop} />
      )
      const nodesWithId = container.querySelectorAll('[data-node-id]')
      expect(nodesWithId.length).toBeGreaterThanOrEqual(3)
      expect(container.querySelector('[data-node-id="root-page"]')).not.toBeNull()
      expect(container.querySelector('[data-node-id="heading-attr"]')).not.toBeNull()
      expect(container.querySelector('[data-node-id="text-attr"]')).not.toBeNull()
    })

    it('all nodes have data-node-type attribute', () => {
      const doc: DslDocument = {
        version: '0.1',
        root: {
          id: 'type-page',
          type: 'Page',
          props: { title: 'Type Test' },
          children: [
            { id: 'type-btn', type: 'Button', props: { text: 'Go' } },
          ],
        },
      }
      const { container } = render(
        <DslRenderer node={doc.root} selectedNodeId={null} onSelect={noop} />
      )
      const pageEl = container.querySelector('[data-node-id="type-page"]')!
      expect(pageEl.getAttribute('data-node-type')).toBe('Page')
      const btnEl = container.querySelector('[data-node-id="type-btn"]')!
      expect(btnEl.getAttribute('data-node-type')).toBe('Button')
    })
  })

  describe('Style handling', () => {
    it('style whitelist: known fields are applied', () => {
      const textNode: TextNode = {
        id: 'styled-text',
        type: 'Text',
        props: { text: 'Styled' },
        style: { color: '#ff0000', fontSize: '20px', padding: '8px' },
      }
      const { container } = render(
        <DslRenderer node={textNode} selectedNodeId={null} onSelect={noop} />
      )
      const p = container.querySelector('p')!
      expect(p.style.color).toBe('rgb(255, 0, 0)')
      expect(p.style.fontSize).toBe('20px')
      expect(p.style.padding).toBe('8px')
    })

    it('style: unknown fields do NOT enter DOM style', () => {
      const textNode: TextNode = {
        id: 'bad-style',
        type: 'Text',
        props: { text: 'No bad style' },
        style: { color: 'blue' } as TextNode['style'],
      }
      // Add unknown field to test filtering（display 已在 Style v2 白名单内，改用真正未知字段）
      const nodeWithBadStyle = {
        ...textNode,
        style: { ...textNode.style, objectFit: 'cover', position: 'absolute' },
      } as unknown as TextNode
      const { container } = render(
        <DslRenderer node={nodeWithBadStyle} selectedNodeId={null} onSelect={noop} />
      )
      const p = container.querySelector('p')!
      expect(p.style.color).toBe('blue')
      expect(p.style.objectFit).toBe('')
      expect(p.style.position).toBe('')
    })
  })

  describe('Nullable / optional props', () => {
    it('renders node with missing optional props (inputType undefined)', () => {
      const inputNode: InputNode = {
        id: 'input-no-type',
        type: 'Input',
        props: { name: 'field', label: 'Field' },
      }
      const { container } = render(
        <DslRenderer node={inputNode} selectedNodeId={null} onSelect={noop} />
      )
      const input = container.querySelector('input')
      expect(input).not.toBeNull()
      expect(input!.getAttribute('type')).toBeFalsy()
    })

    it('renders node with null style', () => {
      const textNode: TextNode = {
        id: 'null-style-text',
        type: 'Text',
        props: { text: 'Null style' },
        style: null,
      }
      const { container } = render(
        <DslRenderer node={textNode} selectedNodeId={null} onSelect={noop} />
      )
      const p = container.querySelector('p')
      expect(p).not.toBeNull()
      expect(p!.textContent).toBe('Null style')
    })

    it('renders container with empty children array', () => {
      const pageNode: PageNode = {
        id: 'empty-children-page',
        type: 'Page',
        props: {},
        children: [],
      }
      const { container } = render(
        <DslRenderer node={pageNode} selectedNodeId={null} onSelect={noop} />
      )
      const main = container.querySelector('main')
      expect(main).not.toBeNull()
      expect(main!.getAttribute('data-node-id')).toBe('empty-children-page')
    })
  })

  describe('Error handling', () => {
    it('unknown component type throws error (fail closed)', () => {
      const unknownNode = {
        id: 'unknown-1',
        type: 'UnknownWidget',
        props: {},
      } as unknown as DslNode

      expect(() => {
        render(
          <DslRenderer node={unknownNode} selectedNodeId={null} onSelect={noop} />
        )
      }).toThrow('Unknown DSL node type: UnknownWidget')
    })
  })

  describe('Error Boundary integration', () => {
    it('ErrorBoundary catches unknown type and displays error message', () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => { /* suppress */ })
      const unknownNode = {
        id: 'unknown-eb',
        type: 'UnknownWidget',
        props: {},
      } as unknown as DslNode

      const { container } = render(
        <ErrorBoundary>
          <DslRenderer node={unknownNode} selectedNodeId={null} onSelect={noop} />
        </ErrorBoundary>
      )

      const errorDiv = container.querySelector('[data-testid="dsl-error-boundary"]')
      expect(errorDiv).not.toBeNull()
      expect(errorDiv!.textContent).toContain('Unknown DSL node type: UnknownWidget')
      consoleSpy.mockRestore()
    })

    it('ErrorBoundary does not interfere with valid rendering', () => {
      const textNode: TextNode = {
        id: 'valid-eb',
        type: 'Text',
        props: { text: 'Valid' },
      }
      const { container } = render(
        <ErrorBoundary>
          <DslRenderer node={textNode} selectedNodeId={null} onSelect={noop} />
        </ErrorBoundary>
      )
      const p = container.querySelector('p')
      expect(p).not.toBeNull()
      expect(p!.textContent).toBe('Valid')
      expect(container.querySelector('[data-testid="dsl-error-boundary"]')).toBeNull()
    })
  })

  describe('Gold Case rendering', () => {
    it('Gold Case can be fully rendered without errors', () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => { /* suppress */ })
      const { container } = render(
        <DslRenderer node={goldCase.root} selectedNodeId={null} onSelect={noop} />
      )
      // Should render without throwing
      expect(container.querySelector('main')).not.toBeNull()
      // Should contain expected structure elements
      expect(container.querySelector('[data-node-id="page"]')).not.toBeNull()
      expect(container.querySelector('[data-node-id="hero"]')).not.toBeNull()
      expect(container.querySelector('[data-node-id="menu"]')).not.toBeNull()
      expect(container.querySelector('[data-node-id="contact"]')).not.toBeNull()
      // No console.error should have been called
      expect(consoleSpy).not.toHaveBeenCalled()
      consoleSpy.mockRestore()
    })
  })

  describe('Security', () => {
    it('no dangerouslySetInnerHTML in rendered output', () => {
      const doc: DslDocument = {
        version: '0.1',
        root: {
          id: 'safe-page',
          type: 'Page',
          props: { title: 'Safe' },
          children: [
            { id: 'safe-text', type: 'Text', props: { text: '<script>alert("xss")</script>' } },
            { id: 'safe-heading', type: 'Heading', props: { text: '<img onerror=alert(1)>', level: 1 } },
          ],
        },
      }
      const { container } = render(
        <DslRenderer node={doc.root} selectedNodeId={null} onSelect={noop} />
      )
      // The dangerous content should be HTML-escaped, not rendered as real HTML elements
      // Check that no actual <script> element was created
      expect(container.querySelector('script')).toBeNull()
      // Check that no actual <img> element with onerror was injected by the heading text
      const headingImgs = container.querySelector('[data-node-id="safe-heading"] img')
      expect(headingImgs).toBeNull()
      // Text content should preserve the original string (as text, not HTML)
      const textEl = container.querySelector('[data-node-id="safe-text"]')!
      expect(textEl.textContent).toBe('<script>alert("xss")</script>')
      const headingEl = container.querySelector('[data-node-id="safe-heading"]')!
      expect(headingEl.textContent).toBe('<img onerror=alert(1)>')
    })
  })

  describe('Containers with omitted props and children (Schema 对齐)', () => {
    it('renders Page as <main> with omitted props and children', () => {
      const pageNode: PageNode = { id: 'bare-page', type: 'Page' }
      const { container } = render(
        <DslRenderer node={pageNode} selectedNodeId={null} onSelect={noop} />
      )
      const main = container.querySelector('main')
      expect(main).not.toBeNull()
      expect(main!.getAttribute('data-node-id')).toBe('bare-page')
      expect(main!.getAttribute('data-node-type')).toBe('Page')
      expect(main!.hasAttribute('aria-label')).toBe(false)
      expect(main!.children).toHaveLength(0)
    })

    it('renders Section as <section> with omitted props and children', () => {
      const sectionNode: SectionNode = { id: 'bare-section', type: 'Section' }
      const { container } = render(
        <DslRenderer node={sectionNode} selectedNodeId={null} onSelect={noop} />
      )
      const section = container.querySelector('section')
      expect(section).not.toBeNull()
      expect(section!.getAttribute('data-node-id')).toBe('bare-section')
      expect(section!.getAttribute('data-node-type')).toBe('Section')
      expect(section!.hasAttribute('aria-label')).toBe(false)
      expect(section!.children).toHaveLength(0)
    })

    it('renders Card as <article> with omitted props and children', () => {
      const cardNode: CardNode = { id: 'bare-card', type: 'Card' }
      const { container } = render(
        <DslRenderer node={cardNode} selectedNodeId={null} onSelect={noop} />
      )
      const article = container.querySelector('article')
      expect(article).not.toBeNull()
      expect(article!.getAttribute('data-node-id')).toBe('bare-card')
      expect(article!.getAttribute('data-node-type')).toBe('Card')
      expect(article!.hasAttribute('aria-label')).toBe(false)
      expect(article!.children).toHaveLength(0)
    })

    it('renders Form as <form> with omitted props and children', () => {
      const formNode: FormNode = { id: 'bare-form', type: 'Form' }
      const { container } = render(
        <DslRenderer node={formNode} selectedNodeId={null} onSelect={noop} />
      )
      const form = container.querySelector('form')
      expect(form).not.toBeNull()
      expect(form!.getAttribute('data-node-id')).toBe('bare-form')
      expect(form!.getAttribute('data-node-type')).toBe('Form')
      expect(form!.hasAttribute('name')).toBe(false)
      expect(form!.children).toHaveLength(0)
    })
  })

  describe('DslDocument metadata typing (Schema 对齐)', () => {
    it('accepts metadata with title and description', () => {
      const doc: DslDocument = {
        version: '0.1',
        root: { id: 'meta-page', type: 'Page' },
        metadata: { title: 'Doc Title', description: 'Doc Description' },
      }
      expect(doc.metadata?.title).toBe('Doc Title')
      expect(doc.metadata?.description).toBe('Doc Description')
    })

    it('accepts explicit null metadata', () => {
      const doc: DslDocument = {
        version: '0.1',
        root: { id: 'meta-null-page', type: 'Page' },
        metadata: null,
      }
      expect(doc.metadata).toBeNull()
    })

    it('accepts omitted metadata', () => {
      const doc: DslDocument = {
        version: '0.1',
        root: { id: 'meta-omitted-page', type: 'Page' },
      }
      expect(doc.metadata).toBeUndefined()
    })

    it('rejects arbitrary metadata fields at type level', () => {
      const doc: DslDocument = {
        version: '0.1',
        root: { id: 'meta-bad-page', type: 'Page' },
        metadata: {
          title: 'ok',
          // @ts-expect-error metadata 仅允许 title/description（Schema additionalProperties: false）
          arbitrary: 'not-allowed',
        },
      }
      expect(doc.version).toBe('0.1')
    })

    it('rejects null props on container nodes at type level', () => {
      // @ts-expect-error 容器 props 只允许省略，不允许 null（Schema 中无 null anyOf）
      const badPage: PageNode = { id: 'null-props-page', type: 'Page', props: null }
      expect(badPage.id).toBe('null-props-page')
    })
  })
})
