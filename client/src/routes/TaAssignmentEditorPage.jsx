import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import CodeEditor from '../components/student/CodeEditor.jsx';
import MarkdownContent from '../components/student/MarkdownContent.jsx';
import * as adminApi from '../api/admin.js';

const NEW_SLIDE_ID = 'new';

const GRADING_MODE_OPTIONS = [
  { value: 'simple', label: 'Simple (call → expected value)' },
  { value: 'doctest', label: 'Doctest (docstring >>> examples)' },
  { value: 'pltest', label: 'Custom test code' },
  { value: 'discussion', label: 'Discussion (no code)' },
];

const blankForm = {
  title: '',
  gradingMode: 'simple',
  prompt: '',
  starterCode: '',
  setupCode: '',
  referenceSolution: '',
  testCode: '',
  solutionMarkdown: '',
};

export default function TaAssignmentEditorPage() {
  const { worksheetId } = useParams();
  const navigate = useNavigate();

  const [worksheet, setWorksheet] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [form, setForm] = useState(blankForm);
  const [testCases, setTestCases] = useState([{ call: '', expected: '' }]);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState('');
  const [failingCases, setFailingCases] = useState(null);

  const [dragIndex, setDragIndex] = useState(null);
  const [deletingId, setDeletingId] = useState(null);
  const [reordering, setReordering] = useState(false);

  const [detailsTitle, setDetailsTitle] = useState('');
  const [detailsDescription, setDetailsDescription] = useState('');
  const [detailsPublished, setDetailsPublished] = useState(false);
  const [savingDetails, setSavingDetails] = useState(false);

  const load = () => {
    setLoading(true);
    Promise.all([adminApi.getWorksheet(worksheetId), adminApi.listQuestions(worksheetId)])
      .then(([worksheetRes, questionsRes]) => {
        const found = worksheetRes.worksheet;
        setWorksheet(found || null);
        if (found) {
          setDetailsTitle(found.title);
          setDetailsDescription(found.description || '');
          setDetailsPublished(found.is_published);
        }
        setQuestions(questionsRes.questions);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [worksheetId]);

  useEffect(() => {
    if (selectedId === null) {
      setSelectedId(questions.length > 0 ? questions[0].id : NEW_SLIDE_ID);
    }
  }, [questions, selectedId]);

  useEffect(() => {
    setSaveError('');
    setFailingCases(null);
    if (selectedId === NEW_SLIDE_ID) {
      setForm(blankForm);
      setTestCases([{ call: '', expected: '' }]);
      return;
    }
    const q = questions.find((q) => q.id === selectedId);
    if (!q) return;
    setForm({
      title: q.title,
      gradingMode: q.grading_mode || 'simple',
      prompt: q.prompt,
      starterCode: q.starter_code || '',
      setupCode: q.setup_code || '',
      referenceSolution: q.reference_solution || '',
      testCode: q.test_code || '',
      solutionMarkdown: q.solution_markdown || '',
    });
    setTestCases(q.test_cases && q.test_cases.length ? q.test_cases : [{ call: '', expected: '' }]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  const updateCase = (i, field, value) => {
    setTestCases((cases) => cases.map((c, idx) => (idx === i ? { ...c, [field]: value } : c)));
  };
  const addCase = () => setTestCases((cases) => [...cases, { call: '', expected: '' }]);
  const removeCase = (i) => setTestCases((cases) => cases.filter((_, idx) => idx !== i));

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    setSaveError('');
    setFailingCases(null);
    const payload = {
      title: form.title.trim(),
      grading_mode: form.gradingMode,
      prompt: form.prompt,
      starter_code: form.starterCode,
      setup_code: form.setupCode,
      reference_solution: form.referenceSolution,
      test_code: form.testCode,
      solution_markdown: form.solutionMarkdown,
      test_cases: testCases
        .map((c) => ({ call: c.call.trim(), expected: c.expected.trim() }))
        .filter((c) => c.call && c.expected),
    };
    try {
      const res =
        selectedId === NEW_SLIDE_ID
          ? await adminApi.createQuestion(worksheetId, payload)
          : await adminApi.updateQuestion(selectedId, payload);
      const savedId = res.question.id;
      load();
      setSelectedId(savedId);
    } catch (err) {
      setSaveError(err.message);
      if (err.data?.failing_cases) setFailingCases(err.data.failing_cases);
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteQuestion = async (q) => {
    if (!window.confirm(`Delete "${q.title}"?`)) return;
    setError('');
    setDeletingId(q.id);
    try {
      await adminApi.deleteQuestion(q.id);
      if (selectedId === q.id) setSelectedId(null);
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setDeletingId(null);
    }
  };

  const handleDrop = async (dropIndex) => {
    if (dragIndex === null || dragIndex === dropIndex) {
      setDragIndex(null);
      return;
    }
    const reordered = [...questions];
    const [moved] = reordered.splice(dragIndex, 1);
    reordered.splice(dropIndex, 0, moved);
    setQuestions(reordered);
    setDragIndex(null);
    setReordering(true);
    try {
      await adminApi.reorderQuestions(worksheetId, reordered.map((q) => q.id));
    } catch (err) {
      setError(err.message);
      load();
    } finally {
      setReordering(false);
    }
  };

  const handleSaveDetails = async (e) => {
    e.preventDefault();
    setSavingDetails(true);
    setError('');
    try {
      await adminApi.updateWorksheet(worksheetId, {
        title: detailsTitle.trim(),
        description: detailsDescription.trim(),
        is_published: detailsPublished,
      });
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setSavingDetails(false);
    }
  };

  if (loading) return <div className="page-loading">Loading…</div>;

  return (
    <div>
      <div className="breadcrumb-row">
        <a
          href="/"
          onClick={(e) => {
            e.preventDefault();
            navigate('/assignments');
          }}
        >
          ← Back to assignments
        </a>
      </div>
      <div className="page-header-row">
        <h1>Edit — {worksheet?.title}</h1>
        <p>Each question is a slide — pick one on the left, edit it in the middle, preview what students see on the right. Drag to reorder.</p>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      <div className="panel">
        <div className="panel-heading">
          <h4>Assignment details</h4>
        </div>
        <div className="panel-body">
          <form onSubmit={handleSaveDetails} style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}>
            <div className="form-group" style={{ flex: '2 1 220px', marginBottom: 0 }}>
              <label htmlFor="detailsTitle">Title</label>
              <input
                id="detailsTitle"
                className="form-control"
                value={detailsTitle}
                onChange={(e) => setDetailsTitle(e.target.value)}
                required
              />
            </div>
            <div className="form-group" style={{ flex: '3 1 260px', marginBottom: 0 }}>
              <label htmlFor="detailsDescription">Description</label>
              <input
                id="detailsDescription"
                className="form-control"
                value={detailsDescription}
                onChange={(e) => setDetailsDescription(e.target.value)}
              />
            </div>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, marginBottom: 9 }}>
              <input
                type="checkbox"
                checked={detailsPublished}
                onChange={(e) => setDetailsPublished(e.target.checked)}
              />
              Released to students
            </label>
            <button className="btn" type="submit" disabled={savingDetails}>
              {savingDetails ? 'Saving…' : 'Save details'}
            </button>
          </form>
        </div>
      </div>

      <div className="editor-columns">
        <div className="editor-slide-rail">
          <button
            type="button"
            className="btn btn-sm btn-primary"
            style={{ width: '100%', marginBottom: 10 }}
            onClick={() => setSelectedId(NEW_SLIDE_ID)}
            disabled={selectedId === NEW_SLIDE_ID}
          >
            + Add question
          </button>
          {reordering && (
            <p style={{ fontSize: 11, color: 'var(--muted)', margin: '0 0 6px' }}>Saving order…</p>
          )}
          {questions.map((q, i) => (
            <div
              key={q.id}
              className={`editor-slide-row ${selectedId === q.id ? 'selected' : ''}`}
              draggable
              onDragStart={() => setDragIndex(i)}
              onDragOver={(e) => e.preventDefault()}
              onDrop={() => handleDrop(i)}
              onClick={() => setSelectedId(q.id)}
            >
              <span className="editor-slide-drag-handle">⠿</span>
              <span className="editor-slide-label">
                {i + 1}. {q.title}
              </span>
              <button
                type="button"
                className="editor-slide-delete"
                onClick={(e) => {
                  e.stopPropagation();
                  if (deletingId !== q.id) handleDeleteQuestion(q);
                }}
                disabled={deletingId === q.id}
                title="Delete question"
              >
                {deletingId === q.id ? '…' : '✕'}
              </button>
            </div>
          ))}
        </div>

        {selectedId !== null && (
          <div className="editor-panes">
            <form className="editor-form-pane" onSubmit={handleSave}>
              <div className="panel">
                <div className="panel-body">
                  <div className="form-group">
                    <label htmlFor="qTitle">Title</label>
                    <input
                      id="qTitle"
                      className="form-control"
                      value={form.title}
                      onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label htmlFor="qGradingMode">Question type</label>
                    <select
                      id="qGradingMode"
                      className="form-control"
                      value={form.gradingMode}
                      onChange={(e) => setForm((f) => ({ ...f, gradingMode: e.target.value }))}
                      style={{ maxWidth: 320 }}
                    >
                      {GRADING_MODE_OPTIONS.map((o) => (
                        <option key={o.value} value={o.value}>
                          {o.label}
                        </option>
                      ))}
                    </select>
                    <p style={{ fontSize: 12, color: 'var(--muted)', margin: '6px 0 0' }}>
                      {form.gradingMode === 'simple' &&
                        'Grades a list of call → expected-value pairs — test code is generated for you.'}
                      {form.gradingMode === 'doctest' &&
                        "Grades the >>> examples already in the student's own docstrings — no separate test code needed."}
                      {form.gradingMode === 'pltest' &&
                        'Grades hand-written test code (a PLTestCase class) for cases the call/expected shape can’t express.'}
                      {form.gradingMode === 'discussion' &&
                        'No code editor or autograder — just a prompt (embed any code as a markdown code block) and an optional written-up solution.'}
                    </p>
                  </div>
                  <div className="form-group" style={{ marginBottom: 0 }}>
                    <label htmlFor="qPrompt">Problem description (markdown)</label>
                    <textarea
                      id="qPrompt"
                      className="form-control"
                      rows={5}
                      value={form.prompt}
                      onChange={(e) => setForm((f) => ({ ...f, prompt: e.target.value }))}
                      required
                    />
                  </div>
                </div>
              </div>

              {form.gradingMode !== 'discussion' && (
                <div className="panel">
                  <div className="panel-heading">
                    <h4>Problem code</h4>
                  </div>
                  <div className="panel-body">
                    {form.gradingMode === 'doctest' && (
                      <p style={{ fontSize: 12, color: 'var(--muted)', marginTop: 0 }}>
                        Include real <code className="code">&gt;&gt;&gt;</code> examples with their expected output in
                        a function docstring below — those are what get graded.
                      </p>
                    )}
                    <CodeEditor
                      code={form.starterCode}
                      readOnly={false}
                      onChange={(v) => setForm((f) => ({ ...f, starterCode: v }))}
                      editorLabel="problem code"
                    />
                    <div className="form-group" style={{ marginTop: 12, marginBottom: 0 }}>
                      <label htmlFor="qSetup">Setup code (optional)</label>
                      <textarea
                        id="qSetup"
                        className="form-control code"
                        rows={3}
                        value={form.setupCode}
                        onChange={(e) => setForm((f) => ({ ...f, setupCode: e.target.value }))}
                      />
                    </div>
                  </div>
                </div>
              )}

              {form.gradingMode === 'simple' && (
                <div className="panel">
                  <div className="panel-heading">
                    <h4>Test cases</h4>
                  </div>
                  <div className="panel-body">
                    {testCases.map((c, i) => (
                      <div key={i} style={{ display: 'flex', gap: 8, marginBottom: 8, alignItems: 'flex-end' }}>
                        <div className="form-group" style={{ flex: 1, marginBottom: 0 }}>
                          <label>Call</label>
                          <input
                            className="form-control code"
                            value={c.call}
                            onChange={(e) => updateCase(i, 'call', e.target.value)}
                            placeholder="e.g. double(3)"
                          />
                        </div>
                        <div className="form-group" style={{ flex: 1, marginBottom: 0 }}>
                          <label>Expected</label>
                          <input
                            className="form-control code"
                            value={c.expected}
                            onChange={(e) => updateCase(i, 'expected', e.target.value)}
                            placeholder="e.g. 6"
                          />
                        </div>
                        <button
                          type="button"
                          className="btn btn-sm"
                          onClick={() => removeCase(i)}
                          disabled={testCases.length === 1}
                        >
                          Remove
                        </button>
                      </div>
                    ))}
                    <button type="button" className="btn btn-sm" onClick={addCase}>
                      + Add test case
                    </button>
                  </div>
                </div>
              )}

              {form.gradingMode === 'pltest' && (
                <div className="panel">
                  <div className="panel-heading">
                    <h4>Test code</h4>
                  </div>
                  <div className="panel-body">
                    <p style={{ fontSize: 12, color: 'var(--muted)', marginTop: 0 }}>
                      A hand-written <code className="code">class Test(PLTestCase)</code> — see{' '}
                      <code className="code">grader/harness/</code> for the test-authoring API.
                    </p>
                    <CodeEditor
                      code={form.testCode}
                      readOnly={false}
                      onChange={(v) => setForm((f) => ({ ...f, testCode: v }))}
                      editorLabel="test code"
                    />
                  </div>
                </div>
              )}

              {form.gradingMode !== 'discussion' && (
                <div className="panel">
                  <div className="panel-heading">
                    <h4>Passing solution</h4>
                  </div>
                  <div className="panel-body">
                    <p style={{ fontSize: 12, color: 'var(--muted)', marginTop: 0 }}>
                      Validated against the {form.gradingMode === 'doctest' ? 'docstring examples' : 'test code'}{' '}
                      before saving — never shown to students.
                    </p>
                    <CodeEditor
                      code={form.referenceSolution}
                      readOnly={false}
                      onChange={(v) => setForm((f) => ({ ...f, referenceSolution: v }))}
                      editorLabel="reference solution"
                    />
                  </div>
                </div>
              )}

              <div className="panel">
                <div className="panel-heading">
                  <h4>Solution write-up (optional)</h4>
                </div>
                <div className="panel-body">
                  <p style={{ fontSize: 12, color: 'var(--muted)', marginTop: 0 }}>
                    Markdown reference for TAs — not shown to students automatically.
                  </p>
                  <textarea
                    id="qSolutionMarkdown"
                    className="form-control"
                    rows={4}
                    value={form.solutionMarkdown}
                    onChange={(e) => setForm((f) => ({ ...f, solutionMarkdown: e.target.value }))}
                  />
                </div>
              </div>

              {saveError && (
                <div className="alert alert-danger">
                  <strong>{saveError}</strong>
                  {failingCases && (
                    <div className="rows" style={{ marginTop: 8 }}>
                      {failingCases.map((f, i) => (
                        <div key={i}>
                          {f.name}: {f.message}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              <button className="btn btn-primary" type="submit" disabled={saving}>
                {saving ? 'Validating & saving…' : selectedId === NEW_SLIDE_ID ? 'Add question' : 'Save changes'}
              </button>
            </form>

            <div className="panel editor-preview-pane">
              <div className="panel-heading">
                <h4>Preview</h4>
                <span style={{ fontSize: 11, color: 'var(--muted)' }}>what students see</span>
              </div>
              <div className="panel-body">
                <div className="q-label" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span>{form.title || 'Untitled question'}</span>
                  <span className="badge badge-default">
                    {GRADING_MODE_OPTIONS.find((o) => o.value === form.gradingMode)?.label || form.gradingMode}
                  </span>
                </div>
                <MarkdownContent content={form.prompt || '_Nothing written yet._'} />
                {form.starterCode && (
                  <pre className="code-editor-wrap" style={{ padding: 10, color: '#eee', margin: 0 }}>
                    <code className="code">{form.starterCode}</code>
                  </pre>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
