import React, { useState } from 'react'
import {
  Card, Row, Col, Select, Button, Table, Tag, DatePicker,
  Statistic, Spin, message, Input, Divider, Modal,
} from 'antd'
import { SearchOutlined, ClearOutlined, DownloadOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import axios from 'axios'
import { getStore, setStore } from '../store'
import { downloadXLSX } from '../xlsx'

const { Option } = Select
const { RangePicker } = DatePicker
const api = axios.create({ baseURL: '/api' })
const STORE_KEY = 'period'

const HOURS = Array.from({ length: 24 }, (_, i) => i)

// ── 테이블 컬럼 ───────────────────────────────────────────────────────────────
const COLUMNS = [
  { title: '날짜',   dataIndex: 'broadcast_date', width: 110, align: 'center' },
  { title: '시간',   dataIndex: 'broadcast_time', width: 90,  align: 'center' },
  { title: '소재명', dataIndex: 'item_name',       ellipsis: true },
  {
    title: '종류', dataIndex: 'content_type_label', width: 90, align: 'center',
    render: v => <Tag color={v === 'ID' ? 'purple' : 'blue'}>{v}</Tag>,
  },
  { title: '길이(초)', dataIndex: 'duration_sec', width: 80, align: 'right' },
  {
    title: '송출구분', dataIndex: 'source', width: 80, align: 'center',
    render: v => (
      <Tag color={v === 'apst' ? 'green' : 'orange'}>
        {v === 'apst' ? '자동' : '수동'}
      </Tag>
    ),
  },
]

export default function PeriodView() {
  // ── 저장된 상태 복원 ──────────────────────────────────────────────────────
  const saved = getStore(STORE_KEY)

  const [dateRange,   setDateRange]   = useState(
    saved.dateRange
      ? [dayjs(saved.dateRange[0]), dayjs(saved.dateRange[1])]
      : [dayjs().startOf('month'), dayjs()]
  )
  const [startHour,   setStartHour]   = useState(saved.startHour   ?? undefined)
  const [endHour,     setEndHour]     = useState(saved.endHour     ?? undefined)
  const [typeFilter,  setTypeFilter]  = useState(saved.typeFilter  ?? undefined)
  const [sourceFilter, setSourceFilter] = useState(saved.sourceFilter ?? undefined)
  const [itemFilter,  setItemFilter]  = useState(saved.itemFilter  ?? '')
  const [data,        setData]        = useState(saved.data        ?? null)
  const [loading,     setLoading]     = useState(false)

  // 소재명 다중 매칭 시 선택 모달
  const [modalOpen,    setModalOpen]    = useState(false)
  const [candidates,   setCandidates]   = useState([])
  const [matchLoading, setMatchLoading] = useState(false)
  const [selectedKeys, setSelectedKeys] = useState([])   // 체크박스로 선택한 소재명들

  const save = (patch) =>
    setStore(STORE_KEY, {
      dateRange: dateRange ? [dateRange[0].format('YYYY-MM-DD'), dateRange[1].format('YYYY-MM-DD')] : null,
      startHour, endHour, typeFilter, sourceFilter, itemFilter, data, ...patch,
    })

  // ── 실제 /api/period 조회 실행 ──────────────────────────────────────────────
  // exactItem: 단일 소재명 완전일치 / exactItems: 여러 소재명(배열) 완전일치(OR)
  const runQuery = async (exactItem, exactItems) => {
    if (!dateRange || !dateRange[0] || !dateRange[1]) {
      message.warning('기간을 선택하세요.')
      return
    }
    setLoading(true)
    try {
      const params = {
        start_date: dateRange[0].format('YYYY-MM-DD'),
        end_date:   dateRange[1].format('YYYY-MM-DD'),
      }
      if (startHour  !== undefined) params.start_hour = startHour
      if (endHour    !== undefined) params.end_hour   = endHour
      if (typeFilter)               params.type       = typeFilter
      if (sourceFilter)             params.source     = sourceFilter
      if (exactItems && exactItems.length) params.items = exactItems.join(',')
      else if (exactItem)           params.item       = exactItem

      const res = await api.get('/period', { params })
      setData(res.data)
      save({
        dateRange: [params.start_date, params.end_date],
        startHour, endHour, typeFilter, sourceFilter,
        itemFilter, data: res.data,
      })
    } catch (e) {
      message.error(e.response?.data?.detail || '조회 실패')
    } finally {
      setLoading(false)
    }
  }

  // ── 조회 버튼 — 소재명이 입력되어 있으면 먼저 후보 개수를 확인 (소재종류 필터 적용) ──
  const search = async () => {
    const q = itemFilter.trim()

    // 소재명 미입력 → 전체 조회
    if (!q) {
      runQuery(undefined)
      return
    }

    setMatchLoading(true)
    try {
      const res = await api.get('/items', { params: { q, limit: 50, type: typeFilter } })
      const matches = res.data   // [{item_name, content_type_label, count}, ...]

      if (matches.length === 1) {
        // 결과가 정확히 1개일 때만 바로 조회
        const onlyName = matches[0].item_name
        setItemFilter(onlyName)
        save({ itemFilter: onlyName })
        runQuery(onlyName)
        return
      }

      // 0개 또는 2개 이상 → 선택 모달 표시
      setCandidates(matches)
      setSelectedKeys([])
      setModalOpen(true)
      if (matches.length === 0) {
        message.warning(`'${q}'를 포함하는 소재가 없습니다.`)
      }
    } catch {
      message.error('소재 검색 실패')
    } finally {
      setMatchLoading(false)
    }
  }

  // 모달에서 소재명 클릭 → 그 소재만 바로 조회
  const selectCandidate = (name) => {
    setItemFilter(name)
    setModalOpen(false)
    setSelectedKeys([])
    save({ itemFilter: name })
    runQuery(name)
  }

  // 모달에서 체크박스로 여러 소재 선택 후 조회
  const selectMultiCandidates = () => {
    if (selectedKeys.length === 0) return
    setItemFilter(selectedKeys.join(', '))
    setModalOpen(false)
    save({ itemFilter: selectedKeys.join(', ') })
    runQuery(undefined, selectedKeys)
  }

  // ── 엑셀(xlsx) 저장 ──────────────────────────────────────────────────────
  const exportXLSX = async () => {
    if (!data?.items?.length) { message.warning('저장할 데이터가 없습니다.'); return }
    try {
      await downloadXLSX(
        `상세조회_${dateRange[0].format('YYYYMMDD')}-${dateRange[1].format('YYYYMMDD')}.xlsx`,
        ['날짜', '시간', '소재명', '종류', '길이(초)', '송출구분'],
        data.items.map(r => [
          r.broadcast_date, r.broadcast_time, r.item_name,
          r.content_type_label, r.duration_sec,
          r.source === 'apst' ? '자동' : '수동',
        ]),
        '상세조회',
      )
    } catch { message.error('엑셀 저장 실패') }
  }

  // ── 초기화 ────────────────────────────────────────────────────────────────
  const reset = () => {
    const dr = [dayjs().startOf('month'), dayjs()]
    setDateRange(dr)
    setStartHour(undefined)
    setEndHour(undefined)
    setTypeFilter(undefined)
    setSourceFilter(undefined)
    setItemFilter('')
    setData(null)
    setModalOpen(false)
    setCandidates([])
    setSelectedKeys([])
    setStore(STORE_KEY, {})
  }

  return (
    <div style={{ padding: 24 }}>
      {/* ── 필터 카드 ── */}
      <Card title="상세조회" style={{ marginBottom: 16 }}>
        <Row gutter={[0, 14]}>

          {/* 기간 — RangePicker (달력 + 직접 선택) */}
          <Col span={24}>
            <Row align="middle" gutter={8}>
              <Col style={{ width: 74, fontWeight: 600, color: '#555' }}>기간</Col>
              <Col>
                <RangePicker
                  value={dateRange}
                  onChange={setDateRange}
                  format="YYYY-MM-DD"
                  allowClear={false}
                  style={{ width: 300 }}
                />
              </Col>
            </Row>
          </Col>

          {/* 송출 시간 */}
          <Col span={24}>
            <Row align="middle" gutter={8}>
              <Col style={{ width: 74, fontWeight: 600, color: '#555' }}>송출시간</Col>
              <Col>
                <Select value={startHour} onChange={setStartHour}
                  style={{ width: 88 }} allowClear placeholder="전체">
                  {HOURS.map(h => <Option key={h} value={h}>{h}시</Option>)}
                </Select>
              </Col>
              <Col style={{ color: '#bbb' }}>~</Col>
              <Col>
                <Select value={endHour} onChange={setEndHour}
                  style={{ width: 88 }} allowClear placeholder="전체">
                  {HOURS.map(h => <Option key={h} value={h}>{h}시</Option>)}
                </Select>
              </Col>
              <Col style={{ fontSize: 12, color: '#bbb' }}>
                (지정하지 않으면 24시간 전체)
              </Col>
            </Row>
          </Col>

          {/* 소재종류 + 송출구분 */}
          <Col span={24}>
            <Row align="middle" gutter={16}>
              {/* 소재종류 */}
              <Col>
                <Row align="middle" gutter={8}>
                  <Col style={{ fontWeight: 600, color: '#555' }}>소재종류</Col>
                  <Col>
                    <Select value={typeFilter} onChange={setTypeFilter}
                      style={{ width: 120 }} allowClear placeholder="전체">
                      <Option value="캠페인">캠페인</Option>
                      <Option value="ID">ID</Option>
                    </Select>
                  </Col>
                </Row>
              </Col>

              {/* 송출구분 */}
              <Col>
                <Row align="middle" gutter={8}>
                  <Col style={{ fontWeight: 600, color: '#555' }}>송출구분</Col>
                  <Col>
                    <Select value={sourceFilter} onChange={setSourceFilter}
                      style={{ width: 110 }} allowClear placeholder="전체">
                      <Option value="apst">자동</Option>
                      <Option value="ddr1">수동</Option>
                    </Select>
                  </Col>
                </Row>
              </Col>
            </Row>
          </Col>

          {/* 소재명 */}
          <Col span={24}>
            <Row align="middle" gutter={8}>
              <Col style={{ width: 74, fontWeight: 600, color: '#555' }}>소재명</Col>
              <Col>
                <Input
                  value={itemFilter}
                  onChange={e => setItemFilter(e.target.value)}
                  onPressEnter={search}
                  placeholder="입력하지 않으면 전체"
                  style={{ width: 230 }}
                  allowClear
                />
              </Col>
            </Row>
          </Col>
        </Row>

        <Divider style={{ margin: '16px 0 12px' }} />

        {/* 버튼 */}
        <Row gutter={8} align="middle">
          <Col>
            <Button
              type="primary"
              icon={<SearchOutlined />}
              onClick={search}
              loading={matchLoading || loading}
              size="large"
            >
              조회
            </Button>
          </Col>
          <Col>
            <Button icon={<ClearOutlined />} onClick={reset}>초기화</Button>
          </Col>
          {data && (
            <>
              <Col style={{ marginLeft: 16 }}>
                <Statistic value={data.total} suffix="건"
                  valueStyle={{ fontSize: 18, color: '#1677ff' }} />
              </Col>
              <Col>
                <Button icon={<DownloadOutlined />} onClick={exportXLSX}>
                  엑셀 저장
                </Button>
              </Col>
            </>
          )}
        </Row>
      </Card>

      {/* ── 결과 테이블 ── */}
      <Card>
        <Spin spinning={loading}>
          <Table
            dataSource={data?.items ?? []}
            columns={COLUMNS}
            rowKey={(_, i) => i}
            size="small"
            pagination={{
              pageSize: 50,
              showTotal: t => `총 ${t}건`,
              showSizeChanger: true,
              pageSizeOptions: ['50', '100', '200'],
            }}
            scroll={{ y: 500 }}
            locale={{ emptyText: '조회 버튼을 눌러 검색하세요.' }}
          />
        </Spin>
      </Card>

      {/* ── 소재명 다중 매칭 시 선택 모달 ── */}
      <Modal
        title={`'${itemFilter}' 를 포함하는 소재 선택`}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        footer={null}
        width={560}
      >
        <Table
          dataSource={candidates}
          rowKey="item_name"
          size="small"
          pagination={{ pageSize: 10, size: 'small' }}
          scroll={{ y: 320 }}
          rowSelection={{
            selectedRowKeys: selectedKeys,
            onChange: setSelectedKeys,
          }}
          columns={[
            { title: '소재명', dataIndex: 'item_name',
              sorter: (a, b) => a.item_name.localeCompare(b.item_name),
              render: (v) => <a onClick={() => selectCandidate(v)}>{v}</a> },
            { title: '종류', dataIndex: 'content_type_label', width: 80, align: 'center',
              sorter: (a, b) => (a.content_type_label ?? '').localeCompare(b.content_type_label ?? ''),
              render: v => <Tag color={v === 'ID' ? 'purple' : 'blue'}>{v}</Tag> },
            { title: '총횟수', dataIndex: 'count', width: 80, align: 'right',
              sorter: (a, b) => a.count - b.count,
              render: v => `${v}회` },
            { title: '추가 날짜', dataIndex: 'first_added', width: 110, align: 'center',
              sorter: (a, b) => (a.first_added ?? '').localeCompare(b.first_added ?? ''),
              defaultSortOrder: 'descend',
              render: v => v ? v.slice(0, 10) : '-' },
          ]}
          locale={{ emptyText: '일치하는 소재가 없습니다.' }}
        />
        <Row justify="space-between" align="middle" style={{ marginTop: 8 }}>
          <Col style={{ fontSize: 12, color: '#aaa' }}>
            * 소재명을 클릭하면 그 소재만 바로 조회됩니다. 체크박스로 여러 개를 선택한 뒤
            아래 버튼으로 한번에 조회할 수 있습니다 (검색 결과가 여러 페이지여도 전체 선택 가능).
          </Col>
        </Row>
        <Row justify="end" style={{ marginTop: 8 }}>
          <Button type="primary" disabled={selectedKeys.length === 0} onClick={selectMultiCandidates}>
            선택 {selectedKeys.length}건 조회
          </Button>
        </Row>
      </Modal>
    </div>
  )
}
