-- 이글스 라운지 · 알림 주제 선택(커뮤니티 / 한화 소식) + 소식 알림
-- 'HOOK_SECRET_HERE'  = Edge Function notify 의 HOOK_SECRET
-- 'NEWS_SECRET_HERE'  = GitHub Actions 비밀값 NEWS_HOOK_SECRET
-- 저장소에는 자리표시만 둬요.

alter table public.push_subs add column if not exists topics text[] not null default '{board}';

-- 비밀값 보관(밖에서 못 읽음)
create table if not exists public.app_secrets (name text primary key, value text not null);
alter table public.app_secrets enable row level security;
revoke all on public.app_secrets from anon, authenticated;
insert into public.app_secrets(name, value) values ('news_hook', 'NEWS_SECRET_HERE'), ('edge_hook', 'HOOK_SECRET_HERE')
on conflict (name) do update set value = excluded.value;

drop function if exists public.push_subscribe(text, text, text);
create or replace function public.push_subscribe(p_endpoint text, p_p256dh text, p_auth text, p_topics text[] default '{board}')
returns boolean language plpgsql security definer set search_path = public as $$
begin
  if p_endpoint !~ '^https://' or char_length(p_endpoint) > 1000 or char_length(p_p256dh) > 200 or char_length(p_auth) > 100 then
    raise exception '알림 정보가 올바르지 않아요';
  end if;
  if p_topics is null or cardinality(p_topics) = 0 or not (p_topics <@ array['board','news']) then
    raise exception '알림 종류가 올바르지 않아요';
  end if;
  if (select count(*) from push_subs) >= 5000 then raise exception '알림 신청이 너무 많아요'; end if;
  insert into push_subs(endpoint, p256dh, auth, topics) values (p_endpoint, p_p256dh, p_auth, p_topics)
  on conflict (endpoint) do update set p256dh = excluded.p256dh, auth = excluded.auth, topics = excluded.topics;
  return true;
end $$;

-- 이 기기가 받는 알림 종류(없으면 빈 배열)
create or replace function public.push_topics(p_endpoint text)
returns text[] language sql stable security definer set search_path = public as $$
  select coalesce((select topics from push_subs where endpoint = p_endpoint), '{}'::text[])
$$;

-- 커뮤니티 트리거: 'board' 를 고른 기기만
create or replace function public.board_notify()
returns trigger language plpgsql security definer set search_path = public, net as $$
declare v_subs jsonb;
begin
  select coalesce(jsonb_agg(jsonb_build_object('endpoint', endpoint, 'p256dh', p256dh, 'auth', auth)), '[]'::jsonb)
    into v_subs from push_subs where 'board' = any(topics);
  if jsonb_array_length(v_subs) = 0 then return new; end if;
  perform net.http_post(
    url := 'https://hluwwdskhyjoxntoqvux.supabase.co/functions/v1/notify',
    body := jsonb_build_object('post', jsonb_build_object('id', new.id, 'parent_id', new.parent_id, 'category', new.category,
                                                          'nickname', new.nickname, 'body', new.body),
                               'subs', v_subs),
    headers := jsonb_build_object('Content-Type', 'application/json',
                                  'x-hook-secret', (select value from app_secrets where name = 'edge_hook')),
    timeout_milliseconds := 10000
  );
  return new;
end $$;

-- 소식 알림: GitHub Actions 가 새 기사를 올린 뒤 호출
create or replace function public.news_notify(p_secret text, p_count int, p_first text)
returns int language plpgsql security definer set search_path = public, net as $$
declare v_subs jsonb;
begin
  if p_secret is null or p_secret <> (select value from app_secrets where name = 'news_hook') then
    raise exception 'forbidden';
  end if;
  select coalesce(jsonb_agg(jsonb_build_object('endpoint', endpoint, 'p256dh', p256dh, 'auth', auth)), '[]'::jsonb)
    into v_subs from push_subs where 'news' = any(topics);
  if jsonb_array_length(v_subs) = 0 or coalesce(p_count, 0) <= 0 then return 0; end if;
  perform net.http_post(
    url := 'https://hluwwdskhyjoxntoqvux.supabase.co/functions/v1/notify',
    body := jsonb_build_object('news', jsonb_build_object('count', p_count, 'first', left(coalesce(p_first, ''), 200)), 'subs', v_subs),
    headers := jsonb_build_object('Content-Type', 'application/json',
                                  'x-hook-secret', (select value from app_secrets where name = 'edge_hook')),
    timeout_milliseconds := 10000
  );
  return jsonb_array_length(v_subs);
end $$;

revoke all on function public.push_subscribe(text, text, text, text[]) from public;
revoke all on function public.push_topics(text) from public;
revoke all on function public.news_notify(text, int, text) from public;
grant execute on function public.push_subscribe(text, text, text, text[]) to anon, authenticated;
grant execute on function public.push_topics(text) to anon, authenticated;
grant execute on function public.news_notify(text, int, text) to anon, authenticated;
