import React, { useState, useEffect } from 'react'
import { Card, Table, Tag, Button, message, Popconfirm } from 'antd'
import { ReloadOutlined, DeleteOutlined } from '@ant-design/icons'
import { getLogs, clearLogs } from '../api'

const LEVEL_COLOR = { info: 'blue', warning: 'orange', error: 'red' }

const COLUMNS = [
  { title: '시간', dataIndex: 'created_at', width: 170 },
  {
    title: '수준', dataIndex: 'level', width: 90, align: 'center',
    render: v => <Tag color={LEVEL_COLOR[v] || 'default'}>{v}</Tag>,
  },
  { title: '구분', dataIndex: 'category', width: 130 },
  { title: '내용', dataIndex: 'message' },
]

export default function LogPage({ isAdmin = false }) {
  const [logs,    setLogs]    = useState([])
  const [loading, setLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const res = await getLogs(300)
      setLogs(res)
    } catch {
      message.error('로그를 불러오지 못했습니다.')
    } finally {
      setLoading(false)
    }
  }

  const [clearing, setClearing] = useState(false)

  const handleClear = async () => {
    setClearing(true)
    try {
      const res = await clearLogs()
      message.success(`로그를 초기화했습니다. (${res.deleted}건 삭제)`)
      load()
    } catch {
      message.error('로그 초기화에 실패했습니다.')
    } finally {
      setClearing(false)
    }
  }

  useEffect(() => { load() }, [])

  return (
    <div style={{ padding: 24 }}>
      <Card
        title="로그 기록"
        extra={
          <span style={{ display: 'flex', gap: 8 }}>
            <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>
              새로고침
            </Button>
            {isAdmin && (
              <Popconfirm
                title="로그를 모두 삭제할까요?"
                description="기록된 모든 로그가 삭제됩니다. 되돌릴 수 없습니다."
                okText="초기화"
                cancelText="취소"
                okButtonProps={{ danger: true }}
                onConfirm={handleClear}
              >
                <Button danger icon={<DeleteOutlined />} loading={clearing}>
                  로그 초기화
                </Button>
              </Popconfirm>
            )}
          </span>
        }
      >
        <Table
          dataSource={logs}
          columns={COLUMNS}
          rowKey="id"
          size="small"
          pagination={{ pageSize: 30, showTotal: t => `총 ${t}건` }}
          scroll={{ y: 500 }}
          locale={{ emptyText: '기록된 로그가 없습니다.' }}
        />
      </Card>
    </div>
  )
}
