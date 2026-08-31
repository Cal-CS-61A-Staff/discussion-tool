import { lazy, Suspense } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import Layout from './components/layout/Layout.jsx';
import ErrorBoundary from './components/ErrorBoundary.jsx';
import { AuthProvider, useAuth } from './context/AuthContext.jsx';

// Route-level code splitting: CodeMirror + react-markdown (pulled in by the
// worksheet/editor/history pages) are the bulk of the bundle — lazy-loading
// per route means a student landing on the lightweight pages (login, home,
// class picker) doesn't pay for that weight up front.
const AdminPage = lazy(() => import('./routes/AdminPage.jsx'));
const AssignmentPage = lazy(() => import('./routes/AssignmentPage.jsx'));
const AssignmentsPage = lazy(() => import('./routes/AssignmentsPage.jsx'));
const ClassSectionsPage = lazy(() => import('./routes/ClassSectionsPage.jsx'));
const DiscussionsPage = lazy(() => import('./routes/DiscussionsPage.jsx'));
const HomePage = lazy(() => import('./routes/HomePage.jsx'));
const LoginPage = lazy(() => import('./routes/LoginPage.jsx'));
const StudentWorksheetPage = lazy(() => import('./routes/StudentWorksheetPage.jsx'));
const TaAssignmentEditorPage = lazy(() => import('./routes/TaAssignmentEditorPage.jsx'));
const TaDashboardPage = lazy(() => import('./routes/TaDashboardPage.jsx'));
const TaGradesPage = lazy(() => import('./routes/TaGradesPage.jsx'));
const WorkBrowserPage = lazy(() => import('./routes/WorkBrowserPage.jsx'));

function RequireAuth({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="page-loading">Loading…</div>;
  if (!user) return <Navigate to="/login" replace />;
  return <Layout>{children}</Layout>;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/"
        element={
          <RequireAuth>
            <HomePage />
          </RequireAuth>
        }
      />
      <Route
        path="/admin"
        element={
          <RequireAuth>
            <AdminPage />
          </RequireAuth>
        }
      />
      <Route
        path="/discussions"
        element={
          <RequireAuth>
            <DiscussionsPage />
          </RequireAuth>
        }
      />
      <Route
        path="/discussions/:classId"
        element={
          <RequireAuth>
            <ClassSectionsPage />
          </RequireAuth>
        }
      />
      <Route
        path="/assignments"
        element={
          <RequireAuth>
            <AssignmentsPage />
          </RequireAuth>
        }
      />
      <Route
        path="/assignments/:worksheetId/edit"
        element={
          <RequireAuth>
            <TaAssignmentEditorPage />
          </RequireAuth>
        }
      />
      <Route
        path="/assignments/:worksheetId/dashboard"
        element={
          <RequireAuth>
            <TaDashboardPage />
          </RequireAuth>
        }
      />
      <Route
        path="/assignments/:worksheetId/grades"
        element={
          <RequireAuth>
            <TaGradesPage />
          </RequireAuth>
        }
      />
      <Route
        path="/classes/:sectionId/assignments/:worksheetId"
        element={
          <RequireAuth>
            <AssignmentPage />
          </RequireAuth>
        }
      />
      <Route
        path="/classes/:sectionId/assignments/:worksheetId/groups/:groupId"
        element={
          <RequireAuth>
            <StudentWorksheetPage />
          </RequireAuth>
        }
      />
      <Route
        path="/groups/:groupId/worksheets/:worksheetId/work"
        element={
          <RequireAuth>
            <WorkBrowserPage />
          </RequireAuth>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <AuthProvider>
        <Suspense fallback={<div className="page-loading">Loading…</div>}>
          <AppRoutes />
        </Suspense>
      </AuthProvider>
    </ErrorBoundary>
  );
}
