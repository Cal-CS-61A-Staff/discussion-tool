import { useEffect, useRef, useState } from 'react';
import CodeEditor from './CodeEditor.jsx';
import TestRunner from './TestRunner.jsx';

function storageKey(groupId, questionId, userId) {
  return `scratch:${groupId}:${questionId}:${userId}`;
}

export default function ScratchEditor({
  groupId,
  worksheetId,
  questionId,
  userId,
  starterCode,
  predictCall,
  graderCooldown,
}) {
  const [code, setCode] = useState('');
  const debounceRef = useRef(null);
  const loadedKeyRef = useRef(null);

  // Load (or seed from starterCode) whenever the question changes; save is
  // debounced to localStorage on every edit, keyed per group+question+user
  // so it never touches the shared group state other members see.
  useEffect(() => {
    const key = storageKey(groupId, questionId, userId);
    if (loadedKeyRef.current === key) return;
    loadedKeyRef.current = key;
    const saved = window.localStorage.getItem(key);
    setCode(saved !== null ? saved : starterCode || '');
  }, [groupId, questionId, userId, starterCode]);

  const handleChange = (value) => {
    setCode(value);
    clearTimeout(debounceRef.current);
    const key = storageKey(groupId, questionId, userId);
    debounceRef.current = setTimeout(() => {
      window.localStorage.setItem(key, value);
    }, 400);
  };

  return (
    <div className="panel" style={{ marginTop: 16 }}>
      <div className="panel-heading">
        <h4>Your scratch work</h4>
        <span style={{ fontSize: 11, color: 'var(--muted)' }}>private — not shared with your group</span>
      </div>
      <div className="panel-body">
        <p style={{ fontSize: 13, color: 'var(--muted)', marginTop: 0 }}>
          Not the typist right now? Use this space to try things out on your own — it's only visible to you, and
          you can run it against the tests independently.
        </p>
        <CodeEditor code={code} readOnly={false} onChange={handleChange} editorLabel="scratch" />
        <TestRunner
          groupId={groupId}
          worksheetId={worksheetId}
          source="scratch"
          code={code}
          predictCall={predictCall}
          label="Run tests on my scratch code"
          graderCooldown={graderCooldown}
        />
      </div>
    </div>
  );
}
