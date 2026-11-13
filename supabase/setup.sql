-- 한화 야구 노트 · 커뮤니티 게시판 설정
-- Supabase 대시보드 > SQL Editor 에 통째로 붙여넣고 Run 하면 돼요. 여러 번 실행해도 안전해요.
-- 글 테이블은 브라우저에서 직접 읽거나 쓸 수 없고, 아래 세 함수로만 다룰 수 있어요(비밀번호 해시가 밖으로 나가지 않게).

create extension if not exists pgcrypto with schema extensions;

create table if not exists public.board_posts (
  id bigint generated always as identity primary key,
  parent_id bigint references public.board_posts(id) on delete cascade,
  category text not null default '잡담',
  nickname text not null,
  body text not null,
  pw_hash text not null,
  created_at timestamptz not null default now()
);
create index if not exists board_posts_created_idx on public.board_posts(created_at desc);
create index if not exists board_posts_parent_idx on public.board_posts(parent_id);
alter table public.board_posts enable row level security;
revoke all on public.board_posts from anon, authenticated;

create table if not exists public.board_admin (
  id int primary key default 1 check (id = 1),
  pw_hash text not null
);
alter table public.board_admin enable row level security;
revoke all on public.board_admin from anon, authenticated;

-- 최신 원글 p_limit개 + 그 댓글들
create or replace function public.board_list(p_limit int default 50, p_before timestamptz default null)
returns table(id bigint, parent_id bigint, category text, nickname text, body text, created_at timestamptz)
language sql stable security definer set search_path = public as $$
  with top as (
    select p.* from board_posts p
    where p.parent_id is null and (p_before is null or p.created_at < p_before)
    order by p.created_at desc
    limit least(greatest(coalesce(p_limit, 50), 1), 100)
  )
  select t.id, t.parent_id, t.category, t.nickname, t.body, t.created_at from top t
  union all
  select c.id, c.parent_id, c.category, c.nickname, c.body, c.created_at
  from board_posts c join top t on c.parent_id = t.id
$$;

create or replace function public.board_create(p_parent bigint, p_category text, p_nickname text, p_body text, p_pw text)
returns bigint
language plpgsql security definer set search_path = public, extensions as $$
declare
  v_id bigint;
  v_nick text := btrim(coalesce(p_nickname, ''));
  v_body text := btrim(coalesce(p_body, ''));
begin
  if char_length(v_nick) not between 1 and 20 then raise exception '닉네임은 1~20자로 써주세요'; end if;
  if char_length(v_body) not between 1 and 1000 then raise exception '내용은 1~1000자로 써주세요'; end if;
  if p_pw is null or char_length(p_pw) not between 4 and 50 then raise exception '비밀번호는 4자 이상으로 정해주세요'; end if;
  if p_parent is null and coalesce(p_category, '') not in ('잡담', '경기', '직관', '질문') then raise exception '분류를 골라주세요'; end if;
  if p_parent is not null and not exists (select 1 from board_posts where id = p_parent and parent_id is null) then
    raise exception '원글을 찾을 수 없어요';
  end if;
  if (select count(*) from board_posts where created_at > now() - interval '1 minute') >= 20 then
    raise exception '지금 글이 너무 많이 올라오고 있어요. 잠시 뒤에 다시 써주세요';
  end if;
  insert into board_posts(parent_id, category, nickname, body, pw_hash)
  values (p_parent, case when p_parent is null then p_category else '댓글' end, v_nick, v_body, crypt(p_pw, gen_salt('bf')))
  returning id into v_id;
  return v_id;
end $$;

-- 글쓴이 비밀번호 또는 관리자 비밀번호로 삭제(원글을 지우면 댓글도 같이 지워져요)
create or replace function public.board_delete(p_id bigint, p_pw text)
returns boolean
language plpgsql security definer set search_path = public, extensions as $$
declare v_hash text;
begin
  select pw_hash into v_hash from board_posts where id = p_id;
  if v_hash is null then return false; end if;
  if crypt(coalesce(p_pw, ''), v_hash) = v_hash
     or exists (select 1 from board_admin a where crypt(coalesce(p_pw, ''), a.pw_hash) = a.pw_hash) then
    delete from board_posts where id = p_id;
    return true;
  end if;
  raise exception '비밀번호가 맞지 않아요';
end $$;

revoke all on function public.board_list(int, timestamptz) from public;
revoke all on function public.board_create(bigint, text, text, text, text) from public;
revoke all on function public.board_delete(bigint, text) from public;
grant execute on function public.board_list(int, timestamptz) to anon, authenticated;
grant execute on function public.board_create(bigint, text, text, text, text) to anon, authenticated;
grant execute on function public.board_delete(bigint, text) to anon, authenticated;

-- ▼ 관리자 비밀번호 정하기: 아래 줄의 '여기에_관리자_비밀번호'를 원하는 비밀번호로 바꾸고 실행하세요.
--   이 비밀번호를 쓰면 누구 글이든 지울 수 있어요. 바꾸고 싶으면 같은 줄을 다시 실행하면 돼요.
insert into public.board_admin(id, pw_hash)
values (1, extensions.crypt('여기에_관리자_비밀번호', extensions.gen_salt('bf')))
on conflict (id) do update set pw_hash = excluded.pw_hash;
