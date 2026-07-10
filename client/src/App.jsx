import React, { useState, useMemo } from 'react'
import { Routes, Route, Link, useLocation, useNavigate } from 'react-router-dom'
import { Layout, Menu, Modal, Form, Input, Button, message, Tooltip } from 'antd'
import {
  DashboardOutlined,
  CalendarOutlined,
  UnorderedListOutlined,
  FilePdfOutlined,
  UploadOutlined,
  SettingOutlined,
  UserOutlined,
  LogoutOutlined,
  LockOutlined,
  FileTextOutlined,
  FormOutlined,
} from '@ant-design/icons'

import { login, logout, workerLogin } from './api'

import Dashboard      from './pages/Dashboard'
import CalendarView   from './pages/CalendarView'
import PeriodView     from './pages/PeriodView'
import ReportView     from './pages/ReportView'
import LogPage        from './pages/LogPage'
import IngestPage     from './pages/IngestPage'
import SettingsPage   from './pages/SettingsPage'
import WorkerPage     from './pages/WorkerPage'

const { Sider, Content } = Layout

// ── 일반 사용자 메뉴 ────────────────────────────────────────────────────────
const PUBLIC_NAV = [
  { key: '/',          label: <Link to="/">대시보드</Link>,     icon: <DashboardOutlined /> },
  { key: '/calendar',  label: <Link to="/calendar">달력</Link>,  icon: <CalendarOutlined /> },
  { key: '/period',    label: <Link to="/period">상세조회</Link>, icon: <UnorderedListOutlined /> },
  { key: '/report',    label: <Link to="/report">송출내역 출력</Link>, icon: <FilePdfOutlined /> },
  { key: '/logs',      label: <Link to="/logs">로그 기록</Link>, icon: <FileTextOutlined /> },
]

// ── 근무자 전용 메뉴 ────────────────────────────────────────────────────────
const WORKER_NAV = [
  { key: '/worker', label: <Link to="/worker">송출 수동입력</Link>, icon: <FormOutlined /> },
]

// ── 관리자 전용 메뉴 (추가분) ───────────────────────────────────────────────
const ADMIN_EXTRA = [
  { key: '/ingest',     label: <Link to="/ingest">파일 적재</Link>,     icon: <UploadOutlined /> },
  { key: '/settings',   label: <Link to="/settings">환경설정</Link>,     icon: <SettingOutlined /> },
]

export default function App() {
  const location  = useLocation()
  const navigate  = useNavigate()
  const [isAdmin, setIsAdmin]       = useState(false)
  const [isWorker, setIsWorker]     = useState(false)
  const [loginOpen, setLoginOpen]   = useState(false)
  const [workerOpen, setWorkerOpen] = useState(false)
  const [loginLoading, setLoginLoading] = useState(false)
  const [workerLoading, setWorkerLoading] = useState(false)
  const [form] = Form.useForm()
  const [wForm] = Form.useForm()

  const selectedKey = '/' + location.pathname.split('/')[1]

  // 역할에 따라 메뉴 구성 (근무자 메뉴가 관리자 메뉴 위에 표시)
  const navItems = useMemo(() => {
    const items = [...PUBLIC_NAV]
    if (isWorker) {
      items.push({ type: 'divider' }, ...WORKER_NAV)
    }
    if (isAdmin) {
      items.push({ type: 'divider' }, ...ADMIN_EXTRA)
    }
    return items
  }, [isAdmin, isWorker])

  // ── 관리자 로그인 처리 ─────────────────────────────────────────────────────
  const handleLogin = async () => {
    try {
      const { username, password } = await form.validateFields()
      setLoginLoading(true)
      await login(username, password)
      setIsAdmin(true)
      setLoginOpen(false)
      form.resetFields()
      message.success('관리자 모드로 전환되었습니다.')
    } catch (e) {
      if (e.response) {
        message.error(e.response.data?.detail || '로그인 실패')
      }
      // form validation error → 무시
    } finally {
      setLoginLoading(false)
    }
  }

  // ── 근무자 로그인 처리 ─────────────────────────────────────────────────────
  const handleWorkerLogin = async () => {
    try {
      const { username, password } = await wForm.validateFields()
      setWorkerLoading(true)
      await workerLogin(username, password)
      setIsWorker(true)
      setWorkerOpen(false)
      wForm.resetFields()
      message.success('근무자 모드로 전환되었습니다.')
      navigate('/worker')
    } catch (e) {
      if (e.response) {
        message.error(e.response.data?.detail || '로그인 실패')
      }
    } finally {
      setWorkerLoading(false)
    }
  }

  // ── 관리자 로그아웃 처리 ───────────────────────────────────────────────────
  const handleLogout = async () => {
    await logout()
    setIsAdmin(false)
    // 관리자 전용 페이지에 있었다면 대시보드로 이동
    const adminPaths = ['/ingest', '/settings']
    if (adminPaths.includes(location.pathname)) {
      navigate('/')
    }
    message.info('로그아웃 되었습니다.')
  }

  // ── 근무자 로그아웃 처리 ───────────────────────────────────────────────────
  const handleWorkerLogout = () => {
    setIsWorker(false)
    if (location.pathname === '/worker') {
      navigate('/')
    }
    message.info('근무자 로그아웃 되었습니다.')
  }

  return (
    <Layout style={{ minHeight: '100vh' }}>
      {/* ── 사이드바 ── */}
      <Sider
        width={180}
        style={{
          background: '#001529',
          display: 'flex',
          flexDirection: 'column',
          position: 'fixed',
          height: '100vh',
          left: 0,
          top: 0,
          zIndex: 100,
        }}
      >
        {/* 로고 */}
        <div style={{
          color: '#fff',
          textAlign: 'center',
          padding: '16px 8px',
          fontWeight: 'bold',
          fontSize: 13,
          borderBottom: '1px solid #1f3a55',
          lineHeight: 1.6,
        }}>
          광주MBC<br />
          <span style={{ fontSize: 13, color: '#91caff' }}>SB 송출 관리</span>
        </div>

        {/* 네비게이션 메뉴 */}
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          items={navItems}
          style={{ flex: 1, borderRight: 0, marginTop: 4 }}
        />

        {/* 하단 근무자/관리자 버튼 영역 (근무자가 위, 관리자가 아래) */}
        <div style={{
          borderTop: '1px solid #1f3a55',
          padding: '12px 16px',
          display: 'flex',
          flexDirection: 'column',
          gap: 4,
        }}>
          {/* 근무자 */}
          {isWorker ? (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ color: '#40a9ff', fontSize: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
                <FormOutlined />
                근무자
              </span>
              <Tooltip title="근무자 로그아웃">
                <Button type="text" size="small" icon={<LogoutOutlined />}
                  onClick={handleWorkerLogout} style={{ color: '#8c8c8c' }} />
              </Tooltip>
            </div>
          ) : (
            <Button
              type="text"
              icon={<FormOutlined />}
              onClick={() => setWorkerOpen(true)}
              style={{ width: '100%', color: '#8c8c8c', textAlign: 'left', fontSize: 12 }}
            >
              근무자
            </Button>
          )}

          {/* 관리자 */}
          {isAdmin ? (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ color: '#52c41a', fontSize: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
                <UserOutlined />
                관리자
              </span>
              <Tooltip title="로그아웃">
                <Button type="text" size="small" icon={<LogoutOutlined />}
                  onClick={handleLogout} style={{ color: '#8c8c8c' }} />
              </Tooltip>
            </div>
          ) : (
            <Button
              type="text"
              icon={<LockOutlined />}
              onClick={() => setLoginOpen(true)}
              style={{ width: '100%', color: '#8c8c8c', textAlign: 'left', fontSize: 12 }}
            >
              관리자
            </Button>
          )}
        </div>
      </Sider>

      {/* ── 메인 콘텐츠 영역 (상단 헤더 띠 제거 — 내용이 맨 위에서부터 표시) ── */}
      <Layout style={{ marginLeft: 180 }}>
        <Content style={{
          margin: '24px',
          background: '#f5f5f5',
          borderRadius: 8,
          minHeight: 'calc(100vh - 48px)',
        }}>
          <Routes>
            <Route path="/"            element={<Dashboard />} />
            <Route path="/calendar"    element={<CalendarView />} />
            <Route path="/period"      element={<PeriodView />} />
            <Route path="/report"      element={<ReportView />} />
            <Route path="/logs"        element={<LogPage />} />
            {/* 근무자 전용 라우트 */}
            <Route path="/worker"      element={isWorker ? <WorkerPage /> : <NotAllowedWorker />} />
            {/* 관리자 전용 라우트 */}
            <Route path="/ingest"      element={isAdmin ? <IngestPage />     : <NotAllowed />} />
            <Route path="/settings"    element={isAdmin ? <SettingsPage />   : <NotAllowed />} />
          </Routes>
        </Content>
      </Layout>

      {/* ── 로그인 모달 ── */}
      <Modal
        title={
          <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <LockOutlined style={{ color: '#1677ff' }} />
            관리자 로그인
          </span>
        }
        open={loginOpen}
        onCancel={() => { setLoginOpen(false); form.resetFields() }}
        footer={null}
        width={360}
        destroyOnClose
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleLogin}
          style={{ marginTop: 16 }}
        >
          <Form.Item
            name="username"
            label="아이디"
            initialValue="admin"
            rules={[{ required: true, message: '아이디를 입력하세요.' }]}
          >
            <Input prefix={<UserOutlined />} placeholder="admin" />
          </Form.Item>

          <Form.Item
            name="password"
            label="비밀번호"
            rules={[{ required: true, message: '비밀번호를 입력하세요.' }]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="비밀번호"
              onPressEnter={handleLogin}
            />
          </Form.Item>

          <Form.Item style={{ marginBottom: 0 }}>
            <Button
              type="primary"
              htmlType="submit"
              loading={loginLoading}
              block
              size="large"
            >
              로그인
            </Button>
          </Form.Item>
        </Form>
      </Modal>

      {/* ── 근무자 로그인 모달 ── */}
      <Modal
        title={
          <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <FormOutlined style={{ color: '#1677ff' }} />
            근무자 로그인
          </span>
        }
        open={workerOpen}
        onCancel={() => { setWorkerOpen(false); wForm.resetFields() }}
        footer={null}
        width={360}
        destroyOnClose
      >
        <Form form={wForm} layout="vertical" onFinish={handleWorkerLogin} style={{ marginTop: 16 }}>
          <Form.Item
            name="username"
            label="아이디"
            initialValue="user"
            rules={[{ required: true, message: '아이디를 입력하세요.' }]}
          >
            <Input prefix={<UserOutlined />} placeholder="user" />
          </Form.Item>
          <Form.Item
            name="password"
            label="비밀번호"
            rules={[{ required: true, message: '비밀번호를 입력하세요.' }]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="비밀번호" onPressEnter={handleWorkerLogin} />
          </Form.Item>
          <Form.Item style={{ marginBottom: 0 }}>
            <Button type="primary" htmlType="submit" loading={workerLoading} block size="large">
              로그인
            </Button>
          </Form.Item>
        </Form>
      </Modal>
    </Layout>
  )
}

// ── 권한 없음 페이지 ──────────────────────────────────────────────────────────
function NotAllowed() {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      height: '60vh',
      color: '#8c8c8c',
    }}>
      <LockOutlined style={{ fontSize: 48, marginBottom: 16, color: '#d9d9d9' }} />
      <p style={{ fontSize: 16 }}>관리자 권한이 필요합니다.</p>
      <p style={{ fontSize: 13 }}>좌측 하단 "관리자" 버튼으로 로그인하세요.</p>
    </div>
  )
}

// ── 근무자 권한 없음 페이지 ───────────────────────────────────────────────────
function NotAllowedWorker() {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      height: '60vh',
      color: '#8c8c8c',
    }}>
      <FormOutlined style={{ fontSize: 48, marginBottom: 16, color: '#d9d9d9' }} />
      <p style={{ fontSize: 16 }}>근무자 로그인이 필요합니다.</p>
      <p style={{ fontSize: 13 }}>좌측 하단 "근무자" 버튼으로 로그인하세요.</p>
    </div>
  )
}
