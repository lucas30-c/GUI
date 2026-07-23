// DSL v0.1 TypeScript types — mirrors backend/src/genui_api/contracts/dsl.py exactly

/** Style whitelist (11 fields only) */
export interface DslStyle {
  color?: string | null;
  backgroundColor?: string | null;
  fontSize?: string | null;
  fontWeight?: 'normal' | 'medium' | 'semibold' | 'bold' | null;
  textAlign?: 'left' | 'center' | 'right' | null;
  width?: string | null;
  height?: string | null;
  padding?: string | null;
  margin?: string | null;
  borderRadius?: string | null;
  gap?: string | null;
}

// Props for each component
export interface PageProps { title?: string | null; }
export interface SectionProps { ariaLabel?: string | null; }
export interface HeadingProps { text: string; level: 1 | 2 | 3 | 4 | 5 | 6; }
export interface TextProps { text: string; }
export interface ButtonProps { text: string; variant?: 'primary' | 'secondary' | 'ghost' | null; disabled?: boolean | null; }
export interface ImageProps { src: string; alt: string; }
export interface CardProps { title?: string | null; }
export interface FormProps { name?: string | null; }
export interface InputProps { name: string; label: string; inputType?: 'text' | 'email' | 'tel' | 'number' | null; placeholder?: string | null; required?: boolean | null; }

// Node types
// 容器节点 props 仅允许省略，不允许 null（对齐 Schema：props 不在 required 中，且无 null anyOf）
export interface PageNode { id: string; type: 'Page'; props?: PageProps; style?: DslStyle | null; children?: DslNode[]; }
export interface SectionNode { id: string; type: 'Section'; props?: SectionProps; style?: DslStyle | null; children?: DslNode[]; }
export interface HeadingNode { id: string; type: 'Heading'; props: HeadingProps; style?: DslStyle | null; }
export interface TextNode { id: string; type: 'Text'; props: TextProps; style?: DslStyle | null; }
export interface ButtonNode { id: string; type: 'Button'; props: ButtonProps; style?: DslStyle | null; }
export interface ImageNode { id: string; type: 'Image'; props: ImageProps; style?: DslStyle | null; }
export interface CardNode { id: string; type: 'Card'; props?: CardProps; style?: DslStyle | null; children?: DslNode[]; }
export interface FormNode { id: string; type: 'Form'; props?: FormProps; style?: DslStyle | null; children?: DslNode[]; }
export interface InputNode { id: string; type: 'Input'; props: InputProps; style?: DslStyle | null; }

export type DslNode = PageNode | SectionNode | HeadingNode | TextNode | ButtonNode | ImageNode | CardNode | FormNode | InputNode;

export type ContainerNode = PageNode | SectionNode | CardNode | FormNode;
export type LeafNode = HeadingNode | TextNode | ButtonNode | ImageNode | InputNode;

/** 文档元数据 — 仅允许预定义字段（对齐 Schema DslMetadata, additionalProperties: false） */
export interface DslMetadata {
  title?: string | null;
  description?: string | null;
}

export interface DslDocument {
  version: '0.1';
  root: PageNode;
  metadata?: DslMetadata | null;
}
