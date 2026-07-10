import React, { useState, useEffect, useMemo } from 'react'
import {
  Card, Tabs, Row, Col, Select, Button, Table, DatePicker,
  Statistic, Spin, message, Input, Modal, Tag,
} from 'antd'
import { FilePdfOutlined, FileWordOutlined, FileExcelOutlined, SearchOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import axios from 'axios'
import { getMonthlyReport, getMonthlyPdfUrl } from '../api'
import { getStore, setStore } from '../store'
import { downloadXLSX } from '../xlsx'

const { Option } = Select
const api = axios.create({ baseURL: '/api' })

const getDailyPdfUrl    = (date) => `/api/report/daily/pdf?date=${date}`
const getDisasterPdfUrl = (date) => `/api/report/disaster/pdf?date=${date}`

// ── 소재별 월 리포트 탭 ────────────────────────────────────────────────────────
const MONTHLY_STORE = 'report_monthly'

function MonthlyTab() {
  const now  = dayjs()
  const saved = getStore(MONTHLY_STORE)

  const [item,    setItem]    = useState(saved.item    ?? '')
  const [year,    setYear]    = useState(saved.year    ?? now.year())
  const [month,   setMonth]   = useState(saved.month   ?? now.month() + 1)
  const [data,    setData]    = useState(saved.data    ?? null)
  const [loading, setLoading] = useState(false)

  // 소재명 검색 모달
  const [modalOpen,    setModalOpen]    = useState(false)
  const [searchQuery,  setSearchQuery]  = useState('')
  const [searchResult, setSearchResult] = useState([])
  const [searchLoading, setSearchLoading] = useState(false)
  const [selectedKeys, setSelectedKeys] = useState([])
  const [modalType,    setModalType]    = useState('캠페인')

  // 저장(송출 내용 입력) 모달
  const [saveOpen,    setSaveOpen]    = useState(false)
  const [saveFmt,     setSaveFmt]     = useState('pdf')
  const [saveContent, setSaveContent] = useState('')

  const YEARS  = Array.from({ length: 5 }, (_, i) => now.year() - i)
  const MONTHS = Array.from({ length: 12 }, (_, i) => i + 1)

  const save = (patch) =>
    setStore(MONTHLY_STORE, { item, year, month, data, ...patch })

  const fetchItems = async (q, type) => {
    const params = { q: q.trim(), limit: 50 }
    if (type) params.type = type
    const res = await api.get('/items', { params })
    return res.data
  }

  const selectItem = (name) => {
    setItem(name)
    setModalOpen(false)
    setSelectedKeys([])
    save({ item: name })
    doReport(name)
  }

  const doReport = async (itemName) => {
    setLoading(true)
    try {
      const res = await getMonthlyReport(itemName.trim(), year, month)
      setData(res)
      save({ item: itemName, year, month, data: res })
    } catch (e) {
      message.error(e.response?.data?.detail || '조회 실패')
    } finally {
      setLoading(false)
    }
  }

  const doReportMulti = async (names) => {
    console.log('[doReportMulti] names:', names, 'year:', year, 'month:', month)
    setLoading(true)
    setModalOpen(false)
    try {
      const results = await Promise.allSettled(
        names.map(n => getMonthlyReport(n.trim(), year, month))
      )
      console.log('[doReportMulti] results:', results)
      const dayMap = new Map()
      let total = 0
      for (const r of results) {
        if (r.status === 'rejected') continue
        const res = r.value
        total += res.total
        for (const d of res.days) {
          const existing = dayMap.get(d.date)
          if (existing) {
            existing.times = [...existing.times, ...d.times].sort()
            existing.count += d.count
          } else {
            dayMap.set(d.date, { ...d, times: [...d.times] })
          }
        }
      }
      const merged = {
        item_name: names.join(', '),
        year, month, total,
        days: [...dayMap.values()].sort((a, b) => a.date.localeCompare(b.date)),
      }
      setItem(names.join(', '))
      setData(merged)
      save({ item: names.join(', '), data: merged })
      if (total === 0) message.warning('선택한 소재의 해당 월 송출 내역이 없습니다.')
    } catch (e) {
      message.error('조회 실패: ' + (e.message || ''))
    } finally {
      setLoading(false)
    }
  }

  const search = async () => {
    const q = item.trim()
    if (!q) { message.warning('소재명을 입력하세요.'); return }

    // 다중 소재가 입력된 경우 바로 멀티 조회 재실행
    if (q.includes(', ')) {
      const names = q.split(', ').map(n => n.trim()).filter(Boolean)
      doReportMulti(names)
      return
    }

    setSearchLoading(true)
    try {
      const candidates = await fetchItems(q, modalType)
      if (candidates.length === 1) {
        // 결과가 정확히 1개일 때만 바로 조회
        doReport(candidates[0].item_name)
        return
      }
      setSearchQuery(q)
      setSearchResult(candidates)
      setSelectedKeys([])
      setModalOpen(true)
      if (candidates.length === 0) {
        message.warning(`'${q}'를 포함하는 소재가 없습니다.`)
      }
    } catch {
      message.error('소재 검색 실패')
    } finally {
      setSearchLoading(false)
    }
  }

  const searchInModal = async (q, type) => {
    if (!q.trim()) return
    setSearchLoading(true)
    try {
      const res = await fetchItems(q, type ?? modalType)
      setSearchResult(res)
    } catch {
      message.error('소재 검색 실패')
    } finally {
      setSearchLoading(false)
    }
  }

  const handleModalType = (t) => {
    setModalType(t)
    searchInModal(searchQuery, t)
  }

  const isMultiItem = item.includes(', ')

  // 저장 버튼 → '송출 내용' 입력 모달 표시 (기본값 = 검색 소재명)
  const openSave = (fmt) => {
    if (!item.trim()) { message.warning('소재명을 선택하세요.'); return }
    setSaveFmt(fmt)
    setSaveContent(item.trim())
    setSaveOpen(true)
  }

  const confirmSave = () => {
    const content = saveContent.trim() || item.trim()
    const base = saveFmt === 'word' ? '/api/report/word' : '/api/report/pdf'
    const url = `${base}?item=${encodeURIComponent(item.trim())}`
      + `&year=${year}&month=${month}&content=${encodeURIComponent(content)}`
    window.open(url, '_blank')
    setSaveOpen(false)
  }

  const ITEM_SEARCH_COLS = [
    { title: '소재명',   dataIndex: 'item_name',
      sorter: (a, b) => a.item_name.localeCompare(b.item_name),
      render: (v) => <a onClick={() => selectItem(v)}>{v}</a> },
    { title: '종류',     dataIndex: 'content_type_label',  width: 80, align: 'center',
      sorter: (a, b) => (a.content_type_label ?? '').localeCompare(b.content_type_label ?? ''),
      render: v => <Tag color={v === 'ID' ? 'purple' : 'blue'}>{v}</Tag> },
    { title: '총 횟수', dataIndex: 'count',                width: 80, align: 'right',
      sorter: (a, b) => a.count - b.count,
      render: v => `${v}회` },
    { title: '추가 날짜', dataIndex: 'first_added',        width: 110, align: 'center',
      sorter: (a, b) => (a.first_added ?? '').localeCompare(b.first_added ?? ''),
      defaultSortOrder: 'descend',
      render: v => v ? v.slice(0, 10) : '-' },
  ]

  const toHM = (t) => (t ?? '').slice(0, 5)

  const DAY_COLS = [
    { title: '날짜',   dataIndex: 'date',  width: 120 },
    { title: '횟수',   dataIndex: 'count', width: 70, align: 'center', render: v => `${v}회` },
    { title: '송출 시간', dataIndex: 'times', render: ts => ts.map(toHM).join('  /  ') },
  ]

  return (
    <div>
      <Row gutter={8} style={{ marginBottom: 16 }} align="middle" wrap>
        <Col>
          <Select value={modalType} onChange={v => setModalType(v)} style={{ width: 100 }} allowClear placeholder="전체">
            <Option value="캠페인">캠페인</Option>
            <Option value="ID">ID</Option>
          </Select>
        </Col>
        <Col>
          <Input
            value={item}
            onChange={e => { setItem(e.target.value); save({ item: e.target.value }) }}
            placeholder="소재명 입력 후 조회"
            style={{ width: 220 }}
            onPressEnter={search}
            allowClear
          />
        </Col>
        <Col>
          <Select value={year} onChange={v => { setYear(v); save({ year: v }) }} style={{ width: 90 }}>
            {YEARS.map(y => <Option key={y} value={y}>{y}년</Option>)}
          </Select>
        </Col>
        <Col>
          <Select value={month} onChange={v => { setMonth(v); save({ month: v }) }} style={{ width: 80 }}>
            {MONTHS.map(m => <Option key={m} value={m}>{m}월</Option>)}
          </Select>
        </Col>
        <Col>
          <Button
            type="primary"
            icon={<SearchOutlined />}
            onClick={search}
            loading={searchLoading || loading}
          >
            조회
          </Button>
        </Col>
        {data && (
          <>
            <Col>
              <Statistic value={data.total} suffix="회" valueStyle={{ fontSize: 16 }} />
            </Col>
            <Col>
              <Button icon={<FilePdfOutlined />} onClick={() => openSave('pdf')} danger>
                PDF 저장
              </Button>
            </Col>
            <Col>
              <Button icon={<FileWordOutlined />} onClick={() => openSave('word')} style={{ borderColor: '#2b579a', color: '#2b579a' }}>
                Word 저장
              </Button>
            </Col>
          </>
        )}
      </Row>

      <Spin spinning={loading}>
        <Table
          dataSource={data?.days ?? []}
          columns={DAY_COLS}
          rowKey="date"
          size="small"
          pagination={false}
          locale={{ emptyText: data ? `${year}년 ${month}월 송출 내역이 없습니다.` : '소재를 선택하고 조회 버튼을 누르세요.' }}
        />
      </Spin>

      {/* 저장 시 '송출 내용' 입력 모달 */}
      <Modal
        title={`${saveFmt === 'word' ? 'Word' : 'PDF'} 저장 — 송출 내용 입력`}
        open={saveOpen}
        onOk={confirmSave}
        onCancel={() => setSaveOpen(false)}
        okText="저장"
        cancelText="취소"
        width={460}
      >
        <div style={{ fontSize: 13, color: '#888', marginBottom: 8 }}>
          리포트의 '송출 내용' 칸에 표시할 문구입니다. (기본값: 검색한 소재명)
        </div>
        <Input
          value={saveContent}
          onChange={e => setSaveContent(e.target.value)}
          onPressEnter={confirmSave}
          placeholder="송출 내용"
          autoFocus
        />
      </Modal>

      <Modal
        title={
          <span>
            소재 선택
            <span style={{ fontSize: 12, color: '#aaa', fontWeight: 400, marginLeft: 10 }}>
              '{searchQuery}' 와 일치하는 소재명이 없어 유사 목록을 표시합니다.
            </span>
          </span>
        }
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        footer={null}
        width={620}
      >
        <Row gutter={8} style={{ marginBottom: 12 }}>
          <Col>
            <Select value={modalType} onChange={handleModalType} style={{ width: 100 }} allowClear placeholder="전체">
              <Option value="캠페인">캠페인</Option>
              <Option value="ID">ID</Option>
            </Select>
          </Col>
          <Col flex="auto">
            <Input
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              onPressEnter={() => searchInModal(searchQuery)}
              placeholder="소재명 일부를 입력하세요"
              autoFocus
            />
          </Col>
          <Col>
            <Button
              type="primary"
              icon={<SearchOutlined />}
              onClick={() => searchInModal(searchQuery)}
              loading={searchLoading}
            >
              검색
            </Button>
          </Col>
        </Row>
        <Spin spinning={searchLoading}>
          <Table
            dataSource={searchResult}
            columns={ITEM_SEARCH_COLS}
            rowKey="item_name"
            size="small"
            pagination={{ pageSize: 10, size: 'small' }}
            scroll={{ y: 320 }}
            rowSelection={{
              selectedRowKeys: selectedKeys,
              onChange: setSelectedKeys,
            }}
            locale={{ emptyText: '검색어를 입력하고 검색 버튼을 누르세요.' }}
          />
        </Spin>
        <Row justify="space-between" align="middle" style={{ marginTop: 8 }}>
          <Col style={{ fontSize: 12, color: '#aaa' }}>
            * 소재명을 클릭하면 그 소재만 바로 조회됩니다. 체크박스로 여러 개를 선택한 뒤
            아래 버튼으로 한번에 조회할 수 있습니다.
          </Col>
        </Row>
        <Row justify="end" style={{ marginTop: 8 }}>
          <Button
            type="primary"
            disabled={selectedKeys.length === 0}
            onClick={() => doReportMulti(selectedKeys)}
          >
            선택 {selectedKeys.length}건 조회
          </Button>
        </Row>
      </Modal>
    </div>
  )
}

// ── 일별 리포트 탭 ─────────────────────────────────────────────────────────────
const DAILY_STORE = 'report_daily'

const DAILY_COLS = [
  { title: '시간',    dataIndex: 'broadcast_time_display', width: 90, align: 'center',
    render: (v, r) => v || r.broadcast_time },
  { title: '프로그램', dataIndex: 'program_block',  width: 160 },
  {
    title: '소재종류', dataIndex: 'content_type_label', width: 90, align: 'center',
    // 행 음영으로 소재종류를 구분하므로 글자 색상(Tag)은 사용하지 않음
    render: v => v || '',
  },
  { title: '소재 제목', dataIndex: 'item_name_raw',  ellipsis: true },
]

// 방송운행표 화면 행 음영/굵은 선 스타일 (PDF/Word 저장본과 동일하게 표시)
const DAILY_ROW_STYLE = `
  .daily-report-wrap .ant-table-thead > tr > th { border-top: 2px solid #555 !important; border-bottom: 2px solid #555 !important; }
  .daily-report-wrap .ant-table-tbody > tr.daily-row-prog > td { background: #DCE6F1 !important; }
  .daily-report-wrap .ant-table-tbody > tr.daily-row-ad > td { background: #E2EFDA !important; }
  .daily-report-wrap .ant-table-tbody > tr.daily-row-prog:hover > td { background: #DCE6F1 !important; }
  .daily-report-wrap .ant-table-tbody > tr.daily-row-ad:hover > td { background: #E2EFDA !important; }
  .daily-report-wrap .ant-table-tbody > tr.daily-row-boundary > td { border-top: 2px solid #555 !important; }
  .daily-report-wrap .ant-table-tbody > tr:first-child > td { border-top: 2px solid #555 !important; }
  .daily-report-wrap .ant-table-tbody > tr:last-child > td { border-bottom: 2px solid #555 !important; }
`

// 각 행에 음영/구분선 CSS 클래스를 계산해 붙인다.
function _dailyRowClass(items) {
  return items.map((it, i) => {
    const cls = []
    const lbl = it.content_type_label
    const prog = it.program_block || ''
    // 첫부분 '방송순서 안내'는 프로그램이어도 하늘색 음영 제외
    if (lbl === '프로그램' && !prog.includes('방송순서')) cls.push('daily-row-prog')
    else if (lbl === '광고' || lbl === '광고그룹') cls.push('daily-row-ad')
    // 프로그램(program_block)이 바뀌는 지점 → 위쪽 굵은 구분선
    // (방송종료 안내 시작도 program_block 변경으로 처리됨)
    const prev = i > 0 ? items[i - 1] : null
    if (prev && (prev.program_block || '') !== (it.program_block || ''))
      cls.push('daily-row-boundary')
    return { ...it, _rowClass: cls.join(' ') }
  })
}


function DailyTab() {
  const saved = getStore(DAILY_STORE)

  const [date,            setDate]            = useState(saved.date ? dayjs(saved.date) : null)
  const [dailyData,       setDailyData]       = useState(saved.dailyData    ?? null)
  const [loadingDaily,    setLoadingDaily]    = useState(false)

  const save = (patch) =>
    setStore(DAILY_STORE, {
      date: date?.format('YYYY-MM-DD'),
      dailyData, ...patch,
    })

  const loadDaily = async () => {
    if (!date) { message.warning('날짜를 선택하세요.'); return }
    setLoadingDaily(true)
    try {
      const res = await api.get('/report/daily', { params: { date: date.format('YYYY-MM-DD') } })
      setDailyData(res.data)
      save({ date: date.format('YYYY-MM-DD'), dailyData: res.data })
    } catch (e) {
      message.error(e.response?.data?.detail || '조회 실패')
    } finally {
      setLoadingDaily(false)
    }
  }

  const dstr = date?.format('YYYY-MM-DD')

  const styledItems = useMemo(
    () => _dailyRowClass(dailyData?.items || []),
    [dailyData],
  )

  return (
    <div>
      <style>{DAILY_ROW_STYLE}</style>
      <Row gutter={12} align="middle" style={{ marginBottom: 20 }}>
        <Col style={{ fontWeight: 600, color: '#555' }}>날짜</Col>
        <Col>
          <DatePicker
            value={date}
            onChange={d => { setDate(d); save({ date: d?.format('YYYY-MM-DD') }) }}
            format="YYYY-MM-DD"
            size="large"
            placeholder="날짜 선택"
          />
        </Col>
        <Col>
          <Button type="primary" icon={<SearchOutlined />} size="large"
            onClick={loadDaily} loading={loadingDaily}>
            방송 운행표
          </Button>
        </Col>
        <Col>
          <Button icon={<FilePdfOutlined />} size="large" danger disabled={!dailyData}
            onClick={() => window.open(getDailyPdfUrl(dstr), '_blank')}>
            PDF 저장
          </Button>
        </Col>
        <Col>
          <Button icon={<FileWordOutlined />} size="large" disabled={!dailyData}
            style={{ borderColor: '#2b579a', color: '#2b579a' }}
            onClick={() => window.open(`/api/report/daily/word?date=${dstr}`, '_blank')}>
            Word 저장
          </Button>
        </Col>
      </Row>

      {dailyData ? (
        <Card
          title={
            <span>
              <span style={{ fontWeight: 600 }}>{dstr} 방송 운행표</span>
              <span style={{ marginLeft: 12, fontSize: 13, color: '#1677ff' }}>
                총 {dailyData.total}건
              </span>
            </span>
          }
        >
          {dailyData.total === 0 ? (
            <div style={{ textAlign: 'center', padding: '40px 0', color: '#aaa' }}>
              해당 날짜에 SB 내역이 없습니다.
            </div>
          ) : (
            <Table
              className="daily-report-wrap"
              dataSource={styledItems}
              columns={DAILY_COLS}
              rowClassName={r => r._rowClass}
              rowKey={(_, i) => i}
              size="small"
              pagination={false}
              scroll={{ y: 450 }}
            />
          )}
        </Card>
      ) : (
        <div style={{ textAlign: 'center', padding: '60px 0', color: '#bbb' }}>
          날짜를 선택하고 버튼을 눌러 조회하세요.
        </div>
      )}
    </div>
  )
}

// ── 일일 운행표 / 일일 ID 운행표 탭 ────────────────────────────────────────────
const SUMMARY_COLS = [
  {
    title: '소재명', dataIndex: 'item_name',
    sorter: (a, b) => a.item_name.localeCompare(b.item_name),
  },
  {
    title: '총횟수', dataIndex: 'total_count', width: 80, align: 'right',
    sorter: (a, b) => a.total_count - b.total_count,
    defaultSortOrder: 'descend',
    render: v => `${v}회`,
  },
  { title: 'SA', dataIndex: 'sa', width: 60, align: 'right', render: v => v || 0 },
  { title: 'A',  dataIndex: 'a',  width: 60, align: 'right', render: v => v || 0 },
  { title: 'B',  dataIndex: 'b',  width: 60, align: 'right', render: v => v || 0 },
  { title: 'C',  dataIndex: 'c',  width: 60, align: 'right', render: v => v || 0 },
]

function DailySummaryTab({ type, storeKey }) {
  const saved = getStore(storeKey)

  const [date,    setDate]    = useState(saved.date ? dayjs(saved.date) : null)
  const [data,    setData]    = useState(saved.data ?? null)
  const [loading, setLoading] = useState(false)

  const save = (patch) =>
    setStore(storeKey, { date: date?.format('YYYY-MM-DD'), data, ...patch })

  const load = async () => {
    if (!date) { message.warning('날짜를 선택하세요.'); return }
    setLoading(true)
    try {
      const res = await api.get('/report/daily-summary', {
        params: { date: date.format('YYYY-MM-DD'), type },
      })
      setData(res.data)
      save({ date: date.format('YYYY-MM-DD'), data: res.data })
    } catch (e) {
      message.error(e.response?.data?.detail || '조회 실패')
    } finally {
      setLoading(false)
    }
  }

  const accentColor = type === 'ID' ? '#722ed1' : '#1677ff'

  return (
    <div>
      <Row gutter={12} align="middle" style={{ marginBottom: 20 }}>
        <Col style={{ fontWeight: 600, color: '#555' }}>날짜</Col>
        <Col>
          <DatePicker
            value={date}
            onChange={d => { setDate(d); save({ date: d?.format('YYYY-MM-DD') }) }}
            format="YYYY-MM-DD"
            size="large"
            placeholder="날짜 선택"
          />
        </Col>
        <Col>
          <Button
            type="primary"
            icon={<SearchOutlined />}
            size="large"
            onClick={load}
            loading={loading}
            style={{ background: accentColor, borderColor: accentColor }}
          >
            조회
          </Button>
        </Col>
        {data && (
          <>
            <Col>
              <Statistic value={data.total} suffix="회" valueStyle={{ fontSize: 16, color: accentColor }} />
            </Col>
            <Col>
              <Button
                icon={<FilePdfOutlined />}
                danger
                onClick={() => window.open(
                  `/api/report/daily-summary/pdf?date=${date.format('YYYY-MM-DD')}&type=${encodeURIComponent(type)}`,
                  '_blank'
                )}
              >
                PDF 저장
              </Button>
            </Col>
            <Col>
              <Button
                icon={<FileWordOutlined />}
                style={{ borderColor: '#2b579a', color: '#2b579a' }}
                onClick={() => window.open(
                  `/api/report/daily-summary/word?date=${date.format('YYYY-MM-DD')}&type=${encodeURIComponent(type)}`,
                  '_blank'
                )}
              >
                Word 저장
              </Button>
            </Col>
          </>
        )}
      </Row>

      {data ? (
        <Card title={`${date?.format('YYYY-MM-DD')} ${type === 'ID' ? '일일 ID 운행표' : '일일 운행표'}`}>
          {data.items.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '40px 0', color: '#aaa' }}>
              해당 날짜에 {type} 송출 내역이 없습니다.
            </div>
          ) : (
            <Table
              dataSource={data.items}
              columns={SUMMARY_COLS}
              rowKey="item_name"
              size="small"
              pagination={{ pageSize: 30, showTotal: t => `총 ${t}종` }}
              scroll={{ y: 450 }}
            />
          )}
        </Card>
      ) : (
        <div style={{ textAlign: 'center', padding: '60px 0', color: '#bbb' }}>
          날짜를 선택하고 조회 버튼을 누르세요.
        </div>
      )}
    </div>
  )
}

// ── 소재 목록 탭 ──────────────────────────────────────────────────────────────
const ITEM_LIST_PAGE_SIZES = [30, 50, 100]

const ITEM_LIST_COLS = [
  { title: '소재명',        dataIndex: 'item_name',        ellipsis: true,
    sorter: (a, b) => a.item_name.localeCompare(b.item_name) },
  { title: '송출시 소재명', dataIndex: 'item_name_raw',    ellipsis: true,
    sorter: (a, b) => a.item_name_raw.localeCompare(b.item_name_raw) },
  { title: '종류', dataIndex: 'content_type_label', width: 80, align: 'center',
    sorter: (a, b) => (a.content_type_label ?? '').localeCompare(b.content_type_label ?? ''),
    render: v => v ? <Tag color={v === 'ID' ? 'purple' : 'blue'}>{v}</Tag> : '' },
  { title: '추가 날짜', dataIndex: 'added_at', width: 120, align: 'center',
    sorter: (a, b) => (a.added_at ?? '').localeCompare(b.added_at ?? ''),
    defaultSortOrder: 'descend',
    render: v => v ? v.slice(0, 10) : '-' },
]

function ItemListTab() {
  const now = dayjs()
  const [years,    setYears]    = useState([])
  const [selYear,  setSelYear]  = useState(now.year())
  const [selType,  setSelType]  = useState('캠페인')
  const [data,     setData]     = useState([])
  const [loading,  setLoading]  = useState(false)
  const [pageSize, setPageSize] = useState(50)

  const loadYears = async () => {
    try {
      const res = await api.get('/items/years')
      setYears(res.data)
    } catch { /* 무시 */ }
  }

  const load = async (year, type) => {
    setLoading(true)
    try {
      const params = { year }
      if (type) params.type = type
      const res = await api.get('/items/list', { params })
      setData(res.data)
    } catch {
      message.error('소재 목록 조회 실패')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadYears()
    load(now.year(), '캠페인')
  }, [])

  const handleYear = (y) => { setSelYear(y); load(y, selType) }
  const handleType = (t) => { setSelType(t); load(selYear, t) }

  const downloadXlsx = async () => {
    if (!data.length) { message.warning('저장할 데이터가 없습니다.'); return }
    try {
      await downloadXLSX(
        `소재목록-${selYear}.xlsx`,
        ['소재명', '송출시 소재명', '종류', '추가 날짜'],
        data.map(r => [
          r.item_name, r.item_name_raw, r.content_type_label,
          (r.added_at || '').slice(0, 10),
        ]),
        '소재목록',
      )
    } catch { message.error('엑셀 저장 실패') }
  }

  return (
    <div>
      <Row gutter={12} align="middle" style={{ marginBottom: 16 }}>
        <Col style={{ fontWeight: 600, color: '#555' }}>추가 연도</Col>
        <Col>
          <Select value={selYear} onChange={handleYear} style={{ width: 100 }}>
            {years.map(y => <Option key={y} value={y}>{y}년</Option>)}
          </Select>
        </Col>
        <Col style={{ fontWeight: 600, color: '#555' }}>종류</Col>
        <Col>
          <Select value={selType} onChange={handleType} style={{ width: 100 }} allowClear placeholder="전체">
            <Option value="캠페인">캠페인</Option>
            <Option value="ID">ID</Option>
          </Select>
        </Col>
        <Col>
          <span style={{ color: '#888', fontSize: 13 }}>총 {data.length}종</span>
        </Col>
        <Col>
          <Button icon={<FileExcelOutlined />} onClick={downloadXlsx} disabled={!data.length}
            style={{ borderColor: '#217346', color: '#217346' }}>
            엑셀 저장
          </Button>
        </Col>
        <Col style={{ marginLeft: 'auto' }}>
          <span style={{ fontSize: 12, color: '#aaa', marginRight: 8 }}>페이지당</span>
          <Select value={pageSize} onChange={setPageSize} size="small" style={{ width: 80 }}>
            {ITEM_LIST_PAGE_SIZES.map(n => <Option key={n} value={n}>{n}개</Option>)}
          </Select>
        </Col>
      </Row>

      <Spin spinning={loading}>
        <Table
          dataSource={data}
          columns={ITEM_LIST_COLS}
          rowKey={(r, i) => r.item_name + i}
          size="small"
          pagination={{
            pageSize,
            showTotal: t => `총 ${t}종`,
            showSizeChanger: false,
          }}
          scroll={{ y: 500 }}
          locale={{ emptyText: '소재 데이터가 없습니다.' }}
        />
      </Spin>
    </div>
  )
}

// ── 흘림자막·공익·재난 송출내역 탭 ─────────────────────────────────────────────
const SUBTITLE_STORE = 'report_subtitle'

const getSubtitlePdfUrl = (date) => `/api/report/subtitle-campaign/pdf?date=${date}`

// 초 → '30"' / "1'09\"" 형식
const fmtDur = (sec) => {
  if (!sec) return ''
  sec = Number(sec)
  if (sec < 60) return `${sec}"`
  return `${Math.floor(sec / 60)}'${String(sec % 60).padStart(2, '0')}"`
}
// 'HH:MM:SS' → 'HH시MM분'
const hhmmKo = (t) => {
  if (!t) return ''
  const p = t.split(':')
  return `${p[0]}시${p[1]}분`
}

// 섹션 표 (제목 + 테이블)
function Section({ title, columns, data }) {
  return (
    <div style={{ marginBottom: 20 }}>
      <div style={{ fontWeight: 600, marginBottom: 8, fontSize: 14 }}>□ {title}</div>
      <Table
        columns={columns}
        dataSource={data.map((r, i) => ({ ...r, _k: i }))}
        rowKey="_k"
        size="small"
        pagination={false}
        bordered
        locale={{ emptyText: '해당 내역 없음' }}
      />
    </div>
  )
}

function SubtitleCampaignTab() {
  const saved = getStore(SUBTITLE_STORE)
  const [date,    setDate]    = useState(saved.date ? dayjs(saved.date) : null)
  const [data,    setData]    = useState(saved.data ?? null)
  const [loading, setLoading] = useState(false)

  const load = async () => {
    if (!date) { message.warning('날짜를 선택하세요.'); return }
    setLoading(true)
    try {
      const res = await api.get('/report/subtitle-campaign', { params: { date: date.format('YYYY-MM-DD') } })
      setData(res.data)
      setStore(SUBTITLE_STORE, { date: date.format('YYYY-MM-DD'), data: res.data })
    } catch (e) {
      message.error(e.response?.data?.detail || '조회 실패')
    } finally {
      setLoading(false)
    }
  }

  // 컬럼 정의
  const timeProgCols = (timeLabel) => [
    { title: timeLabel, dataIndex: 'time', width: 130, align: 'center', render: hhmmKo },
    { title: '프로그램', dataIndex: 'program', align: 'center' },
  ]
  const campCols = [
    { title: '방송시간', dataIndex: 'time', width: 110, align: 'center' },
    { title: '프로그램', dataIndex: 'program', align: 'center' },
    { title: '초수', dataIndex: 'duration', width: 80, align: 'center', render: fmtDur },
    { title: '시급', dataIndex: 'grade', width: 60, align: 'center' },
    { title: '근무자', dataIndex: 'worker', width: 90, align: 'center' },
  ]
  const disCols = [
    { title: '방송시간', dataIndex: 'time', width: 110, align: 'center' },
    { title: '프로그램', dataIndex: 'program', align: 'center' },
    { title: '초수', dataIndex: 'duration', width: 80, align: 'center', render: fmtDur },
    { title: '근무자', dataIndex: 'worker', width: 90, align: 'center' },
  ]

  // UHD: 영상/자막을 좌우로 합쳐 표시
  const uhdCols = [
    { title: '송출시간(영상)', dataIndex: 'vtime', width: 120, align: 'center', render: hhmmKo },
    { title: '프로그램', dataIndex: 'vprog', align: 'center' },
    { title: '송출시간(자막)', dataIndex: 'stime', width: 120, align: 'center', render: hhmmKo },
    { title: '프로그램', dataIndex: 'sprog', align: 'center' },
  ]

  let uhdRows = [], tvRows = [], campRows = [], disRows = []
  if (data) {
    const v = data.uhd_video, s = data.uhd_sub
    const n = Math.max(v.length, s.length)
    for (let i = 0; i < n; i++) {
      uhdRows.push({
        vtime: v[i]?.time || '', vprog: v[i]?.program || '',
        stime: s[i]?.time || '', sprog: s[i]?.program || '',
      })
    }
    // TV직접수신: 2쌍씩
    const tv = data.tv_direct
    for (let i = 0; i < tv.length; i += 2) {
      tvRows.push({
        vtime: tv[i]?.time || '', vprog: tv[i]?.program || '',
        stime: tv[i + 1]?.time || '', sprog: tv[i + 1]?.program || '',
      })
    }
    campRows = data.campaign.map(r => ({ ...r, worker: data.campaign_worker || '' }))
    disRows  = data.disaster.map(r => ({ ...r, worker: data.campaign_worker || '' }))
  }

  return (
    <div>
      <Row gutter={12} align="middle" style={{ marginBottom: 20 }}>
        <Col style={{ fontWeight: 600, color: '#555' }}>날짜</Col>
        <Col>
          <DatePicker value={date} onChange={setDate} format="YYYY-MM-DD" size="large" placeholder="날짜 선택" />
        </Col>
        <Col>
          <Button type="primary" icon={<SearchOutlined />} size="large" onClick={load} loading={loading}>
            조회
          </Button>
        </Col>
        <Col>
          <Button
            icon={<FilePdfOutlined />}
            size="large"
            danger
            disabled={!data}
            onClick={() => window.open(getSubtitlePdfUrl(date?.format('YYYY-MM-DD')), '_blank')}
          >
            PDF 저장
          </Button>
        </Col>
        <Col>
          <Button
            icon={<FileWordOutlined />}
            size="large"
            disabled={!data}
            style={{ borderColor: '#2b579a', color: '#2b579a' }}
            onClick={() => window.open(`/api/report/subtitle-campaign/word?date=${date?.format('YYYY-MM-DD')}`, '_blank')}
          >
            Word 저장
          </Button>
        </Col>
      </Row>

      {!data ? (
        <div style={{ textAlign: 'center', padding: '60px 0', color: '#bbb' }}>
          날짜를 선택하고 조회 버튼을 누르세요.
        </div>
      ) : (
        <Card title={`${data.date} 흘림자막·공익·재난 송출내역`}>
          <Section title="UHD방송홍보"            columns={uhdCols}                    data={uhdRows} />
          <Section title="TV직접수신"             columns={uhdCols}                    data={tvRows} />
          <Section title="시청자의견 (주1회 목요일)" columns={timeProgCols('송출시간(자막)')} data={data.viewer_opinion} />
          <Section title="공익광고 송출내역 (본사 포함)"           columns={campCols} data={campRows} />
          <Section title="재난피해 사전예방 프로그램 송출내역 (본사 포함)" columns={disCols}  data={disRows} />
        </Card>
      )}
    </div>
  )
}

// ── 공익/재난 월별 송출내역 탭 ─────────────────────────────────────────────────
const GJ_STORE = 'report_gongik_jaenan_monthly'

const getGjXlsxUrl = (year, month) =>
  `/api/report/gongik-jaenan-monthly/xlsx?year=${year}&month=${month}`

const GJ_YEARS = (() => {
  const cur = dayjs().year()
  const arr = []
  for (let y = 2023; y <= cur; y++) arr.push(y)
  return arr
})()

function GongikJaenanMonthlyTab() {
  const saved = getStore(GJ_STORE)
  const [year,  setYear]  = useState(saved.year  ?? dayjs().year())
  const [month, setMonth] = useState(saved.month ?? dayjs().month() + 1)
  const [data,  setData]  = useState(saved.data ?? null)
  const [loading, setLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const res = await api.get('/report/gongik-jaenan-monthly', { params: { year, month } })
      setData(res.data)
      setStore(GJ_STORE, { year, month, data: res.data })
    } catch (e) {
      message.error(e.response?.data?.detail || '조회 실패')
    } finally {
      setLoading(false)
    }
  }

  const GONGIK_COLS = [
    { title: '날짜', dataIndex: 'date', width: 110, align: 'center' },
    { title: '요일', dataIndex: 'weekday', width: 50, align: 'center' },
    { title: '방송시간', dataIndex: 'time', width: 100, align: 'center' },
    { title: '공익광고명', dataIndex: 'name', ellipsis: true },
    { title: '초수', dataIndex: 'duration', width: 60, align: 'center' },
    { title: '시급', dataIndex: 'grade', width: 55, align: 'center' },
    { title: '가중치', dataIndex: 'weighted', width: 60, align: 'center',
      render: v => v ? <Tag color="red">O</Tag> : '' },
    { title: '가중치 적용', dataIndex: 'weighted_value', width: 90, align: 'center' },
    { title: '미적용', dataIndex: 'unweighted_value', width: 70, align: 'center' },
  ]
  const JAENAN_COLS = [
    { title: '날짜', dataIndex: 'date', width: 110, align: 'center' },
    { title: '요일', dataIndex: 'weekday', width: 50, align: 'center' },
    { title: '방송시간', dataIndex: 'time', width: 100, align: 'center' },
    { title: '공익광고명', dataIndex: 'name', ellipsis: true },
    { title: '분', dataIndex: 'duration', width: 45, align: 'center',
      render: d => { const m = Math.floor((d||0)/60); return m > 0 ? m : '' } },
    { title: '초', dataIndex: 'duration', width: 45, align: 'center',
      render: d => { const s = (d||0)%60; return s > 0 ? s : '' } },
    { title: '초수(총)', dataIndex: 'duration', width: 70, align: 'center' },
    { title: '가중치', dataIndex: 'weighted', width: 60, align: 'center',
      render: v => v ? <Tag color="red">O</Tag> : '' },
    { title: '가중치 적용', dataIndex: 'weighted_value', width: 90, align: 'center' },
    { title: '미적용', dataIndex: 'unweighted_value', width: 70, align: 'center' },
  ]

  return (
    <div>
      <Row gutter={12} align="middle" style={{ marginBottom: 20 }}>
        <Col style={{ fontWeight: 600, color: '#555' }}>년/월</Col>
        <Col>
          <Select value={year} onChange={setYear} style={{ width: 100 }} size="large"
            options={GJ_YEARS.map(y => ({ value: y, label: `${y}년` }))} />
        </Col>
        <Col>
          <Select value={month} onChange={setMonth} style={{ width: 90 }} size="large"
            options={Array.from({ length: 12 }, (_, i) => ({ value: i + 1, label: `${i + 1}월` }))} />
        </Col>
        <Col>
          <Button type="primary" icon={<SearchOutlined />} size="large" onClick={load} loading={loading}>
            조회
          </Button>
        </Col>
        <Col>
          <Button icon={<FilePdfOutlined />} size="large" disabled={!data}
            onClick={() => window.open(getGjXlsxUrl(year, month), '_blank')}>
            엑셀 저장
          </Button>
        </Col>
      </Row>

      {!data ? (
        <div style={{ textAlign: 'center', padding: '60px 0', color: '#bbb' }}>
          년/월을 선택하고 조회 버튼을 누르세요.
        </div>
      ) : (
        <div>
          <Card title={`공익광고 송출내역 (${data.year}년 ${data.month}월, 총 ${data.campaign.length}건)`}
            style={{ marginBottom: 20 }}>
            <Table columns={GONGIK_COLS} dataSource={data.campaign.map((r, i) => ({ ...r, _k: i }))}
              rowKey="_k" size="small" pagination={{ pageSize: 50, showTotal: t => `총 ${t}건` }}
              scroll={{ y: 400 }} />
          </Card>
          <Card title={`재난피해 사전예방 송출내역 (${data.year}년 ${data.month}월, 총 ${data.disaster.length}건)`}>
            <Table columns={JAENAN_COLS} dataSource={data.disaster.map((r, i) => ({ ...r, _k: i }))}
              rowKey="_k" size="small" pagination={{ pageSize: 50, showTotal: t => `총 ${t}건` }}
              scroll={{ y: 400 }} />
          </Card>
        </div>
      )}
    </div>
  )
}

// ── Main ─────────────────────────────────────────────────────────────────────
const TABS = [
  { key: 'monthly',       label: '소재별 월 리포트', children: <MonthlyTab /> },
  { key: 'daily',         label: '방송 운행표',      children: <DailyTab /> },
  { key: 'daily-summary', label: '일일 운행표',
    children: <DailySummaryTab type="캠페인" storeKey="report_daily_summary_campaign" /> },
  { key: 'daily-id',      label: '일일 ID 운행표',
    children: <DailySummaryTab type="ID" storeKey="report_daily_summary_id" /> },
  { key: 'subtitle',      label: '흘림자막,공익,재난 송출내역', children: <SubtitleCampaignTab /> },
  { key: 'gj-monthly',    label: '공익,재난 월별 송출내역', children: <GongikJaenanMonthlyTab /> },
  { key: 'item-list',     label: '소재 목록',        children: <ItemListTab /> },
]

export default function ReportView() {
  return (
    <div style={{ padding: 24 }}>
      <Card title="송출내역 출력">
        <Tabs items={TABS} />
      </Card>
    </div>
  )
}
