# 보관

## manuscript-worktree-deletion.diff

`docs/manuscript.md` 가 작업트리에서만 삭제돼 있던 상태를 기록한 것이다 (HEAD
에는 그대로 있었다). 지시대로 삭제 상태를 diff 로 남긴 뒤 HEAD 버전을 복원했다.

내용상 이 diff 는 HEAD 의 blob 과 중복이다 - `git show HEAD:docs/manuscript.md`
로 같은 것을 얻을 수 있고, 삭제 diff 는 파일 전체를 그대로 담기 때문이다.
그래도 남기는 이유는 삭제가 있었다는 사실 자체가 git 이력에는 남지 않기
때문이다. 커밋되지 않은 작업트리 상태는 복원하는 순간 사라진다.

복원 시점 HEAD: 248beda
