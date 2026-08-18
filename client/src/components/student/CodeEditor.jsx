import { python } from '@codemirror/lang-python';
import CodeMirror from '@uiw/react-codemirror';

export default function CodeEditor({ code, readOnly, onChange, editorLabel }) {
  return (
    <div className="code-editor-wrap">
      <div className="editor-locked-badge">{editorLabel}</div>
      <CodeMirror
        value={code}
        theme="dark"
        extensions={[python()]}
        editable={!readOnly}
        onChange={onChange}
        basicSetup={{ lineNumbers: true, foldGutter: false }}
      />
    </div>
  );
}
