import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import TaQuestionList from '../components/ta/TaQuestionList.jsx';
import * as adminApi from '../api/admin.js';
import * as sectionsApi from '../api/sections.js';

/** Staff view of one assignment: the question list, links to the live
 * dashboard / editor, and the student share link to hand out. Students no
 * longer see this page — they open /w/<share_code> directly. */
export default function AssignmentPage() {
  const { classId, worksheetId } = useParams();
  const navigate = useNavigate();

  const [worksheet, setWorksheet] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setLoading(true);
    Promise.all([sectionsApi.classWorksheets(classId), adminApi.listQuestions(worksheetId)])
      .then(([worksheetsRes, questionsRes]) => {
        setWorksheet(worksheetsRes.worksheets.find((w) => String(w.id) === String(worksheetId)) || null);
        setQuestions(questionsRes.questions);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [classId, worksheetId]);

  if (loading) return <div className="page-loading">Loading…</div>;

  const shareUrl = worksheet?.share_code ? `${window.location.origin}/w/${worksheet.share_code}` : null;
  const copy = () => {
    navigator.clipboard?.writeText(shareUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div>
      <div className="breadcrumb-row">
        <a
          href="/"
          onClick={(e) => {
            e.preventDefault();
            navigate(`/assignments?classId=${classId}`);
          }}
        >
          ← Back to assignments
        </a>
      </div>
      <div className="page-header-row">
        <div>
          <h1>{worksheet ? worksheet.title : 'Assignment'}</h1>
          {worksheet?.description && <p>{worksheet.description}</p>}
        </div>
        <div style={{ display: 'flex', gap: 14 }}>
          <a
            href="/"
            onClick={(e) => {
              e.preventDefault();
              navigate(`/assignments/${worksheetId}/dashboard`);
            }}
          >
            Live dashboard →
          </a>
          <a
            href="/"
            onClick={(e) => {
              e.preventDefault();
              navigate(`/assignments/${worksheetId}/edit`);
            }}
          >
            Edit assignment →
          </a>
        </div>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      <div className="panel" style={{ maxWidth: 560 }}>
        <div className="panel-heading">
          <h4>Student link</h4>
        </div>
        <div className="panel-body">
          {shareUrl ? (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <code className="code" style={{ padding: '4px 8px', wordBreak: 'break-all' }}>{shareUrl}</code>
              <button className="btn btn-sm" onClick={copy}>
                {copied ? 'Copied ✓' : 'Copy'}
              </button>
            </div>
          ) : (
            <p style={{ margin: 0, fontSize: 13, color: 'var(--muted)' }}>
              Publish this assignment to get a share link.
            </p>
          )}
        </div>
      </div>

      <div className="page-header-row" style={{ marginTop: 24 }}>
        <h3 style={{ margin: 0 }}>Questions ({questions.length})</h3>
      </div>
      <TaQuestionList questions={questions} />
    </div>
  );
}
