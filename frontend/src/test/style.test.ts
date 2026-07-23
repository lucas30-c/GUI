import { describe, it, expect } from 'vitest'
import { mapDslStyle } from '../dsl/style'
import type { DslStyle } from '../dsl/types'

describe('mapDslStyle', () => {
  it('returns empty object for undefined input', () => {
    const result = mapDslStyle(undefined)
    expect(result).toEqual({})
  })

  it('maps color correctly', () => {
    const style: DslStyle = { color: '#ff0000' }
    const result = mapDslStyle(style)
    expect(result.color).toBe('#ff0000')
  })

  it('maps backgroundColor correctly', () => {
    const style: DslStyle = { backgroundColor: '#00ff00' }
    const result = mapDslStyle(style)
    expect(result.backgroundColor).toBe('#00ff00')
  })

  it('maps fontSize correctly', () => {
    const style: DslStyle = { fontSize: '16px' }
    const result = mapDslStyle(style)
    expect(result.fontSize).toBe('16px')
  })

  it('maps fontWeight correctly', () => {
    const style: DslStyle = { fontWeight: 'bold' }
    const result = mapDslStyle(style)
    expect(result.fontWeight).toBe('bold')
  })

  it('maps textAlign correctly', () => {
    const style: DslStyle = { textAlign: 'center' }
    const result = mapDslStyle(style)
    expect(result.textAlign).toBe('center')
  })

  it('maps width and height correctly', () => {
    const style: DslStyle = { width: '100%', height: '200px' }
    const result = mapDslStyle(style)
    expect(result.width).toBe('100%')
    expect(result.height).toBe('200px')
  })

  it('maps padding and margin correctly', () => {
    const style: DslStyle = { padding: '8px', margin: '16px' }
    const result = mapDslStyle(style)
    expect(result.padding).toBe('8px')
    expect(result.margin).toBe('16px')
  })

  it('maps borderRadius correctly', () => {
    const style: DslStyle = { borderRadius: '4px' }
    const result = mapDslStyle(style)
    expect(result.borderRadius).toBe('4px')
  })

  it('maps gap correctly', () => {
    const style: DslStyle = { gap: '12px' }
    const result = mapDslStyle(style)
    expect(result.gap).toBe('12px')
  })

  it('maps all 11 whitelist fields together', () => {
    const style: DslStyle = {
      color: '#000',
      backgroundColor: '#fff',
      fontSize: '14px',
      fontWeight: 'semibold',
      textAlign: 'right',
      width: '50%',
      height: '100px',
      padding: '10px',
      margin: '20px',
      borderRadius: '6px',
      gap: '8px',
    }
    const result = mapDslStyle(style)
    expect(Object.keys(result)).toHaveLength(11)
    expect(result.color).toBe('#000')
    expect(result.backgroundColor).toBe('#fff')
    expect(result.fontSize).toBe('14px')
    expect(result.fontWeight).toBe('semibold')
    expect(result.textAlign).toBe('right')
    expect(result.width).toBe('50%')
    expect(result.height).toBe('100px')
    expect(result.padding).toBe('10px')
    expect(result.margin).toBe('20px')
    expect(result.borderRadius).toBe('6px')
    expect(result.gap).toBe('8px')
  })

  it('does NOT include unknown fields', () => {
    const style = { color: 'red', display: 'flex', position: 'absolute' } as unknown as DslStyle
    const result = mapDslStyle(style)
    expect(result.color).toBe('red')
    expect('display' in result).toBe(false)
    expect('position' in result).toBe(false)
  })

  it('does NOT include undefined values', () => {
    const style: DslStyle = { color: undefined, fontSize: '12px' }
    const result = mapDslStyle(style)
    expect('color' in result).toBe(false)
    expect(result.fontSize).toBe('12px')
  })

  it('does not mutate input', () => {
    const style: DslStyle = { color: '#333', padding: '4px' }
    const originalStyle = { ...style }
    mapDslStyle(style)
    expect(style).toEqual(originalStyle)
  })
})
