import React, { useState, useEffect } from 'react'
import { Card, Row, Col, Select, Table, Statistic, Segmented, Spin, message, Button } from 'antd'
import { DownloadOutlined } from '@ant-design/icons'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell,
} from 'recharts'
import dayjs from 'dayjs'
import { getDashboard } from '../api'
import { getStore, setStore } from '../store'
import { downloadXLSX } from '../xlsx'

const { Option } = Select
const STORE_KEY = 'dashboard'

const TYPE_OPTIONS = [
  { label: '전체',   value: undefined },
  { label: '캠페인', value: '캠페인' },
  { label: 'ID',     value: 'ID' },
]

// 페이지 번호가 연속되도록 currentPage·pageSize를 받아 컬럼 생성
const makeItemColumns = (currentPage, pageSize) => [
  {
    title: '순위',
    width: 54,
    align: 'center',
    render: (_, __, i) => (currentPage - 1) * pageSize + i + 1,
  },
  { title: '소재명',  dataIndex: 'item_name',          ellipsis: true },
  {
    title: '종류',    dataIndex: 'content_type_label',  width: 68, align: 'center',
    render: v => (
      <span style={{ color: v === 'ID' ? '#722ed1' : '#1677ff', fontWeight: 600 }}>{v}</span>
    ),
  },
  {
    title: '횟수',    dataIndex: 'count',               width: 64, align: 'right',
    render: v => <strong>{v}회</strong>,
  },
  { title: 'SA', dataIndex: 'sa_count', width: 48, align: 'right',
    render: v => v || 0 },
  { title: 'A',  dataIndex: 'a_count',  width: 44, align: 'right',
    render: v => v || 0 },
  { title: 'B',  dataIndex: 'b_count',  width: 44, align: 'right',
    render: v => v || 0 },
  { title: 'C',  dataIndex: 'c_count',  width: 44, align: 'right',
    render: v => v || 0 },
]

export default function Dashboard() {
  const now = dayjs()

  // ── 저장된 상태 복원 ──────────────────────────────────────────────────────
  const saved = getStore(STORE_KEY)

  const [year,    setYear]    = useState(saved.year    ?? now.year())
  const [month,   setMonth]   = useState(saved.month   ?? now.month() + 1)
  const [type,    setType]    = useState(saved.type    ?? undefined)
  const [data,    setData]    = useState(saved.data    ?? null)
  const [loading,     setLoading]     = useState(false)
  const [pageSize,    setPageSize]    = useState(saved.pageSize    ?? 10)
  const [currentPage, setCurrentPage] = useState(saved.currentPage ?? 1)

  // 상태 변경 시마다 store에 저장
  const save = (patch) =>
    setStore(STORE_KEY, { year, month, type, data, pageSize, currentPage, ...patch })

  const load = async (y = year, m = month, t = type) => {
    setLoading(true)
    try {
      const res = await getDashboard(y, m, t)
      setData(res)
      save({ year: y, month: m, type: t, data: res })
    } catch {
      message.error('데이터를 불러오지 못했습니다.')
    } finally {
      setLoading(false)
    }
  }

  // 최초 마운트 시: 저장된 결과가 없으면 자동 조회
  useEffect(() => {
    if (!saved.data) load()
  }, [])

  const YEARS  = Array.from({ length: 5 }, (_, i) => now.year() - i)
  const MONTHS = Array.from({ length: 12 }, (_, i) => i + 1)

  const handleYear  = (v) => { setYear(v);  save({ year: v });  load(v, month, type) }
  const handleMonth = (v) => { setMonth(v); save({ month: v }); load(year, v, type)  }
  const handleType  = (v) => { setType(v);  save({ type: v });  load(year, month, v) }

  const ROW_H = 36  // 테이블 행 높이(px)
  const tableScroll = pageSize * ROW_H + 8
  const CHART_HEIGHT = 428  // pageSize와 무관하게 항상 고정 (10개 기준 높이)

  return (
    <div style={{ padding: 24 }}>
      {/* ── 필터 ── */}
      <Row gutter={12} style={{ marginBottom: 20 }} align="middle">
        <Col>
          <Select value={year} onChange={handleYear} style={{ width: 90 }}>
            {YEARS.map(y => <Option key={y} value={y}>{y}년</Option>)}
          </Select>
        </Col>
        <Col>
          <Select value={month} onChange={handleMonth} style={{ width: 80 }}>
            {MONTHS.map(m => <Option key={m} value={m}>{m}월</Option>)}
          </Select>
        </Col>
        <Col>
          <Segmented options={TYPE_OPTIONS} value={type} onChange={handleType} />
        </Col>
      </Row>

      <Spin spinning={loading}>
        {/* ── 요약 카드 ── */}
        <Row gutter={16} style={{ marginBottom: 20 }}>
          <Col span={6}>
            <Card>
              <Statistic
                title="총 송출 횟수"
                value={data?.total ?? 0}
                suffix="회"
                valueStyle={{ color: '#1677ff' }}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="소재 종류 수"
                value={data?.by_item?.length ?? 0}
                suffix="종"
              />
            </Card>
          </Col>
        </Row>

        <Row gutter={16}>
          {/* ── 좌측: 소재별 송출 횟수 (SA/A/B/C 급지별 횟수 포함) ── */}
          <Col span={15}>
            <Card
              title="소재별 송출 횟수"
              extra={
                <Row gutter={8} align="middle">
                  <Col>
                    <Button
                      size="small"
                      icon={<DownloadOutlined />}
                      onClick={async () => {
                        if (!data?.by_item?.length) { message.warning('데이터가 없습니다.'); return }
                        const fname = `대시보드_${year}년${month ? `${String(month).padStart(2,'0')}월` : '연간'}.xlsx`
                        try {
                          await downloadXLSX(fname,
                            ['소재명', '종류', '횟수', 'SA', 'A', 'B', 'C'],
                            data.by_item.map(r => [
                              r.item_name, r.content_type_label, r.count,
                              r.sa_count || 0, r.a_count || 0, r.b_count || 0, r.c_count || 0,
                            ]),
                            '대시보드',
                          )
                        } catch { message.error('엑셀 저장 실패') }
                      }}
                    >
                      엑셀
                    </Button>
                  </Col>
                  <Col>
                    <Select
                      value={pageSize}
                      size="small"
                      style={{ width: 80 }}
                      onChange={v => {
                        setPageSize(v)
                        setCurrentPage(1)
                        save({ pageSize: v, currentPage: 1 })
                      }}
                    >
                      {[10, 20, 30, 40, 50].map(n => (
                        <Option key={n} value={n}>{n}개</Option>
                      ))}
                    </Select>
                  </Col>
                </Row>
              }
            >
              <Table
                dataSource={data?.by_item ?? []}
                columns={makeItemColumns(currentPage, pageSize)}
                rowKey="item_name"
                size="small"
                scroll={{ y: tableScroll }}
                pagination={{
                  current: currentPage,
                  pageSize,
                  size: 'small',
                  showTotal: t => `총 ${t}종`,
                  onChange: (page) => {
                    setCurrentPage(page)
                    save({ currentPage: page })
                  },
                }}
              />
            </Card>
          </Col>

          {/* ── 우측: 시간대별 송출 횟수 ── */}
          <Col span={9}>
            <Card title="시간대별 송출 횟수">
              <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
                <BarChart data={data?.by_hour ?? []} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="hour" tickFormatter={h => `${h}시`} tick={{ fontSize: 11 }} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                  <Tooltip
                    formatter={(v) => [`${v}회`, '송출 횟수']}
                    labelFormatter={h => `${h}시`}
                  />
                  <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                    {(data?.by_hour ?? []).map((_, i) => (
                      <Cell key={i} fill={i >= 6 && i <= 22 ? '#1677ff' : '#adc6ff'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </Card>
          </Col>
        </Row>
      </Spin>
    </div>
  )
}
