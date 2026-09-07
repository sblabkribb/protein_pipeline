// frontend/guided/dom.js — 텍스트 전용 DOM 헬퍼.
//
// el 은 원래 plan.js 에 있었다. 그런데 plan 은 facade(guided.js)와 순환
// import 를 이루고 facade 는 모듈 최상위에서 DOM 을 만지므로, node 테스트가
// 직접 import 하는 모듈(sidebar.js)에서 plan 을 끌어오면 브라우저 밖에서
// document 가 없어 터진다. 도우미는 여기 두고 plan 은 재노출만 유지한다.
//
// 값은 textContent 로만 넣는다. 아티팩트 경로와 실행 상태는 서버에서 오고,
// 산출물 경로에는 사용자가 정한 이름(run id, design id)이 섞인다. 그 이름을
// innerHTML 로 넣으면 안에 든 마크업이 실행된다.
export function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = String(text);
  return node;
}
