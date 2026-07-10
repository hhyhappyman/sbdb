import React, { useState, useEffect } from 'react'
import { Card, Table, Tag, Button, message } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { getLogs } from '../api'

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

export default function LogPage() {
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

  useEffect(() => { load() }, [])

  return (
    <div style={{ padding: 24 }}>
      <Card
        title="로그 기록"
        extra={
          <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>
            새로고침
          </Button>
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
