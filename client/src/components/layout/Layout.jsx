import Navbar from './Navbar.jsx';

export default function Layout({ children }) {
  return (
    <div className="app-root">
      <Navbar />
      <main className="app-main">
        <div className="container">{children}</div>
      </main>
    </div>
  );
}
