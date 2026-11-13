-- 한화 야구 노트 · 커뮤니티 새 글 알림(웹 푸시)
-- 'HOOK_SECRET_HERE' 는 Edge Function 의 HOOK_SECRET 과 같은 값이어야 해요(저장소에는 자리표시만 둬요).

create extension if not exists pg_net;

create table if not exists public.push_subs (
  endpoint text primary key,
  p256dh text not null,
  auth text not null,
  created_at timestamptz not null default now()
);
alter table public.push_subs enable row level security;
revoke all on public.push_subs from anon, authenticated;

create or replace function public.push_subscribe(p_endpoint text, p_p256dh text, p_auth text)
returns boolean language plpgsql security definer set search_path = public as $$
begin
  if p_endpoint !~ '^https://' or char_length(p_endpoint) > 1000 or char_length(p_p256dh) > 200 or char_length(p_auth) > 100 then
    raise exception '알림 정보가 올바르지 않아요';
  end if;
  if (select count(*) from push_subs) >= 5000 then raise exception '알림 신청이 너무 많아요'; end if;
  insert into push_subs(endpoint, p256dh, auth) values (p_endpoint, p_p256dh, p_auth)
  on conflict (endpoint) do update set p256dh = excluded.p256dh, auth = excluded.auth;
  return true;
end $$;

create or replace function public.push_unsubscribe(p_endpoint text)
returns boolean language sql security definer set search_path = public as $$
  with d as (delete from push_subs where endpoint = p_endpoint returning 1) select exists(select 1 from d)
$$;

revoke all on function public.push_subscribe(text, text, text) from public;
revoke all on function public.push_unsubscribe(text) from public;
grant execute on function public.push_subscribe(text, text, text) to anon, authenticated;
grant execute on function public.push_unsubscribe(text) to anon, authenticated;

-- 새 글·댓글이 들어오면 Edge Function(notify)에 글 + 구독 목록을 보내요
create or replace function public.board_notify()
returns trigger language plpgsql security definer set search_path = public, net as $$
declare v_subs jsonb;
begin
  select coalesce(jsonb_agg(jsonb_build_object('endpoint', endpoint, 'p256dh', p256dh, 'auth', auth)), '[]'::jsonb)
    into v_subs from push_subs;
  if jsonb_array_length(v_subs) = 0 then return new; end if;
  perform net.http_post(
    url := 'https://hluwwdskhyjoxntoqvux.supabase.co/functions/v1/notify',
    body := jsonb_build_object('post', jsonb_build_object('id', new.id, 'parent_id', new.parent_id, 'category', new.category,
                                                          'nickname', new.nickname, 'body', new.body),
                               'subs', v_subs),
    headers := jsonb_build_object('Content-Type', 'application/json', 'x-hook-secret', 'HOOK_SECRET_HERE'),
    timeout_milliseconds := 10000
  );
  return new;
end $$;

drop trigger if exists board_notify_trg on public.board_posts;
create trigger board_notify_trg after insert on public.board_posts
for each row execute function public.board_notify();
