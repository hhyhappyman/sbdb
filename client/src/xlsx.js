// 공용 XLSX 다운로드 유틸.
// 클라이언트에서 계산한 표 데이터(headers + rows)를 서버(/api/export/xlsx)로 보내
// openpyxl로 생성된 .xlsx 파일을 받아 다운로드한다.
export async function downloadXLSX(filename, headers, rows, sheetName = 'Sheet1') {
  const res = await fetch('/api/export/xlsx', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename, sheet_name: sheetName, headers, rows }),
  })
  if (!res.ok) throw new Error('엑셀 저장에 실패했습니다.')

  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
