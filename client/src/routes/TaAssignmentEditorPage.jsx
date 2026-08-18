import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import CodeEditor from '../components/student/CodeEditor.jsx';
import MarkdownContent from '../components/student/MarkdownContent.jsx';
import * as adminApi from '../api/admin.js';
import * as sectionsApi from '../api/sections.js';

const DIFFICULTY_BADGE_CLASS = { easy: 'badge-success', medium: 'badge-warning', hard: 'badge-danger' };
const NEW_SLIDE_ID = 'new';

const blankForm = { title: '', difficulty: 'medium', prompt: '', starterCode: '', setupCode: '', referenceSolution: '' };

export default function TaAssignmentEditorPage() {
  const { sectionId, worksheetId } = useParams();
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

  const [detailsTitle, setDetailsTitle] = useState('');
  const [detailsDescription, setDetailsDescription] = useState('');
  const [detailsDueDate, setDetailsDueDate] = useState('');
  const [detailsPublished, setDetailsPublished] = useState(false);
  const [savingDetails, setSavingDetails] = useState(false);

  const load = () => {
    setLoading(true);
    Promise.all([sectionsApi.sectionWorksheets(sectionId), adminApi.listQuestions(worksheetId)])
      .then(([worksheetsRes, questionsRes]) => {
        const found = worksheetsRes.worksheets.find((w) => String(w.id) === String(worksheetId));
        setWorksheet(found || null);
        if (found) {
          setDetailsTitle(found.title);
          setDetailsDescription(found.description || '');
          setDetailsDueDate(found.due_date || '');
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
  }, [sectionId, worksheetId]);

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
      difficulty: q.difficulty || 'medium',
      prompt: q.prompt,
      starterCode: q.starter_code || '',
      setupCode: q.setup_code || '',
      referenceSolution: q.reference_solution || '',
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
      difficulty: form.difficulty,
      prompt: form.prompt,
      starter_code: form.starterCode,
      setup_code: form.setupCode,
      reference_solution: form.referenceSolution,
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
    try {
      await adminApi.deleteQuestion(q.id);
      if (selectedId === q.id) setSelectedId(null);
      load();
    } catch (err) {
      setError(err.message);
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
    try {
      await adminApi.reorderQuestions(worksheetId, reordered.map((q) => q.id));
    } catch (err) {
      setError(err.message);
      load();
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
        due_date: detailsDueDate || null,
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
            navigate(`/classes/${sectionId}/assignments/${worksheetId}`);
          }}
        >
          ← Back to assignment
        </a>
      </div>
      <div className="page-header-row">
        <h1>Edit — {worksheet?.title}</h1>
        <p>Each question is a slide — pick one on the left, edit it on the right, drag to reorder.</p>
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
            <div className="form-group" style={{ flex: '1 1 160px', marginBottom: 0 }}>
              <label htmlFor="detailsDueDate">Due date</label>
              <input
                id="detailsDueDate"
                type="date"
                className="form-control"
                value={detailsDueDate}
                onChange={(e) => setDetailsDueDate(e.target.value)}
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
                  handleDeleteQuestion(q);
                }}
                title="Delete question"
              >
                ✕
              </button>
            </div>
          ))}
          <div
            className={`editor-slide-row editor-slide-add ${selectedId === NEW_SLIDE_ID ? 'selected' : ''}`}
            onClick={() => setSelectedId(NEW_SLIDE_ID)}
          >
            + Add question
          </div>
        </div>

        {selectedId !== null && (
          <div className="editor-panes">
            <div className="panel editor-preview-pane">
              <div className="panel-heading">
                <h4>Preview</h4>
                <span style={{ fontSize: 11, color: 'var(--muted)' }}>what students see</span>
              </div>
              <div className="panel-body">
                <div className="q-label" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span>{form.title || 'Untitled question'}</span>
                  {form.difficulty && (
                    <span className={`badge ${DIFFICULTY_BADGE_CLASS[form.difficulty] || 'badge-default'}`}>
                      {form.difficulty}
                    </span>
                  )}
                </div>
                <MarkdownContent content={form.prompt || '_Nothing written yet._'} />
                {form.starterCode && (
                  <pre className="code-editor-wrap" style={{ padding: 10, color: '#eee', margin: 0 }}>
                    <code className="code">{form.starterCode}</code>
                  </pre>
                )}
              </div>
            </div>

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
                    <label htmlFor="qDifficulty">Difficulty</label>
                    <select
                      id="qDifficulty"
                      className="form-control"
                      value={form.difficulty}
                      onChange={(e) => setForm((f) => ({ ...f, difficulty: e.target.value }))}
                      style={{ maxWidth: 200 }}
                    >
                      <option value="easy">Easy</option>
                      <option value="medium">Medium</option>
                      <option value="hard">Hard</option>
                    </select>
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

              <div className="panel">
                <div className="panel-heading">
                  <h4>Problem code</h4>
                </div>
                <div className="panel-body">
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

              <div className="panel">
                <div className="panel-heading">
                  <h4>Passing solution</h4>
                </div>
                <div className="panel-body">
                  <p style={{ fontSize: 12, color: 'var(--muted)', marginTop: 0 }}>
                    Validated against your test cases before saving — never shown to students.
                  </p>
                  <CodeEditor
                    code={form.referenceSolution}
                    readOnly={false}
                    onChange={(v) => setForm((f) => ({ ...f, referenceSolution: v }))}
                    editorLabel="reference solution"
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
          </div>
        )}
      </div>
    </div>
  );
}
