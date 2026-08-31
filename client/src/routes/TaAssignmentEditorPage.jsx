import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import CodeEditor from '../components/student/CodeEditor.jsx';
import MarkdownContent from '../components/student/MarkdownContent.jsx';
import ProblemWidget from '../components/student/ProblemWidget.jsx';
import ProblemTypeEditor, { PROBLEM_TYPE_DEFAULT_CONTENT } from '../components/ta/ProblemTypeEditor.jsx';
import * as adminApi from '../api/admin.js';

const NEW_SLIDE_ID = 'new';

// One flat dropdown for the TA. Under the hood a question still stores two
// columns — `problem_type` (the answer/content widget) and, for coding,
// `grading_mode` (which autograder path runs). The four coding grading
// modes are surfaced here as sub-options of "Coding"; every other entry is
// a non-code widget and rides on grading_mode='discussion' as a shim so
// the server's "no grader" guards apply unchanged. `key` is only the
// <select> value — it's mapped to/from {problemType, gradingMode} at the
// edges. See server/services/response_grading.py for each widget's config.
const PROBLEM_TYPE_OPTIONS = [
  { key: 'coding_doctest', label: 'Coding — Doctest (docstring >>> examples)', problemType: 'coding', gradingMode: 'doctest' },
  { key: 'coding_pltest', label: 'Coding — Custom test code', problemType: 'coding', gradingMode: 'pltest' },
  { key: 'prediction', label: 'Prediction (guess the output)', problemType: 'prediction', gradingMode: 'discussion' },
  { key: 'discussion', label: 'Discussion (no code)', problemType: 'coding', gradingMode: 'discussion' },
  { key: 'multiple_choice', label: 'Multiple Choice', problemType: 'multiple_choice', gradingMode: 'discussion' },
  { key: 'fill_blank_code', label: 'Fill in the Blank (Coding)', problemType: 'fill_blank_code', gradingMode: 'discussion' },
  { key: 'fill_blank_markdown', label: 'Fill in the Blank (Markdown)', problemType: 'fill_blank_markdown', gradingMode: 'discussion' },
  { key: 'short_answer', label: 'Short Answer', problemType: 'short_answer', gradingMode: 'discussion' },
  { key: 'text_markdown', label: 'Text (Markdown)', problemType: 'text_markdown', gradingMode: 'discussion' },
  { key: 'dropdown', label: 'Dropdown', problemType: 'dropdown', gradingMode: 'discussion' },
  { key: 'plain_text', label: 'Plain Text Box', problemType: 'plain_text', gradingMode: 'discussion' },
  { key: 'image', label: 'Image', problemType: 'image', gradingMode: 'discussion' },
  { key: 'iframe', label: 'Iframe', problemType: 'iframe', gradingMode: 'discussion' },
];

// 'Simple' coding mode is retired — not offered for new questions, but a
// legacy question already on it stays editable (and keeps saving as simple)
// via this hidden option, appended to the list only when it's in use.
const LEGACY_SIMPLE_OPTION = {
  key: 'coding_simple',
  label: 'Coding — Simple (legacy call → expected)',
  problemType: 'coding',
  gradingMode: 'simple',
};

// key -> the {problem_type, grading_mode} pair the form/API works in.
const typeKeyToForm = (key) =>
  [...PROBLEM_TYPE_OPTIONS, LEGACY_SIMPLE_OPTION].find((o) => o.key === key) || PROBLEM_TYPE_OPTIONS[0];
// and back: derive the dropdown value from a loaded question's two fields.
const formToTypeKey = (problemType, gradingMode) =>
  problemType === 'coding'
    ? gradingMode === 'discussion'
      ? 'discussion'
      : `coding_${gradingMode || 'doctest'}`
    : problemType;

// The preview badge just needs a quick at-a-glance tag, not the full
// dropdown-option description — the long labels above wrap and overflow
// the pill shape there.
const PROBLEM_TYPE_SHORT_LABELS = {
  coding_simple: 'Simple',
  coding_doctest: 'Doctest',
  coding_pltest: 'Custom test',
  prediction: 'Prediction',
  discussion: 'No code',
  multiple_choice: 'Multiple choice',
  fill_blank_code: 'Fill blank (code)',
  fill_blank_markdown: 'Fill blank (md)',
  short_answer: 'Short answer',
  text_markdown: 'Text',
  dropdown: 'Dropdown',
  plain_text: 'Plain text',
  image: 'Image',
  iframe: 'Iframe',
};

// Shown under the dropdown for the coding grading modes.
const GRADING_MODE_HINTS = {
  simple: 'Grades a list of call → expected-value pairs — test code is generated for you.',
  doctest:
    "Grades the >>> examples already in the student's own docstrings — no separate test code needed.",
  pltest:
    'Grades hand-written test code (a PLTestCase class) for cases the call/expected shape can’t express.',
  discussion:
    'No code editor or autograder — just a prompt (embed any code as a markdown code block) and an optional written-up solution.',
};

const blankForm = {
  title: '',
  problemType: 'coding',
  content: {},
  gradingMode: 'doctest',
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
      problemType: q.problem_type || 'coding',
      content: q.content || {},
      gradingMode: q.grading_mode || 'doctest',
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
      problem_type: form.problemType,
      content: form.content,
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

  const isCoding = form.problemType === 'coding';

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
        {questions.length > 0 && (
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
        )}

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
                    <label htmlFor="qProblemType">Problem type</label>
                    <select
                      id="qProblemType"
                      className="form-control"
                      value={formToTypeKey(form.problemType, form.gradingMode)}
                      onChange={(e) =>
                        setForm((f) => {
                          const opt = typeKeyToForm(e.target.value);
                          const makeDefault = PROBLEM_TYPE_DEFAULT_CONTENT[opt.problemType];
                          const keepContent = opt.problemType === f.problemType;
                          return {
                            ...f,
                            problemType: opt.problemType,
                            gradingMode: opt.gradingMode,
                            content:
                              opt.problemType === 'coding'
                                ? {}
                                : keepContent
                                  ? f.content
                                  : makeDefault
                                    ? makeDefault()
                                    : {},
                          };
                        })
                      }
                      style={{ maxWidth: 320 }}
                    >
                      {(formToTypeKey(form.problemType, form.gradingMode) === 'coding_simple'
                        ? [...PROBLEM_TYPE_OPTIONS, LEGACY_SIMPLE_OPTION]
                        : PROBLEM_TYPE_OPTIONS
                      ).map((o) => (
                        <option key={o.key} value={o.key}>
                          {o.label}
                        </option>
                      ))}
                    </select>
                    {isCoding && (
                      <p style={{ fontSize: 12, color: 'var(--muted)', margin: '6px 0 0' }}>
                        {GRADING_MODE_HINTS[form.gradingMode]}
                      </p>
                    )}
                    {form.problemType === 'prediction' && (
                      <p style={{ fontSize: 12, color: 'var(--muted)', margin: '6px 0 0' }}>
                        Students are shown one randomly-chosen snippet from your suite and predict its output; it&apos;s
                        marked right if their prediction matches what the code actually prints in the sandbox.
                      </p>
                    )}
                  </div>
                  <div className="form-group" style={{ marginBottom: isCoding ? 0 : 16 }}>
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
                  {!isCoding && (
                    <ProblemTypeEditor
                      type={form.problemType}
                      content={form.content}
                      onChange={(content) => setForm((f) => ({ ...f, content }))}
                    />
                  )}
                </div>
              </div>

              {isCoding && form.gradingMode !== 'discussion' && (
                <div className="panel">
                  <div className="panel-heading">
                    <h4>Problem code</h4>
                    <span style={{ fontSize: 11, color: 'var(--muted)' }}>Shown to students</span>
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
                    <div className="form-group" style={{ marginTop: 16, marginBottom: 0 }}>
                      <label htmlFor="qSetup">Setup code (optional)</label>
                      <p style={{ fontSize: 12, color: 'var(--muted)', margin: '2px 0 6px' }}>
                        Define any classes, helper functions, or imports here (not shown to students).
                      </p>
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

              {isCoding && form.gradingMode === 'simple' && (
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

              {isCoding && form.gradingMode === 'pltest' && (
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

              {isCoding && form.gradingMode !== 'discussion' && (
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
                    {PROBLEM_TYPE_SHORT_LABELS[formToTypeKey(form.problemType, form.gradingMode)] ||
                      form.problemType}
                  </span>
                </div>
                <MarkdownContent content={form.prompt || '_Nothing written yet._'} />
                {isCoding && form.starterCode && (
                  <pre className="code-editor-wrap" style={{ padding: 10, color: '#eee', margin: 0 }}>
                    <code className="code">{form.starterCode}</code>
                  </pre>
                )}
                {!isCoding && (
                  <ProblemWidget readOnly problemType={form.problemType} content={form.content} />
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
