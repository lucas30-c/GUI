import { useReducer, useRef } from 'react';
import type { KeyboardEvent } from 'react';
import goldCaseRaw from '../../examples/dsl/coffee-shop-landing.json';
import { DslRenderer } from './dsl';
import { ErrorBoundary } from './dsl/ErrorBoundary';
import type { DslDocument, DslNode } from './dsl';
import { isDslDocumentShape, refineNode } from './api/refine';
import type { Fetcher } from './api/refine';
import type {
  PatchDocument,
  RefinementIntegrity,
  RefineLocalError,
  RefineServerError,
  VerifiedRefinementIntegrity,
} from './api/types';

/** instruction 前端长度上限，与后端对齐（DD-7） */
export const MAX_INSTRUCTION_LENGTH = 1000;

/** 提交层完整性检查失败文案（前端自有固定文案，不含服务端原文或 document 内容） */
export const INTEGRITY_ERROR_MESSAGES = {
  nonTargetChanged: '完整性校验未通过：响应未证明非目标区域零变更，本次结果已被拒绝。',
  nodeMismatch: '完整性校验未通过：响应的选中节点与本次提交不一致，本次结果已被拒绝。',
  nodeMissing: '完整性校验未通过：返回文档中找不到本次提交的选中节点，本次结果已被拒绝。',
} as const;

/** Gold Case 在单一边界上通过运行时守卫收窄，不使用类型断言 */
function loadGoldCase(raw: unknown): DslDocument {
  if (!isDslDocumentShape(raw)) {
    throw new Error('Gold Case 不符合 DSL Document 基本结构');
  }
  return raw;
}

const goldCase = loadGoldCase(goldCaseRaw);

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

/** C-5 类型守卫：只有运行时确认 `nonTargetNodesUnchanged === true` 才收窄为已验证完整性 */
function isVerifiedIntegrity(
  integrity: RefinementIntegrity,
): integrity is VerifiedRefinementIntegrity {
  return integrity.nonTargetNodesUnchanged === true;
}

interface RefinementState {
  currentDocument: DslDocument;
  selectedNodeId: string | null;
  lastPatch: PatchDocument | null;
  lastIntegrity: VerifiedRefinementIntegrity | null;
  lastSuccess: { selectedNodeId: string } | null;
  loading: boolean;
  error: RefineServerError | RefineLocalError | null;
  instruction: string;
}

type RefinementAction =
  | { type: 'SELECT_NODE'; nodeId: string }
  | { type: 'SET_INSTRUCTION'; instruction: string }
  | { type: 'REFINE_START' }
  | {
      type: 'REFINE_SUCCESS';
      document: DslDocument;
      patch: PatchDocument;
      integrity: VerifiedRefinementIntegrity;
      selectedNodeId: string;
    }
  | { type: 'REFINE_FAILURE'; error: RefineServerError | RefineLocalError }
  | { type: 'REFINE_END' };

const initialState: RefinementState = {
  currentDocument: goldCase,
  selectedNodeId: null,
  lastPatch: null,
  lastIntegrity: null,
  lastSuccess: null,
  loading: false,
  error: null,
  instruction: '',
};

function refinementReducer(
  state: RefinementState,
  action: RefinementAction,
): RefinementState {
  switch (action.type) {
    case 'SELECT_NODE':
      return { ...state, selectedNodeId: action.nodeId };

    case 'SET_INSTRUCTION':
      return { ...state, instruction: action.instruction };

    case 'REFINE_START':
      return { ...state, loading: true, error: null };

    // 唯一的成功提交入口：单次 dispatch 原子完成全部成功字段更新
    case 'REFINE_SUCCESS':
      return {
        ...state,
        currentDocument: action.document,
        selectedNodeId: action.selectedNodeId,
        lastPatch: action.patch,
        lastIntegrity: action.integrity,
        lastSuccess: { selectedNodeId: action.selectedNodeId },
        instruction: '',
        error: null,
      };

    // 结构上无法写入任何成功字段
    case 'REFINE_FAILURE':
      return { ...state, error: action.error };

    case 'REFINE_END':
      return { ...state, loading: false };
  }
}

function localFailure(message: string): RefineLocalError {
  return { kind: 'local', code: 'invalid_response', message };
}

interface AppProps {
  /** 测试可注入的 fetch 实现（DD-12）；未传时 API Client 使用全局 fetch */
  fetcher?: Fetcher;
}

function App({ fetcher }: AppProps) {
  const [state, dispatch] = useReducer(refinementReducer, initialState);
  // 始终同步最新选择的 ref：在选择的同一同步代码路径中写入，先于 dispatch
  const latestSelectedNodeIdRef = useRef<string | null>(null);
  // in-flight 守卫：保证同时只有一个精修请求（DD-22）
  const inFlightRef = useRef(false);

  const selectedNode = state.selectedNodeId
    ? findNodeById(state.currentDocument.root, state.selectedNodeId)
    : null;

  const trimmedInstruction = state.instruction.trim();
  const canSubmit =
    !state.loading &&
    state.selectedNodeId !== null &&
    trimmedInstruction.length > 0 &&
    state.instruction.length <= MAX_INSTRUCTION_LENGTH;

  function handleSelect(nodeId: string) {
    latestSelectedNodeIdRef.current = nodeId;
    dispatch({ type: 'SELECT_NODE', nodeId });
  }

  async function submitRefinement() {
    if (inFlightRef.current) return;

    // 步骤 1：捕获快照
    const snapshot = {
      document: state.currentDocument,
      selectedNodeId: state.selectedNodeId,
      instruction: state.instruction,
    };
    if (snapshot.selectedNodeId === null) return;
    if (snapshot.instruction.trim().length === 0) return;
    if (snapshot.instruction.length > MAX_INSTRUCTION_LENGTH) return;
    const snapshotSelectedNodeId = snapshot.selectedNodeId;

    // 步骤 2：REFINE_START
    inFlightRef.current = true;
    dispatch({ type: 'REFINE_START' });

    try {
      // 步骤 3：使用快照字段构造请求
      const result = await refineNode(
        {
          document: snapshot.document,
          selectedNodeId: snapshotSelectedNodeId,
          instruction: snapshot.instruction,
        },
        fetcher,
      );

      // 旧响应校验：快照选择与最新选择不一致时一律丢弃（不触碰任何成功状态）
      if (snapshotSelectedNodeId !== latestSelectedNodeIdRef.current) return;

      // 步骤 5：结果种类
      if (result.kind !== 'success') {
        dispatch({ type: 'REFINE_FAILURE', error: result });
        return;
      }

      // 步骤 6（C-5）
      const integrity = result.integrity;
      if (!isVerifiedIntegrity(integrity)) {
        dispatch({
          type: 'REFINE_FAILURE',
          error: localFailure(INTEGRITY_ERROR_MESSAGES.nonTargetChanged),
        });
        return;
      }

      // 步骤 7（C-6）
      if (integrity.selectedNodeId !== snapshotSelectedNodeId) {
        dispatch({
          type: 'REFINE_FAILURE',
          error: localFailure(INTEGRITY_ERROR_MESSAGES.nodeMismatch),
        });
        return;
      }

      // 步骤 8（C-7）
      if (findNodeById(result.document.root, snapshotSelectedNodeId) === null) {
        dispatch({
          type: 'REFINE_FAILURE',
          error: localFailure(INTEGRITY_ERROR_MESSAGES.nodeMissing),
        });
        return;
      }

      // 提交前最终竞态确认
      if (snapshotSelectedNodeId !== latestSelectedNodeIdRef.current) return;

      // 步骤 9：唯一成功提交入口
      dispatch({
        type: 'REFINE_SUCCESS',
        document: result.document,
        patch: result.patch,
        integrity,
        selectedNodeId: snapshotSelectedNodeId,
      });
    } finally {
      // 步骤 10
      inFlightRef.current = false;
      dispatch({ type: 'REFINE_END' });
    }
  }

  function handleSubmitClick() {
    if (!canSubmit) return;
    void submitRefinement();
  }

  function handleInstructionKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== 'Enter') return;
    // 单独 Enter 插入换行，不提交
    if (!event.ctrlKey && !event.metaKey) return;
    event.preventDefault();
    if (!canSubmit) return;
    void submitRefinement();
  }

  return (
    <div className="workbench">
      <header className="workbench-header">
        <h1>GenUI</h1>
        <span className="status">局部精修（Mock Provider）</span>
      </header>
      <div className="workbench-main">
        <div className="workbench-canvas">
          <ErrorBoundary>
            <DslRenderer
              node={state.currentDocument.root}
              selectedNodeId={state.selectedNodeId}
              onSelect={handleSelect}
            />
          </ErrorBoundary>
        </div>
        <aside className="workbench-panel">
          <h2>节点信息</h2>
          {selectedNode ? (
            <dl>
              <div className="panel-field">
                <dt>ID</dt>
                <dd data-testid="panel-node-id">{selectedNode.id}</dd>
              </div>
              <div className="panel-field">
                <dt>Type</dt>
                <dd data-testid="panel-node-type">{selectedNode.type}</dd>
              </div>
              <div className="panel-field">
                <dt>Props</dt>
                <dd className="panel-props" data-testid="panel-node-props">
                  {JSON.stringify(selectedNode.props ?? {}, null, 2)}
                </dd>
              </div>
            </dl>
          ) : (
            <p className="panel-hint">点击页面中的任意元素以选中</p>
          )}

          <section className="refine-section">
            <h2>精修操作</h2>
            <textarea
              className="refine-instruction"
              data-testid="refine-instruction"
              aria-label="精修指令"
              placeholder="例如：set_text:新的标题文案（Ctrl/Cmd + Enter 提交）"
              value={state.instruction}
              onChange={(event) =>
                dispatch({ type: 'SET_INSTRUCTION', instruction: event.target.value })
              }
              onKeyDown={handleInstructionKeyDown}
            />
            <p className="refine-counter" data-testid="refine-counter">
              {state.instruction.length} / {MAX_INSTRUCTION_LENGTH}
            </p>
            <button
              type="button"
              className="refine-submit"
              data-testid="refine-submit"
              disabled={!canSubmit}
              onClick={handleSubmitClick}
            >
              {state.loading ? '精修中...' : '提交精修'}
            </button>
            {state.loading ? (
              <p className="refine-loading" data-testid="refine-loading">
                精修中...
              </p>
            ) : null}
          </section>

          <section className="refine-section">
            <h2>结果</h2>
            {state.lastPatch === null && state.error === null ? (
              <p className="panel-hint" data-testid="refine-result-empty">
                尚无精修结果
              </p>
            ) : null}

            {state.lastPatch !== null ? (
              <div className="refine-result" data-testid="refine-patch">
                <p className="refine-label">Patch 操作</p>
                <ul className="refine-patch-list" data-testid="refine-patch-operations">
                  {state.lastPatch.operations.map((operation, index) => (
                    <li key={`${operation.targetNodeId}-${index}`} data-testid="refine-patch-operation">
                      <span data-testid="refine-patch-op">{operation.op}</span>
                      <span data-testid="refine-patch-target">{operation.targetNodeId}</span>
                      <pre data-testid="refine-patch-props">
                        {JSON.stringify(operation.props)}
                      </pre>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {state.lastIntegrity !== null ? (
              <div className="refine-result" data-testid="refine-integrity">
                <p className="refine-label">完整性证明</p>
                <p data-testid="refine-integrity-flag">
                  nonTargetNodesUnchanged: {String(state.lastIntegrity.nonTargetNodesUnchanged)}
                </p>
                <p data-testid="refine-integrity-node">
                  上一轮结果所属节点：{state.lastIntegrity.selectedNodeId}
                </p>
              </div>
            ) : null}

            {state.lastSuccess !== null ? (
              <p className="refine-owner" data-testid="refine-last-success">
                上一轮成功精修节点：{state.lastSuccess.selectedNodeId}
              </p>
            ) : null}

            {state.error !== null ? (
              <div className="refine-error" data-testid="refine-error">
                <p className="refine-label">精修失败</p>
                <p data-testid="refine-error-kind">
                  {state.error.kind === 'server' ? '服务端错误' : '本地错误'}
                </p>
                <p data-testid="refine-error-code">{state.error.code}</p>
                <p data-testid="refine-error-message">{state.error.message}</p>
                {state.error.kind === 'server' && state.error.issues.length > 0 ? (
                  <ul data-testid="refine-error-issues">
                    {state.error.issues.map((issue, index) => (
                      <li key={`${issue.path}-${index}`} data-testid="refine-error-issue">
                        {issue.path} · {issue.code} · {issue.message}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ) : null}
          </section>
        </aside>
      </div>
    </div>
  );
}

export default App;
