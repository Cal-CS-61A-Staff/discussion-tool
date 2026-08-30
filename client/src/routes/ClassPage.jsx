import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import * as sectionsApi from '../api/sections.js';

export default function ClassPage() {
  const { sectionId } = useParams();
  const navigate = useNavigate();

  const [sectionName, setSectionName] = useState('');
  const [worksheets, setWorksheets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = () => {
    setLoading(true);
    Promise.all([sectionsApi.listSections(), sectionsApi.sectionWorksheets(sectionId)])
      .then(([sectionsRes, worksheetsRes]) => {
        const section = sectionsRes.sections.find((s) => String(s.id) === String(sectionId));
        setSectionName(section ? `${section.course_name} · ${section.name}` : 'Class');
        setWorksheets(worksheetsRes.worksheets);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sectionId]);

  if (loading) return <div className="page-loading">Loading…</div>;

  return (
    <div>
      <div className="breadcrumb-row">
        <a
          href="/"
          onClick={(e) => {
            e.preventDefault();
            navigate('/');
          }}
        >
          ← Home
        </a>
      </div>
      <div className="page-header-row">
        <div>
          <h1>{sectionName}</h1>
          <p>Assignments in this class.</p>
        </div>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      <div className="table-wrap">
        <table className="admin-table">
          <thead>
            <tr>
              <th>Problem Set Name</th>
            </tr>
          </thead>
          <tbody>
            {worksheets.map((w) => (
              <tr key={w.id}>
                <td>
                  <a
                    href="/"
                    onClick={(e) => {
                      e.preventDefault();
                      navigate(`/classes/${sectionId}/assignments/${w.id}`);
                    }}
                  >
                    {w.title}
                  </a>
                </td>
              </tr>
            ))}
            {worksheets.length === 0 && (
              <tr>
                <td style={{ color: 'var(--muted)', textAlign: 'center', padding: 20 }}>
                  No assignments yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
