import React, { useState, useEffect } from 'react'
import { Card, Table, Button, Modal, Form, Input, Space, Popconfirm, message } from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons'
import { getAdvertisers, createAdvertiser, updateAdvertiser, deleteAdvertiser } from '../api'

const FORM_ITEMS = [
  { name: 'item_name',        label: '소재명',        required: true },
  { name: 'company_name',     label: '회사명' },
  { name: 'business_reg_no',  label: '사업자등록번호' },
  { name: 'ceo_name',         label: '대표이사' },
  { name: 'business_type',    label: '업태·업종' },
  { name: 'broadcast_medium', label: '송출 매체' },
  { name: 'note',             label: '비고' },
]

export default function AdvertiserPage() {
  const [data, setData]     = useState([])
  const [loading, setLoading] = useState(false)
  const [modal, setModal]   = useState({ open: false, mode: 'create', record: null })
  const [form] = Form.useForm()

  const load = async () => {
    setLoading(true)
    try { setData(await getAdvertisers()) }
    catch { message.error('목록 조회 실패') }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const openCreate = () => {
    form.resetFields()
    form.setFieldValue('broadcast_medium', 'TV')
    form.setFieldValue('note', '송출시간은 방송사 상황에 따라 변동될 수 있음')
    setModal({ open: true, mode: 'create', record: null })
  }

  const openEdit = (rec) => {
    form.setFieldsValue(rec)
    setModal({ open: true, mode: 'edit', record: rec })
  }

  const handleOk = async () => {
    try {
      const vals = await form.validateFields()
      if (modal.mode === 'create') {
        await createAdvertiser(vals)
        message.success('광고주 정보가 등록되었습니다.')
      } else {
        await updateAdvertiser(modal.record.item_name, vals)
        message.success('광고주 정보가 수정되었습니다.')
      }
      setModal(m => ({ ...m, open: false }))
      load()
    } catch (e) {
      if (e.response) message.error(e.response.data.detail || '처리 실패')
    }
  }

  const handleDelete = async (itemName) => {
    try {
      await deleteAdvertiser(itemName)
      message.success('삭제되었습니다.')
      load()
    } catch (e) {
      message.error(e.response?.data?.detail || '삭제 실패')
    }
  }

  const COLUMNS = [
    { title: '소재명', dataIndex: 'item_name', width: 160 },
    { title: '회사명', dataIndex: 'company_name', width: 150 },
    { title: '사업자번호', dataIndex: 'business_reg_no', width: 130 },
    { title: '대표이사', dataIndex: 'ceo_name', width: 100 },
    { title: '업태·업종', dataIndex: 'business_type', width: 120 },
    { title: '송출 매체', dataIndex: 'broadcast_medium', width: 100 },
    {
      title: '관리', width: 100, align: 'center',
      render: (_, rec) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(rec)} />
          <Popconfirm title="삭제하시겠습니까?" onConfirm={() => handleDelete(rec.item_name)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div style={{ padding: 24 }}>
      <Card
        title="광고주 정보 관리"
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            광고주 등록
          </Button>
        }
      >
        <Table
          dataSource={data}
          columns={COLUMNS}
          rowKey="item_name"
          loading={loading}
          size="small"
          pagination={{ pageSize: 20 }}
          scroll={{ x: 900 }}
        />
      </Card>

      <Modal
        title={modal.mode === 'create' ? '광고주 등록' : '광고주 수정'}
        open={modal.open}
        onOk={handleOk}
        onCancel={() => setModal(m => ({ ...m, open: false }))}
        okText="저장"
        cancelText="취소"
        destroyOnClose
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          {FORM_ITEMS.map(fi => (
            <Form.Item
              key={fi.name}
              name={fi.name}
              label={fi.label}
              rules={fi.required ? [{ required: true, message: `${fi.label}을 입력하세요.` }] : []}
            >
              <Input disabled={fi.name === 'item_name' && modal.mode === 'edit'} />
            </Form.Item>
          ))}
        </Form>
      </Modal>
    </div>
  )
}
