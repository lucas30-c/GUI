import { useState } from 'react';
import type { CSSProperties, FormEvent, KeyboardEvent, MouseEvent } from 'react';
import type { DslNode } from './types';
import { mapDslStyle } from './style';

interface DslRendererProps {
  node: DslNode;
  selectedNodeId: string | null;
  onSelect: (nodeId: string) => void;
}

function DslImage({ commonProps, src, alt }: {
  commonProps: Record<string, unknown>;
  src: string;
  alt: string;
}) {
  const [failed, setFailed] = useState(false);

  if (failed) {
    return (
      <div
        {...commonProps}
        role="img"
        aria-label={alt}
        style={{
          ...(commonProps.style as CSSProperties),
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          backgroundColor: '#f3f4f6',
          color: '#9ca3af',
          fontSize: '14px',
          minHeight: '120px',
        }}
      >
        <span>{alt || '图片加载失败'}</span>
      </div>
    );
  }

  return (
    <img
      {...commonProps}
      src={src}
      alt={alt}
      onError={() => setFailed(true)}
    />
  );
}

export function DslRenderer({ node, selectedNodeId, onSelect }: DslRendererProps) {
  const isSelected = node.id === selectedNodeId;

  const handleClick = (e: MouseEvent) => {
    e.stopPropagation();
    onSelect(node.id);
  };

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      e.stopPropagation();
      onSelect(node.id);
    }
  };

  const baseStyle: CSSProperties = {
    ...mapDslStyle(node.style ?? undefined),
    ...(isSelected ? { outline: '2px solid #2563eb', outlineOffset: '2px' } : {}),
  };

  const commonProps = {
    'data-node-id': node.id,
    'data-node-type': node.type,
    tabIndex: 0,
    'data-selected': isSelected || undefined,
    'aria-current': isSelected ? 'true' as const : undefined,
    onClick: handleClick,
    onKeyDown: handleKeyDown,
    style: baseStyle,
    className: isSelected ? 'dsl-node-selected' : undefined,
  };

  function renderChildren(children?: DslNode[]) {
    if (!children) return null;
    return children.map((child) => (
      <DslRenderer
        key={child.id}
        node={child}
        selectedNodeId={selectedNodeId}
        onSelect={onSelect}
      />
    ));
  }

  switch (node.type) {
    case 'Page':
      return (
        <main {...commonProps} aria-label={node.props?.title ?? undefined}>
          {renderChildren(node.children)}
        </main>
      );

    case 'Section':
      return (
        <section {...commonProps} aria-label={node.props?.ariaLabel ?? undefined}>
          {renderChildren(node.children)}
        </section>
      );

    case 'Heading': {
      const Tag = `h${node.props.level}` as const;
      return <Tag {...commonProps}>{node.props.text}</Tag>;
    }

    case 'Text':
      return <p {...commonProps}>{node.props.text}</p>;

    case 'Button':
      return (
        <button
          {...commonProps}
          type="button"
          className={[isSelected ? 'dsl-node-selected' : '', `btn-${node.props.variant ?? 'secondary'}`].filter(Boolean).join(' ') || undefined}
          aria-disabled={node.props.disabled || undefined}
        >
          {node.props.text}
        </button>
      );

    case 'Image':
      return <DslImage commonProps={commonProps} src={node.props.src} alt={node.props.alt} />;

    case 'Card':
      return (
        <article {...commonProps} aria-label={node.props?.title ?? undefined}>
          {renderChildren(node.children)}
        </article>
      );

    case 'Form': {
      const handleSubmit = (e: FormEvent) => { e.preventDefault(); };
      return (
        <form {...commonProps} name={node.props?.name ?? undefined} onSubmit={handleSubmit}>
          {renderChildren(node.children)}
        </form>
      );
    }

    case 'Input':
      return (
        <label {...commonProps}>
          {node.props.label}
          <input
            name={node.props.name}
            type={node.props.inputType ?? undefined}
            placeholder={node.props.placeholder ?? undefined}
            required={node.props.required ?? undefined}
          />
        </label>
      );

    default: {
      const _exhaustive: never = node;
      throw new Error(`Unknown DSL node type: ${(_exhaustive as DslNode).type}`);
    }
  }
}
