import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ToastContainer } from 'react-toastify';
import { AuthProvider } from './context/AuthContext';
import MainLayout from './layouts/MainLayout';
import ProtectedRoute from './components/auth/ProtectedRoute';

import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import ForgotPasswordPage from './pages/ForgotPasswordPage';
import OrgSetupPage from './pages/OrgSetupPage';

import DashboardPage from './pages/DashboardPage';
import SubjectListPage from './pages/SubjectListPage';
import SubjectDetailPage from './pages/SubjectDetailPage';
import ThemeListPage from './pages/ThemeListPage';
import GenerationListPage from './pages/GenerationListPage';
import GenerationBatchPage from './pages/GenerationBatchPage';
import NewBatchPage from './pages/NewBatchPage';
import MusicLibraryPage from './pages/MusicLibraryPage';
import StoryListPage from './pages/StoryListPage';
import NewStoryPage from './pages/NewStoryPage';
import StoryDetailPage from './pages/StoryDetailPage';

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ToastContainer position="top-right" autoClose={3000} />
        <Routes>
          {/* Public auth routes */}
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />

          {/* Org setup — protected but doesn't require an org */}
          <Route path="/setup" element={<ProtectedRoute requireOrg={false}><OrgSetupPage /></ProtectedRoute>} />

          {/* App routes — wrapped in MainLayout */}
          <Route element={<ProtectedRoute><MainLayout /></ProtectedRoute>}>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/subjects" element={<SubjectListPage />} />
            <Route path="/subjects/:uuid" element={<SubjectDetailPage />} />
            <Route path="/themes" element={<ThemeListPage />} />
            <Route path="/music" element={<MusicLibraryPage />} />
            <Route path="/generate" element={<NewBatchPage />} />
            <Route path="/generations" element={<GenerationListPage />} />
            <Route path="/generations/:uuid" element={<GenerationBatchPage />} />
            <Route path="/stories" element={<StoryListPage />} />
            <Route path="/stories/new" element={<NewStoryPage />} />
            <Route path="/stories/:uuid" element={<StoryDetailPage />} />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
