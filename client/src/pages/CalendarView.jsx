import React, { useState, useEffect, useRef, useCallback } from 'react'
import { Calendar, Card, Table, Select, Spin, message, Tag, Divider, Button, Row, Col } from 'antd'
import { CloseOutlined, DownloadOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { getCalendar, getDayDetail, ftpFetch } from '../api'
import { getStore, setStore } from '../store'
import { downloadXLSX } from '../xlsx'

const { Option } = Select
const STORE_KEY = 'calendar'

const ALL_VALUE = '__ALL__'   // antd Select에서 undefined value 회피용 센티넬
const TYPE_OPTIONS = [
  { label: '전체',   value: ALL_VALUE },
  { label: '캠페인', value: '캠페인' },
  { label: 'ID',     value: 'ID' },
]
// API 호출 시 ALL_VALUE → undefined(전체) 로 변환
const toApiType = (v) => (v === ALL_VALUE ? undefined : v)

const MIN_PANEL_WIDTH     = 360
const MIN_CALENDAR_WIDTH  = 420

// ── 대한민국 공휴일 (고정일 + 대체공휴일·음력 환산일 포함, 근사치) ─────────────
// 음력 환산 날짜(설날·추석·부처님오신날)는 연도별로 다르므로 직접 명시.
// 정확도가 중요한 경우 최신 공식 공휴일 자료로 갱신 필요.
const HOLIDAYS = {
  2025: [
    '2025-01-01',
    '2025-01-27', '2025-01-28', '2025-01-29', '2025-01-30',
    '2025-03-01', '2025-03-03',
    '2025-05-05', '2025-05-06',
    '2025-06-06',
    '2025-08-15',
    '2025-10-03',
    '2025-10-05', '2025-10-06', '2025-10-07', '2025-10-08',
    '2025-10-09',
    '2025-12-25',
  ],
  2026: [
    '2026-01-01',
    '2026-02-16', '2026-02-17', '2026-02-18',
    '2026-03-01', '2026-03-02',
    '2026-05-05',
    '2026-05-24', '2026-05-25',
    '2026-06-06',
    '2026-08-15', '2026-08-17',
    '2026-09-24', '2026-09-25', '2026-09-26',
    '2026-10-03',
    '2026-10-09',
    '2026-12-25',
  ],
  2027: [
    '2027-01-01',
    '2027-02-06', '2027-02-07', '2027-02-08',
    '2027-03-01',
    '2027-05-05',
    '2027-06-06',
    '2027-08-15', '2027-08-16',
    '2027-09-14', '2027-09-15', '2027-09-16',
    '2027-10-03', '2027-10-04',
    '2027-10-09',
    '2027-12-25',
  ],
}

function isHoliday(dateStr) {
  const year = dateStr.slice(0, 4)
  return HOLIDAYS[year]?.includes(dateStr) ?? false
}


// ── 시간 순서 테이블 (모든 컬럼 정렬 토글 지원, 기본 정렬: 시간 오름차순) ──────
const DETAIL_COLUMNS = [
  {
    title: '시간', dataIndex: 'broadcast_time', width: 90, align: 'center',
    sorter: (a, b) => a.broadcast_time.localeCompare(b.broadcast_time),
    defaultSortOrder: 'ascend',
  },
  {
    title: '소재명', dataIndex: 'item_name',
    sorter: (a, b) => a.item_name.localeCompare(b.item_name),
  },
  {
    title: '종류', dataIndex: 'content_type_label', width: 90, align: 'center',
    sorter: (a, b) => a.content_type_label.localeCompare(b.content_type_label),
    render: v => <Tag color={v === 'ID' ? 'purple' : 'blue'}>{v}</Tag>,
  },
  {
    title: '구분', dataIndex: 'source', width: 80, align: 'center',
    sorter: (a, b) => a.source.localeCompare(b.source),
    render: v => <Tag color={v === 'apst' ? 'green' : 'orange'}>{v === 'apst' ? '자동' : '수동'}</Tag>,
  },
]

// ── 소재별 횟수 요약 테이블 (정렬 토글, 기본 정렬: 총횟수 내림차순) ────────────
const SUMMARY_COLUMNS = [
  {
    title: '소재명', dataIndex: 'item_name',
    sorter: (a, b) => a.item_name.localeCompare(b.item_name),
  },
  {
    title: '종류', dataIndex: 'content_type_label', width: 80, align: 'center',
    sorter: (a, b) => a.content_type_label.localeCompare(b.content_type_label),
    render: v => <Tag color={v === 'ID' ? 'purple' : 'blue'}>{v}</Tag>,
  },
  {
    title: '총횟수', dataIndex: 'total_count', width: 80, align: 'right',
    sorter: (a, b) => a.total_count - b.total_count,
    defaultSortOrder: 'descend',
    render: v => <strong>{v}회</strong>,
  },
  { title: 'SA', dataIndex: 'sa', width: 50, align: 'right' },
  { title: 'A',  dataIndex: 'a',  width: 50, align: 'right' },
  { title: 'B',  dataIndex: 'b',  width: 50, align: 'right' },
  { title: 'C',  dataIndex: 'c',  width: 50, align: 'right' },
]

// 시간 순서 목록(items) → 소재별 총횟수 + 급지별 횟수 요약으로 집계 (클라이언트 계산)
function buildItemSummary(items) {
  const map = new Map()
  for (const it of items) {
    const key = it.item_name
    if (!map.has(key)) {
      map.set(key, {
        item_name: key,
        content_type_label: it.content_type_label,
        total_count: 0,
        sa: 0, a: 0, b: 0, c: 0,
      })
    }
    const row = map.get(key)
    row.total_count += 1
    if (it.grade === 'SA') row.sa += 1
    else if (it.grade === 'A') row.a += 1
    else if (it.grade === 'B') row.b += 1
    else if (it.grade === 'C') row.c += 1
  }
  return Array.from(map.values())
}

export default function CalendarView() {
  const now = dayjs()

  // ── 저장된 상태 복원 (월/년도, 종류필터, 날짜별 건수, 패널 폭, 선택일·조회결과 모두 복원) ──
  const saved = getStore(STORE_KEY)

  // 월의 1일로 정규화 — 특정 "일"이 남아있으면 달력 셀이 계속 강조 표시되는 문제 방지
  const [current,  setCurrent]  = useState(
    saved.current ? dayjs(saved.current).startOf('month') : now.startOf('month')
  )
  // 디폴트는 캠페인만 표시
  const [typeFilter, setTypeFilter] = useState(
    saved.typeFilter !== undefined ? saved.typeFilter : '캠페인'
  )
  const [countMap, setCountMap] = useState(saved.countMap ?? {})
  const [missingSet, setMissingSet] = useState(new Set(saved.missing ?? []))
  const [loading,  setLoading]  = useState(false)
  // 패널이 차지하는 비율(%) — 달력과 패널이 항상 정확히 같은 폭(50%)으로 시작하고,
  // 컨테이너 폭에 비례하므로 화면 크기와 무관하게 좌우 여백 없이 꽉 채워짐
  const [panelPercent, setPanelPercent] = useState(saved.panelPercent ?? 50)

  // 상세 패널 — 마지막 조회 결과를 그대로 복원 (다른 메뉴 갔다 와도 유지)
  const [panel, setPanel] = useState(saved.panel ?? { open: false, date: '', items: [] })
  // 클릭해서 선택한 날짜 (셀 시안색 강조용) — antd 기본 selected와 분리해서 직접 관리
  const [selectedDate, setSelectedDate] = useState(saved.selectedDate ?? null)
  const [detailLoading, setDetailLoading] = useState(false)

  const containerRef    = useRef(null)
  const resizingRef     = useRef(false)
  const panelPercentRef = useRef(panelPercent)   // 드래그 중 최신값을 동기적으로 추적 (stale closure 방지)

  // ── store 저장 — 항상 "지정한 필드만" 병합 (전체 상태를 스냅샷하는 헬퍼는
  // 비동기 콜백에서 stale closure를 일으켜 다른 필드를 되돌리는 버그가 있었음) ──
  const patchStore = (patch) => setStore(STORE_KEY, patch)

  const loadMonth = async (m, t = typeFilter) => {
    setLoading(true)
    try {
      const res = await getCalendar(m.year(), m.month() + 1, toApiType(t))
      const map = {}
      res.days.forEach(d => { map[d.date] = d.count })
      const missing = res.missing ?? []
      setCountMap(map)
      setMissingSet(new Set(missing))
      patchStore({ current: m.startOf('month').format('YYYY-MM-DD'), typeFilter: t, countMap: map, missing })
    } catch {
      message.error('달력 데이터를 불러오지 못했습니다.')
    } finally {
      setLoading(false)
    }
  }

  // 최초 마운트 시: 저장된 결과가 없으면 자동 조회
  useEffect(() => {
    if (!saved.countMap) loadMonth(current)
  }, [])

  const onPanelChange = (val) => {
    const normalized = val.startOf('month')
    setCurrent(normalized)
    loadMonth(normalized)
  }

  const onTypeChange = (t) => {
    setTypeFilter(t)
    loadMonth(current, t)
    // 종류 필터가 바뀌면 이미 열려있는 상세 패널도 새 필터로 다시 조회
    if (panel.open && panel.date) {
      reloadDetail(panel.date, t)
    }
  }

  const reloadDetail = async (dateStr, t) => {
    setDetailLoading(true)
    try {
      const res = await getDayDetail(dateStr, toApiType(t))
      setPanel(p => {
        const next = { ...p, items: res.items }
        patchStore({ panel: next })
        return next
      })
    } catch {
      message.error('상세 데이터를 불러오지 못했습니다.')
    } finally {
      setDetailLoading(false)
    }
  }

  // 날짜를 "직접 클릭"했을 때만 상세 패널 표시
  // antd Calendar는 연/월 헤더 선택 시에도 onSelect를 함께 호출하므로
  // source가 'date'(실제 날짜 클릭)인 경우에만 동작하도록 차단
  const onSelect = async (val, info) => {
    if (info?.source !== 'date') return

    const dateStr = val.format('YYYY-MM-DD')
    setSelectedDate(dateStr)
    const opened = { open: true, date: dateStr, items: [] }
    setPanel(opened)
    patchStore({ selectedDate: dateStr, panel: opened })
    setDetailLoading(true)

    // 파일 누락일(붉은 0)을 클릭하면 FTP에서 다시 가져와 적재
    if (missingSet.has(dateStr)) {
      try {
        const r = await ftpFetch(dateStr)
        if (r.ok) {
          message.success(`${dateStr} 파일을 FTP에서 가져와 적재했습니다.`)
          await loadMonth(current)   // 붉은 0 제거 + 건수 갱신
        } else if (r.missing) {
          message.warning(`${dateStr} — FTP에 아직 파일이 없습니다.`)
        } else {
          message.error(r.error || 'FTP 가져오기 실패')
        }
      } catch (e) {
        message.error(e.response?.data?.detail || 'FTP 가져오기 실패')
      }
    }

    try {
      const res = await getDayDetail(dateStr, toApiType(typeFilter))
      setPanel(d => {
        const next = { ...d, items: res.items }
        patchStore({ panel: next })   // panel 필드만 갱신 — selectedDate 등 다른 필드는 그대로 유지
        return next
      })
    } catch {
      message.error('상세 데이터를 불러오지 못했습니다.')
    } finally {
      setDetailLoading(false)
    }
  }

  // 날짜 숫자(앞자리 0 없음) + 주말·공휴일 빨강 + 선택일 시안 강조 + 중앙 건수 배지
  const dateCellRender = (val) => {
    const key = val.format('YYYY-MM-DD')
    const cnt = countMap[key]
    const dayNum = val.date()           // 1~31, 앞자리 0 없음
    const dow = val.day()               // 0=일요일, 6=토요일
    const isRed = dow === 0 || dow === 6 || isHoliday(key)
    const isSelected = selectedDate === key
    const isMissing = missingSet.has(key)   // FTP 파일 없음 → 붉은 0 표시

    return (
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background: isSelected ? '#e6fffb' : 'transparent',
          border: isSelected ? '2px solid #13c2c2' : 'none',
          boxSizing: 'border-box',
          borderRadius: 4,
        }}
      >
        {/* 날짜 숫자 (기존 antd 기본 숫자는 CSS로 숨기고 직접 렌더링) */}
        <div
          style={{
            position: 'absolute',
            top: 4,
            left: 6,
            fontSize: 20,            // 기존 28px 대비 30% 감소
            fontWeight: 500,
            lineHeight: 1,
            color: isRed ? '#ff4d4f' : '#262626',
          }}
        >
          {dayNum}
        </div>

        {/* 건수 배지 (중앙) — 당일 파일이 누락된 경우, 건수(전날 파일에 섞인 새벽분 등)와
            무관하게 붉은색으로 표시. 정상 수신된 날짜만 파란색. */}
        {(cnt > 0 || isMissing) && (
          <div
            title={isMissing ? '파일 누락 — 클릭하면 FTP에서 다시 가져옵니다' : undefined}
            style={{
              position: 'absolute',
              top: '50%',
              left: '50%',
              transform: 'translate(-50%, -50%)',
              fontSize: 22,
              fontWeight: 700,
              color: '#fff',
              background: isMissing ? '#ff4d4f' : '#1677ff',
              borderRadius: 8,
              minWidth: 32,
              padding: '2px 8px',
              textAlign: 'center',
              lineHeight: 1.3,
              pointerEvents: 'none',
              boxShadow: '0 1px 4px rgba(0,0,0,0.15)',
            }}
          >
            {cnt || 0}
          </div>
        )}
      </div>
    )
  }

  // ── 마우스 드래그로 패널 비율(%) 조정 ─────────────────────────────────────
  // 픽셀이 아닌 비율로 저장하므로 달력+패널이 항상 컨테이너 폭을 정확히 채움 (좌우 여백 없음)
  // panelPercentRef로 항상 최신값을 동기 추적 → stopResize의 stale closure 문제 방지
  const onResizeMove = useCallback((e) => {
    if (!resizingRef.current || !containerRef.current) return
    const rect = containerRef.current.getBoundingClientRect()
    const usable = rect.width - 8   // 리사이저 폭 제외
    const newPanelWidthPx = rect.right - e.clientX
    const minPercent = (MIN_PANEL_WIDTH / usable) * 100
    const maxPercent = 100 - (MIN_CALENDAR_WIDTH / usable) * 100
    const rawPercent = (newPanelWidthPx / usable) * 100
    const clamped = Math.min(Math.max(rawPercent, minPercent), Math.max(maxPercent, minPercent))
    panelPercentRef.current = clamped
    setPanelPercent(clamped)
  }, [])

  const stopResize = useCallback(() => {
    if (!resizingRef.current) return
    resizingRef.current = false
    document.body.style.userSelect = ''
    document.body.style.cursor = ''
    window.removeEventListener('mousemove', onResizeMove)
    window.removeEventListener('mouseup', stopResize)
    patchStore({ panelPercent: panelPercentRef.current })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onResizeMove])

  const startResize = (e) => {
    e.preventDefault()
    resizingRef.current = true
    document.body.style.userSelect = 'none'
    document.body.style.cursor = 'col-resize'
    window.addEventListener('mousemove', onResizeMove)
    window.addEventListener('mouseup', stopResize)
  }

  const closePanel = () => {
    setPanel(p => {
      const next = { ...p, open: false }
      patchStore({ panel: next })
      return next
    })
  }

  const itemSummary = buildItemSummary(panel.items)

  // ── 엑셀(xlsx) 내보내기 ──────────────────────────────────────────────────────
  const exportDetailXLSX = async () => {
    try {
      await downloadXLSX(
        `송출내역_${panel.date}.xlsx`,
        ['시간', '소재명', '종류', '구분'],
        panel.items.map(r => [
          r.broadcast_time, r.item_name, r.content_type_label,
          r.source === 'apst' ? '자동' : '수동',
        ]),
        '송출내역',
      )
    } catch { message.error('엑셀 저장 실패') }
  }

  const exportSummaryXLSX = async () => {
    try {
      await downloadXLSX(
        `송출횟수_${panel.date}.xlsx`,
        ['소재명', '종류', '총횟수', 'SA', 'A', 'B', 'C'],
        itemSummary.map(r => [
          r.item_name, r.content_type_label, r.total_count, r.sa, r.a, r.b, r.c,
        ]),
        '송출횟수',
      )
    } catch { message.error('엑셀 저장 실패') }
  }

  return (
    <div style={{ padding: 24 }}>
      {/*
        - antd 기본 날짜 숫자는 숨기고(dateCellRender에서 직접 렌더링) 앞자리 0 없이 표시
        - antd의 자동 "선택됨" 배경(1일이 항상 선택된 것처럼 보이던 문제)도 무력화
      */}
      <style>{`
        .sb-calendar .ant-picker-calendar-date-value {
          display: none !important;
        }
        .sb-calendar .ant-picker-cell-inner.ant-picker-calendar-date {
          position: relative !important;
          height: 90px !important;
        }
        .sb-calendar .ant-picker-calendar-date-content {
          height: auto !important;
        }
        .sb-calendar .ant-picker-cell-selected .ant-picker-calendar-date,
        .sb-calendar .ant-picker-cell-selected .ant-picker-cell-inner {
          background: transparent !important;
        }
      `}</style>

      {/* 달력 + 리사이저 + 상세 패널을 한 행에 배치 — 패널이 열려도 달력이 가려지지 않음 */}
      <div ref={containerRef} style={{ display: 'flex', alignItems: 'flex-start', width: '100%' }}>

        {/* ── 좌측: 달력 (패널이 열리면 패널과 정확히 같은 폭으로 컨테이너를 꽉 채움) ── */}
        <div style={
          panel.open
            ? { flex: `1 1 ${100 - panelPercent}%`, minWidth: MIN_CALENDAR_WIDTH }
            : { flex: 1, minWidth: MIN_CALENDAR_WIDTH }
        }>
          <Card title="SB 송출 달력" className="sb-calendar">
            <Spin spinning={loading}>
              <Calendar
                value={current}
                onPanelChange={onPanelChange}
                onSelect={onSelect}
                cellRender={(val, info) =>
                  info.type === 'date' ? dateCellRender(val) : null
                }
                headerRender={({ value, onChange }) => {
                  const years  = Array.from({ length: 5 }, (_, i) => now.year() - i)
                  const months = Array.from({ length: 12 }, (_, i) => i + 1)
                  return (
                    <div style={{ display: 'flex', gap: 8, padding: '8px 0' }}>
                      <Select
                        value={value.year()}
                        onChange={y => onChange(value.year(y))}
                        style={{ width: 90 }}
                      >
                        {years.map(y => <Option key={y} value={y}>{y}년</Option>)}
                      </Select>
                      <Select
                        value={value.month() + 1}
                        onChange={m => onChange(value.month(m - 1))}
                        style={{ width: 80 }}
                      >
                        {months.map(m => <Option key={m} value={m}>{m}월</Option>)}
                      </Select>
                      <Select
                        value={typeFilter}
                        onChange={onTypeChange}
                        style={{ width: 100 }}
                      >
                        {TYPE_OPTIONS.map(o => (
                          <Option key={o.label} value={o.value}>{o.label}</Option>
                        ))}
                      </Select>
                    </div>
                  )
                }}
              />
            </Spin>
          </Card>
        </div>

        {/* ── 리사이저 + 우측 상세 패널 (날짜 클릭 시에만 표시) ── */}
        {panel.open && (
          <>
            <div
              onMouseDown={startResize}
              title="드래그하여 폭 조절"
              style={{
                width: 8,
                cursor: 'col-resize',
                flexShrink: 0,
                alignSelf: 'stretch',
                position: 'relative',
                margin: '0 -4px',
                zIndex: 10,
              }}
            >
              <div style={{
                position: 'absolute', left: '50%', top: 0, bottom: 0,
                width: 2, background: '#e8e8e8', transform: 'translateX(-50%)',
              }} />
            </div>

            <div style={{ flex: `1 1 ${panelPercent}%`, minWidth: MIN_PANEL_WIDTH }}>
              <Card
                title={`${panel.date} 송출 내역`}
                extra={
                  <Button
                    type="text"
                    size="small"
                    icon={<CloseOutlined />}
                    onClick={closePanel}
                  />
                }
              >
                <Spin spinning={detailLoading}>
                  {/* ① 소재별 횟수(총횟수, SA/A/B/C) 요약 */}
                  <Row justify="space-between" align="middle" style={{ marginBottom: 8 }}>
                    <Col style={{ fontWeight: 600, color: '#555' }}>소재별 송출 횟수</Col>
                    <Col>
                      <Button
                        size="small"
                        icon={<DownloadOutlined />}
                        onClick={exportSummaryXLSX}
                        disabled={itemSummary.length === 0}
                      >
                        엑셀 저장
                      </Button>
                    </Col>
                  </Row>
                  {/* minHeight로 영역 고정 — 마지막 페이지 행 수가 10개 미만이어도
                      테이블이 줄어들지 않아 아래 송출내역이 따라 올라오지 않음 */}
                  <div style={{ minHeight: 488 }}>
                    <Table
                      dataSource={itemSummary}
                      columns={SUMMARY_COLUMNS}
                      rowKey="item_name"
                      size="small"
                      pagination={{ pageSize: 10, size: 'small', showTotal: t => `총 ${t}종` }}
                    />
                  </div>

                  <Divider style={{ margin: '20px 0 12px' }} />

                  {/* ② 시간 순서 목록 */}
                  <Row justify="space-between" align="middle" style={{ marginBottom: 8 }}>
                    <Col style={{ fontWeight: 600, color: '#555' }}>송출내역</Col>
                    <Col>
                      <Button
                        size="small"
                        icon={<DownloadOutlined />}
                        onClick={exportDetailXLSX}
                        disabled={panel.items.length === 0}
                      >
                        엑셀 저장
                      </Button>
                    </Col>
                  </Row>
                  <Table
                    dataSource={panel.items}
                    columns={DETAIL_COLUMNS}
                    rowKey={(_, i) => i}
                    size="small"
                    pagination={false}
                    scroll={{ y: 400 }}
                  />
                </Spin>
              </Card>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
