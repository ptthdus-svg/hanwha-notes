-- 한화 야구 노트 · 게시판 변경: 글 삭제는 관리자만
-- setup.sql 을 실행한 뒤 SQL Editor 에서 이 파일을 통째로 실행하세요. 여러 번 실행해도 안전해요.
-- (관리자 비밀번호는 바뀌지 않아요. 이 파일에는 비밀번호를 적을 필요가 없어요.)

alter table public.board_posts alter column pw_hash drop not null;

-- 글쓰기: 비밀번호 없이 닉네임만. p_pw 는 예전 화면과의 호환용으로 받기만 하고 쓰지 않아요.
create or replace function public.board_create(p_parent bigint, p_category text, p_nickname text, p_body text, p_pw text default null)
returns bigint
language plpgsql security definer set search_path = public, extensions as $$
declare
  v_id bigint;
  v_nick text := btrim(coalesce(p_nickname, ''));
  v_body text := btrim(coalesce(p_body, ''));
begin
  if char_length(v_nick) not between 1 and 20 then raise exception '닉네임은 1~20자로 써주세요'; end if;
  if char_length(v_body) not between 1 and 1000 then raise exception '내용은 1~1000자로 써주세요'; end if;
  if p_parent is null and coalesce(p_category, '') not in ('잡담', '경기', '직관', '질문') then raise exception '분류를 골라주세요'; end if;
  if p_parent is not null and not exists (select 1 from board_posts where id = p_parent and parent_id is null) then
    raise exception '원글을 찾을 수 없어요';
  end if;
  if (select count(*) from board_posts where created_at > now() - interval '1 minute') >= 20 then
    raise exception '지금 글이 너무 많이 올라오고 있어요. 잠시 뒤에 다시 써주세요';
  end if;
  insert into board_posts(parent_id, category, nickname, body, pw_hash)
  values (p_parent, case when p_parent is null then p_category else '댓글' end, v_nick, v_body, null)
  returning id into v_id;
  return v_id;
end $$;

-- 삭제: 관리자 비밀번호로만(원글을 지우면 댓글도 같이 지워져요)
create or replace function public.board_delete(p_id bigint, p_pw text)
returns boolean
language plpgsql security definer set search_path = public, extensions as $$
begin
  if not exists (select 1 from board_admin a where crypt(coalesce(p_pw, ''), a.pw_hash) = a.pw_hash) then
    raise exception '관리자 비밀번호가 맞지 않아요';
  end if;
  delete from board_posts where id = p_id;
  return found;
end $$;

-- 관리자 로그인 확인용
create or replace function public.board_is_admin(p_pw text)
returns boolean
language sql stable security definer set search_path = public, extensions as $$
  select exists (select 1 from board_admin a where crypt(coalesce(p_pw, ''), a.pw_hash) = a.pw_hash)
$$;

revoke all on function public.board_create(bigint, text, text, text, text) from public;
revoke all on function public.board_delete(bigint, text) from public;
revoke all on function public.board_is_admin(text) from public;
grant execute on function public.board_create(bigint, text, text, text, text) to anon, authenticated;
grant execute on function public.board_delete(bigint, text) to anon, authenticated;
grant execute on function public.board_is_admin(text) to anon, authenticated;
