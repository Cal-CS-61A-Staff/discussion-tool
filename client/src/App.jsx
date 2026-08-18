import { Navigate, Route, Routes } from 'react-router-dom';
import Layout from './components/layout/Layout.jsx';
import { AuthProvider, useAuth } from './context/AuthContext.jsx';
import AssignmentPage from './routes/AssignmentPage.jsx';
import ClassPage from './routes/ClassPage.jsx';
import HomePage from './routes/HomePage.jsx';
import LoginPage from './routes/LoginPage.jsx';
import StudentWorksheetPage from './routes/StudentWorksheetPage.jsx';
import TaAssignmentEditorPage from './routes/TaAssignmentEditorPage.jsx';
import TaDashboardPage from './routes/TaDashboardPage.jsx';
import TaGradesPage from './routes/TaGradesPage.jsx';
import TaGroupsPage from './routes/TaGroupsPage.jsx';

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
        path="/classes/:sectionId"
        element={
          <RequireAuth>
            <ClassPage />
          </RequireAuth>
        }
      />
      <Route
        path="/classes/:sectionId/groups"
        element={
          <RequireAuth>
            <TaGroupsPage />
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
        path="/classes/:sectionId/assignments/:worksheetId/edit"
        element={
          <RequireAuth>
            <TaAssignmentEditorPage />
          </RequireAuth>
        }
      />
      <Route
        path="/classes/:sectionId/assignments/:worksheetId/dashboard"
        element={
          <RequireAuth>
            <TaDashboardPage />
          </RequireAuth>
        }
      />
      <Route
        path="/classes/:sectionId/assignments/:worksheetId/grades"
        element={
          <RequireAuth>
            <TaGradesPage />
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
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppRoutes />
    </AuthProvider>
  );
}
