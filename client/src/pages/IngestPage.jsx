import React, { useState, useEffect, useRef } from 'react'
import {
  Card, Upload, Button, DatePicker, Alert, Tabs, Spin,
  message, Table, Tag, Statistic, Row, Col, Divider, Tooltip, Switch, Badge,
} from 'antd'
import {
  UploadOutlined, SyncOutlined,
  FolderOpenOutlined, InfoCircleOutlined,
  EyeOutlined, PoweroffOutlined, CloudDownloadOutlined,
} from '@ant-design/icons'
import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

// ── API 함수 ────────────────────────────────────────────────────────────────
const ingestCml     = (file) => { const fd = new FormData(); fd.append('file', file); return api.post('/ingest/cml', fd).then(r => r.data) }
const scanCmlDir    = () => api.post('/ingest/cml/scan').then(r => r.data)
const ingestApst    = (file) => { const fd = new FormData(); fd.append('file', file); return api.post('/ingest/apst', fd).then(r => r.data) }
const ingestDdr1    = (file, date) => { const fd = new FormData(); fd.append('file', file); fd.append('broadcast_date', date); return api.post('/ingest/ddr1', fd).then(r => r.data) }
const scanApstDir   = () => api.post('/ingest/apst/scan').then(r => r.data)
const scanDdr1Dir   = () => api.post('/ingest/ddr1/scan').then(r => r.data)
const resyncManual  = () => api.post('/ingest/ddr1/resync-manual').then(r => r.data)
const getStatus     = () => api.get('/ingest/status').then(r => r.data)
const getWatcher    = () => api.get('/ingest/watcher').then(r => r.data)
const startWatcher  = () => api.post('/ingest/watcher/start').then(r => r.data)
const stopWatcher   = () => api.post('/ingest/watcher/stop').then(r => r.data)
const getWatcherLog = () => api.get('/ingest/watcher/log').then(r => r.data)
const ftpTestApi  = () => api.get('/ftp/test').then(r => r.data)
const ftpFetchApi = (date) => api.post('/ftp/fetch', null, { params: { date } }).then(r => r.data)

// ── FTP 파일 가져오기 카드 ────────────────────────────────────────────────────
function FtpCard() {
  const [date, setDate]       = useState(null)
  const [fetching, setFetching] = useState(false)
  const [testing, setTesting] = useState(false)
  const [result, setResult]   = useState(null)

  const doTest = async () => {
    setTesting(true)
    try {
      const r = await ftpTestApi()
      message.success(`${r.message} (폴더: ${r.folders_found.join(', ') || '없음'})`)
    } catch (e) {
      message.error(e.response?.data?.detail || 'FTP 접속 실패')
    } finally { setTesting(false) }
  }

  const runFetch = async (fn) => {
    setFetching(true); setResult(null)
    try {
      const r = await fn()
      setResult(r)
      if (r.ok) message.success(`${r.date} 가져오기 완료`)
      else if (r.missing) message.warning(`${r.date} — APST 파일이 FTP에 없습니다.`)
      else message.error(r.error || '가져오기 실패')
    } catch (e) {
      message.error(e.response?.data?.detail || '가져오기 실패')
    } finally { setFetching(false) }
  }

  return (
    <Card
      title={<span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <CloudDownloadOutlined /> FTP 파일 가져오기</span>}
      style={{ marginBottom: 16 }}
    >
      <Alert
        type="info" showIcon style={{ marginBottom: 16 }}
        message="환경설정의 FTP 정보로 apst / ddr1_log / cml 파일을 가져와 자동 적재합니다."
        description="매일 설정한 시각에 전날 파일을 자동으로 가져옵니다. 아래에서 수동으로도 가져올 수 있습니다."
      />
      <Row gutter={12} align="middle">
        <Col><Button onClick={doTest} loading={testing}>접속 테스트</Button></Col>
        <Col><DatePicker value={date} onChange={setDate} format="YYYY-MM-DD" placeholder="날짜 선택" /></Col>
        <Col>
          <Button type="primary" icon={<CloudDownloadOutlined />}
            onClick={() => { if (!date) { message.warning('날짜를 선택하세요.'); return } runFetch(() => ftpFetchApi(date.format('YYYY-MM-DD'))) }}
            loading={fetching}>
            선택 날짜 가져오기
          </Button>
        </Col>
      </Row>
      {result && (
        <Alert
          style={{ marginTop: 12 }} showIcon
          type={result.ok ? 'success' : (result.missing ? 'warning' : 'error')}
          message={result.ok
            ? `${result.date} 가져오기 완료 — APST ${result.ingested.apst}건 · 수동 ${result.ingested.manual}건 · CML ${result.ingested.cml}건`
            : (result.missing ? `${result.date} — APST 파일이 FTP에 없습니다.` : `오류: ${result.error}`)}
        />
      )}
    </Card>
  )
}

// ── 폴더 감시 카드 ────────────────────────────────────────────────────────────
const LOG_COLS = [
  { title: '시간', dataIndex: 'time', width: 160 },
  {
    title: '구분', dataIndex: 'level', width: 70, align: 'center',
    render: v => v === 'error'
      ? <Tag color="red">오류</Tag>
      : <Tag color="green">완료</Tag>,
  },
  { title: '내용', dataIndex: 'message' },
]

function WatcherCard() {
  const [status, setStatus]   = useState(null)
  const [log, setLog]         = useState([])
  const [loading, setLoading] = useState(false)
  const [toggling, setToggling] = useState(false)
  const timerRef = useRef(null)

  const loadStatus = async () => {
    try {
      const s = await getWatcher()
      setStatus(s)
      setLog(s.log || [])
    } catch { /* 서버 미실행 시 무시 */ }
  }

  // 감시 중일 때 10초마다 로그 자동 갱신
  useEffect(() => {
    loadStatus()
    timerRef.current = setInterval(loadStatus, 10000)
    return () => clearInterval(timerRef.current)
  }, [])

  const toggle = async (on) => {
    setToggling(true)
    try {
      const res = on ? await startWatcher() : await stopWatcher()
      message.success(res.message)
      await loadStatus()
    } catch (e) {
      message.error(e.response?.data?.detail || '처리 실패')
    } finally {
      setToggling(false)
    }
  }

  const running = status?.running ?? false
  const watching = status?.watching ?? []

  return (
    <Card
      title={
        <span style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <EyeOutlined />
          폴더 실시간 감시
          <Badge
            status={running ? 'processing' : 'default'}
            text={running ? '감시 중' : '중지'}
            style={{ marginLeft: 4 }}
          />
        </span>
      }
      extra={
        <Button size="small" icon={<SyncOutlined />} onClick={loadStatus}>
          새로고침
        </Button>
      }
      style={{ marginBottom: 16 }}
    >
      <Row gutter={24} align="middle">
        <Col>
          <div style={{ fontSize: 13, color: '#666', marginBottom: 6 }}>감시 ON/OFF</div>
          <Switch
            checked={running}
            onChange={toggle}
            loading={toggling}
            checkedChildren="감시 중"
            unCheckedChildren="중지"
            style={{ width: 90 }}
          />
        </Col>
        <Col flex="auto">
          {running && watching.length > 0 ? (
            <div>
              <div style={{ fontSize: 12, color: '#888', marginBottom: 4 }}>감시 중인 폴더</div>
              {watching.map(p => (
                <div key={p} style={{
                  fontSize: 12, color: '#1677ff',
                  background: '#f0f7ff', borderRadius: 4,
                  padding: '2px 8px', marginBottom: 2,
                  display: 'inline-block', marginRight: 8,
                }}>
                  <FolderOpenOutlined style={{ marginRight: 4 }} />{p}
                </div>
              ))}
            </div>
          ) : (
            <div style={{ fontSize: 12, color: '#aaa' }}>
              {running ? '감시 폴더 없음 — 환경설정을 확인하세요.' : '감시가 중지되어 있습니다.'}
            </div>
          )}
        </Col>
      </Row>

      {/* 이벤트 로그 */}
      {log.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div style={{ fontSize: 12, color: '#888', marginBottom: 6 }}>
            최근 이벤트 로그
          </div>
          <Table
            dataSource={log}
            columns={LOG_COLS}
            rowKey={(_, i) => i}
            size="small"
            pagination={false}
            scroll={{ y: 180 }}
            rowClassName={r => r.level === 'error' ? 'ant-table-row-error' : ''}
          />
        </div>
      )}

      <Alert
        type="info"
        showIcon
        style={{ marginTop: 12 }}
        message="FTP로 파일이 도착하면 자동으로 DB에 적재됩니다."
        description={
          <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12 }}>
            <li><b>.apst</b> 파일 → APST 자동 송출 DB 적재</li>
            <li><b>.Log</b> 파일 → DDR1 수동 송출 DB 적재 (파일명에서 날짜 자동 추출)</li>
            <li><b>.cml</b> 파일 → 소재 매핑 테이블 자동 갱신</li>
          </ul>
        }
      />
    </Card>
  )
}

// ── 현황 카드 ────────────────────────────────────────────────────────────────
function StatusCard() {
  const [status, setStatus]   = useState(null)
  const [loading, setLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    try { setStatus(await getStatus()) }
    catch { message.error('현황 조회 실패') }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  return (
    <Card
      title="DB 적재 현황"
      extra={<Button size="small" icon={<SyncOutlined />} onClick={load} loading={loading}>새로고침</Button>}
      style={{ marginBottom: 20 }}
    >
      <Spin spinning={loading}>
        <Row gutter={32}>
          <Col>
            <div style={{ color: '#888', fontSize: 12, marginBottom: 4 }}>자동 송출 (APST)</div>
            <Statistic value={status?.apst?.total ?? 0} suffix="건" valueStyle={{ fontSize: 20, color: '#1677ff' }} />
            <div style={{ fontSize: 12, color: '#aaa', marginTop: 4 }}>
              파일 {status?.apst?.files ?? 0}개 &nbsp;|&nbsp;
              {status?.apst?.from_date ?? '-'} ~ {status?.apst?.to_date ?? '-'}
            </div>
          </Col>
          <Col>
            <div style={{ color: '#888', fontSize: 12, marginBottom: 4 }}>수동 송출 (DDR1)</div>
            <Statistic value={status?.ddr1?.total ?? 0} suffix="건" valueStyle={{ fontSize: 20, color: '#fa8c16' }} />
            <div style={{ fontSize: 12, color: '#aaa', marginTop: 4 }}>
              파일 {status?.ddr1?.files ?? 0}개 &nbsp;|&nbsp;
              {status?.ddr1?.from_date ?? '-'} ~ {status?.ddr1?.to_date ?? '-'}
            </div>
          </Col>
        </Row>
      </Spin>
    </Card>
  )
}

// ── 스캔 결과 테이블 ──────────────────────────────────────────────────────────
const SCAN_COLS = [
  { title: '파일명', dataIndex: 'file', ellipsis: true },
  {
    title: '결과', dataIndex: 'status', width: 80, align: 'center',
    render: v => ({
      ok:      <Tag color="green">완료</Tag>,
      skipped: <Tag color="default">건너뜀</Tag>,
      error:   <Tag color="red">오류</Tag>,
    }[v] ?? <Tag>{v}</Tag>),
  },
  { title: '날짜', dataIndex: 'broadcast_date', width: 110, align: 'center', render: v => v ?? '-' },
  { title: '적재 건수', dataIndex: 'inserted', width: 90, align: 'right', render: v => v != null ? `${v}건` : '-' },
  { title: '메시지', dataIndex: 'message', width: 220, render: v => v ?? '' },
]

function ScanResult({ result }) {
  if (!result) return null
  return (
    <div style={{ marginTop: 16 }}>
      <Alert
        type={result.total_inserted > 0 ? 'success' : 'info'}
        message={result.message}
        description={`총 ${result.total_inserted}건 적재 완료`}
        showIcon
        style={{ marginBottom: 12 }}
      />
      <Table
        dataSource={result.files}
        columns={SCAN_COLS}
        rowKey="file"
        size="small"
        pagination={false}
        scroll={{ y: 250 }}
      />
    </div>
  )
}

// ── CML 스캔 결과 테이블 컬럼 ────────────────────────────────────────────────
const CML_SCAN_COLS = [
  { title: '파일명', dataIndex: 'file', ellipsis: true },
  {
    title: '결과', dataIndex: 'status', width: 80, align: 'center',
    render: v => ({
      ok:    <Tag color="green">완료</Tag>,
      error: <Tag color="red">오류</Tag>,
    }[v] ?? <Tag>{v}</Tag>),
  },
  { title: '클립 수', dataIndex: 'clips', width: 90, align: 'right', render: v => v != null ? `${v}건` : '-' },
  { title: '메시지', dataIndex: 'message', render: v => v ?? '' },
]

// ── CML 탭 ───────────────────────────────────────────────────────────────────
function CmlTab() {
  const [fileList,   setFileList]   = useState([])
  const [result,     setResult]     = useState(null)
  const [scanResult, setScanResult] = useState(null)
  const [loading,    setLoading]    = useState(false)
  const [scanning,   setScanning]   = useState(false)

  const upload = async () => {
    if (!fileList[0]) { message.warning('파일을 선택하세요.'); return }
    setLoading(true)
    try {
      const res = await ingestCml(fileList[0].originFileObj)
      setResult(res)
      setFileList([])
      message.success(res.message)
    } catch (e) {
      message.error(e.response?.data?.detail || '처리 실패')
    } finally { setLoading(false) }
  }

  const scan = async () => {
    setScanning(true)
    setScanResult(null)
    try {
      const res = await scanCmlDir()
      setScanResult(res)
      message.success(res.message)
    } catch (e) {
      message.error(e.response?.data?.detail || '스캔 실패')
    } finally { setScanning(false) }
  }

  return (
    <Card title="CML 매핑 파일 적재">
      <Alert message="DDR1 로그 적재 전에 반드시 먼저 실행하세요." type="warning" showIcon style={{ marginBottom: 16 }} />

      {/* 디렉터리 전체 스캔 */}
      <div style={{ background: '#f6ffed', border: '1px solid #b7eb8f',
                    borderRadius: 8, padding: 16, marginBottom: 20 }}>
        <div style={{ fontWeight: 600, marginBottom: 8 }}>
          <FolderOpenOutlined style={{ marginRight: 6, color: '#52c41a' }} />
          디렉터리 전체 스캔 적재
          <Tooltip title="환경설정에서 지정한 cml_path 폴더의 모든 .cml 파일을 자동으로 찾아 적재합니다.">
            <InfoCircleOutlined style={{ marginLeft: 8, color: '#aaa' }} />
          </Tooltip>
        </div>
        <Button
          style={{ borderColor: '#52c41a', color: '#52c41a' }}
          icon={<SyncOutlined />}
          onClick={scan}
          loading={scanning}
          size="large"
        >
          전체 스캔 적재 시작
        </Button>
        {scanResult && (
          <div style={{ marginTop: 16 }}>
            <Alert
              type={scanResult.total_clips > 0 ? 'success' : 'info'}
              message={scanResult.message}
              description={`총 ${scanResult.total_clips}건 클립 적재 완료`}
              showIcon style={{ marginBottom: 12 }}
            />
            <Table
              dataSource={scanResult.files}
              columns={CML_SCAN_COLS}
              rowKey="file"
              size="small"
              pagination={false}
              scroll={{ y: 200 }}
            />
          </div>
        )}
      </div>

      <Divider>또는 파일 직접 업로드</Divider>

      <Upload fileList={fileList} beforeUpload={() => false}
        onChange={({ fileList: fl }) => setFileList(fl.slice(-1))} accept=".cml" maxCount={1}>
        <Button icon={<UploadOutlined />}>파일 선택 (.cml)</Button>
      </Upload>
      <Button type="default" onClick={upload} style={{ marginTop: 12 }} loading={loading} disabled={!fileList[0]}>
        업로드 및 적재
      </Button>
      {result && (
        <Alert type="success" message={result.message}
          description={`처리된 클립: ${result.total_clips}건`}
          showIcon style={{ marginTop: 12 }} />
      )}
    </Card>
  )
}

// ── APST 탭 ──────────────────────────────────────────────────────────────────
function ApstTab({ onDone }) {
  const [fileList, setFileList]   = useState([])
  const [scanResult, setScanResult] = useState(null)
  const [loading, setLoading]     = useState(false)
  const [scanning, setScanning]   = useState(false)

  const upload = async () => {
    if (!fileList[0]) { message.warning('파일을 선택하세요.'); return }
    setLoading(true)
    try {
      const res = await ingestApst(fileList[0].originFileObj)
      message.success(`${res.message} (${res.inserted}건)`)
      setFileList([])
      onDone()
    } catch (e) {
      message.error(e.response?.data?.detail || '처리 실패')
    } finally { setLoading(false) }
  }

  const scan = async () => {
    setScanning(true)
    setScanResult(null)
    try {
      const res = await scanApstDir()
      setScanResult(res)
      onDone()
      message.success(res.message)
    } catch (e) {
      message.error(e.response?.data?.detail || '스캔 실패')
    } finally { setScanning(false) }
  }

  return (
    <Card title="APST 자동 송출 파일 적재">
      {/* 디렉터리 전체 스캔 */}
      <div style={{ background: '#f0f7ff', border: '1px solid #91caff',
                    borderRadius: 8, padding: 16, marginBottom: 20 }}>
        <div style={{ fontWeight: 600, marginBottom: 8 }}>
          <FolderOpenOutlined style={{ marginRight: 6, color: '#1677ff' }} />
          디렉터리 전체 스캔 적재
          <Tooltip title="환경설정에서 지정한 apst_dir 폴더의 모든 .apst 파일을 자동으로 찾아 적재합니다. 이미 처리된 파일은 건너뜁니다.">
            <InfoCircleOutlined style={{ marginLeft: 8, color: '#aaa' }} />
          </Tooltip>
        </div>
        <Button
          type="primary"
          icon={<SyncOutlined />}
          onClick={scan}
          loading={scanning}
          size="large"
        >
          전체 스캔 적재 시작
        </Button>
        <ScanResult result={scanResult} />
      </div>

      <Divider>또는 파일 직접 업로드</Divider>

      <Upload fileList={fileList} beforeUpload={() => false}
        onChange={({ fileList: fl }) => setFileList(fl.slice(-1))} accept=".apst" maxCount={1}>
        <Button icon={<UploadOutlined />}>파일 선택 (.apst)</Button>
      </Upload>
      <Button type="default" onClick={upload} style={{ marginTop: 12 }}
        loading={loading} disabled={!fileList[0]}>
        업로드 및 적재
      </Button>
    </Card>
  )
}

// ── DDR1 탭 ──────────────────────────────────────────────────────────────────
function Ddr1Tab({ onDone }) {
  const [fileList, setFileList]   = useState([])
  const [date, setDate]           = useState(null)
  const [scanResult, setScanResult] = useState(null)
  const [loading, setLoading]     = useState(false)
  const [scanning, setScanning]   = useState(false)
  const [resyncing, setResyncing] = useState(false)
  const [resyncResult, setResyncResult] = useState(null)

  const upload = async () => {
    if (!fileList[0]) { message.warning('파일을 선택하세요.'); return }
    if (!date)        { message.warning('날짜를 선택하세요.'); return }
    setLoading(true)
    try {
      const res = await ingestDdr1(fileList[0].originFileObj, date.format('YYYY-MM-DD'))
      message.success(`${res.message} (${res.inserted}건)`)
      setFileList([])
      onDone()
    } catch (e) {
      message.error(e.response?.data?.detail || '처리 실패')
    } finally { setLoading(false) }
  }

  const scan = async () => {
    setScanning(true)
    setScanResult(null)
    try {
      const res = await scanDdr1Dir()
      setScanResult(res)
      onDone()
      message.success(res.message)
    } catch (e) {
      message.error(e.response?.data?.detail || '스캔 실패')
    } finally { setScanning(false) }
  }

  const runResync = async () => {
    setResyncing(true)
    setResyncResult(null)
    try {
      const res = await resyncManual()
      setResyncResult(res)
      onDone()
      message.success(res.message)
    } catch (e) {
      message.error(e.response?.data?.detail || '재추출 실패')
    } finally { setResyncing(false) }
  }

  return (
    <Card title="DDR1 수동 송출 파일 적재">
      {/* 수동 송출 재추출 */}
      <div style={{ background: '#f0f5ff', border: '1px solid #adc6ff',
                    borderRadius: 8, padding: 16, marginBottom: 20 }}>
        <div style={{ fontWeight: 600, marginBottom: 4 }}>
          수동 송출 재추출
          <span style={{ fontSize: 12, color: '#888', fontWeight: 400, marginLeft: 8 }}>
            DDR1 로그가 있는 모든 날짜의 누락 구간을 복구
          </span>
          <Tooltip title="DDR1 로그가 있는 모든 날짜의 APST 수동 송출(MM=DDR1) 구간을 다시 추출합니다. 이미 적재된 구간은 건너뛰므로, 과거에 일부만 적재된 날짜의 누락 구간도 새로 복구됩니다. 달력/상세조회에 수동 송출 내역이 누락된 경우 이 버튼을 누르세요.">
            <InfoCircleOutlined style={{ marginLeft: 8, color: '#aaa' }} />
          </Tooltip>
        </div>
        <div style={{ fontSize: 12, color: '#888', marginBottom: 10 }}>
          이미 적재된 구간은 건너뜁니다 (구간 단위 중복검사, 중복 없음)
        </div>
        <Button
          style={{ borderColor: '#2f54eb', color: '#2f54eb' }}
          icon={<SyncOutlined />}
          onClick={runResync}
          loading={resyncing}
          size="large"
        >
          수동 송출 재추출
        </Button>
        {resyncResult && (
          <Alert
            type={resyncResult.total_inserted > 0 ? 'success' : 'info'}
            message={resyncResult.message}
            showIcon
            style={{ marginTop: 12 }}
          />
        )}
      </div>

      {/* 디렉터리 전체 스캔 */}
      <div style={{ background: '#fff7e6', border: '1px solid #ffd591',
                    borderRadius: 8, padding: 16, marginBottom: 20 }}>
        <div style={{ fontWeight: 600, marginBottom: 8 }}>
          <FolderOpenOutlined style={{ marginRight: 6, color: '#fa8c16' }} />
          디렉터리 전체 스캔 적재
          <Tooltip title="파일명에서 날짜(YYYYMMDD)를 자동 추출합니다. 날짜를 찾을 수 없는 파일은 건너뜁니다.">
            <InfoCircleOutlined style={{ marginLeft: 8, color: '#aaa' }} />
          </Tooltip>
        </div>
        <Button
          style={{ borderColor: '#fa8c16', color: '#fa8c16' }}
          icon={<SyncOutlined />}
          onClick={scan}
          loading={scanning}
          size="large"
        >
          전체 스캔 적재 시작
        </Button>
        <ScanResult result={scanResult} />
      </div>

      <Divider>또는 파일 직접 업로드</Divider>

      <DatePicker placeholder="로그 날짜 선택" onChange={setDate}
        value={date} format="YYYY-MM-DD" style={{ marginBottom: 12 }} />
      <br />
      <Upload fileList={fileList} beforeUpload={() => false}
        onChange={({ fileList: fl }) => setFileList(fl.slice(-1))} accept=".log,.Log" maxCount={1}>
        <Button icon={<UploadOutlined />}>파일 선택 (.Log)</Button>
      </Upload>
      <Button type="default" onClick={upload} style={{ marginTop: 12 }}
        loading={loading} disabled={!fileList[0] || !date}>
        업로드 및 적재
      </Button>
    </Card>
  )
}

// ── 메인 ─────────────────────────────────────────────────────────────────────
export default function IngestPage() {
  const [refreshKey, setRefreshKey] = useState(0)
  const refresh = () => setRefreshKey(k => k + 1)

  const TABS = [
    { key: 'cml',  label: 'CML 매핑',        children: <CmlTab /> },
    { key: 'apst', label: 'APST 자동 송출',  children: <ApstTab onDone={refresh} /> },
    { key: 'ddr1', label: 'DDR1 수동 송출',  children: <Ddr1Tab onDone={refresh} /> },
  ]

  return (
    <div style={{ padding: 24 }}>
      <Alert
        message="파일 적재 순서"
        description="① CML 파일 → ② APST 파일 → ③ DDR1 로그 순서로 적재하세요."
        type="warning" showIcon style={{ marginBottom: 16 }}
      />

      {/* FTP 파일 가져오기 */}
      <FtpCard />

      {/* 실시간 감시 카드 (선택 사용) */}
      <WatcherCard />

      {/* DB 적재 현황 */}
      <StatusCard key={refreshKey} />

      {/* 수동 적재 탭 */}
      <Tabs items={TABS} />
    </div>
  )
}
