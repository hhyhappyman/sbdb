import React, { useState, useEffect } from 'react'
import {
  Card, Row, Col, DatePicker, Input, Select, Button,
  Table, Tag, Popconfirm, message, Divider, Space,
} from 'antd'
import {
  PlusOutlined, DeleteOutlined, SaveOutlined,
  UserOutlined, GlobalOutlined, ClockCircleOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import {
  getClientIp, createManualEntry, listManualEntries, deleteManualEntry,
  getCampaignWorker, setCampaignWorker,
} from '../api'

// 소재종류 옵션
const CONTENT_TYPES = ['흘림자막', '공익재난', '캠페인']
// 흘림자막일 때 소재제목 옵션
const SUBTITLE_TITLES = ['UHD방송홍보', 'TV직접수신', '시청자의견', '기타']

const TYPE_COLOR = { '흘림자막': 'blue', '공익재난': 'volcano', '캠페인': 'green' }

// 사용자가 직접 입력한 문자열을 시간(dayjs)으로 변환.
// '053000'→05:30:00, '0530'→05:30:00, '530'→05:30:00, '5:30:0'/'05:30:00'도 허용.
// 유효하지 않으면 null 반환.
function parseTimeInput(raw) {
  if (!raw) return null
  const s = String(raw).trim()
  let h, m, sec
  if (s.includes(':')) {
    const p = s.split(':')
    h = parseInt(p[0], 10); m = parseInt(p[1] || '0', 10); sec = parseInt(p[2] || '0', 10)
  } else {
    const d = s.replace(/\D/g, '')
    if (!d) return null
    if (d.length <= 2)      { h = parseInt(d, 10); m = 0; sec = 0 }
    else if (d.length <= 4) { h = parseInt(d.slice(0, d.length - 2), 10); m = parseInt(d.slice(-2), 10); sec = 0 }
    else                    { h = parseInt(d.slice(0, d.length - 4), 10); m = parseInt(d.slice(-4, -2), 10); sec = parseInt(d.slice(-2), 10) }
  }
  if ([h, m, sec].some(n => Number.isNaN(n))) return null
  if (h < 0 || h > 23 || m < 0 || m > 59 || sec < 0 || sec > 59) return null
  return dayjs().hour(h).minute(m).second(sec).millisecond(0)
}

export default function WorkerPage() {
  // ── 페이지 공통 정보 (한 번만 입력) ──
  const [date,        setDate]        = useState(dayjs())
  const [workerName,  setWorkerName]  = useState('')
  const [campWorker,  setCampWorker]  = useState('')
  const [clientIp,    setClientIp]    = useState('')
  const [now,         setNow]         = useState(dayjs().format('YYYY-MM-DD HH:mm:ss'))

  // ── 입력 폼 ──
  const [contentType, setContentType] = useState('흘림자막')
  const [time,        setTime]        = useState(null)
  const [timeText,    setTimeText]    = useState('')   // 송출시간 직접 입력 문자열
  const [program,     setProgram]     = useState('')
  const [title,       setTitle]       = useState('')

  // ── 목록 ──
  const [entries, setEntries] = useState([])
  const [loading, setLoading] = useState(false)
  const [adding,  setAdding]  = useState(false)

  const dateStr = date?.format('YYYY-MM-DD')

  // 접속 IP 조회 + 시계 갱신
  useEffect(() => {
    getClientIp().then(r => setClientIp(r.ip)).catch(() => {})
    const timer = setInterval(() => setNow(dayjs().format('YYYY-MM-DD HH:mm:ss')), 1000)
    return () => clearInterval(timer)
  }, [])

  // 날짜 변경 시 목록 + 공익광고 근무자 로드
  useEffect(() => {
    if (!dateStr) return
    loadEntries()
    getCampaignWorker(dateStr).then(r => setCampWorker(r.worker_name || '')).catch(() => {})
  }, [dateStr])

  const loadEntries = async () => {
    if (!dateStr) return
    setLoading(true)
    try {
      const res = await listManualEntries(dateStr)
      setEntries(res.entries)
    } catch {
      message.error('목록을 불러오지 못했습니다.')
    } finally {
      setLoading(false)
    }
  }

  // 소재종류 변경 시 소재제목 초기화
  const onTypeChange = (v) => {
    setContentType(v)
    setTitle('')
  }

  // 입력창에서 벗어나거나(탭/클릭) 엔터를 누르면 숫자를 시간으로 확정
  const commitTime = () => {
    if (!timeText.trim()) { setTime(null); return null }
    const parsed = parseTimeInput(timeText)
    if (parsed) {
      setTime(parsed)
      setTimeText(parsed.format('HH:mm:ss'))   // 확정된 형식으로 표시 정리
      return parsed
    }
    message.warning('송출시간 형식이 올바르지 않습니다. 예: 053000, 0530, 5:30:00')
    return null
  }

  const addEntry = async () => {
    // 아직 확정되지 않은 입력이 있으면 확정 시도
    const effTime = time || parseTimeInput(timeText)

    if (!dateStr)        { message.warning('방송일자를 선택하세요.'); return }
    if (!workerName.trim()) { message.warning('근무자 이름을 입력하세요.'); return }
    if (!effTime)        { message.warning('송출시간을 입력하세요. (예: 053000)'); return }
    if (!title.trim())   { message.warning('소재제목을 입력/선택하세요.'); return }

    setAdding(true)
    try {
      await createManualEntry({
        broadcast_date: dateStr,
        content_type:   contentType,
        broadcast_time: effTime.format('HH:mm:ss'),
        program_name:   program.trim(),
        item_title:     title.trim(),
        worker_name:    workerName.trim(),
      })
      message.success('입력되었습니다.')
      // 폼 일부 초기화 (소재종류/근무자는 유지)
      setTime(null); setTimeText(''); setProgram(''); setTitle('')
      loadEntries()
    } catch (e) {
      message.error(e.response?.data?.detail || '입력 실패')
    } finally {
      setAdding(false)
    }
  }

  const removeEntry = async (id) => {
    try {
      await deleteManualEntry(id)
      message.success('삭제되었습니다.')
      loadEntries()
    } catch (e) {
      message.error(e.response?.data?.detail || '삭제 실패')
    }
  }

  const saveCampWorker = async () => {
    if (!dateStr) { message.warning('방송일자를 선택하세요.'); return }
    try {
      await setCampaignWorker(dateStr, campWorker.trim())
      message.success('공익광고 근무자가 저장되었습니다.')
    } catch (e) {
      message.error(e.response?.data?.detail || '저장 실패')
    }
  }

  const COLS = [
    { title: '송출시간', dataIndex: 'broadcast_time', width: 110, align: 'center' },
    {
      title: '소재종류', dataIndex: 'content_type', width: 100, align: 'center',
      render: v => <Tag color={TYPE_COLOR[v]}>{v}</Tag>,
    },
    { title: '프로그램명', dataIndex: 'program_name', ellipsis: true },
    { title: '소재제목', dataIndex: 'item_title', ellipsis: true },
    { title: '급지', dataIndex: 'grade', width: 60, align: 'center', render: v => v || '-' },
    { title: '근무자', dataIndex: 'worker_name', width: 90, align: 'center', render: v => v || '-' },
    {
      title: '삭제', key: 'del', width: 60, align: 'center',
      render: (_, r) => (
        <Popconfirm title="삭제하시겠습니까?" onConfirm={() => removeEntry(r.id)} okText="삭제" cancelText="취소">
          <Button type="text" danger size="small" icon={<DeleteOutlined />} />
        </Popconfirm>
      ),
    },
  ]

  return (
    <div style={{ padding: 24 }}>
      {/* 근무 정보 카드 */}
      <Card title="근무 정보" style={{ marginBottom: 16 }}>
        <Row gutter={[16, 16]} align="middle">
          <Col>
            <div style={{ fontSize: 12, color: '#888', marginBottom: 4 }}>방송일자</div>
            <DatePicker value={date} onChange={setDate} format="YYYY-MM-DD" allowClear={false} />
          </Col>
          <Col>
            <div style={{ fontSize: 12, color: '#888', marginBottom: 4 }}>근무자 이름</div>
            <Input
              prefix={<UserOutlined style={{ color: '#bbb' }} />}
              value={workerName}
              onChange={e => setWorkerName(e.target.value)}
              placeholder="예: 홍길동"
              style={{ width: 160 }}
            />
          </Col>
          <Col>
            <div style={{ fontSize: 12, color: '#888', marginBottom: 4 }}>
              공익광고 송출 근무자
            </div>
            <Space.Compact>
              <Input
                prefix={<UserOutlined style={{ color: '#bbb' }} />}
                value={campWorker}
                onChange={e => setCampWorker(e.target.value)}
                placeholder="공익광고 담당 근무자"
                style={{ width: 180 }}
              />
              <Button icon={<SaveOutlined />} onClick={saveCampWorker}>저장</Button>
            </Space.Compact>
          </Col>
        </Row>

        <Divider style={{ margin: '16px 0' }} />

        <Row gutter={32}>
          <Col>
            <span style={{ fontSize: 12, color: '#888' }}>
              <ClockCircleOutlined style={{ marginRight: 6 }} />입력일시
            </span>
            <div style={{ fontWeight: 600, color: '#1677ff' }}>{now}</div>
          </Col>
          <Col>
            <span style={{ fontSize: 12, color: '#888' }}>
              <GlobalOutlined style={{ marginRight: 6 }} />접속 IP
            </span>
            <div style={{ fontWeight: 600, color: '#1677ff' }}>{clientIp || '조회 중...'}</div>
          </Col>
        </Row>
      </Card>

      {/* 입력 폼 카드 */}
      <Card title="송출 내역 입력" style={{ marginBottom: 16 }}>
        <Row gutter={[12, 12]} align="bottom">
          <Col>
            <div style={{ fontSize: 12, color: '#888', marginBottom: 4 }}>소재종류</div>
            <Select value={contentType} onChange={onTypeChange} style={{ width: 120 }}
              options={CONTENT_TYPES.map(t => ({ value: t, label: t }))} />
          </Col>
          <Col>
            <div style={{ fontSize: 12, color: '#888', marginBottom: 4 }}>송출시간</div>
            <Input
              value={timeText}
              onChange={e => setTimeText(e.target.value)}
              onBlur={commitTime}
              onPressEnter={commitTime}
              placeholder="예: 053000"
              style={{ width: 120 }}
              prefix={<ClockCircleOutlined style={{ color: '#bbb' }} />}
            />
          </Col>
          <Col>
            <div style={{ fontSize: 12, color: '#888', marginBottom: 4 }}>프로그램명</div>
            <Input value={program} onChange={e => setProgram(e.target.value)}
              placeholder="프로그램명" style={{ width: 200 }} />
          </Col>
          <Col>
            <div style={{ fontSize: 12, color: '#888', marginBottom: 4 }}>소재제목</div>
            {contentType === '흘림자막' ? (
              <Select value={title || undefined} onChange={setTitle} style={{ width: 180 }}
                placeholder="선택"
                options={SUBTITLE_TITLES.map(t => ({ value: t, label: t }))} />
            ) : (
              <Input value={title} onChange={e => setTitle(e.target.value)}
                placeholder="소재제목" style={{ width: 220 }} />
            )}
          </Col>
          <Col>
            <Button type="primary" icon={<PlusOutlined />} onClick={addEntry} loading={adding}>
              추가
            </Button>
          </Col>
        </Row>
      </Card>

      {/* 목록 카드 */}
      <Card title={
        <span>
          {dateStr} 입력 목록
          <span style={{ marginLeft: 12, fontSize: 13, color: '#1677ff' }}>총 {entries.length}건</span>
        </span>
      }>
        <Table
          dataSource={entries}
          columns={COLS}
          rowKey="id"
          size="small"
          loading={loading}
          pagination={{ pageSize: 20, showTotal: t => `총 ${t}건` }}
          locale={{ emptyText: '입력된 송출 내역이 없습니다.' }}
        />
      </Card>
    </div>
  )
}
