/**
 * 탭 이동 후 돌아와도 마지막 검색 결과를 유지하기 위한 전역 메모리 store.
 * 브라우저 탭이 열려 있는 동안 유지됩니다. (새로고침 시 초기화)
 */
const _store = {}

export function getStore(key) {
  return _store[key] ?? {}
}

export function setStore(key, partial) {
  _store[key] = { ...(_store[key] ?? {}), ...partial }
}

export function clearStore(key) {
  delete _store[key]
}
