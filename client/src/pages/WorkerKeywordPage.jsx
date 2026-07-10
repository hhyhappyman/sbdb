import React, { useState, useEffect } from 'react'
import { Card, Form, Input, Button, message, Alert } from 'antd'
import { SaveOutlined } from '@ant-design/icons'
import { getSettings, updateSettings } from '../api'

// 근무자 모드에서 편집 가능한 '공익/재난 분류 키워드' 항목만 노출한다.
const KEYWORD_FIELDS = [
  {
    name: 'gongik_include_keywords',
    label: '공익 포함 키워드',
    placeholder: '예: 학교폭력예방',
    help: (
      <span>
        소재명에 이 키워드가 들어가면 <b>공익</b>으로 분류합니다.
        여러 개는 <b>콤마(,)나 줄바꿈</b>으로 구분. (소재명에 '공익' 글자가 없어도 포함)
      </span>
    ),
  },
  {
    name: 'jaenan_include_keywords',
    label: '재난 포함 키워드',
    placeholder: '예: 산불조심, 폭염',
    help: (
      <span>
        소재명에 이 키워드가 들어가면 <b>재난</b>으로 분류합니다.
        여러 개는 <b>콤마(,)나 줄바꿈</b>으로 구분.
      </span>
    ),
  },
  {
    name: 'gongik_jaenan_exclude_keywords',
    label: '공익/재난 제외 키워드',
    placeholder: '예: 협찬',
    help: (
      <span>
        소재명에 이 키워드가 들어가면 공익/재난 집계에서 <b>제외</b>합니다.
        여러 개는 <b>콤마(,)나 줄바꿈</b>으로 구분.
      </span>
    ),
  },
]

export default function WorkerKeywordPage() {
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setLoading(true)
    getSettings()
      .then(data => {
        // 키워드 3개 항목만 폼에 채운다
        const vals = {}
        for (const f of KEYWORD_FIELDS) vals[f.name] = data[f.name] ?? ''
        form.setFieldsValue(vals)
      })
      .catch(() => message.error('설정을 불러오지 못했습니다.'))
      .finally(() => setLoading(false))
  }, [])

  const save = async () => {
    // 키워드 3개 항목만 저장 (다른 설정은 건드리지 않음)
    const vals = form.getFieldsValue(KEYWORD_FIELDS.map(f => f.name))
    setSaving(true)
    try {
      await updateSettings(vals)
      message.success('공익/재난 분류 키워드가 저장되었습니다.')
    } catch {
      message.error('저장 실패')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div style={{ padding: 24 }}>
      <Alert
        message="공익/재난 분류 키워드만 수정할 수 있습니다. (월별·흘림자막 송출내역 집계에 사용)"
        type="info"
        showIcon
        style={{ marginBottom: 20 }}
      />

      <Card title="공익/재난 분류 키워드" loading={loading}>
        <Form form={form} layout="vertical" style={{ maxWidth: 600 }}>
          {KEYWORD_FIELDS.map(item => (
            <Form.Item key={item.name} name={item.name} label={item.label} help={item.help}>
              <Input.TextArea placeholder={item.placeholder} autoSize={{ minRows: 2, maxRows: 5 }} />
            </Form.Item>
          ))}

          <Form.Item style={{ marginTop: 8 }}>
            <Button type="primary" icon={<SaveOutlined />} onClick={save} loading={saving} size="large">
              저장
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  )
}
