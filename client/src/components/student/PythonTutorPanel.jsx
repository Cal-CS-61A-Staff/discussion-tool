/** Embeds a pythontutor.com environment-diagram stepper for the given
 * Python source. Shown below a question's prompt (any problem_type) when
 * Question.python_tutor_code is set, and in the TA editor preview. */
export default function PythonTutorPanel({ code }) {
  if (!code || !code.trim()) return null;
  const src =
    'https://pythontutor.com/iframe-embed.html#code=' +
    encodeURIComponent(code) +
    '&cumulative=true&py=3&origin=composingprograms.js&codeDivWidth=350&codeDivHeight=400&curInstr=0';
  return (
    <div className="panel" style={{ marginTop: 14 }}>
      <div className="panel-heading">
        <h4>Environment diagram</h4>
        <span style={{ fontSize: 11, color: 'var(--muted)' }}>step through it to check your thinking</span>
      </div>
      <div className="panel-body" style={{ padding: 0 }}>
        <iframe
          title="Python Tutor environment diagram"
          src={src}
          style={{ width: '100%', height: 500, border: 0, display: 'block' }}
        />
      </div>
    </div>
  );
}
