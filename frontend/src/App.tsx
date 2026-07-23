import { useState } from 'react';
import goldCaseRaw from '../../examples/dsl/coffee-shop-landing.json';
import { DslRenderer } from './dsl';
import { ErrorBoundary } from './dsl/ErrorBoundary';
import type { DslDocument, DslNode } from './dsl';

// Single explicit type boundary for pre-validated Gold Case
const goldCase = goldCaseRaw as unknown as DslDocument;

function findNodeById(node: DslNode, id: string): DslNode | null {
  if (node.id === id) return node;
  if ('children' in node && node.children) {
    for (const child of node.children) {
      const found = findNodeById(child, id);
      if (found) return found;
    }
  }
  return null;
}

function App() {
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  const selectedNode = selectedNodeId
    ? findNodeById(goldCase.root, selectedNodeId)
    : null;

  return (
    <div className="workbench">
      <header className="workbench-header">
        <h1>GenUI</h1>
        <span className="status">静态 DSL 预览</span>
      </header>
      <div className="workbench-main">
        <div className="workbench-canvas">
          <ErrorBoundary>
            <DslRenderer
              node={goldCase.root}
              selectedNodeId={selectedNodeId}
              onSelect={setSelectedNodeId}
            />
          </ErrorBoundary>
        </div>
        <aside className="workbench-panel">
          <h2>节点信息</h2>
          {selectedNode ? (
            <dl>
              <div className="panel-field">
                <dt>ID</dt>
                <dd>{selectedNode.id}</dd>
              </div>
              <div className="panel-field">
                <dt>Type</dt>
                <dd>{selectedNode.type}</dd>
              </div>
              <div className="panel-field">
                <dt>Props</dt>
                <dd className="panel-props">
                  {JSON.stringify(selectedNode.props ?? {}, null, 2)}
                </dd>
              </div>
            </dl>
          ) : (
            <p className="panel-hint">点击页面中的任意元素以选中</p>
          )}
        </aside>
      </div>
    </div>
  );
}

export default App;
