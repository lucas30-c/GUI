import { useReducer, useRef } from 'react';
import type { KeyboardEvent } from 'react';
import goldCaseRaw from '../../examples/dsl/coffee-shop-landing.json';
import { DslRenderer } from './dsl';
import { ErrorBoundary } from './dsl/ErrorBoundary';
import type { DslDocument, DslNode } from './dsl';
import { isDslDocumentShape, refineNode } from './api/refine';
import type { Fetcher } from './api/refine';
import { generateDraft } from './api/generate';
import type {
  ConfirmedTurn,
  GenerateLocalError,
  GenerateServerError,
  PatchDocument,
  PatchPropValue,
  RefinementIntegrity,
  RefineLocalError,
  RefineServerError,
  VerifiedRefinementIntegrity,
} from './api/types';

/** instruction 前端长度上限，与后端对齐（DD-7） */
export const MAX_INSTRUCTION_LENGTH = 1000;

/** prompt 前端长度上限，与后端 MAX_PROMPT_LENGTH 同值（DD-5@007） */
export const MAX_PROMPT_LENGTH = 500;

/** 已确认对话历史轮数上限；后端 provider/base.py 的 MAX_HISTORY_TURNS 是唯一事实来源，
 *  本常量是其镜像，一致性由后端漂移测试守护（DD-21@009） */
export const MAX_HISTORY_TURNS = 20;

/** 单轮 patchProps 键数上限，与后端 MAX_TURN_PROPS_KEYS 同值（DD-13@009） */
export const MAX_TURN_PROPS_KEYS = 16;

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

/** patchProps 值域守卫：只有 JSON 标量能进入 history（DD-17 的净化规则） */
function isPatchPropValue(value: unknown): value is PatchPropValue {
  return (
    value === null ||
    typeof value === 'string' ||
    typeof value === 'number' ||
    typeof value === 'boolean'
  );
}

/**
 * 由已通过完整性校验的响应 patch 确定性派生 `patchProps`（DD-17）：
 * 只取 `targetNodeId` 等于本次提交节点的操作 → 按数组顺序浅合并 → 丢弃非标量值
 * → 键数超过 16 时按插入顺序保留前 16 个。
 *
 * 净化使「下一轮请求必然满足后端 schema」成为前端可自证的性质。
 */
export function derivePatchProps(
  patch: PatchDocument,
  selectedNodeId: string,
): Record<string, PatchPropValue> {
  const merged: Record<string, PatchPropValue> = {};
  for (const operation of patch.operations) {
    if (operation.targetNodeId !== selectedNodeId) continue;
    for (const [key, value] of Object.entries(operation.props)) {
      if (!isPatchPropValue(value)) continue;
      merged[key] = value;
    }
  }
  const entries = Object.entries(merged);
  if (entries.length <= MAX_TURN_PROPS_KEYS) return merged;
  const capped: Record<string, PatchPropValue> = {};
  for (const [key, value] of entries.slice(0, MAX_TURN_PROPS_KEYS)) {
    capped[key] = value;
  }
  return capped;
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
  /** 已确认对话历史（oldest → newest）；**不是**状态事实来源（CS-1@009） */
  conversationHistory: ConfirmedTurn[];
  // --- 生成侧状态（与精修侧 loading / error 分离，DD-17） ---
  prompt: string;
  generateLoading: boolean;
  generateError: GenerateServerError | GenerateLocalError | null;
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
      turn: ConfirmedTurn;
    }
  | { type: 'REFINE_FAILURE'; error: RefineServerError | RefineLocalError }
  | { type: 'REFINE_END' }
  | { type: 'SET_PROMPT'; prompt: string }
  | { type: 'GENERATE_START' }
  | { type: 'GENERATE_SUCCESS'; document: DslDocument }
  | { type: 'GENERATE_FAILURE'; error: GenerateServerError | GenerateLocalError }
  | { type: 'GENERATE_END' };

const initialState: RefinementState = {
  currentDocument: goldCase,
  selectedNodeId: null,
  lastPatch: null,
  lastIntegrity: null,
  lastSuccess: null,
  loading: false,
  error: null,
  instruction: '',
  conversationHistory: [],
  prompt: '',
  generateLoading: false,
  generateError: null,
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
    // history 入队与文档替换在同一次 dispatch 中完成 → 不存在两者不一致的中间态（CS-3@009）
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
        conversationHistory: [...state.conversationHistory, action.turn].slice(
          -MAX_HISTORY_TURNS,
        ),
      };

    // 结构上无法写入任何成功字段
    case 'REFINE_FAILURE':
      return { ...state, error: action.error };

    case 'REFINE_END':
      return { ...state, loading: false };

    case 'SET_PROMPT':
      return { ...state, prompt: action.prompt };

    case 'GENERATE_START':
      return { ...state, generateLoading: true, generateError: null };

    // 唯一的初稿提交入口：单次 dispatch 原子设置 9 项（DD-18）
    // 新文档意味着新对话：历史轮次全部指向旧文档的节点，必须清空（DD-6@009）
    case 'GENERATE_SUCCESS': {
      const generatedDocument = action.document;
      return {
        ...state,
        currentDocument: generatedDocument,
        selectedNodeId: null,
        lastPatch: null,
        lastIntegrity: null,
        lastSuccess: null,
        error: null,
        instruction: '',
        prompt: '',
        generateError: null,
        conversationHistory: [],
      };
    }

    // 结构上只触碰 generateError：旧文档与精修成功状态一律不被污染
    case 'GENERATE_FAILURE':
      return { ...state, generateError: action.error };

    case 'GENERATE_END':
      return { ...state, generateLoading: false };
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
  // 生成侧 in-flight 守卫：与 inFlightRef 共同构成双同步互斥事实来源（DD-20）
  const generateInFlightRef = useRef(false);

  const selectedNode = state.selectedNodeId
    ? findNodeById(state.currentDocument.root, state.selectedNodeId)
    : null;

  const trimmedInstruction = state.instruction.trim();
  const canSubmit =
    !state.loading &&
    !state.generateLoading &&
    state.selectedNodeId !== null &&
    trimmedInstruction.length > 0 &&
    state.instruction.length <= MAX_INSTRUCTION_LENGTH;

  const trimmedPrompt = state.prompt.trim();
  const canGenerate =
    !state.generateLoading &&
    !state.loading &&
    trimmedPrompt.length > 0 &&
    trimmedPrompt.length <= MAX_PROMPT_LENGTH;

  function handleSelect(nodeId: string) {
    latestSelectedNodeIdRef.current = nodeId;
    dispatch({ type: 'SELECT_NODE', nodeId });
  }

  async function submitRefinement() {
    if (inFlightRef.current) return;
    // 跨链路同步互斥：生成在途时禁止精修提交（DD-20）
    if (generateInFlightRef.current) return;

    // 步骤 1：捕获快照（history 与 nodeType 与其余字段在同一快照中捕获）
    const snapshot = {
      document: state.currentDocument,
      selectedNodeId: state.selectedNodeId,
      instruction: state.instruction,
      history: state.conversationHistory.slice(-MAX_HISTORY_TURNS),
    };
    if (snapshot.selectedNodeId === null) return;
    if (snapshot.instruction.trim().length === 0) return;
    if (snapshot.instruction.length > MAX_INSTRUCTION_LENGTH) return;
    const snapshotSelectedNodeId = snapshot.selectedNodeId;
    // nodeType 取**快照文档**而非响应（延续「响应一律不可信」口径）；解析不到则不发请求（DD-17@009）
    const snapshotNode = findNodeById(snapshot.document.root, snapshotSelectedNodeId);
    if (snapshotNode === null) return;
    const snapshotNodeType = snapshotNode.type;

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
          history: snapshot.history,
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

      // 步骤 9：由快照 + 已校验响应 patch 确定性派生 turn，随成功提交一次 dispatch
      const turn: ConfirmedTurn = {
        instruction: snapshot.instruction,
        selectedNodeId: snapshotSelectedNodeId,
        nodeType: snapshotNodeType,
        patchProps: derivePatchProps(result.patch, snapshotSelectedNodeId),
      };
      dispatch({
        type: 'REFINE_SUCCESS',
        document: result.document,
        patch: result.patch,
        integrity,
        selectedNodeId: snapshotSelectedNodeId,
        turn,
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

  /** 生成提交固定 7 步（Spec 007「生成提交过程」） */
  async function submitGeneration() {
    // 步骤 1：同步守卫（事实来源是 ref，不是 state）
    if (generateInFlightRef.current) return;
    if (inFlightRef.current) return;
    const prompt = state.prompt.trim();
    if (prompt.length === 0) return;
    if (prompt.length > MAX_PROMPT_LENGTH) return;

    // 步骤 2：先设置生成侧 in-flight ref
    generateInFlightRef.current = true;
    // 步骤 3：后 dispatch START
    dispatch({ type: 'GENERATE_START' });

    try {
      // 步骤 4：发送 trim 后的 prompt
      const result = await generateDraft({ prompt }, fetcher);

      // 步骤 6：失败（server / local）只更新生成侧错误
      if (result.kind !== 'success') {
        dispatch({ type: 'GENERATE_FAILURE', error: result });
        return;
      }

      // 步骤 5：同一同步路径中先重置选择 ref（DD-19），再原子提交
      latestSelectedNodeIdRef.current = null;
      dispatch({ type: 'GENERATE_SUCCESS', document: result.document });
    } finally {
      // 步骤 7：释放 ref 并结束 loading
      generateInFlightRef.current = false;
      dispatch({ type: 'GENERATE_END' });
    }
  }

  function handleGenerateClick() {
    if (!canGenerate) return;
    void submitGeneration();
  }

  function handlePromptKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key !== 'Enter') return;
    event.preventDefault();
    if (!canGenerate) return;
    void submitGeneration();
  }

  return (
    <div className="workbench">
      <header className="workbench-header">
        <h1>GenUI</h1>
        <span className="status">初稿生成 + 局部精修（Mock Provider）</span>
      </header>
      <section className="generate-bar">
        <div className="generate-row">
          <input
            type="text"
            className="generate-prompt"
            data-testid="generate-prompt"
            aria-label="初稿需求"
            placeholder="用一句话描述你要的网页，例如：我要一个咖啡店的落地页（Enter 提交）"
            value={state.prompt}
            onChange={(event) =>
              dispatch({ type: 'SET_PROMPT', prompt: event.target.value })
            }
            onKeyDown={handlePromptKeyDown}
          />
          <button
            type="button"
            className="generate-submit"
            data-testid="generate-submit"
            disabled={!canGenerate}
            onClick={handleGenerateClick}
          >
            {state.generateLoading ? '生成中...' : '生成初稿'}
          </button>
        </div>
        <p className="generate-counter" data-testid="generate-counter">
          {state.prompt.length} / {MAX_PROMPT_LENGTH}
        </p>
        {state.generateLoading ? (
          <p className="generate-loading" data-testid="generate-loading">
            生成中...
          </p>
        ) : null}
        {state.generateError !== null ? (
          <div className="generate-error" data-testid="generate-error">
            <p className="refine-label">初稿生成失败</p>
            <p data-testid="generate-error-kind">
              {state.generateError.kind === 'server' ? '服务端错误' : '本地错误'}
            </p>
            <p data-testid="generate-error-code">{state.generateError.code}</p>
            <p data-testid="generate-error-message">{state.generateError.message}</p>
            {state.generateError.kind === 'server' &&
            state.generateError.issues.length > 0 ? (
              <ul data-testid="generate-error-issues">
                {state.generateError.issues.map((issue, index) => (
                  <li key={`${issue.path}-${index}`} data-testid="generate-error-issue">
                    {issue.path} · {issue.code} · {issue.message}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
      </section>
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
            <h2>对话上下文</h2>
            <p className="refine-history-count" data-testid="refine-history-count">
              已确认轮次：{state.conversationHistory.length} / {MAX_HISTORY_TURNS}
            </p>
            {state.conversationHistory.length === 0 ? (
              <p className="panel-hint" data-testid="refine-history-empty">
                尚无已确认轮次
              </p>
            ) : (
              <ol className="refine-history-list" data-testid="refine-history-list">
                {state.conversationHistory.map((turn, index) => (
                  <li
                    key={`${turn.selectedNodeId}-${index}`}
                    data-testid="refine-history-item"
                  >
                    {index + 1} · {turn.selectedNodeId} · {turn.instruction}
                  </li>
                ))}
              </ol>
            )}
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
