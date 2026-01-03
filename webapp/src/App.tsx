import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './contexts/AuthContext';
import { ThemeProvider } from './contexts/ThemeContext';
import { ReauthProvider } from './contexts/ReauthContext';
import ProtectedRoute from './components/ProtectedRoute';
import Layout from './components/Layout';
import LoginPage from './pages/LoginPage';
import ChatPage from './pages/ChatPage';
import ContactsPage from './pages/ContactsPage';
import TasksPage from './pages/TasksPage';
import ReportsPage from './pages/ReportsPage';
import UpcomingPage from './pages/UpcomingPage';
import RemindersPage from './pages/RemindersPage';
import IntegrationsPage from './pages/IntegrationsPage';

function App() {
  return (
    <ThemeProvider>
      <BrowserRouter>
        <AuthProvider>
        <ReauthProvider>
        <Routes>
          {/* Public routes */}
          <Route path="/login" element={<LoginPage />} />
          
          {/* Protected routes with layout */}
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <Layout />
              </ProtectedRoute>
            }
          >
            <Route index element={<Navigate to="chat" replace />} />
            <Route path="chat" element={<ChatPage />} />
            <Route path="integrations" element={<IntegrationsPage />} />
            <Route path="contacts" element={<ContactsPage />} />
            <Route path="tasks" element={<TasksPage />} />
            <Route path="reports" element={<ReportsPage />} />
            <Route path="upcoming" element={<UpcomingPage />} />
            <Route path="reminders" element={<RemindersPage />} />
          </Route>

          {/* Legacy user routes - redirect to new routes */}
          <Route path="/user/:userId/*" element={<Navigate to="/" replace />} />

          {/* Catch-all redirect */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </ReauthProvider>
        </AuthProvider>
      </BrowserRouter>
    </ThemeProvider>
  );
}

export default App;
