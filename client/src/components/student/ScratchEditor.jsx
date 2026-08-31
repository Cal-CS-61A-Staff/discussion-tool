import { useRef, useState } from 'react';
import CodeEditor from './CodeEditor.jsx';
import TestRunner from './TestRunner.jsx';
import { updateScratchCode } from '../../api/groups.js';

export default function ScratchEditor({
  groupId,
  worksheetId,
  initialCode,
  starterCode,
  predictCall,
  graderCooldown,
  isIndividual,
}) {
  const [code, setCode] = useState(initialCode || starterCode || '');
  const [saveStatus, setSaveStatus] = useState('idle');
  const debounceRef = useRef(null);

  // Persisted server-side (ScratchCode) rather than only in browser
  // localStorage, so it's still visible later — on the History page, or
  // when browsing back to an earlier unlocked question mid-assignment.
  const handleChange = (value) => {
    setCode(value);
    setSaveStatus('saving');
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      try {
        await updateScratchCode(groupId, worksheetId, value);
        setSaveStatus('saved');
      } catch {
        setSaveStatus('error');
      }
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
          {isIndividual
            ? "Not the typist right now? Use this space to try things out on your own. It's only visible to you."
            : "Not the typist right now? Use this space to try things out on your own. It's only visible to you."}
        </p>
        <CodeEditor code={code} readOnly={false} onChange={handleChange} editorLabel="scratch" />
        {saveStatus !== 'idle' && (
          <p style={{ fontSize: 11, color: 'var(--muted)', margin: '4px 0 0' }}>
            {saveStatus === 'saving' && 'Saving…'}
            {saveStatus === 'saved' && '✓ Saved'}
            {saveStatus === 'error' && "⚠ Couldn't save — check your connection"}
          </p>
        )}
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
