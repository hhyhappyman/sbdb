import React, { useState, useEffect } from 'react'
import { Card, Form, Input, Button, message, Divider, Alert } from 'antd'
import { SaveOutlined, FolderOpenOutlined, LockOutlined } from '@ant-design/icons'
import { getSettings, updateSettings, changePassword } from '../api'

const FIELDS = [
  {
    section: '공익/재난 분류 키워드 (월별·흘림자막 송출내역)',
    items: [
      {
        name: 'gongik_include_keywords',
        label: '공익 포함 키워드',
        plain: true,
        multiline: true,
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
        plain: true,
        multiline: true,
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
        plain: true,
        multiline: true,
        placeholder: '예: 협찬',
        help: (
          <span>
            소재명에 이 키워드가 들어가면 공익/재난 집계에서 <b>제외</b>합니다.
            여러 개는 <b>콤마(,)나 줄바꿈</b>으로 구분.
          </span>
        ),
      },
    ],
  },
  {
    section: '소재별 월 리포트(PDF) 표기 정보',
    items: [
      {
        name: 'company_name',
        label: '회사명',
        plain: true,
        placeholder: '예: 광주문화방송',
        help: <span>월 리포트 문서의 <b>회사명</b> 칸과 하단 <b>「○○(주)」</b>에 표기됩니다.</span>,
      },
      {
        name: 'company_short',
        label: '약칭',
        plain: true,
        placeholder: '예: 광주MBC',
        help: <span>좌측 상단 로고와 월 리포트 <b>제목</b>에 표기됩니다. (예: 광주MBC, MBC경남)</span>,
      },
      { name: 'ceo_name', label: '대표이사명', placeholder: '예: 홍길동' },
    ],
  },
  {
    section: '접근 제한 (허용 IP 대역)',
    items: [
      {
        name: 'allowed_ip_ranges',
        label: '접근 허용 IP 대역',
        plain: true,
        multiline: true,
        placeholder: '218.237.3.0/24, 192.168.0.0/24',
        help: (
          <span>
            입력 예시 —{' '}
            <b>대역</b>: <code>218.237.3.0/24</code> (218.237.3.0 ~ 218.237.3.255),{' '}
            <b>단일 IP</b>: <code>192.168.0.10</code>,{' '}
            여러 개는 <b>콤마(,)나 줄바꿈</b>으로 구분.{' '}
            <b>모든 IP 허용</b>은 <code>0.0.0.0</code> 입력.{' '}
            (내 컴퓨터=localhost는 항상 허용)
          </span>
        ),
      },
    ],
  },
  {
    section: 'FTP 파일 가져오기 설정',
    items: [
      { name: 'ftp_host',       label: 'FTP 서버 주소', placeholder: '예: 192.168.0.10', plain: true },
      { name: 'ftp_port',       label: 'FTP 포트',      placeholder: '기본값: 21',       plain: true },
      { name: 'ftp_user',       label: 'FTP 아이디',    placeholder: 'FTP 로그인 아이디', plain: true },
      { name: 'ftp_password',   label: 'FTP 비밀번호',  placeholder: 'FTP 로그인 비밀번호', plain: true },
      { name: 'ftp_fetch_time', label: '자동 가져오기 시각', placeholder: '예: 06:00 (매일 전날 파일 자동 수집)', plain: true },
    ],
  },
  {
    section: '데이터 파일 경로',
    items: [
      { name: 'apst_dir',  label: 'APST 파일 디렉터리', placeholder: '/data/apst/' },
      { name: 'ddr1_dir',  label: 'DDR1 로그 디렉터리',  placeholder: '/data/ddr1/' },
      { name: 'cml_path',  label: 'CML 파일 디렉터리',
        placeholder: '/data/cml/  (날짜별 imc<YYYYMMDD>.cml 파일을 자동으로 찾습니다)' },
    ],
  },
  {
    section: '이미지 파일',
    items: [
      { name: 'logo_path', label: '광주MBC 로고 이미지 경로', placeholder: '/assets/logo.png' },
      { name: 'seal_path', label: '직인 이미지 경로',         placeholder: '/assets/seal.png' },
    ],
  },
  {
    section: '근무자 로그인 설정',
    items: [
      { name: 'worker_id',       label: '근무자 아이디',   placeholder: '기본값: user',     plain: true },
      { name: 'worker_password', label: '근무자 비밀번호', placeholder: '기본값: user2450', plain: true },
    ],
  },
]

export default function SettingsPage() {
  const [form]    = Form.useForm()
  const [pwForm]  = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [saving,  setSaving]  = useState(false)
  const [pwSaving, setPwSaving] = useState(false)

  useEffect(() => {
    setLoading(true)
    getSettings()
      .then(data => form.setFieldsValue(data))
      .catch(() => message.error('설정을 불러오지 못했습니다.'))
      .finally(() => setLoading(false))
  }, [])

  const save = async () => {
    const vals = form.getFieldsValue()
    setSaving(true)
    try {
      await updateSettings(vals)
      message.success('설정이 저장되었습니다.')
    } catch {
      message.error('저장 실패')
    } finally {
      setSaving(false)
    }
  }

  const savePw = async () => {
    try {
      const { current_password, new_password, confirm_password } = await pwForm.validateFields()
      if (new_password !== confirm_password) {
        message.error('새 비밀번호가 일치하지 않습니다.')
        return
      }
      setPwSaving(true)
      await changePassword(current_password, new_password)
      message.success('비밀번호가 변경되었습니다.')
      pwForm.resetFields()
    } catch (e) {
      if (e.response) message.error(e.response.data?.detail || '변경 실패')
    } finally {
      setPwSaving(false)
    }
  }

  return (
    <div style={{ padding: 24 }}>
      <Alert
        message="모든 경로는 서버 기준 절대 경로를 입력하세요."
        type="info"
        showIcon
        style={{ marginBottom: 20 }}
      />

      <Card title="환경설정" loading={loading}>
        <Form form={form} layout="vertical" style={{ maxWidth: 600 }}>
          {FIELDS.map((section, idx) => (
            <div key={section.section} style={{ marginTop: idx > 0 ? 48 : 0 }}>
              <Divider
                orientation="left"
                style={{ color: '#666', fontWeight: 600, margin: '4px 0 24px', borderColor: '#d0d0d0' }}
              >
                {section.section}
              </Divider>
              {section.items.map(item => (
                <Form.Item key={item.name} name={item.name} label={item.label}
                  help={item.help} extra={item.help ? undefined : null}>
                  {item.multiline ? (
                    <Input.TextArea placeholder={item.placeholder} autoSize={{ minRows: 2, maxRows: 5 }} />
                  ) : (
                    <Input
                      placeholder={item.placeholder}
                      prefix={item.plain
                        ? <LockOutlined style={{ color: '#bbb' }} />
                        : <FolderOpenOutlined style={{ color: '#bbb' }} />}
                    />
                  )}
                </Form.Item>
              ))}
            </div>
          ))}

          <Form.Item style={{ marginTop: 8 }}>
            <Button
              type="primary"
              icon={<SaveOutlined />}
              onClick={save}
              loading={saving}
              size="large"
            >
              설정 저장
            </Button>
          </Form.Item>
        </Form>
      </Card>

      {/* 비밀번호 변경 카드 */}
      <Card
        title={
          <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <LockOutlined />
            관리자 비밀번호 변경
          </span>
        }
        style={{ maxWidth: 460, marginTop: 20 }}
      >
        <Form form={pwForm} layout="vertical">
          <Form.Item
            name="current_password"
            label="현재 비밀번호"
            rules={[{ required: true, message: '현재 비밀번호를 입력하세요.' }]}
          >
            <Input.Password placeholder="현재 비밀번호" />
          </Form.Item>
          <Form.Item
            name="new_password"
            label="새 비밀번호"
            rules={[
              { required: true, message: '새 비밀번호를 입력하세요.' },
              { min: 4, message: '4자 이상 입력하세요.' },
            ]}
          >
            <Input.Password placeholder="새 비밀번호 (4자 이상)" />
          </Form.Item>
          <Form.Item
            name="confirm_password"
            label="새 비밀번호 확인"
            rules={[{ required: true, message: '비밀번호를 한 번 더 입력하세요.' }]}
          >
            <Input.Password placeholder="새 비밀번호 확인" />
          </Form.Item>
          <Form.Item>
            <Button
              type="primary"
              icon={<LockOutlined />}
              onClick={savePw}
              loading={pwSaving}
            >
              비밀번호 변경
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  )
}
